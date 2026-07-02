# redis

## 用途

在 plan 中直接访问 Redis，用于缓存读取、任务状态写入、队列/list/set 操作，或用原生命令兜底。

`redis` 是 common action，`automation_type: "browser"` 和 `automation_type: "desktop"` 都可以使用。

## 依赖

源码开发环境使用 Redis action 需要可选依赖：

```powershell
pip install -e '.[db-redis]'
```

源码默认安装不包含 Redis 驱动。只有 plan 使用 `redis` action 时才需要安装，运行时也只在执行该 action 前加载驱动。发行包支持 Redis 时，驱动必须在打包环境中安装并随包进入 `_internal/`。

## 必填字段

- `action`: 固定为 `redis`
- `type`: Redis 操作类型
- `connection`: 连接名或连接对象

连接名从 `config.json.connections` 或 plan 变量 `connections` 读取。

```json
{
  "connections": {
    "cache": {
      "type": "redis",
      "url": "redis://127.0.0.1:6379/0"
    }
  }
}
```

## 支持类型

| type | 必填字段 |
| --- | --- |
| `get` | `key` |
| `set` | `key`、`value` |
| `delete` | `key` 或 `keys` |
| `hget` | `key`、`field` |
| `hset` | `key` + `mapping`，或 `key`、`field`、`value` |
| `hgetall` | `key` |
| `lpush` / `rpush` | `key` + `value` 或 `values` |
| `lrange` | `key` |
| `sadd` | `key` + `value` 或 `members` |
| `smembers` | `key` |
| `expire` | `key`、`seconds` |
| `command` | `command` |
| `pipeline` | `commands` |

## 示例

```json
{
  "action": "redis",
  "type": "set",
  "connection": "cache",
  "key": "job:{{job_id}}",
  "value": "{{payload_json}}",
  "ttl_seconds": 3600,
  "output": {
    "as": "cache_write"
  }
}
```

```json
{
  "action": "redis",
  "type": "hgetall",
  "connection": "cache",
  "key": "user:{{user_id}}",
  "output": {
    "as": "user_cache"
  }
}
```

```json
{
  "action": "redis",
  "type": "command",
  "connection": "cache",
  "command": "SET",
  "args": ["job:{{job_id}}", "{{payload_json}}", "EX", 3600],
  "output": {
    "as": "redis_result"
  }
}
```

```json
{
  "action": "redis",
  "type": "pipeline",
  "connection": "cache",
  "commands": [
    {
      "command": "SET",
      "args": ["a", "1"]
    },
    {
      "command": "GET",
      "args": ["a"]
    }
  ],
  "output": {
    "as": "pipeline_result"
  }
}
```

## 常用字段

- `url`/`dsn`: Redis URL，写在连接对象里。
- `host`、`port`、`db`、`username`、`password`: 分字段连接配置。
- `decode_responses`: 连接对象字段，默认 `true`。
- `ttl_seconds`: `set` 时设置过期时间。
- `result_path`: 执行结果写入 `output/redis/`。
- `timeout_ms`: 连接和命令超时毫秒。
- `batch_size`: `pipeline` 拆分批次大小。
- `output`: 发布响应摘要的声明；`output.as` 是变量名。

## 返回变量

```json
{
  "type": "hgetall",
  "connection": "cache",
  "result": {
    "name": "demo"
  },
  "elapsed_ms": 8
}
```

## 输出约束

- `result_path` 相对于当前 plan 包 `output/redis/`。
- 不要以 `output/` 开头。
- 返回值保留原文，不自动脱敏 key、value、token 或密码。
- `pipeline` 支持 `batch_size`，适合大批量命令分批执行。
