# sql

## 用途

在 plan 中直接访问关系型数据库，把上一节点数据写入数据库、更新记录，或查询数据传给下一节点。

`sql` 是 common action，`automation_type: "browser"` 和 `automation_type: "desktop"` 都可以使用。

## 必填字段

- `action`: 固定为 `sql`
- `type`: `query`、`scalar`、`execute`、`executemany`、`bulk_insert`、`import`、`export`、`copy`、`transaction`、`inspect`
- `connection`: 连接名或连接对象

## 连接

连接名从 `config.json.connections` 或 plan 变量 `connections` 读取。

```json
{
  "connections": {
    "crm_pg": {
      "type": "postgresql",
      "dsn": "postgresql://user:password@127.0.0.1:5432/crm"
    },
    "local_sqlite": {
      "type": "sqlite",
      "path": "output/sql/local.db"
    },
    "local_duckdb": {
      "type": "duckdb",
      "path": "output/sql/local.duckdb"
    },
    "erp_sqlserver": {
      "type": "sqlserver",
      "host": "127.0.0.1",
      "port": 1433,
      "database": "erp",
      "user": "sa",
      "password": "password",
      "odbc_driver": "ODBC Driver 18 for SQL Server",
      "trust_server_certificate": true
    }
  }
}
```

SQLite 是推荐的本地化默认方案。它不需要搭建服务，也不需要额外 Python 包，适合自动化过程中的本地数据缓存、批量结果落库和轻量查询。

DuckDB 是本地分析型 SQL 方案，适合处理 CSV/JSONL/Parquet 或较大的中间数据集。DuckDB 驱动默认不安装，需要时按需安装。

服务型数据库驱动默认不安装。运行到对应连接时才会加载驱动，用户按需要选择安装：

```powershell
pip install -e '.[db-postgresql]'
pip install -e '.[db-mysql]'
pip install -e '.[db-oracle]'
pip install -e '.[db-duckdb]'
pip install -e '.[db-sqlserver]'
pip install -e '.[database-local]'
```

需要一次性安装当前已支持的 SQL 驱动时，可以显式使用：

```powershell
pip install -e '.[database-sql]'
```

SQLite 使用 Python 内置驱动，不需要额外依赖。默认安装不会拉取 PostgreSQL、MySQL/MariaDB、Oracle、DuckDB 或 SQL Server 驱动。

## 类型

### query

```json
{
  "action": "sql",
  "type": "query",
  "connection": "crm_pg",
  "sql": "select id, status from orders where customer_id = :customer_id",
  "params": {
    "customer_id": "{{customer.id}}"
  },
  "max_rows": 1000,
  "page_size": 100,
  "page": 1,
  "save_as": "orders"
}
```

### scalar

```json
{
  "action": "sql",
  "type": "scalar",
  "connection": "crm_pg",
  "sql": "select count(*) from orders where status = :status",
  "params": {
    "status": "paid"
  },
  "save_as": "paid_count"
}
```

### execute

```json
{
  "action": "sql",
  "type": "execute",
  "connection": "crm_pg",
  "sql": "update orders set status = :status where id = :id",
  "params": {
    "status": "{{next_status}}",
    "id": "{{order.id}}"
  },
  "expect_affected_rows": 1,
  "save_as": "update_result"
}
```

### executemany

```json
{
  "action": "sql",
  "type": "executemany",
  "connection": "local_sqlite",
  "sql": "insert into items (sku, title) values (:sku, :title)",
  "params_list": "{{items}}",
  "save_as": "insert_result"
}
```

### bulk_insert

```json
{
  "action": "sql",
  "type": "bulk_insert",
  "connection": "warehouse_mysql",
  "table": "page_items",
  "rows": "{{extracted_items}}",
  "columns": ["sku", "title", "price", "source_url"],
  "mode": "upsert",
  "conflict_keys": ["sku"],
  "save_as": "insert_result"
}
```

### copy

从一个 SQL 连接查询数据，批量写入另一个 SQL 连接。`connection` 是源连接，`target_connection` 是目标连接。

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

需要较大批量复制时，使用 `stream: true` 分批读取源游标、分批写入目标表。`rows_path` 只支持 `.jsonl`，避免把完整 rows 放入内存。

```json
{
  "action": "sql",
  "type": "copy",
  "connection": "crm_pg",
  "target_connection": "local_sqlite",
  "sql": "select id, status, total from orders order by id",
  "table": "orders_snapshot",
  "column_map": {
    "order_id": "id",
    "status": "status",
    "total": "total"
  },
  "stream": true,
  "fetch_size": 1000,
  "batch_size": 500,
  "rows_path": "orders-copy.jsonl",
  "result_path": "orders-copy.json",
  "save_as": "orders_copy"
}
```

