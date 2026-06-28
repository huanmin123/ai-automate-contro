# Action 手册索引

本目录按执行线分层。AI 写 plan 时先确定 `automation_type`，再读取对应目录。

## 目录

- [browser](./browser/README.md): 只给 `automation_type: "browser"` 使用，控制 Playwright 浏览器、页面、DOM、网络、下载和浏览器上下文。
- [desktop](./desktop/README.md): 只给 `automation_type: "desktop"` 使用，控制本机桌面、App、窗口、控件、键鼠、截图和桌面状态。
- [common](./common/README.md): browser 和 desktop 都可使用，不绑定浏览器 DOM 或桌面控件。

## 使用规则

- browser plan = `actions/browser` + `actions/common`。
- desktop plan = `actions/desktop` + `actions/common`。
- 不存在 `handbook/actions/<action>.md` 平铺路径。
- 查具体 action 时读精确文件，不要把相似 action 混用。例如浏览器 `element` 和桌面 `desktop_element` 是两套定位模型。

## 常用路径

| action | 路径 | 场景 |
| --- | --- | --- |
| `open_browser` | `actions/browser/open_browser.md` | 创建 Playwright 浏览器会话 |
| `navigate` | `actions/browser/navigation/navigate.md` | 页面跳转、刷新、前进后退 |
| `element` | `actions/browser/interaction/element.md` | 浏览器 DOM 元素点击、填写、选择 |
| `extract` | `actions/browser/data/extract.md` | 从页面提取文本、表格、属性、ARIA |
| `open_desktop` | `actions/desktop/open_desktop.md` | 创建桌面控制 session |
| `desktop_window` | `actions/desktop/desktop_window.md` | 列出、聚焦、关闭、最小化、最大化窗口 |
| `desktop_element` | `actions/desktop/desktop_element.md` | 桌面控件树定位、读取、点击、写值、表格、树、菜单、滚动容器 |
| `desktop_input` | `actions/desktop/desktop_input.md` | 系统级输入、快捷键、坐标级点击/双击/右键/滚动/拖拽 |
| `desktop_capture` | `actions/desktop/desktop_capture.md` | 截图、状态快照、`type=observe` 统一观察 |
| `write` | `actions/common/io/write.md` | 写 JSON、文本、CSV、变量快照 |
| `command` | `actions/common/utility/command.md` | 同步执行本机命令 |
| `manual_confirm` | `actions/common/utility/manual_confirm.md` | 人工登录、验证码、权限或不确定 UI 交接 |
