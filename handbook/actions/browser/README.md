# 浏览器 action

本目录只给 `automation_type: "browser"` 使用。它控制 Playwright 浏览器会话、页面、DOM、网络、弹窗、下载、截图和浏览器上下文状态。

## 功能目录

- 会话和页面：[open_browser](./open_browser.md)、[page](./page.md)、[close_browser](./close_browser.md)。
- 导航、等待和触发事件：`navigate`、`wait`、`assert`、`network`、`event`。
- 页面交互：`element`、`input`。
- 页面数据：`extract`、`storage`、`detect_challenge`。
- 浏览器工具：`capture`、`dialog`、`event`、`coverage`、`trace`、`script`。

## 常用 action

| action | 作用 | 关键参数 | 典型场景 |
| --- | --- | --- | --- |
| `open_browser` | 打开浏览器会话 | `name`、`headed`、`browser_type`、`use_profile`、`storage_state_path` | 登录探索、复用状态、打开真实网页 |
| `navigate` | 页面跳转 | `type`、`url`、`browser`、`page` | `goto`、`refresh`、`back`、`forward` |
| `element` | DOM 元素操作 | `type`、locator、`value` | 点击、填写、上传、选择、勾选 |
| `wait` | 等待页面状态 | `type`、locator/URL/text/time | 等待加载、元素、文本、URL、函数 |
| `assert` | 页面断言 | `type`、locator/expected | 校验文本、URL、元素状态、数量 |
| `input` | 页面输入 | `device`、`type`、`key/value/x/y/delta_y` | 键盘、鼠标、触控、滚动 |
| `extract` | 页面提取 | `type`、locator、`output.as` | 提取文本、表格、属性、ARIA 快照 |
| `capture` | 保存浏览器产物 | `type`、`path` | 截图、HTML、storage state |
| `network` | 浏览器网络控制 | `type`、`url`、`headers` | route、unroute、HAR、headers |
| `event` | 浏览器事件 | `type`、`trigger`、`path/url/files` | 下载、文件选择器、popup、请求/响应捕获、运行事件采集 |
| `script` | 页面 JS | `type`、`js`、`arg` | 读取页面状态、注册初始化脚本 |

## 使用规则

- 浏览器 `input` 只作用于 Playwright 页面，不是操作系统级键鼠。
- 浏览器 `element` 使用 DOM/ARIA/文本等页面 locator，不读取桌面控件树。
- 下载、文件选择器、popup、请求/响应捕获统一使用 `event` action。
- 普通浏览器 action 不隐式截图；页面截图必须显式使用 `capture type=screenshot`。失败截图默认关闭，需要在 `config.failure_capture.browser_screenshot=true` 时才写入。
- 浏览器稳定性优先靠语义 locator、条件等待和结果断言，不靠固定 sleep、截图识别、长 CSS 层级或页面坐标。
- 批量流程优先复用同一个浏览器会话和页面；需要复用登录态时使用 `open_browser use_profile=true`，不要每条数据都重新启动、登录和关闭浏览器。
- 需要读写文件、执行本机命令、人工确认、变量或控制流时，读 [common](../common/README.md)。

## 最小示例

```json
{
  "automation_type": "browser",
  "steps": [
    {"description": "打开浏览器会话", "action": "open_browser", "name": "main", "headed": true},
    {"description": "进入示例页面", "action": "navigate", "browser": "main", "type": "goto", "url": "https://example.com"},
    {"description": "提取页面标题文本", "action": "extract", "browser": "main", "type": "text", "selector": "h1", "output": {"as": "title"}},
    {"description": "把标题写入 JSON 文件", "action": "write", "type": "json", "path": "title.json", "value": "{{title}}"},
    {"description": "关闭浏览器会话", "action": "close_browser", "browser": "main"}
  ]
}
```
