# 执行线隔离与 Plan 类型设计

## 背景

项目即将从单一浏览器自动化内核，扩展为浏览器自动化和桌面控制两条执行线。两条线都使用 JSON plan、变量、输出目录、运行日志和 AI 终端协作，但它们的定位方式、运行时资源、权限边界、失败证据和 action 语义完全不同。

如果继续让执行器只按 `action` 名称猜测运行方式，桌面能力会逐步污染浏览器模型，浏览器 selector、桌面控件 selector、坐标、截图和权限处理也会混在一起。新的 schema 必须先声明 plan 属于哪条执行线，再由执行器选择对应解析器和 action registry。

## 顶层类型

下一版 plan 顶层新增必填字段：

```json
{
  "automation_type": "browser",
  "variables": {},
  "steps": []
}
```

允许值：

- `browser`: 浏览器自动化 plan，只能使用浏览器线 action 和通用 action。
- `desktop`: 桌面控制 plan，面向真实 Windows/macOS 桌面会话中的 App、窗口、控件、键鼠、截图和视觉识别，只能使用桌面线 action 和通用 action。

不使用顶层字段名 `type`，因为 step 内部已经统一用 `type` 区分同一 action 下的具体操作。`automation_type` 明确表示执行线，不和 action 参数混淆。

当前不引入 `hybrid`。同一个 `plan.json` 不能同时混用浏览器和桌面专属 action。未来如果确实需要跨线编排，应单独设计更高层的 orchestration plan，而不是让普通 plan 同时拥有两个运行时。

## 兼容边界

项目默认按当前最优 schema 开发。桌面线落地时，`automation_type` 应成为主 `plan.json` 必填字段，不做“缺省为 browser”的长期运行时兜底。

迁移既有 browser plan 时，应通过一次性文档化迁移或批量更新示例 plan，把顶层补为：

```json
{
  "automation_type": "browser",
  "variables": {},
  "steps": []
}
```

子计划规则：

- 主 `plan.json` 必须声明 `automation_type`。
- `sub-plans/*-plan.json` 默认继承主 plan 的 `automation_type`。
- 子计划如果显式声明 `automation_type`，必须和主 plan 一致。
- 不允许 browser 主 plan 调用 desktop 子计划，也不允许 desktop 主 plan 调用 browser 子计划。

## Action 分区

执行器按 `automation_type` 加载 action 分区：

| 分区 | browser plan | desktop plan | 说明 |
| --- | --- | --- | --- |
| browser actions | 允许 | 禁止 | `open_browser`、`navigate`、`element`、浏览器 `mouse`/`keyboard`、浏览器 `capture` 等 |
| desktop actions | 禁止 | 允许 | `open_desktop`、`desktop_app type=launch`、`desktop_window`、`desktop_element`、`desktop_input type_text/hotkey/click/double_click/right_click/scroll/drag`、`desktop_capture`、`desktop_wait`、`desktop_assert` 等 |
| common actions | 允许 | 允许 | `if`、`foreach`、`retry`、`trigger`、`run_sub_plan`、`read`、`write`、`http`、`command`、`print`、`sleep`、`manual_confirm`、受控专项 `ai` 等 |

通用 action 也必须避免隐式绑定某一条执行线。例如 `manual_confirm` 可以用于浏览器登录，也可以用于 macOS 权限授权；具体提示文案由 plan 决定。

## 执行器分发

执行器入口先读取和校验 plan 顶层：

```text
load plan
  -> validate common plan shape
  -> read automation_type
  -> select action registry
  -> select runtime managers
  -> execute steps
```

`browser` plan 创建浏览器运行时：

- `BrowserSession`
- Playwright lifecycle
- 浏览器失败截图、HTML、page state
- 浏览器 action registry

`desktop` plan 创建桌面运行时：

- `DesktopSession`
- Windows/macOS backend adapter
- 桌面截图、窗口列表、控件树、`capability_matrix`、权限诊断和鼠标/控件操作标注证据
- 桌面 action registry

