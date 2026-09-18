# mongo

## 用途

在 plan 中访问 MongoDB，把上一节点产生的 JSON 文档写入 collection、按条件查询文档、更新/删除临时数据，或执行 `aggregate`/`command` 传给下一节点。

`mongo` 是 common action，`automation_type: "browser"` 和 `automation_type: "desktop"` 都可以使用。

源码开发环境默认不安装 MongoDB 驱动。需要时按需安装：

```powershell
pip install -e '.[db-mongodb]'
```

发行包支持 MongoDB 时，驱动必须在打包环境中安装并随包进入 `_internal/`。

## 必填字段

- `action`: 固定为 `mongo`
- `type`: `find`、`find_one`、`insert_one`、`insert_many`、`update_one`、`update_many`、`delete_one`、`delete_many`、`aggregate`、`command`、`list_indexes`、`create_index`、`drop_index`
- `connection`: 连接名或连接对象

## 连接

连接名从 `config.json.connections` 或 plan 变量 `connections` 读取。

```json
{
  "connections": {
    "content_mongo": {
      "type": "mongodb",
      "uri": "mongodb://127.0.0.1:27017/content",
      "database": "content"
    }
  }
}
```

也可以使用 `host`、`port`、`username`、`password`、`auth_source` 和 `database` 组合连接；`host` 默认 `127.0.0.1`，`port` 默认 `27017`。`uri`/`url`/`dsn` 提供时优先使用，不再读取分字段默认值。`database` 不写时使用 URI 自带的默认数据库，URI 也没有时步骤报错。

## 类型

### find

```json
{
  "action": "mongo",
  "type": "find",
  "connection": "content_mongo",
  "collection": "articles",
  "filter": {
    "status": "draft"
  },
  "projection": ["title", "status"],
  "sort": {
    "created_at": -1
  },
  "limit": 100,
  "result_path": "draft-articles.json",
  "output": {
    "as": "draft_articles"
  }
}
```

### insert_many

```json
{
  "action": "mongo",
  "type": "insert_many",
  "connection": "content_mongo",
  "collection": "articles",
  "documents": "{{articles}}",
  "result_path": "articles-insert.json",
  "output": {
    "as": "insert_result"
  }
}
```

### update_one

```json
{
  "action": "mongo",
  "type": "update_one",
  "connection": "content_mongo",
  "collection": "articles",
  "filter": {
    "_id": "{{article_id}}"
  },
  "update": {
    "$set": {
      "status": "published"
    }
  },
  "upsert": false,
  "output": {
    "as": "update_result"
  }
}
```

### aggregate

```json
{
  "action": "mongo",
  "type": "aggregate",
  "connection": "content_mongo",
  "collection": "articles",
  "pipeline": [
    {
      "$match": {
        "status": "published"
      }
    },
    {
      "$group": {
        "_id": "$author_id",
        "article_count": {
          "$sum": 1
        }
      }
    }
  ],
  "result_path": "author-counts.json",
  "output": {
    "as": "author_counts"
  }
}
```

### create_index

```json
{
  "action": "mongo",
  "type": "create_index",
  "connection": "content_mongo",
  "collection": "articles",
  "keys": {
    "author_id": 1,
    "created_at": -1
  },
  "name": "author_created_idx",
  "result_path": "article-index-create.json",
  "output": {
    "as": "article_index"
  }
}
```

`keys` 可以写成对象、字段名、`[["field", 1]]` 或 `[{ "field": "title", "direction": "text" }]`。方向支持 `1`、`-1`、`asc`、`desc`、`text`、`hashed`、`2d` 和 `2dsphere`。

### list_indexes

```json
{
  "action": "mongo",
  "type": "list_indexes",
  "connection": "content_mongo",
  "collection": "articles",
  "result_path": "article-indexes.json",
  "output": {
    "as": "article_indexes"
  }
}
```

### drop_index

```json
{
  "action": "mongo",
  "type": "drop_index",
  "connection": "content_mongo",
  "collection": "articles",
  "name": "author_created_idx",
  "result_path": "article-index-drop.json"
}
```

### command

```json
{
  "action": "mongo",
  "type": "command",
  "connection": "content_mongo",
  "command": "ping",
  "result_path": "mongo-ping.json",
  "output": {
    "as": "mongo_ping"
  }
}
```

