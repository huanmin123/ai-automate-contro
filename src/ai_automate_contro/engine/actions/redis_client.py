from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

from ai_automate_contro.engine.output_contract import publish_step_output


REDIS_ACTION_TYPES = {
    "get",
    "set",
    "delete",
    "hget",
    "hset",
    "hgetall",
    "lpush",
    "rpush",
    "lrange",
    "sadd",
    "smembers",
    "expire",
    "command",
    "pipeline",
}


def run(executor: Any, step: dict[str, Any]) -> None:
    step_type = str(step["type"])
    if step_type not in REDIS_ACTION_TYPES:
        raise ValueError(f"redis.type 不支持：{step_type}")
    started_at = time.perf_counter()
    client, connection_name = _redis_client(executor, step)
    try:
        result = _execute_redis(client, step_type, step)
    finally:
        client.close()
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload = {
        "type": step_type,
        "connection": connection_name,
        "result": _json_safe(result),
        "elapsed_ms": elapsed_ms,
    }
    _write_optional_result(executor, step, payload)
    publish_step_output(executor, step, payload, action="redis")
    executor.state.logger.log(
        "info",
        "redis action finished",
        type=step_type,
        connection=connection_name,
        elapsed_ms=elapsed_ms,
        output_as=step.get("output", {}).get("as", "") if isinstance(step.get("output"), dict) else "",
        result_path=step.get("result_path", ""),
    )


def _redis_client(executor: Any, step: dict[str, Any]) -> tuple[Any, str]:
    try:
        import redis
    except ImportError as error:
        raise RuntimeError(
            "redis action 需要按需安装 Redis 驱动："
            "pip install -e '.[db-redis]'；也可以直接安装 redis。"
            "默认安装不会包含该驱动。"
        ) from error
    config = _connection_config(executor, step)
    timeout_seconds = max(0.001, float(step.get("timeout_ms", 30_000)) / 1000)
    decode_responses = bool(config.get("decode_responses", True))
    connection_name = str(config.get("name", "inline"))
    url = config.get("url") or config.get("dsn")
    if url:
        return (
            redis.Redis.from_url(
                str(url),
                socket_timeout=timeout_seconds,
                socket_connect_timeout=timeout_seconds,
                decode_responses=decode_responses,
            ),
            connection_name,
        )
    kwargs = {
        "host": config.get("host", "127.0.0.1"),
        "port": int(config.get("port", 6379)),
        "db": int(config.get("db", 0)),
        "username": config.get("username"),
        "password": config.get("password"),
        "socket_timeout": timeout_seconds,
        "socket_connect_timeout": timeout_seconds,
        "decode_responses": decode_responses,
    }
    return redis.Redis(**{key: value for key, value in kwargs.items() if value is not None}), connection_name


def _connection_config(executor: Any, step: dict[str, Any]) -> dict[str, Any]:
    raw_connection = step["connection"]
    if isinstance(raw_connection, dict):
        config = dict(raw_connection)
        config.setdefault("name", "inline")
        return config
    if not isinstance(raw_connection, str) or not raw_connection.strip():
        raise ValueError("redis.connection 必须是连接名或连接对象。")
    name = raw_connection.strip()
    variables = getattr(executor.state, "variables", {})
    connections = variables.get("connections")
    config_connections = variables.get("config", {}).get("connections") if isinstance(variables.get("config"), dict) else None
    for source in (config_connections, connections):
        if isinstance(source, dict) and isinstance(source.get(name), dict):
            config = dict(source[name])
            config.setdefault("name", name)
            return config
    raise KeyError(f"未找到 Redis 连接配置：{name}")


def _execute_redis(client: Any, step_type: str, step: dict[str, Any]) -> Any:
    if step_type == "get":
        return client.get(step["key"])
    if step_type == "set":
        return client.set(step["key"], step["value"], ex=step.get("ttl_seconds"))
    if step_type == "delete":
        keys = step.get("keys") if "keys" in step else [step["key"]]
        if not isinstance(keys, list):
            raise ValueError("redis.delete.keys 必须是数组。")
        return client.delete(*keys)
    if step_type == "hget":
        return client.hget(step["key"], step["field"])
    if step_type == "hset":
        if "mapping" in step:
            return client.hset(step["key"], mapping=step["mapping"])
        return client.hset(step["key"], step["field"], step["value"])
    if step_type == "hgetall":
        return client.hgetall(step["key"])
    if step_type == "lpush":
        return client.lpush(step["key"], *_redis_values(step))
    if step_type == "rpush":
        return client.rpush(step["key"], *_redis_values(step))
    if step_type == "lrange":
        return client.lrange(step["key"], int(step.get("start", 0)), int(step.get("stop", -1)))
    if step_type == "sadd":
        return client.sadd(step["key"], *_redis_values(step, field="members"))
    if step_type == "smembers":
        return client.smembers(step["key"])
    if step_type == "expire":
        return client.expire(step["key"], int(step["seconds"]))
    if step_type == "command":
        return client.execute_command(str(step["command"]), *step.get("args", []))
    if step_type == "pipeline":
        commands = step["commands"]
        if not isinstance(commands, list):
            raise ValueError("redis.pipeline.commands 必须是数组。")
        batch_size = max(1, int(step.get("batch_size", len(commands) or 1)))
        results: list[Any] = []
        for batch_start in range(0, len(commands), batch_size):
            pipe = client.pipeline()
            for offset, item in enumerate(commands[batch_start : batch_start + batch_size]):
                index = batch_start + offset
                if not isinstance(item, dict):
                    raise ValueError(f"redis.pipeline.commands[{index}] 必须是对象。")
                command = item.get("command")
                if not isinstance(command, str) or not command.strip():
                    raise ValueError(f"redis.pipeline.commands[{index}].command 必须是非空字符串。")
                args = item.get("args", [])
                if not isinstance(args, list):
                    raise ValueError(f"redis.pipeline.commands[{index}].args 必须是数组。")
                pipe.execute_command(command, *args)
            results.extend(pipe.execute())
        return results
    raise ValueError(f"redis.type 不支持：{step_type}")


def _redis_values(step: dict[str, Any], *, field: str = "values") -> list[Any]:
    if field in step:
        values = step[field]
    elif "value" in step:
        values = [step["value"]]
    else:
        raise ValueError(f"redis.{step['type']} 需要 value 或 {field}。")
    if not isinstance(values, list):
        raise ValueError(f"redis.{step['type']}.{field} 必须是数组。")
    return values


def _write_optional_result(executor: Any, step: dict[str, Any], payload: dict[str, Any]) -> None:
    if "result_path" not in step:
        return
    path = executor._resolve_output_path(str(step["result_path"]), category="redis")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


ACTION_HANDLERS = {
    "redis": run,
}
