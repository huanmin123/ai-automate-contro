# 通用 action

本目录给 `automation_type: "browser"` 和 `automation_type: "desktop"` 共同使用。通用 action 不依赖浏览器 DOM，也不依赖桌面控件树。

## 功能目录

- [ai](./ai/ai.md): 受控专项 AI action。
- [control-flow](./control-flow/if.md): `if`、`foreach`、`retry`、`trigger`、`run_sub_plan`。
- [data](./data/variable.md): `variable`。
- [io](./io/read.md): `read`、`write`、`http`。
- [utility](./utility/manual_confirm.md): `command`、`manual_confirm`、`print`、`sleep`。

## 常用 action

| action | 作用 | 关键参数 | 场景 |
| --- | --- | --- | --- |
| `variable` | 设置或复制变量 | `type`、`name`、`value` | 拼装后续步骤参数 |
| `read` | 读取文本、JSON、CSV | `type`、`path` | 读取输入资源或本机文件 |
| `write` | 写 JSON、文本、CSV、变量 | `type`、`path`、`value` | 输出结果到当前 plan 包 `output/` |
| `http` | 发 HTTP 请求 | `method`、`url`、`headers`、`body` | 调接口、下载文本、检查服务 |
| `command` | 同步执行本机命令 | `argv`/`command`/`commands` | 调脚本、转换文件、生成中间产物 |
| `manual_confirm` | 暂停等待用户确认 | `message`、`timeout_seconds` | 登录、验证码、权限、不确定 UI |
| `ai` | 专项 AI 处理 | `type`、`input`、`schema` | 抽取、分类、转换、摘要 |
| `if`/`foreach`/`retry` | 控制流 | `condition`、`items`、`steps` | 分支、循环、失败重试 |

## 使用规则

- `write.path`、`read.path` 等 plan 内路径推荐使用 `/`。
- 输出 action 的 `path` 相对于当前 plan 包 `output/` 的对应分区，不要以 `output/` 开头。
- `command` 可以使用本机绝对路径、共享盘或外部工作目录；用户未指定固定路径时优先把输入放入当前 plan 包 `resources/`。
- `manual_confirm` 只负责暂停和交接，不替代后续断言或状态采集。