### find_one

```json
{
  "action": "mongo",
  "type": "find_one",
  "connection": "content_mongo",
  "collection": "articles",
  "filter": {
    "_id": "{{article_id}}"
  },
  "projection": ["title", "status"],
  "output": {
    "as": "article"
  }
}
```

命中返回单个文档，未命中 `result` 为 `null`。

### insert_one

```json
{
  "action": "mongo",
  "type": "insert_one",
  "connection": "content_mongo",
  "collection": "articles",
  "document": {
    "title": "{{title}}",
    "status": "draft"
  },
  "output": {
    "as": "insert_result"
  }
}
```

返回 `inserted_id` 和 `acknowledged`。

### update_many

```json
{
  "action": "mongo",
  "type": "update_many",
  "connection": "content_mongo",
  "collection": "articles",
  "filter": {
    "status": "draft"
  },
  "update": {
    "$set": {
      "status": "archived"
    }
  },
  "upsert": false,
  "output": {
    "as": "update_result"
  }
}
```

返回 `matched_count`、`modified_count`、`upserted_id` 和 `acknowledged`；`update_one` 字段相同，只更新第一条匹配文档。

### delete_one / delete_many

```json
{
  "action": "mongo",
  "type": "delete_many",
  "connection": "content_mongo",
  "collection": "articles",
  "filter": {
    "status": "archived"
  },
  "output": {
    "as": "delete_result"
  }
}
```

两者都只需要 `filter`，返回 `deleted_count` 和 `acknowledged`；`delete_one` 至多删除一条匹配文档。

## 常用字段

- `database`: 覆盖连接里的默认数据库。
- `collection`: 目标 collection；除 `command` 外通常必填。
- `filter`: 查询、更新、删除条件；写操作必须显式提供。
- `document`: `insert_one` 的单个文档。
- `documents`: `insert_many` 的文档数组。
- `update`: MongoDB update 对象，例如 `$set`、`$inc`。
- `pipeline`: `aggregate` 管道数组。
- `projection`: 查询投影，对象或字段数组。
- `sort`: 排序，对象或 `[field, direction]` 数组。
- `command`: `command` 类型的命令名或命令对象。
- `args`: `command` 类型的额外位置参数数组，默认空数组；按顺序透传给 MongoDB 驱动，例如 `command` 用对象写法时补 `{$db: "..."}` 之类的尾参。
- `keys`: `create_index` 的索引键。
- `name` / `index`: 索引名称；`create_index` 可用 `name` 指定，`drop_index` 使用 `name` 或 `index` 删除。
- `unique`、`sparse`、`background`、`collation`、`weights`: `create_index` 可选参数，透传给 MongoDB 驱动。
- `expire_after_seconds` / `expireAfterSeconds`: TTL 索引秒数，两种写法等价，非负整数。
- `partial_filter_expression` / `partialFilterExpression`: 部分索引过滤条件对象，两种写法等价。
- `limit` / `max_docs`: 最大返回文档数，默认 1000；`find` 和 `aggregate` 都生效。
- `upsert`: `update_one`/`update_many` 是否 upsert，默认 `false`。
- `ordered`: `insert_many` 是否按顺序写入，默认 `true`。
- `timeout_ms`: 正整数，默认 `30000`；同时作为服务器选择、连接和 socket 超时传给驱动。
- `result_path`: 执行摘要写入 `output/mongo/`。
- `output`: 发布响应摘要的声明；`output.as` 是变量名。

## 返回变量

所有类型都会返回 `type`、`connection`、`database`、`collection`、`result` 和 `elapsed_ms`。

`find`/`find_one` 的 `result` 是文档或文档数组；`insert_*` 返回插入 ID 和数量；`update_*` 返回匹配/修改数量；`delete_*` 返回删除数量；`aggregate` 返回聚合文档数组；`command` 返回 MongoDB 原生命令结果；`list_indexes` 返回索引列表；`create_index` 返回索引名；`drop_index` 返回已删除的索引名。

## 输出约束

- `result_path` 相对于当前 plan 包 `output/mongo/`。
- 不要以 `output/` 开头。
- ObjectId、日期和 Decimal 等非 JSON 原生值会转成字符串或 ISO 文本写出。
