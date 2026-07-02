from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

from ai_automate_contro.engine.output_contract import publish_step_output


MONGO_ACTION_TYPES = {
    "find",
    "find_one",
    "insert_one",
    "insert_many",
    "update_one",
    "update_many",
    "delete_one",
    "delete_many",
    "aggregate",
    "command",
    "list_indexes",
    "create_index",
    "drop_index",
}


def run(executor: Any, step: dict[str, Any]) -> None:
    step_type = str(step["type"])
    if step_type not in MONGO_ACTION_TYPES:
        raise ValueError(f"mongo.type 不支持：{step_type}")
    started_at = time.perf_counter()
    client, database, connection_name = _mongo_database(executor, step)
    try:
        result = _execute_mongo(database, step_type, step)
    finally:
        client.close()
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload = {
        "type": step_type,
        "connection": connection_name,
        "database": database.name,
        "collection": step.get("collection"),
        "result": _json_safe(result),
        "elapsed_ms": elapsed_ms,
    }
    _write_optional_result(executor, step, payload)
    publish_step_output(executor, step, payload, action="mongo")
    executor.state.logger.log(
        "info",
        "mongo action finished",
        type=step_type,
        connection=connection_name,
        database=database.name,
        collection=step.get("collection", ""),
        elapsed_ms=elapsed_ms,
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
        result_path=step.get("result_path", ""),
    )


def _mongo_database(executor: Any, step: dict[str, Any]) -> tuple[Any, Any, str]:
    try:
        from pymongo import MongoClient
        from pymongo.errors import ConfigurationError
    except ImportError as error:
        raise RuntimeError(
            "mongo action 需要按需安装 MongoDB 驱动："
            "pip install -e '.[db-mongodb]'；也可以直接安装 pymongo。"
            "默认安装不会包含该驱动。"
        ) from error
    config = _connection_config(executor, step)
    timeout_ms = max(1, int(step.get("timeout_ms", 30_000)))
    connection_name = str(config.get("name", "inline"))
    uri = str(config.get("uri") or config.get("url") or config.get("dsn") or "")
    if not uri:
        host = str(config.get("host", "127.0.0.1"))
        port = int(config.get("port", 27017))
        uri = f"mongodb://{host}:{port}"
    kwargs = {
        "serverSelectionTimeoutMS": timeout_ms,
        "connectTimeoutMS": timeout_ms,
        "socketTimeoutMS": timeout_ms,
        "username": config.get("username") or config.get("user"),
        "password": config.get("password"),
        "authSource": config.get("auth_source") or config.get("authSource"),
    }
    client = MongoClient(uri, **{key: value for key, value in kwargs.items() if value is not None})
    database_name = step.get("database") or config.get("database") or config.get("db")
    if database_name:
        return client, client[str(database_name)], connection_name
    try:
        return client, client.get_default_database(), connection_name
    except ConfigurationError as error:
        client.close()
        raise ValueError("mongo.database 或 connection.database 必须设置，除非 URI 自带默认数据库。") from error


def _connection_config(executor: Any, step: dict[str, Any]) -> dict[str, Any]:
    raw_connection = step["connection"]
    if isinstance(raw_connection, dict):
        config = dict(raw_connection)
        config.setdefault("name", "inline")
        return config
    if not isinstance(raw_connection, str) or not raw_connection.strip():
        raise ValueError("mongo.connection 必须是连接名或连接对象。")
    name = raw_connection.strip()
    variables = getattr(executor.state, "variables", {})
    connections = variables.get("connections")
    config_connections = variables.get("config", {}).get("connections") if isinstance(variables.get("config"), dict) else None
    for source in (config_connections, connections):
        if isinstance(source, dict) and isinstance(source.get(name), dict):
            config = dict(source[name])
            config.setdefault("name", name)
            return config
    raise KeyError(f"未找到 MongoDB 连接配置：{name}")