桌面运行时不是终端命令包装，也不是某个单一 App 的专用控制器。它抽象的是当前用户可见桌面会话中人类可以通过键盘、鼠标、窗口、控件、菜单和屏幕视觉完成的操作；遇到系统安全边界、权限缺失或不可可靠识别的 UI 时，应失败、跳过或通过人工确认交接。

两条线共享：

- plan 包定位和输出根
- 变量模板渲染
- 条件、循环、重试和子计划
- 文件读写、HTTP、command
- 运行日志、事件流、result/report/state
- AI 终端工具的 plan 创建、校验、运行和调试入口

## 校验规则

validator 必须在运行前拒绝跨线 action：

- `automation_type=browser` 时，出现 `open_desktop` 或 `desktop_*` 必须失败。
- `automation_type=desktop` 时，出现 `open_browser`、`navigate`、`element`、浏览器 `mouse`、浏览器 `keyboard`、浏览器 `capture` 必须失败。
- 未声明 `automation_type` 的主 plan 必须失败。
- 子计划声明不同 `automation_type` 必须失败。
- `automation_type` 不在允许值内必须失败。

错误信息要面向修复：

```text
plan automation_type=desktop，但 step[3] 使用浏览器 action navigate。桌面 plan 只能使用 desktop action 或 common action。
```

## Handbook 隔离

handbook 入口应先让 AI 或维护者选择执行线：

```text
handbook/
  README.md
  计划结构.md
  browser/
    README.md
  desktop/
    README.md
  actions/
    ...
```

`browser/README.md` 是浏览器线入口，只链接浏览器 action 和通用 action。`desktop/README.md` 是桌面线入口，只链接桌面 action 设计和通用 action。现有 `actions/` 目录在迁移期仍承载已实现 action 文档，但入口必须按执行线过滤阅读，不能把浏览器 `mouse`/`keyboard` 当成桌面键鼠使用。

新增或修改 action 文档时按执行线放置：浏览器专属 action 放入 `handbook/actions/browser/`，桌面专属 action 放入 `handbook/actions/desktop/`，两条执行线共享的 action 放入 `handbook/actions/common/`。

## AI 终端决策

AI 终端收到创建 plan 的需求时，必须先判断执行线：

1. 用户明确说网页、URL、浏览器、Chrome 页面、后台网页、DOM、表单、网页按钮：判定为 `browser`。
2. 用户明确说桌面软件、本机应用、窗口、菜单栏、系统设置、Finder、Excel 桌面版、Notepad、TextEdit、键盘鼠标控制电脑：判定为 `desktop`。
3. 用户描述同时可能是网页也可能是桌面应用，例如“打开微信/企业后台/表格/客户端登录”：必须追问。
4. 用户目标涉及真实桌面权限、macOS 授权、Windows UAC、安全桌面或本机 App 安装位置：必须追问或用探测工具取证。

只要执行线不明确，AI 终端不得直接写 `plan.json`。它必须先向用户确认：

```text
你要自动化的是网页里的流程，还是本机桌面应用里的流程？两者的 plan 类型不同。
```

用户确认后，AI 才能写入 `automation_type` 并进入对应 handbook。

## 终端与 CLI

`cplan create` 应提供 plan 类型参数：

```powershell
python .\cplan.py create --path .\plans\demo --automation-type browser
python .\cplan.py create --path .\plans\desktop-demo --automation-type desktop
```

交互创建时如果缺少 `--automation-type`，管理端可以提示用户输入；非交互脚本应直接报错，避免生成无类型 plan。

`cplan validate` 和 `cplan run` 不允许根据 action 猜类型。它们只读取 `automation_type`，再调用对应校验和执行路径。

## 文档同步

涉及以下改动时必须同步本文：

- 新增或修改 `automation_type` 枚举。
- 新增执行线或允许跨线编排。
- 修改 action 分区。
- 修改 handbook 目录隔离方式。
- 修改 AI 终端的执行线判定和确认规则。
- 修改 `cplan create/validate/run` 的 plan 类型参数。
