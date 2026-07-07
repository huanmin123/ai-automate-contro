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
- 需要读写文件、执行本机命令、人工确认、变量或控制流时，读 [common](../common/README.md)。

## 最小示例

```json
{
  "automation_type": "browser",
  "steps": [
    {"action": "open_browser", "name": "main", "headed": true},
    {"action": "navigate", "browser": "main", "type": "goto", "url": "https://example.com"},
    {"action": "extract", "browser": "main", "type": "text", "selector": "h1", "output": {"as": "title"}},
    {"action": "write", "type": "json", "path": "title.json", "value": "{{title}}"},
    {"action": "close_browser", "browser": "main"}
  ]
}
```
