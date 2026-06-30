# mongo

## 用途

在 plan 中访问 MongoDB，把上一节点产生的 JSON 文档写入 collection、按条件查询文档、更新/删除临时数据，或执行 `aggregate`/`command` 传给下一节点。

`mongo` 是 common action，`automation_type: "browser"` 和 `automation_type: "desktop"` 都可以使用。

MongoDB 驱动默认不安装。需要时按需安装：

```powershell
pip install -e '.[db-mongodb]'
```

## 必填字段

- `action`: 固定为 `mongo`
- `type`: `find`、`find_one`、`insert_one`、`insert_many`、`update_one`、`update_many`、`delete_one`、`delete_many`、`aggregate`、`command`
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

也可以使用 `host`、`port`、`username`、`password`、`auth_source` 和 `database` 组合连接。

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
  "save_as": "draft_articles"
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
  "save_as": "insert_result"
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
  "save_as": "update_result"
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
  "save_as": "author_counts"
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
  "save_as": "mongo_ping"
}
```

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
- `limit` / `max_docs`: 最大返回文档数，默认 1000。
- `upsert`: `update_one`/`update_many` 是否 upsert，默认 `false`。
- `ordered`: `insert_many` 是否按顺序写入，默认 `true`。
- `result_path`: 执行摘要写入 `output/mongo/`。
- `save_as`: 保存响应摘要变量名。

## 返回变量

所有类型都会返回 `type`、`connection`、`database`、`collection`、`result` 和 `elapsed_ms`。

`find`/`find_one` 的 `result` 是文档或文档数组；`insert_*` 返回插入 ID 和数量；`update_*` 返回匹配/修改数量；`delete_*` 返回删除数量；`aggregate` 返回聚合文档数组；`command` 返回 MongoDB 原生命令结果。

## 输出约束

- `result_path` 相对于当前 plan 包 `output/mongo/`。
- 不要以 `output/` 开头。
- ObjectId、日期和 Decimal 等非 JSON 原生值会转成字符串或 ISO 文本写出。
