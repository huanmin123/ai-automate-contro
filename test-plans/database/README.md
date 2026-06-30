# Database Test Plans

数据库示例分两类：

- `sqlite-basic/`: 默认确定性回归，不依赖外部服务。
- `duckdb-local-analysis/`: DuckDB 本地 CSV 分析示例，按需安装 DuckDB 后运行。
- `mongodb-basic/`: MongoDB CRUD/aggregate/index 示例，按需安装 MongoDB 驱动后运行。
- `mysql-basic/`、`postgresql-basic/`、`oracle-basic/`、`redis-basic/`: 真实服务 smoke 示例，只引用连接名，不内置真实账号密码。

`python .\cplan.py self-check database-components` 还会动态生成 SQLite 特性 plan，覆盖事务、批量拆分、CSV 流式导入、导入字段校验、CSV 流式导出、JSONL 落盘、分页查询、`sql.inspect`，以及 `sql.copy` buffered/stream 两种跨 SQLite 文件复制。

SQLite 使用 Python 标准库，不需要额外依赖。真实服务驱动默认不安装，需要按目标库自行安装：

```powershell
pip install -e '.[db-mysql]'
pip install -e '.[db-postgresql]'
pip install -e '.[db-redis]'
pip install -e '.[db-oracle]'
pip install -e '.[db-duckdb]'
pip install -e '.[db-sqlserver]'
pip install -e '.[db-mongodb]'
```

DuckDB 是本地分析型 SQL 选项，也默认不安装。需要本地分析能力时可以安装 `db-duckdb` 或聚合入口 `database-local`。

真实服务连接建议写入本机 `config.json.connections` 或 `local/database-services.json`。`local/` 是本机私有目录，默认由 `.gitignore` 忽略；可提交样例见 `database-services.example.json`。

默认提交前矩阵只运行 SQLite，真实服务需要显式执行：

```powershell
python .\cplan.py self-check database-components --include-real-db --database-config .\local\database-services.json --allow-writes
```

也可以先用环境变量跑样例配置：

```powershell
$env:AIC_DB_MYSQL_HOST = "127.0.0.1"
$env:AIC_DB_MYSQL_USER = "root"
$env:AIC_DB_MYSQL_PASSWORD = "password"
$env:AIC_DB_MYSQL_DATABASE = "mysql"
$env:AIC_DB_POSTGRES_DSN = "postgres://user:password@127.0.0.1:5432/demo"
$env:AIC_DB_REDIS_URL = "redis://:password@127.0.0.1:6379/0"
$env:AIC_DB_ORACLE_USER = "user"
$env:AIC_DB_ORACLE_PASSWORD = "password"
$env:AIC_DB_ORACLE_DSN = "127.0.0.1:1521/service"
$env:AIC_DB_SQLSERVER_HOST = "127.0.0.1"
$env:AIC_DB_SQLSERVER_USER = "sa"
$env:AIC_DB_SQLSERVER_PASSWORD = "password"
$env:AIC_DB_SQLSERVER_DATABASE = "demo"
$env:AIC_DB_MONGODB_URI = "mongodb://127.0.0.1:27017/aic_demo"
$env:AIC_DB_ELASTICSEARCH_URL = "http://127.0.0.1:9200"

python .\cplan.py self-check database-components --include-real-db --database-config .\test-plans\database\database-services.example.json
```

配置支持这些环境变量引用写法：

- `{"env": "AIC_DB_MYSQL_PASSWORD"}`
- `{"env": "AIC_DB_MYSQL_PASSWORD", "default": "password"}`
- `"env:AIC_DB_MYSQL_PASSWORD"`
- `"$env:AIC_DB_MYSQL_PASSWORD"`
- `"${AIC_DB_MYSQL_PASSWORD}"`

内联配置示例：

```json
{
  "connections": {
    "mysql": {
      "type": "mysql",
      "host": "127.0.0.1",
      "port": 3306,
      "user": "user",
      "password": "password",
      "database": "demo"
    },
    "postgresql": {
      "type": "postgresql",
      "dsn": "postgresql://user:password@127.0.0.1:5432/demo"
    },
    "redis": {
      "type": "redis",
      "url": "redis://127.0.0.1:6379/0"
    },
    "oracle": {
      "type": "oracle",
      "user": "user",
      "password": "password",
      "dsn": "127.0.0.1:1521/service"
    },
    "sqlserver": {
      "type": "sqlserver",
      "host": "127.0.0.1",
      "port": 1433,
      "user": "sa",
      "password": "password",
      "database": "demo",
      "trust_server_certificate": true
    },
    "mongodb": {
      "type": "mongodb",
      "uri": "mongodb://127.0.0.1:27017/aic_demo",
      "database": "aic_demo"
    }
  },
  "elasticsearch": {
    "url": "http://127.0.0.1:9200"
  }
}
```

没有设置环境变量时，真实服务 case 会返回 `skipped=true` 和 `unresolved_env_refs`，不会把缺变量当成默认离线回归失败。`--allow-writes` 只对临时写入 smoke 生效，默认不开。开启后，真实 SQL 服务还会把临时表流式复制到本地 SQLite，验证跨库 copy 链路；MongoDB 写入回归会覆盖临时 collection 的插入、查询、索引创建/列出/删除和清理。
