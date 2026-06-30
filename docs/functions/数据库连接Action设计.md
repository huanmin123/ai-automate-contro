# 数据库连接 Action 设计

## 定位

数据库连接能力属于 common action，browser plan 和 desktop plan 都可以使用。它不依赖浏览器 DOM，也不依赖桌面控件树，因此不新增执行线。

数据库能力拆成三个 action：

- `sql`: 关系型数据库。SQLite 是本地化优先路径，DuckDB 是本地分析路径，另覆盖 PostgreSQL、MySQL/MariaDB、Oracle、SQL Server。
- `mongo`: MongoDB 文档数据库，覆盖 CRUD、聚合和原生命令。
- `redis`: Redis 数据结构和原生命令。

不把它们合并为一个 `database` action，原因是 SQL、MongoDB 和 Redis 的数据模型、参数、返回值、批量语义、事务语义都不同，合并后字段会快速失控。

## 依赖策略

数据库能力按“支持优先、依赖按需”落地：

- 默认安装不包含服务型数据库驱动。
- SQLite 使用 Python 标准库 `sqlite3`，不需要额外安装。
- DuckDB、PostgreSQL、MySQL/MariaDB、Oracle、SQL Server、MongoDB 和 Redis 的 action 代码保留在项目中，但驱动只在运行到对应连接或 action 时懒加载。
- 缺少驱动时，运行时返回对应库的安装命令，不提示用户安装整套数据库依赖。
- 聚合 extra 只作为用户明确需要多库能力时的便利入口，不作为 handbook 默认推荐。

当前可选安装入口：

```powershell
pip install -e '.[db-postgresql]'
pip install -e '.[db-mysql]'
pip install -e '.[db-redis]'
pip install -e '.[db-oracle]'
pip install -e '.[db-duckdb]'
pip install -e '.[db-sqlserver]'
pip install -e '.[db-mongodb]'
pip install -e '.[database-local]'
pip install -e '.[database-sql]'
pip install -e '.[database-basic]'
pip install -e '.[database-all]'
```

后续新增 ClickHouse、Snowflake 等能力时，应继续沿用独立 extra。只有 action 能力真正落地后才在 `pyproject.toml` 增加对应 extra，避免安装入口先于能力存在。

## SQLite Local-First

SQLite 应作为自动化场景的默认推荐数据库：

- 不需要搭建 MySQL、PostgreSQL、Redis 等中间件。
- Python 标准库内置 `sqlite3`，无需额外安装数据库驱动。
- 适合本地缓存、抓取结果落库、流程中间状态、轻量任务队列、离线数据清洗和可复制 plan 包。
- 数据库文件可以放在当前 plan 包 `output/sql/`，运行证据和中间数据天然跟随 plan 输出目录。

用户没有明确要求连接服务型数据库时，AI 生成 plan 应优先考虑 SQLite。典型写法是把数据库文件放入当前 plan 包 `output/sql/*.db`，既能复现，也不会要求用户额外安装或启动中间件。

## DuckDB Local Analytics

DuckDB 适合自动化过程中的本地分析场景：

- 处理较大的 CSV、JSONL、Parquet 或临时表数据。
- 在不搭建服务的情况下做聚合、过滤、排序和数据转换。
- 作为 SQLite 之外的本地 SQL 数据处理选项。

DuckDB 驱动默认不安装。用户需要本地分析能力时安装 `db-duckdb` 或 `database-local`。AI 生成 plan 时，只有当任务明显需要较强本地分析、列式文件处理或用户明确要求 DuckDB，才优先使用 DuckDB；普通本地落库仍优先 SQLite。

## `sql` Action

### 类型

| type | 用途 |
| --- | --- |
| `query` | 查询多行数据 |
| `scalar` | 查询单个值 |
| `execute` | 执行单条 DDL/DML |
| `executemany` | 用参数数组批量执行同一 SQL |
| `bulk_insert` | 把数组数据写入表，支持 insert/replace/upsert |
| `import` | 从 CSV/JSON/JSONL/Excel 文件读取对象行并批量写入表 |
| `export` | 查询 SQL 并直接导出 CSV/JSON/JSONL/Excel 文件 |
| `copy` | 从一个 SQL 连接查询数据，批量写入另一个 SQL 连接 |
| `transaction` | 把多个 SQL 子步骤包在同一个事务内执行 |
| `inspect` | 探测表、列和索引元数据 |

