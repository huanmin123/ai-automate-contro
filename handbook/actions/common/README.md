# 通用 action

本目录给 `automation_type: "browser"` 和 `automation_type: "desktop"` 共同使用。通用 action 不依赖浏览器 DOM，也不依赖桌面控件树。

## 功能目录

- [ai](./ai/ai.md): 受控专项 AI action。
- [control-flow](./control-flow/if.md): `if`、`foreach`、`retry`、`trigger`、`run_sub_plan`。
- [data](./data/variable.md): `variable`、`table`。
- [io](./io/read.md): `read`、`write`、`http`、`sql`、`mongo`、`redis`。
- [utility](./utility/manual_confirm.md): `command`、`manual_confirm`、`print`、`sleep`。

## 常用 action

| action | 作用 | 关键参数 | 场景 |
| --- | --- | --- | --- |
| `variable` | 设置或复制变量 | `type`、`name`、`value` | 拼装后续步骤参数 |
| `read` | 读取文本、JSON、CSV、Excel | `type`、`path` | 读取输入资源或本机文件 |
| `write` | 写 JSON、文本、CSV、Excel、变量 | `type`、`path`、`value`/`cells`/`sheets` | 输出结果到当前 plan 包 `output/` |
| `table` | 处理表格行数组 | `type`、`source`、`save_as` | Excel/CSV/JSON/SQL 读入后的筛选、清洗、拆列、合列、日期解析、查表、汇总、连接和透视 |
| `http` | 发 HTTP 请求 | `method`、`url`、`headers`、`body` | 调接口、下载文本、检查服务 |
| `sql` | 访问关系型数据库 | `type`、`connection`、`sql`/`table` | SQLite 本地落库、PG/MySQL/SQL Server 查询和更新、事务、schema 探测和批量写入 |
| `mongo` | 访问 MongoDB | `type`、`connection`、`collection`/`command` | 文档写入、条件查询、更新、聚合和原生命令 |
| `redis` | 访问 Redis | `type`、`connection`、`key`/`command` | 缓存、状态、队列、pipeline 和原生命令 |
| `command` | 同步执行本机命令 | `argv`/`command`/`commands` | 调脚本、转换文件、生成中间产物 |
| `manual_confirm` | 暂停等待用户确认 | `prompt`、`browser` | 登录、验证码、权限、不确定 UI |
| `ai` | 专项 AI 处理 | `type`、`input`、`schema` | 抽取、分类、转换、摘要 |
| `if`/`foreach`/`retry` | 控制流 | `condition`、`items`、`steps` | 分支、循环、失败重试 |

## 使用规则

- `write.path`、`read.path` 等 plan 内路径推荐使用 `/`。
- 输出 action 的 `path` 相对于当前 plan 包 `output/` 的对应分区，不要以 `output/` 开头。
- `command` 可以使用本机绝对路径、共享盘或外部工作目录；用户未指定固定路径时优先把输入放入当前 plan 包 `resources/`。
- 用户没有指定服务型数据库时，优先用 `sql` + SQLite 本地文件，数据库文件放在当前 plan 包 `output/sql/`。
- `manual_confirm` 只负责暂停和交接，不替代后续断言或状态采集。
