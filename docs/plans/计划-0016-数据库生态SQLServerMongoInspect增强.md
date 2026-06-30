# 计划-0016-数据库生态 SQL Server/Mongo/Inspect 增强

## 背景

数据库 common action 已覆盖 SQLite、PostgreSQL、MySQL/MariaDB、Oracle、Redis、DuckDB 和 SQL copy/transaction。后续需要补齐常见数据库生态能力，同时继续保持默认安装轻量，不把服务型数据库驱动打进基础依赖。

## 范围

- SQL Server: 作为 `sql` action 的懒加载后端，使用 `db-sqlserver`/`pyodbc` 按需安装。
- MongoDB: 新增独立 `mongo` common action，覆盖 CRUD、aggregate 和 command。
- DuckDB: 补充本地 CSV 分析示例，不进入默认离线自检。
- Schema 探测: 新增 `sql.inspect`，返回表、列和索引元数据。
- 文件导入导出: 新增 `sql.import`/`sql.export`，封装 CSV/JSON/JSONL/Excel 与 SQL 表之间的高频进出库流程。
- 真实服务回归: SQL 服务写入 smoke 增加“真实服务 -> 本地 SQLite”流式 copy 校验。
- 连接诊断: `database-components` 输出可选驱动安装状态和配置 inventory。

## 设计约束

- 默认安装不新增数据库驱动；所有服务型数据库继续按需安装。
- SQLite 仍是本地自动化默认推荐；DuckDB 只在本地分析需求明确时推荐。
- MongoDB 不并入 `sql`，避免把 SQL 表结构语义和文档数据库语义混合。
- 真实服务写入回归必须使用临时表/临时 collection，并尽量清理。

## 验证

- `python -m compileall -q src main.py cplan.py`
- `python .\cplan.py validate --file .\test-plans\database\duckdb-local-analysis\plan.json`
- `python .\cplan.py validate --file .\test-plans\database\mongodb-basic\plan.json`
- `python .\cplan.py self-check database-components`
- `python .\cplan.py self-check release-matrix --only database_components,compileall,handbook --fail-fast`

真实服务验证按本机配置显式运行：

```powershell
python .\cplan.py self-check database-components --include-real-db --allow-writes --database-config .\local\database-services.json
```
