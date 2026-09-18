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

连接对象写 `url` 或 `dsn` 时按 URL 连接；不写时使用分字段：`host` 默认 `127.0.0.1`、`port` 默认 `6379`、`db` 默认 `0`，可再提供 `username`、`password`。`decode_responses` 默认 `true`，返回值直接是字符串。

## 支持类型

| type | 必填字段 | 说明 |
| --- | --- | --- |
| `get` | `key` | 读字符串值；不存在时 `result` 为 `null` |
| `set` | `key`、`value` | 写字符串值；`ttl_seconds` 可选 |
| `delete` | `key` 或 `keys` | 删除一个或多个 key，返回删除数量 |
| `hget` | `key`、`field` | 读 hash 单个字段 |
| `hset` | `key` + `mapping`，或 `key`、`field`、`value` | 写 hash 字段 |
| `hgetall` | `key` | 读整个 hash |
| `lpush` / `rpush` | `key` + `value` 或 `values` | 从左/右插入列表元素 |
| `lrange` | `key` | 读列表片段；`start` 默认 `0`，`stop` 默认 `-1`，即整个列表 |
| `sadd` | `key` + `value` 或 `members` | 添加 set 成员 |
| `smembers` | `key` | 读全部 set 成员，结果排序后返回 |
| `expire` | `key`、`seconds` | 设置过期秒数 |
| `command` | `command` | 原生命令；`args` 是参数数组，默认空 |
| `pipeline` | `commands` | 批量执行命令并按顺序返回结果 |

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
- `host`、`port`、`db`、`username`、`password`: 分字段连接配置，默认 `127.0.0.1`、`6379`、`0`。
- `decode_responses`: 连接对象字段，默认 `true`。
- `ttl_seconds`: `set` 时设置过期时间；不写该字段会清除 key 原有的过期时间（Redis `SET` 默认语义，无 KEEPTTL 行为）。需要保留原过期策略时应先查询原 TTL 再显式写入。
- `start` / `stop`: `lrange` 的区间索引，默认 `0` 和 `-1`（整个列表），支持负数从尾部计数。
- `args`: `command` 和 `pipeline` 每条命令的参数数组，元素可以是字符串或数字，默认空数组。
- `result_path`: 执行结果写入 `output/redis/`。
- `timeout_ms`: 正整数，默认 `30000`；同时作为连接和命令的 socket 超时。
- `batch_size`: `pipeline` 拆分批次大小，正整数；默认等于命令总数，即全部命令一批执行。
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
