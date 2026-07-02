# AI 编排手册入口

这个目录给 AI 创建、校验、运行和修复 JSON plan 使用。先确定执行线，再读取对应 action 文档，不要一次性读取整本手册。

## 读取顺序

1. 先读 [计划结构](./计划结构.md)，确认 plan 包、`automation_type`、变量、输出和子计划规则。
2. 根据 `automation_type` 进入 [浏览器自动化](./browser/README.md) 或 [桌面控制](./desktop/README.md)。
3. 写 step 时进入 [Action 手册索引](./actions/README.md)，只读对应执行线和通用 action。
4. 需要最小样例时读 [第一个计划示例](./第一个计划示例.md)。

## 执行线规则

- 主 `plan.json` 必须写 `automation_type`，只能是 `browser` 或 `desktop`。
- 子计划默认继承主 plan 执行线；显式声明时必须和主 plan 一致。
- 浏览器网页、DOM、Playwright selector、页面网络、下载、弹窗和浏览器 storage 使用 `browser`。
- 本机 App、窗口、菜单、系统键鼠、控件树、截图、OCR、图像定位和系统权限使用 `desktop`。
- 用户意图不明确时，先确认执行线；不要靠 action 名称猜。
- `browser` plan 只能用 `actions/browser` 和 `actions/common`。
- `desktop` plan 只能用 `actions/desktop` 和 `actions/common`。

## 取证规则

- 真实网页流程不能凭描述猜 selector。最终 browser plan 前先获取页面证据。
- 真实桌面流程不能凭描述猜窗口、控件或坐标。最终 desktop plan 前先获取 `desktop_capture type=observe`、窗口列表、控件树、截图、OCR/图像结果或人工确认。
- 需要登录、验证码、二次验证、安全弹窗或权限确认时，用 `manual_confirm` 交给用户。
- macOS Accessibility、Screen Recording、Automation 权限只能触发提示、打开设置并等待用户确认，不能静默授权。

## 路径和产物

- 输入资源推荐放当前 plan 包 `resources/`；用户明确要求本机绝对路径、共享盘或外部工作目录时按用户要求写。
- plan JSON 内部路径统一使用 `/`。
- 输出 action 的 `path` 相对于当前 plan 包 `output/` 的对应分区，不能以 `output/` 开头。
- 主 `plan.json` 是唯一入口；复用流程只调用同包 `sub-plans/*-plan.json`。

## 文档地图

- `reference/config.md`: `config.json`、AI 服务、运行后检查配置。
- `browser/README.md`: browser 执行线入口。
- `desktop/README.md`: desktop 执行线入口。
- `actions/README.md`: action 分类索引。
- `actions/browser/`: 浏览器专属 action。
- `actions/desktop/`: 桌面专属 action。
- `actions/common/`: 两条执行线共享 action，包括文件、HTTP、数据库、本地命令、控制流和专项 AI。

常用 action 精确路径：

- `navigate`: `actions/browser/navigation/navigate.md`
- `element`: `actions/browser/interaction/element.md`
- `wait`: `actions/browser/navigation/wait.md`
- `extract`: `actions/browser/data/extract.md`
- `desktop_window`: `actions/desktop/desktop_window.md`
- `desktop app profile`: `actions/desktop/app_profile.md`
- `desktop_element`: `actions/desktop/desktop_element.md`，控件定位、读取、写值、选择、表格、树、菜单、滚动容器
- `desktop_input`: `actions/desktop/desktop_input.md`
- `desktop_capture`: `actions/desktop/desktop_capture.md`，截图、状态快照、统一观察
- `desktop 定位策略`: `actions/desktop/locator_strategy.md`
- `read`: `actions/common/io/read.md`
- `write`: `actions/common/io/write.md`
- `table`: `actions/common/data/table.md`
- `http`: `actions/common/io/http.md`
- `sql`: `actions/common/io/sql.md`
- `mongo`: `actions/common/io/mongo.md`
- `redis`: `actions/common/io/redis.md`
- `command`: `actions/common/utility/command.md`
- `manual_confirm`: `actions/common/utility/manual_confirm.md`

## 写 step 规则

- 组件名就是 step 的 `action`。
- 参数结构一致的能力用同一 action 的 `type` 区分，例如 `navigate`、`element`、`wait`、`extract`、`assert`、`read`、`write`、`desktop_window`。
- 生命周期独立的能力保留独立 action，例如 `open_browser`、`open_desktop`、`run_sub_plan`、`trigger`、`foreach`、`retry`、`wait_for_popup`、`wait_for_download`、`http`、`sql`、`mongo`、`redis`、`command`。
- 专项 AI 统一使用 `ai` action，通过 `type` 区分抽取、分类、转换和摘要。
- 变量使用 `{{变量名}}` 引用；业务变量放在 `plan.json.variables`，运行配置放在 `config.json`。
- 跨节点数据由上游 step 使用 `output` 发布，声明 `as`、可选 `from`、`type` 和 `fields`；下游直接引用发布后的变量，不需要声明输入。
