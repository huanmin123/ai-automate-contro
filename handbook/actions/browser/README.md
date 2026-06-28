# 浏览器 action

本目录只给 `automation_type: "browser"` 使用。它控制 Playwright 浏览器会话、页面、DOM、网络、弹窗、下载、截图和浏览器上下文状态。

## 功能目录

- 会话和页面：[open_browser](./open_browser.md)、[page](./page.md)、[close_browser](./close_browser.md)。
- 导航和等待：`navigate`、`wait`、`assert`、`network`、`wait_for_popup`、`wait_for_download`、`wait_for_file_chooser`、`wait_for_network`。
- 页面交互：`element`、`keyboard`、`mouse`、`scroll`。
- 页面数据：`extract`、`storage`、`detect_challenge`。
- 浏览器工具：`capture`、`dialog`、`event`、`coverage`、`trace`、`script`。

## 常用 action

| action | 作用 | 关键参数 | 典型场景 |
| --- | --- | --- | --- |
| `open_browser` | 打开浏览器会话 | `name`、`headed`、`browser_type`、`storage_state_path` | 登录探索、复用状态、打开真实网页 |
| `navigate` | 页面跳转 | `type`、`url`、`browser`、`page` | `goto`、`refresh`、`back`、`forward` |
| `element` | DOM 元素操作 | `type`、locator、`value` | 点击、填写、上传、选择、勾选 |
| `wait` | 等待页面状态 | `type`、locator/URL/text/time | 等待加载、元素、文本、URL、函数 |
| `assert` | 页面断言 | `type`、locator/expected | 校验文本、URL、元素状态、数量 |
| `extract` | 页面提取 | `type`、locator、`save_as` | 提取文本、表格、属性、ARIA 快照 |
| `capture` | 保存浏览器产物 | `type`、`path` | 截图、HTML、storage state |
| `network` | 浏览器网络控制 | `type`、`url`、`headers` | route、unroute、HAR、headers |
| `script` | 页面 JS | `type`、`js`、`arg` | 读取页面状态、注册初始化脚本 |

## 使用规则

- 浏览器 `mouse` 和 `keyboard` 只作用于 Playwright 页面，不是操作系统级键鼠。
- 浏览器 `element` 使用 DOM/ARIA/文本等页面 locator，不读取桌面控件树。
- 需要读写文件、执行本机命令、人工确认、变量或控制流时，读 [common](../common/README.md)。

## 最小示例

```json
{
  "automation_type": "browser",
  "steps": [
    {"action": "open_browser", "name": "main", "headed": true},
    {"action": "navigate", "browser": "main", "type": "goto", "url": "https://example.com"},
    {"action": "extract", "browser": "main", "type": "text", "selector": "h1", "save_as": "title"},
    {"action": "write", "type": "json", "path": "title.json", "value": "{{title}}"},
    {"action": "close_browser", "browser": "main"}
  ]
}
```