def _execute_mongo(database: Any, step_type: str, step: dict[str, Any]) -> Any:
    if step_type == "command":
        command = step["command"]
        args = step.get("args", [])
        if not isinstance(args, list):
            raise ValueError("mongo.command.args 必须是数组。")
        return database.command(command, *args)
    collection = database[str(step["collection"])]
    if step_type == "find":
        cursor = collection.find(_filter(step), projection=_projection(step.get("projection")))
        sort = _sort_spec(step.get("sort"))
        if sort:
            cursor = cursor.sort(sort)
        limit = max(1, int(step.get("limit", step.get("max_docs", 1000))))
        return list(cursor.limit(limit))
    if step_type == "find_one":
        return collection.find_one(_filter(step), projection=_projection(step.get("projection")))
    if step_type == "insert_one":
        result = collection.insert_one(step["document"])
        return {"inserted_id": result.inserted_id, "acknowledged": result.acknowledged}
    if step_type == "insert_many":
        documents = step["documents"]
        if not isinstance(documents, list):
            raise ValueError("mongo.insert_many.documents 必须是数组。")
        result = collection.insert_many(documents, ordered=bool(step.get("ordered", True)))
        return {"inserted_ids": result.inserted_ids, "inserted_count": len(result.inserted_ids), "acknowledged": result.acknowledged}
    if step_type in {"update_one", "update_many"}:
        updater = collection.update_one if step_type == "update_one" else collection.update_many
        result = updater(_filter(step), step["update"], upsert=bool(step.get("upsert", False)))
        return {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "upserted_id": result.upserted_id,
            "acknowledged": result.acknowledged,
        }
    if step_type in {"delete_one", "delete_many"}:
        deleter = collection.delete_one if step_type == "delete_one" else collection.delete_many
        result = deleter(_filter(step))
        return {"deleted_count": result.deleted_count, "acknowledged": result.acknowledged}
    if step_type == "aggregate":
        pipeline = step["pipeline"]
        if not isinstance(pipeline, list):
            raise ValueError("mongo.aggregate.pipeline 必须是数组。")
        limit = max(1, int(step.get("limit", step.get("max_docs", 1000))))
        return list(database[str(step["collection"])].aggregate(pipeline))[:limit]
    if step_type == "list_indexes":
        return list(collection.list_indexes())
    if step_type == "create_index":
        index_name = collection.create_index(_index_keys_spec(step.get("keys")), **_index_options(step))
        return {"name": index_name}
    if step_type == "drop_index":
        collection.drop_index(str(step.get("name") or step.get("index")))
        return {"dropped": str(step.get("name") or step.get("index"))}
    raise ValueError(f"mongo.type 不支持：{step_type}")


def _filter(step: dict[str, Any]) -> dict[str, Any]:
    value = step.get("filter", {})
    if not isinstance(value, dict):
        raise ValueError("mongo.filter 必须是对象。")
    return value


def _projection(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return {str(item): 1 for item in value}
    if isinstance(value, dict):
        return value
    raise ValueError("mongo.projection 必须是对象或字段数组。")


def _sort_spec(value: Any) -> list[tuple[str, int]] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return [(str(key), int(direction)) for key, direction in value.items()]
    if not isinstance(value, list):
        raise ValueError("mongo.sort 必须是对象或数组。")
    result: list[tuple[str, int]] = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            field = item.get("field") or item.get("key")
            direction = item.get("direction", item.get("order", 1))
            if not isinstance(field, str) or not field:
                raise ValueError(f"mongo.sort[{index}].field 必须是非空字符串。")
            result.append((field, int(direction)))
            continue
        if isinstance(item, list) and len(item) == 2:
            result.append((str(item[0]), int(item[1])))
            continue
        raise ValueError(f"mongo.sort[{index}] 必须是 {{field, direction}} 或 [field, direction]。")
    return result


def _index_keys_spec(value: Any) -> str | list[tuple[str, Any]]:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict) and value:
        return [(str(key), _index_direction(direction)) for key, direction in value.items()]
    if not isinstance(value, list) or not value:
        raise ValueError("mongo.create_index.keys 必须是字段名、对象或非空数组。")
    result: list[tuple[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, str) and item:
            result.append((item, 1))
            continue
        if isinstance(item, dict):
            field = item.get("field") or item.get("key") or item.get("name")
            direction = item.get("direction", item.get("order", 1))
            if not isinstance(field, str) or not field:
                raise ValueError(f"mongo.create_index.keys[{index}].field 必须是非空字符串。")
            result.append((field, _index_direction(direction)))
            continue
        if isinstance(item, list) and len(item) == 2:
            field = str(item[0])
            if not field:
                raise ValueError(f"mongo.create_index.keys[{index}][0] 必须是非空字符串。")
            result.append((field, _index_direction(item[1])))
            continue
        raise ValueError(f"mongo.create_index.keys[{index}] 必须是字段名、{{field, direction}} 或 [field, direction]。")
    return result


def _index_direction(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("mongo.create_index.keys.direction 不支持布尔值。")
    if isinstance(value, int):
        if value not in {-1, 1}:
            raise ValueError("mongo.create_index.keys.direction 整数只支持 1 或 -1。")
        return value
    if isinstance(value, str) and value:
        aliases = {
            "asc": 1,
            "ascending": 1,
            "desc": -1,
            "descending": -1,
            "text": "text",
            "hashed": "hashed",
            "2d": "2d",
            "2dsphere": "2dsphere",
        }
        lowered = value.lower()
        if lowered in aliases:
            return aliases[lowered]
    raise ValueError("mongo.create_index.keys.direction 只支持 1、-1、asc、desc、text、hashed、2d 或 2dsphere。")


def _index_options(step: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    option_fields = {
        "name": "name",
        "unique": "unique",
        "sparse": "sparse",
        "background": "background",
        "expire_after_seconds": "expireAfterSeconds",
        "expireAfterSeconds": "expireAfterSeconds",
        "partial_filter_expression": "partialFilterExpression",
        "partialFilterExpression": "partialFilterExpression",
        "collation": "collation",
        "weights": "weights",
    }
    for field, option_name in option_fields.items():
        if field in step:
            options[option_name] = step[field]
    return options


def _write_optional_result(executor: Any, step: dict[str, Any], payload: dict[str, Any]) -> None:
    if "result_path" not in step:
        return
    path = executor._resolve_output_path(str(step["result_path"]), category="mongo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


ACTION_HANDLERS = {
    "mongo": run,
}
