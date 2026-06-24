# 浏览器自动化手册入口

本目录是 `automation_type: "browser"` plan 的阅读入口。浏览器线只控制 Playwright 浏览器会话、页面、DOM、网络、弹窗、下载、截图和浏览器上下文状态。

桌面窗口、系统设置、本机应用菜单、操作系统级键盘鼠标、屏幕 OCR 和图像定位不属于浏览器线；这些能力进入 [桌面控制手册入口](../desktop/README.md)。

## 适用 plan

```json
{
  "automation_type": "browser",
  "variables": {},
  "steps": []
}
```

## 可用 action 范围

浏览器专属 action：

- `open_browser`
- `close_browser`
- `page`
- `navigate`
- `element`
- `mouse`
- `keyboard`
- `scroll`
- `wait`
- `assert`
- `extract`
- `capture`
- `storage`
- `detect_challenge`
- `dialog`
- `network`
- `wait_for_popup`
- `wait_for_download`
- `wait_for_file_chooser`
- `wait_for_network`
- `event`
- `coverage`
- `trace`
- `script`

通用 action：

- `if`
- `foreach`
- `retry`
- `trigger`
- `run_sub_plan`
- `read`
- `write`
- `http`
- `command`
- `print`
- `sleep`
- `manual_confirm`
- `ai`

禁止在 browser plan 中使用 `open_desktop` 或 `desktop_*` action。

## 当前文档映射

现有浏览器 action 文档仍位于：

- [actions/browser](../actions/browser/)
- [actions/navigation](../actions/navigation/)
- [actions/interaction](../actions/interaction/)
- [actions/data](../actions/data/)
- [actions/utility](../actions/utility/)
- [actions/control-flow](../actions/control-flow/)
- [actions/io](../actions/io/)
- [actions/ai](../actions/ai/)

阅读时必须按本入口过滤 action 语义。`actions/interaction/mouse.md` 和 `actions/interaction/keyboard.md` 是浏览器页面内的 Playwright 输入，不是桌面键盘鼠标。

## 取证规则

真实网站、URL、后台页面或网页流程不能凭描述猜 selector。AI 创建最终 browser plan 前必须先获取页面证据，例如 `inspect_web_page` 的 DOM 摘要、表单、输入框、按钮、链接、表格和登录/验证信号。涉及登录、验证码、二次验证或动态后台时，继续运行 headed 探索 plan，并通过同一个 Playwright 浏览器窗口交接人工操作。
