# 计划-0009-数据库连接 Common Action 落地

## 背景

浏览器和桌面自动化经常需要和数据库协作：从页面或桌面软件拿到一批数据后写入数据库，更新某条业务记录，或把上一节点的数据转换为查询条件并把查询结果传给下一节点。

当前可以通过 `command` 调本机脚本绕过，但这种方式缺少 action 级 schema、统一变量结构、输出分区、失败日志和 AI 生成 plan 时的稳定契约。数据库能力应成为 browser/desktop 共享的 common action。

## 目标

- 新增 `sql` common action，SQLite 作为本地化优先路径，另覆盖 PostgreSQL、MySQL/MariaDB、Oracle。
- 新增 `redis` common action，覆盖 Redis 常见 key、hash、list、set、expire、原生命令和 pipeline。
- 数据库 action 不引入第三条执行线，继续由 `automation_type: "browser"` 或 `"desktop"` plan 使用 common action。
- 支持连接配置通过 `config.json.connections` 或 plan 变量引用。
- 查询结果、执行摘要和大结果文件进入当前 plan 包 `output/sql/` 或 `output/redis/`。
- 保持本地调试原文优先，不脱敏 DSN、SQL、参数、Redis key 或返回值。

## 范围

- 新增 `sql` action runtime、校验规则、handbook 和 SQLite 回归 plan；SQLite 不依赖外部服务或额外 Python 包。
- 新增 `redis` action runtime、校验规则和 handbook；真实 Redis 服务回归后续单独补。
- 更新功能文档、handbook 索引和验证说明。
- `pyproject.toml` 增加按驱动拆分的数据库可选依赖组。

## 不做

- 不新增 `automation_type: "database"` 或 `hybrid`。
- 不实现 ORM、迁移系统、连接池或长期后台连接管理。
- 不自动根据字段名脱敏日志或输出。
- 不解析任意复杂 SQL AST；复杂 SQL 仍直接写 `sql` 字段并使用参数绑定。
- 不在第一阶段要求本机具备 PostgreSQL、MySQL、Oracle 或 Redis 服务。

## 关键设计

### `sql`

支持类型：

- `query`: 查询多行，保存 rows/first_row/columns/row_count。
- `scalar`: 查询单值，保存 `value`。
- `execute`: 执行单条 insert/update/delete/DDL。
- `executemany`: 参数数组批量执行。
- `bulk_insert`: 把数组数据写入表，支持 `insert`、`replace`、`upsert`。

连接：

```json
{
  "connections": {
    "crm_pg": {
      "type": "postgresql",
      "dsn": "postgresql://user:password@127.0.0.1:5432/crm"
    },
    "warehouse_mysql": {
      "type": "mysql",
      "dsn": "mysql://user:password@127.0.0.1:3306/warehouse"
    },
    "local_sqlite": {
      "type": "sqlite",
      "path": "output/sql/local.db"
    }
  }
}
```

参数：

- SQLite 使用 `:name` 或 `?`，是默认推荐的本地化自动化存储方案。
- PostgreSQL/MySQL 的命名参数在运行期从 `:name` 转成驱动支持的 pyformat；Oracle 保留原生 `:name` 命名参数。
- 批量插入用生成 SQL，表名和列名只接受简单标识符或 `schema.table`。

### `redis`

支持类型：

- `get`、`set`、`delete`
- `hget`、`hset`、`hgetall`
- `lpush`、`rpush`、`lrange`
- `sadd`、`smembers`
- `expire`
- `command`
- `pipeline`

Redis 依赖可选 `redis` Python 包。没有安装时，运行期返回明确依赖错误。

## 实施步骤

1. 新增 `sql_client.py` 和 `redis_client.py`，加入 action executor 注册。
2. 在 validator 中登记 `sql`、`redis` 的 action 类型、common 分区和输出路径。
3. 在 `pyproject.toml` 新增按驱动拆分的 optional dependency。
4. 新增 `handbook/actions/common/io/sql.md` 和 `redis.md`。
5. 新增 `test-plans/database/sqlite-basic/`，用 SQLite 验证 query/execute/bulk_insert/scalar 和产物。
6. 更新 `docs/functions/数据库连接Action设计.md`、`docs/functions/核心功能设计.md`、handbook 和测试说明。
7. 运行 SQLite 回归、handbook 校验和 Python 编译检查。

## 验收标准

- `python .\cplan.py validate --file .\test-plans\database\sqlite-basic\plan.json` 通过。
- `python .\cplan.py run --file .\test-plans\database\sqlite-basic\plan.json --run-name sqlite-basic` 通过。
- `python -m compileall .\src\ai_automate_contro` 通过。
- `python .\cplan.py self-check handbook` 通过。
- `sql` 和 `redis` 均可在 browser/desktop plan 中通过 common action 分区校验。
- 输出文件只能写入 `output/sql/` 或 `output/redis/`。

## 风险

- SQLite 是默认可用的本地文件数据库；PostgreSQL/MySQL/Oracle/Redis 依赖外部服务，默认回归不能假设本机存在这些服务。
- 跨数据库 upsert 语法存在差异，第一版只覆盖简单冲突键和简单列。
- 大查询结果不能直接塞进变量；需要用 `rows_path` 或收窄查询。
- 用户把生产库连接写进 plan/config 时，项目按本地调试原文保留，是否提交由用户决定。

## 文档同步

- [数据库连接 Action 设计](../functions/数据库连接Action设计.md)
- `handbook/actions/common/io/sql.md`
- `handbook/actions/common/io/redis.md`
- `handbook/actions/common/README.md`
- `handbook/README.md`
- `docs/functions/核心功能设计.md`
- `docs/develop/测试与验证说明.md`
