# 浏览器自动化手册入口

本入口只给 `automation_type: "browser"` plan 使用。浏览器线控制 Playwright 浏览器、页面、DOM、网络、弹窗、下载、截图和浏览器上下文状态。

桌面窗口、本机 App、系统键鼠、图像定位和系统权限进入 [桌面控制手册入口](../desktop/README.md)。

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
- 导航、等待和浏览器事件：[navigate](../actions/browser/navigation/navigate.md)、[wait](../actions/browser/navigation/wait.md)、[assert](../actions/browser/navigation/assert.md)、[network](../actions/browser/navigation/network.md)、[event](../actions/browser/utility/event.md)。
- 页面交互：[element](../actions/browser/interaction/element.md)、[input](../actions/browser/interaction/input.md)。
- 页面数据：[extract](../actions/browser/data/extract.md)、[storage](../actions/browser/data/storage.md)、[detect_challenge](../actions/browser/data/detect_challenge.md)。
- 浏览器工具：[capture](../actions/browser/utility/capture.md)、[dialog](../actions/browser/utility/dialog.md)、[event](../actions/browser/utility/event.md)、[coverage](../actions/browser/utility/coverage.md)、[trace](../actions/browser/utility/trace.md)、[script](../actions/browser/utility/script.md)。

通用 action 文档：

- [actions/common](../actions/common/README.md): `if`、`foreach`、`retry`、`trigger`、`run_sub_plan`、`variable`、`read`、`write`、`http`、`sql`、`mongo`、`redis`、`command`、`print`、`sleep`、`manual_confirm`、`ai`。

禁止在 browser plan 中使用 `open_desktop` 或 `desktop_*` action。

## 写法规则

- 浏览器 `input` 是页面内 Playwright 输入，不是操作系统级键鼠。
- 浏览器 `element` 使用 DOM/ARIA/文本 locator，不使用桌面控件树。
- 下载、文件选择器、popup、新请求和新响应等待统一写 `event type=download/file_chooser/popup/request/response`。
- 真实网站、URL、后台页面或网页流程不能凭描述猜 selector。最终 browser plan 前先获取页面证据。
- 普通浏览器 action 不隐式截图；页面截图必须显式调用 `capture type=screenshot`，失败截图必须在 `config.failure_capture.browser_screenshot` 中显式开启。
- 登录、验证码、二次验证或动态后台需要用户介入时，用 headed 浏览器和 `manual_confirm` 交接。

## 稳定性和耗时经验

- 浏览器线的“定位”优先是页面语义和 DOM 定位，不是屏幕坐标。优先使用 `role + name`、`label`、`placeholder`、`test_id`、稳定业务属性或短 CSS selector；少用长层级 CSS、XPath、nth-child 和绝对坐标。
- 真实网站最终 plan 前先用 `inspect_web_page` 或 headed 探索拿页面证据。不要只凭用户描述猜 selector；登录、后台菜单、验证码、动态表格和 iframe 页面尤其要先探测。
- 输入框优先用 `element type=fill`，下拉框用 `element type=select`，上传文件用 `element type=set_files`。只有需要模拟特殊按键、滚动、拖拽或页面级键鼠时才用浏览器 `input`。
- 等待优先使用条件等待：`wait type=selector/url/text/count/load_state/element_state/function`。固定 `wait type=time` 只适合短暂动画、节流、人工观察或没有稳定条件的兜底，不要用长 sleep 代替 selector 或接口状态。
- `networkidle` 只适合无长轮询、无持续埋点、无 WebSocket/SSE 的页面。后台系统、聊天页、实时看板、广告/埋点多的页面，优先等目标 selector、URL、文本、接口响应或 JS 状态。
- 下载、文件选择器、popup、请求和响应必须用 `event` 的 `trigger` 包起来，让等待先挂上再执行点击。不要先 `element click` 再单独等下载或响应，事件可能已经错过。
- 登录态复用优先用 `open_browser use_profile=true`，同一个 plan 包只保留一套 `profiles/browser/`。批量任务尽量复用同一个浏览器会话和页面，避免每条数据都重新打开浏览器、登录和关闭。
- 数据提取优先用确定性 action：`extract table/all_texts/text/value/attribute`，必要时配合 `script evaluate` 读页面状态或应用 store。页面已有结构化数据时，不要把整页文本交给 `ai` action 重新猜。
- 普通流程不隐式截图、不开 trace screenshot、不过度保存 HTML。需要排查时显式使用 `capture`、`event start/stop`、`trace` 或失败采集配置；默认流程保持轻量。
- 优化前先看 `output/<run>/events.jsonl` 或 `run.log`，按 step 计算耗时。慢点通常在打开浏览器、首次导航、登录人工交接、条件等待超时边缘、接口响应、下载或大表提取；先定位瓶颈再改等待或 selector。
- 对外可复用 plan 每个 step 写中文 `description`，让运行日志能直接显示“这一步为什么存在”和“慢在哪个业务动作”。
