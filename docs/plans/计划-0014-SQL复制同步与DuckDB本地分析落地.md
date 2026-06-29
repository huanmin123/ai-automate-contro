# 计划-0014-SQL复制同步与DuckDB本地分析落地

## 背景

数据库 action 已经覆盖查询、写入、批量、分页、事务和真实服务可选回归。用户常见需求是“上一节点拿到数据或条件后，从一个库查一批数据，再写入另一个库或本地库”。同时，很多自动化任务不想部署中间件，但又需要比 SQLite 更适合分析型数据处理的本地数据库。

本阶段补齐两个能力：

- `sql.copy`: 从一个 SQL 连接查询数据，批量写入另一个 SQL 连接。
- DuckDB: 作为按需安装的本地分析型 SQL 后端。

## 目标

- 新增 `sql type=copy`，支持源连接查询、字段映射、目标表批量写入、批次大小、结果摘要和可选 rows 落盘。
- 新增 DuckDB 连接类型，继续使用 optional extra 和懒加载。
- 默认自检仍不依赖外部服务或 DuckDB 驱动。
- SQLite 动态自检覆盖 `sql.copy`，保证复制链路可离线回归。
- 文档同步 `sql.copy`、DuckDB 和按需安装策略。

## 范围

- `sql.copy` 字段：
  - `connection`: 源 SQL 连接。
  - `target_connection`: 目标 SQL 连接。
  - `sql`、`params`: 源查询。
  - `table`: 目标表。
  - `columns`: 目标列，可省略并从源查询列推断。
  - `column_map`: `{目标列: 源查询列}`。
  - `mode`、`conflict_keys`、`update_columns`: 复用 `bulk_insert` 写入语义。
  - `batch_size`、`max_rows`、`limit`、`offset`、`page_size`、`page`。
  - `rows_path`、`result_path`、`save_as`。
- DuckDB 连接：
  - `{"type": "duckdb", "path": "output/sql/local.duckdb"}`。
  - `duckdb://` URL 简写。
  - `read_only` 连接选项。
- Optional extras：
  - `db-duckdb`
  - `database-local`

## 不做

- 不做无限流式复制。
- 不做后台同步任务、调度器或 CDC。
- 不自动建目标表、推断字段类型或迁移 schema。
- 不为 DuckDB 默认安装驱动。
- 不把 MongoDB、Redis 或 Elasticsearch 混入 `sql.copy`。

## 设计方向

### 1. `sql.copy` 语义

`copy` 是受控的“查询后批量写入”动作，不是长期同步系统。

示例：

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
  "batch_size": 500,
  "result_path": "orders-copy.json",
  "save_as": "orders_copy"
}
```

运行时先读取源查询结果，受 `max_rows` 保护；再按 `bulk_insert` 语义写入目标表。目标表必须已存在，或由前置 `sql.execute` 创建。

### 2. DuckDB 按需接入

DuckDB 适合本地分析任务，但包体比 SQLite 大，因此不进入默认依赖。

```powershell
pip install -e '.[db-duckdb]'
```

DuckDB 连接只在执行到对应连接时导入驱动。缺少驱动时返回明确安装提示。

### 3. 后续 stream/cursor

当前 `copy` 第一版以 `max_rows` 保护变量和内存，适合中小批量自动化数据搬运。

如果后续需要百万级数据同步，应新增 cursor/stream 版本：

- 源端分批 fetch。
- 目标端分批写入。
- 中途失败记录批次位置。
- 可选择每批落 JSONL 审计。

## 实施步骤

1. 在 SQL action 运行时新增 `copy` 类型。
2. 在 SQL 后端新增 DuckDB 连接分支和路径解析。
3. 在 plan 校验中加入 `copy` 类型、`target_connection`、`column_map` 和 DuckDB 连接类型。
4. 更新 optional extras，增加 `db-duckdb` 和 `database-local`。
5. 扩展 SQLite 动态自检，验证 SQLite 文件到 SQLite 文件复制。
6. 更新 handbook、功能设计、核心功能设计、测试说明和计划索引。
7. 运行编译、数据库组件和 release matrix 相关项。

## 风险

- 目标表结构不匹配会导致写入失败；当前不自动建表。
- `copy` 第一版会先取回本页数据再写入，超大数据量要等后续 cursor/stream。
- DuckDB 参数风格和各服务型数据库不同，文档建议使用 `?` 占位。
- `mode=upsert` 仍受目标数据库自身语法限制。

## 验收标准

- `sql.copy` 可以从一个 SQLite 文件复制到另一个 SQLite 文件，并生成结果摘要和 rows JSONL。
- `sql.copy` 支持 `column_map`、`batch_size`、`max_rows` 和分页字段。
- DuckDB 连接类型校验通过，运行时缺驱动提示 `db-duckdb`。
- 默认安装不包含 DuckDB。
- `python .\cplan.py self-check database-components` 通过。
- `python .\cplan.py self-check release-matrix --only database_components,compileall,handbook,workspace_clean --fail-fast` 通过。

## 文档同步

- [数据库连接 Action 设计](../functions/数据库连接Action设计.md)
- [核心功能设计](../functions/核心功能设计.md)
- [测试与验证说明](../develop/测试与验证说明.md)
- `handbook/actions/common/io/sql.md`
- `test-plans/database/README.md`
