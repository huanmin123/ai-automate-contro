# 浏览器自动化手册入口

本入口只给 `automation_type: "browser"` plan 使用。浏览器线控制 Playwright 浏览器、页面、DOM、网络、弹窗、下载、截图和浏览器上下文状态。

桌面窗口、本机 App、系统键鼠、屏幕 OCR、图像定位和系统权限进入 [桌面控制手册入口](../desktop/README.md)。

## 适用 plan

```json
{
  "automation_type": "browser",
  "variables": {},
  "steps": []
}
```

## 可用 action

浏览器专属 action 文档：

- [actions/browser](../actions/browser/README.md): 浏览器专属 action 索引。
- 会话和页面：[open_browser](../actions/browser/open_browser.md)、[page](../actions/browser/page.md)、[close_browser](../actions/browser/close_browser.md)。
- 导航和等待：[navigate](../actions/browser/navigation/navigate.md)、[wait](../actions/browser/navigation/wait.md)、[assert](../actions/browser/navigation/assert.md)、[network](../actions/browser/navigation/network.md)、[wait_for_popup](../actions/browser/navigation/wait_for_popup.md)、[wait_for_download](../actions/browser/navigation/wait_for_download.md)、[wait_for_file_chooser](../actions/browser/navigation/wait_for_file_chooser.md)、[wait_for_network](../actions/browser/navigation/wait_for_network.md)。
- 页面交互：[element](../actions/browser/interaction/element.md)、[mouse](../actions/browser/interaction/mouse.md)、[keyboard](../actions/browser/interaction/keyboard.md)、[scroll](../actions/browser/interaction/scroll.md)。
- 页面数据：[extract](../actions/browser/data/extract.md)、[storage](../actions/browser/data/storage.md)、[detect_challenge](../actions/browser/data/detect_challenge.md)。
- 浏览器工具：[capture](../actions/browser/utility/capture.md)、[dialog](../actions/browser/utility/dialog.md)、[event](../actions/browser/utility/event.md)、[coverage](../actions/browser/utility/coverage.md)、[trace](../actions/browser/utility/trace.md)、[script](../actions/browser/utility/script.md)。

通用 action 文档：

- [actions/common](../actions/common/README.md): `if`、`foreach`、`retry`、`trigger`、`run_sub_plan`、`variable`、`read`、`write`、`http`、`sql`、`mongo`、`redis`、`command`、`print`、`sleep`、`manual_confirm`、`ai`。

禁止在 browser plan 中使用 `open_desktop` 或 `desktop_*` action。

## 写法规则

- 浏览器 `mouse`、`keyboard` 是页面内 Playwright 输入，不是操作系统级键鼠。
- 浏览器 `element` 使用 DOM/ARIA/文本 locator，不使用桌面控件树。
- 真实网站、URL、后台页面或网页流程不能凭描述猜 selector。最终 browser plan 前先获取页面证据。
- 登录、验证码、二次验证或动态后台需要用户介入时，用 headed 浏览器和 `manual_confirm` 交接。
