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

- [actions/browser](../actions/browser/README.md): `open_browser`、`close_browser`、`page`。
- [actions/browser/navigation](../actions/browser/navigation/navigate.md): `navigate`、`wait`、`assert`、`network`、`wait_for_popup`、`wait_for_download`、`wait_for_file_chooser`、`wait_for_network`。
- [actions/browser/interaction](../actions/browser/interaction/element.md): `element`、`mouse`、`keyboard`、`scroll`。
- [actions/browser/data](../actions/browser/data/extract.md): `extract`、`storage`、`detect_challenge`。
- [actions/browser/utility](../actions/browser/utility/capture.md): `capture`、`dialog`、`event`、`coverage`、`trace`、`script`。

通用 action 文档：

- [actions/common](../actions/common/README.md): `if`、`foreach`、`retry`、`trigger`、`run_sub_plan`、`variable`、`read`、`write`、`http`、`command`、`print`、`sleep`、`manual_confirm`、`ai`。

禁止在 browser plan 中使用 `open_desktop` 或 `desktop_*` action。

## 写法规则

- 浏览器 `mouse`、`keyboard` 是页面内 Playwright 输入，不是操作系统级键鼠。
- 浏览器 `element` 使用 DOM/ARIA/文本 locator，不使用桌面控件树。
- 真实网站、URL、后台页面或网页流程不能凭描述猜 selector。最终 browser plan 前先获取页面证据。
- 登录、验证码、二次验证或动态后台需要用户介入时，用 headed 浏览器和 `manual_confirm` 交接。