### import

从 CSV/JSON/JSONL/Excel 文件读取对象行数组，批量写入数据库表。适合“文件结果落库”这类高频流程。

```json
{
  "action": "sql",
  "type": "import",
  "connection": "local_sqlite",
  "source_path": "resources/orders.csv",
  "source_type": "csv",
  "table": "orders",
  "create_table": true,
  "batch_size": 500,
  "result_path": "orders-import.json",
  "save_as": "orders_import"
}
```

CSV/JSONL 大文件可以启用流式导入，边读边写。`required_columns` 校验必填列，`unique_columns` 校验输入文件内的组合唯一，`column_types` 在 `create_table=true` 时覆盖自动推断类型。

```json
{
  "action": "sql",
  "type": "import",
  "connection": "local_sqlite",
  "source_path": "resources/orders.csv",
  "source_type": "csv",
  "table": "orders",
  "create_table": true,
  "stream": true,
  "batch_size": 1000,
  "required_columns": ["order_id", "status"],
  "unique_columns": ["order_id"],
  "column_types": {
    "order_id": "INTEGER",
    "status": "TEXT",
    "total": "REAL"
  },
  "result_path": "orders-import.json",
  "save_as": "orders_import"
}
```

JSON 文件可以是行数组，也可以是包含 `rows`、`data` 或 `items` 的对象；需要读取更深层数组时使用 `record_path`。

```json
{
  "action": "sql",
  "type": "import",
  "connection": "warehouse_mysql",
  "source_path": "resources/orders.json",
  "record_path": "payload.rows",
  "table": "orders",
  "columns": ["order_id", "status", "total"],
  "column_map": {
    "order_id": "id",
    "status": "status",
    "total": "amount"
  },
  "mode": "upsert",
  "conflict_keys": ["order_id"],
  "result_path": "orders-import.json"
}
```

### export