### 连接

`connection` 可以是连接名，也可以是内联连接对象。连接名优先从 `config.json.connections` 读取，其次读取 plan 变量 `connections`。`config.json` 支持完整值环境变量引用，适合把数据库密码、DSN 或 URL 放到本机环境变量中。

SQLite 本地文件示例：

```json
{
  "action": "sql",
  "type": "execute",
  "connection": {
    "type": "sqlite",
    "path": "output/sql/demo.db"
  },
  "sql": "create table if not exists items (id integer primary key, name text)"
}
```

服务型数据库示例：

```json
{
  "action": "sql",
  "type": "query",
  "connection": "crm_pg",
  "sql": "select id, status from orders where customer_id = :customer_id",
  "params": {
    "customer_id": "{{customer.id}}"
  },
  "save_as": "orders"
}
```

跨库复制示例：

```json
{
  "action": "sql",
  "type": "copy",
  "connection": "crm_pg",
  "target_connection": "local_sqlite",
  "sql": "select id, status, total from orders where updated_at >= :since order by id",
  "params": {
    "since": "{{last_sync_at}}"
  },
  "table": "orders_snapshot",
  "column_map": {
    "order_id": "id",
    "status": "status",
    "total": "total"
  },
  "batch_size": 500,
  "result_path": "orders-copy.json",
  "save_as": "orders_copy"
}
```

文件导入示例：

```json
{
  "action": "sql",
  "type": "import",
  "connection": "local_sqlite",
  "source_path": "resources/orders.csv",
  "table": "orders",
  "create_table": true,
  "batch_size": 500,
  "result_path": "orders-import.json",
  "save_as": "orders_import"
}
```

查询导出示例：

```json
{
  "action": "sql",
  "type": "export",
  "connection": "crm_pg",
  "sql": "select id, status, total from orders where status = :status order by id",
  "params": {
    "status": "paid"
  },
  "target_path": "paid-orders.xlsx",
  "target_type": "excel",
  "sheet": "paid_orders",
  "result_path": "paid-orders-export.json"
}
```

### 返回变量

`query` 返回：

```json
{
  "type": "query",
  "connection": "crm_pg",
  "database_type": "postgresql",
  "columns": ["id", "status"],
  "row_count": 2,
  "first_row": {"id": 1, "status": "paid"},
  "rows": [{"id": 1, "status": "paid"}],
  "elapsed_ms": 12
}
```

`execute` 返回：

```json
{
  "type": "execute",
  "connection": "crm_pg",
  "database_type": "postgresql",
  "affected_rows": 1,
  "lastrowid": null,
  "elapsed_ms": 10
}
```

`copy` 返回：

```json
{
  "type": "copy",
  "source_connection": "crm_pg",
  "source_database_type": "postgresql",
  "target_connection": "local_sqlite",
  "target_database_type": "sqlite",
  "source_row_count": 200,
  "table": "orders_snapshot",
  "columns": ["order_id", "status", "total"],
  "input_rows": 200,
  "affected_rows": 200,
  "batch_count": 1,
  "elapsed_ms": 35
}
```

### 输出

- `rows_path`: 查询 rows 写入 `output/sql/`，支持 `.json`、`.csv` 和 `.jsonl`。
- `result_path`: 执行摘要写入 `output/sql/`。
- 指定 `rows_path` 时默认不把完整 rows 放入变量，避免变量池过大；可显式 `include_rows: true`。
- `bulk_insert.batch_size` 允许把大批量拆分成小批次。
- `copy.batch_size` 允许把查询结果分批写入目标连接。
- `copy.stream=true` 允许从源游标按 `fetch_size` 分批读取、按 `batch_size` 分批写入目标连接，适合更大的复制任务。
- `import` 支持 CSV/JSON/JSONL/Excel，按文件后缀推断 `source_type`，也可用 `record_path` 从 JSON 对象中取行数组。
- `export` 支持 CSV/JSON/JSONL/Excel，输出文件写入 `output/sql/`。
- `inspect` 返回 `tables`、`columns`、`indexes` 和数量统计，用于把上一节点数据转换成后续 SQL 条件前先探测 schema。
- `query`/`scalar` 支持 `limit`、`offset`、`page_size` 和 `page`，用于常见分页查询。
- `copy` 支持 `limit`、`offset`、`page_size` 和 `page`，用于受控复制单页数据。
- `transaction` 只写事务摘要到 `result_path`，不写 `rows_path`。

### 约束

- SQL 参数应使用 `params`，不要拼接用户输入。
- `max_rows` 默认 1000，超过时报错。
- 分页查询应显式写 `order by`，否则数据库返回顺序不稳定。
- `bulk_insert` 的表名和列名只接受简单标识符或 `schema.table`。
- `copy` 始终受 `max_rows` 保护；`stream=true` 解决内存占用和 JSONL 分批落盘问题，但不是无限 CDC 或后台同步。
- `copy stream=true` 的 `rows_path` 只支持 `.jsonl`，并且不支持 `include_rows`。
- DuckDB/PostgreSQL/MySQL/Oracle/SQL Server/MongoDB/Redis 驱动默认不安装，按连接类型安装 `db-duckdb`、`db-postgresql`、`db-mysql`、`db-oracle`、`db-sqlserver`、`db-mongodb` 或 `db-redis`。

### 事务

`transaction` 更适合“多个 SQL 必须一起成功或一起失败”的自动化场景。事务内部步骤只允许 `query`、`scalar`、`execute`、`executemany`、`bulk_insert`，并共享父级 connection。

## `mongo` Action

### 类型

| type | 用途 |
| --- | --- |
| `find` / `find_one` | 条件查询文档 |
| `insert_one` / `insert_many` | 写入单个或多个文档 |
| `update_one` / `update_many` | 按 filter 更新文档 |
| `delete_one` / `delete_many` | 按 filter 删除文档 |
| `aggregate` | 执行聚合管道 |
| `command` | 执行 MongoDB 原生命令 |

MongoDB 不并入 `sql`，因为它没有 SQL 参数绑定、表结构和事务批量语义。`mongo` 直接使用 JSON 文档、filter、update 和 pipeline，更贴近自动化节点之间的数据传递。

写操作中的 `filter` 必须显式提供，避免自动化流程误删或误更新整表数据。输出写入 `output/mongo/`，ObjectId、日期等非 JSON 原生值会转换为字符串或 ISO 文本。

## `redis` Action

### 类型

| type | 用途 |
| --- | --- |
| `get` / `set` / `delete` | 基础 key 操作 |
| `hget` / `hset` / `hgetall` | Hash |
| `lpush` / `rpush` / `lrange` | List |
| `sadd` / `smembers` | Set |
| `expire` | 设置过期时间 |
| `command` | 原生命令兜底 |
| `pipeline` | 批量命令 |

### 示例

```json
{
  "action": "redis",
  "type": "hgetall",
  "connection": "cache",
  "key": "user:{{user_id}}",
  "save_as": "user_cache"
}
```

```json
{
  "action": "redis",
  "type": "command",
  "connection": {
    "type": "redis",
    "url": "redis://127.0.0.1:6379/0"
  },
  "command": "SET",
  "args": ["job:{{job_id}}", "{{payload_json}}", "EX", 3600],
  "save_as": "redis_result"
}
```

## 验证策略

- 默认确定性回归使用 SQLite，不依赖外部服务。
- SQLite 动态自检覆盖 `sql.import`、`sql.export`、`sql.copy` buffered、`stream=true` 和 `sql.inspect`，从一个 SQLite 文件复制到另一个 SQLite 文件。
- PostgreSQL、MySQL、Oracle、SQL Server、MongoDB 和 Redis 使用可选本地服务或容器回归，不纳入默认离线矩阵。
- 真实 SQL 服务开启 `--allow-writes` 时，会把临时表数据流式复制到本地 SQLite，以覆盖跨库 copy 回归。
- `handbook` 自检必须确保 action 文档链接有效。

## 边界

- 不提供 ORM、迁移系统、连接池或后台连接保活。
- 不自动脱敏 SQL、DSN、密码、token、Redis key 或返回值。
- 不绕过数据库权限；连接账号能做什么由数据库自身权限决定。