查询数据库并把结果直接写成 CSV/JSON/JSONL/Excel 文件。输出文件写入当前 plan 包 `output/sql/`。

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
  "result_path": "paid-orders-export.json",
  "save_as": "orders_export"
}
```

CSV/JSONL 大结果可以启用流式导出，按游标分批读取并持续写文件，不把完整 rows 放入变量池。

```json
{
  "action": "sql",
  "type": "export",
  "connection": "crm_pg",
  "sql": "select id, status, total from orders order by id",
  "target_path": "orders.jsonl",
  "target_type": "jsonl",
  "stream": true,
  "fetch_size": 1000,
  "result_path": "orders-export.json",
  "save_as": "orders_export"
}
```

### inspect

探测连接里的表、列和索引元数据。SQLite/DuckDB/PostgreSQL/MySQL/SQL Server/Oracle 均支持表和列；SQLite 额外支持索引明细。

```json
{
  "action": "sql",
  "type": "inspect",
  "connection": "local_sqlite",
  "table": "orders_snapshot",
  "include_indexes": true,
  "result_path": "orders-schema.json",
  "save_as": "orders_schema"
}
```

## 常用字段

- `sql`: SQL 文本，`query`、`scalar`、`execute`、`executemany` 必填。
- `target_connection`: `copy` 的目标连接名或连接对象。
- `source_path`: `import` 的输入文件路径，相对当前 plan 包或使用本机绝对路径。
- `source_type`: `import` 输入类型，`csv`、`json`、`jsonl`、`excel`；可从文件后缀推断。
- `target_path`: `export` 的输出文件路径，相对 `output/sql/`。
- `target_type`: `export` 输出类型，`csv`、`json`、`jsonl`、`excel`；可从文件后缀推断。
- `record_path`: `import` 从 JSON 对象中取行数组的点路径，例如 `payload.rows`。
- `sheet`: `import`/`export` 读取或写入的 Excel sheet。
- `params`: 单次 SQL 参数，对象或数组。
- `params_list`: `executemany` 参数数组。
- `table`: `bulk_insert` 或 `copy` 的目标表名；`inspect` 时作为表名过滤条件。
- `schema`: `inspect` 的 schema/owner 过滤条件。
- `rows`: `bulk_insert` 行数组。
- `columns`: `bulk_insert` 列名；`copy` 目标列名；行是对象时可省略并从第一行或查询列推断。
- `column_map`: `copy` 字段映射，格式为 `{目标列: 源查询列}`。
- `create_table`: `import` 写入前按输入列自动建表，默认 `false`；Oracle 暂不支持自动建表。
- `required_columns`: `import` 写入前校验目标列必填，空字符串和 `null` 都视为缺值。
- `unique_columns`: `import` 写入前校验输入文件内这些目标列的组合唯一。
- `column_types`: `import create_table=true` 时指定目标列 SQL 类型，格式为 `{列名: SQL类型}`。
- `mode`: `insert`、`replace`、`upsert`；`copy` 写入目标表时复用该语义。
- `conflict_keys`: `upsert` 冲突键。
- `update_columns`: `upsert` 更新列，默认更新非冲突列。
- `batch_size`: `bulk_insert`、`copy` 或 `import stream=true` 拆分批次大小，默认一次性写完或 1000。
- `stream`: `copy`/`import`/`export` 是否启用分批处理，默认 `false`；`import`/`export` 流式模式只支持 CSV/JSONL。
- `fetch_size`: `copy stream=true` 或 `export stream=true` 时每次从源游标读取的行数。
- `max_rows`: 查询或复制最大行数，默认 1000。
- `limit`: `query`/`scalar`/`copy` 返回行数上限。
- `offset`: `query`/`scalar`/`copy` 跳过前 N 行。
- `page_size`: `query`/`scalar`/`copy` 每页行数。
- `page`: `query`/`scalar`/`copy` 1 基页码，默认 1，需和 `page_size` 一起使用。
- `row_mode`: `dict` 或 `list`，默认 `dict`。
- `rows_path`: 查询结果写入 `output/sql/`，支持 `.json`、`.csv`、`.jsonl`。
- `result_path`: 执行摘要写入 `output/sql/`。
- `include_rows`: 指定 `rows_path` 后如仍需把 rows 放入变量，设为 `true`。
- `include_columns`: `inspect` 是否返回列信息，默认 `true`。
- `include_indexes`: `inspect` 是否返回索引信息，默认 `false`；当前 SQLite 信息最完整。
- `expect_affected_rows`: 断言影响行数，支持整数或整数数组。
- `timeout_ms`: 连接超时毫秒。
- `save_as`: 保存响应摘要变量名。

### transaction

```json
{
  "action": "sql",
  "type": "transaction",
  "connection": "crm_pg",
  "steps": [
    {
      "type": "execute",
      "sql": "update orders set status = :status where id = :id",
      "params": {
        "status": "synced",
        "id": 123
      }
    }
  ],
  "result_path": "transaction.json",
  "save_as": "tx_result"
}
```

- `steps`: 事务内的 SQL 子步骤数组，只允许 `query`、`scalar`、`execute`、`executemany`、`bulk_insert`。
- 事务成功自动提交，失败自动回滚。
- 事务子步骤不写 `action`、`connection`、`commit`、`save_as`、`rows_path` 或 `result_path`。

## 返回变量

`query` 返回 `columns`、`row_count`、`first_row`、可选 `rows` 和 `elapsed_ms`。

`scalar` 额外返回 `value`。

`execute`、`executemany`、`bulk_insert` 返回 `affected_rows`、批量数量或输入行数、`elapsed_ms`。
`import` 返回输入文件、目标表、输入行数、影响行数、批次数、列映射、是否流式和 `elapsed_ms`。
`export` 返回目标文件、输出格式、列名、导出行数、首行、是否流式和 `elapsed_ms`。
`copy` 返回源连接、目标连接、源行数、目标表、目标列、写入行数、影响行数、批次数和 `elapsed_ms`。
`transaction` 返回 `step_count`、`committed`、子步骤结果和 `elapsed_ms`。
`inspect` 返回 `tables`、`columns`、`indexes`、`table_count`、`column_count`、`index_count` 和 `elapsed_ms`。

## 输出约束

- `rows_path`、`result_path` 和 `target_path` 相对于当前 plan 包 `output/sql/`。
- 不要以 `output/` 开头。
- 大查询和大批量复制优先使用 `rows_path`/`result_path`，不要把全部 rows 放入变量池。
- 大结果还可以用 `.jsonl` 落盘。
- `copy stream=true` 时 `rows_path` 只支持 `.jsonl`，且不支持 `include_rows`。
- `import stream=true` 只支持 CSV/JSONL；JSON/Excel 仍使用普通模式。
- `export stream=true` 只支持 CSV/JSONL，且不支持 `include_rows`。
- 分页查询应在 SQL 中显式写 `order by`，避免数据变化时翻页结果不稳定。

## 参数规则

- 优先使用 `params`，不要拼接用户输入。
- SQLite 支持 `:name` 和 `?`。
- PostgreSQL/MySQL 使用 `:name` 时，运行期会转换为驱动支持的参数格式。
- Oracle 支持 `:name` 命名参数，连接可以使用 `oracle://user:password@host:port/service_name`。
- DuckDB 连接可以使用 `{"type": "duckdb", "path": "output/sql/local.duckdb"}`，参数建议使用 `?` 占位。
