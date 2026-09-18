# open_browser

## 用途

创建一个新的浏览器会话，供后续步骤使用。

这是大多数计划里的第一步。后面的 `navigate`、`element`、`wait` 等动作，都需要先绑定到一个已经打开的浏览器会话。

## 必填字段

- `action`: 固定写成 `open_browser`
- `name`: 浏览器会话名称，自定义即可，后续通过 `browser` 字段引用

## 可选字段

- `headed`: 是否显示浏览器窗口，默认 `false`
- `use_profile`: 是否使用当前 plan 包唯一的持久浏览器状态，默认 `false`
- `slow_mo_ms`: 每个 Playwright 动作之间增加的延迟，默认 `0`
- `timeout_ms`: 当前浏览器会话的默认超时时间，默认 `15000`
- `browser_type`: 浏览器类型，支持 `chromium`、`firefox`、`webkit`，默认 `chromium`
- `channel`: Chromium 渠道，例如 `chrome`、`msedge`
- `args`: 浏览器启动参数数组
- `device`: Playwright 设备预设名，例如 `iPhone 12`；预设会填充 viewport、user_agent、device_scale_factor、is_mobile、has_touch
- `proxy`: 代理配置对象
- `storage_state_path`: 从文件加载登录态或上下文状态，仅在显式填写时生效，没有自动默认路径。支持绝对路径和相对路径：以 `resources/`、`output/`、`docs/` 开头的相对路径基于当前 plan 包根解析，其他相对路径基于当前 `plan.json` 所在目录解析
- `viewport`: 视口尺寸，例如 `{"width": 1280, "height": 720}`
- `screen`: 屏幕尺寸
- `user_agent`: 自定义 User-Agent
- `locale`: 浏览器 locale，例如 `zh-CN`
- `timezone_id`: 时区，例如 `Asia/Shanghai`
- `geolocation`: 地理位置，例如 `{"latitude": 31.2, "longitude": 121.5}`
- `permissions`: 权限数组，例如 `["geolocation"]`
- `extra_http_headers`: 上下文级 HTTP 请求头
- `ignore_https_errors`: 是否忽略 HTTPS 错误，默认 `false`
- `accept_downloads`: 是否接受下载
- `color_scheme`、`reduced_motion`、`forced_colors`: 媒体特性
- `device_scale_factor`、`is_mobile`、`has_touch`: 移动端模拟参数
- `record_har_path`: 录制 HAR，路径相对于 `output/har/`
- `record_har_content`、`record_har_mode`、`record_har_url_filter`、`record_har_omit_content`: HAR 录制参数
- `record_video_dir`: 录制视频目录，路径相对于 `output/videos/`
- `record_video_size`: 视频尺寸
- `base_url`、`http_credentials`、`bypass_csp`、`java_script_enabled`、`offline`、`strict_selectors`、`service_workers`: Playwright 上下文参数

## 示例

```json
{
  "action": "open_browser",
  "name": "main",
  "headed": true,
  "slow_mo_ms": 200,
  "timeout_ms": 20000,
  "viewport": {
    "width": 1280,
    "height": 720
  },
  "locale": "zh-CN",
  "timezone_id": "Asia/Shanghai"
}
```

移动设备预设：

```json
{
  "action": "open_browser",
  "name": "mobile",
  "browser_type": "chromium",
  "device": "iPhone 12",
  "ignore_https_errors": true
}
```

复用当前 plan 包登录态：

```json
{
  "action": "open_browser",
  "name": "main",
  "headed": true,
  "channel": "chrome",
  "use_profile": true
}
```

## 什么时候用

- 你需要启动第一个浏览器窗口
- 你需要多个浏览器并行工作
- 你要给不同站点分配不同的会话
- 你要在同一个 plan 包内复用登录态、Cookie、localStorage、IndexedDB 等浏览器状态

## 稳定性和耗时经验

- 真实网站建议显式固定 `viewport`、`locale`、`timezone_id`，必要时固定 `channel`、`user_agent` 和请求头。这样页面布局、语言、时区和站点分流更稳定。
- 长期登录态优先使用 `use_profile: true`。同一个 plan 包只维护一套 `profiles/browser/`，适合后台系统、需要人工登录或二次验证后的重复执行。
- 批量任务尽量一次打开浏览器并复用页面，不要每条数据都 `open_browser`、登录、关闭再重开。启动浏览器和首次导航通常是浏览器流程里最重的固定成本。
- `slow_mo_ms` 只用于人工观察和调试，正式 plan 默认保持 `0`。需要等待页面状态时写 `wait` 条件，不要用 slow motion 代替等待。
- HAR、视频和 trace 都是显式调试产物。默认不要开启 `record_har_path`、`record_video_dir` 或 trace screenshots，除非正在定位网络、渲染或失败复盘问题。

## 注意事项

- `name` 不能重复。
- 如果你后面要写 `browser: "main"`，这里的 `name` 就必须叫 `main`。
- 默认新建一个空白上下文；需要文件级状态导入时使用 `storage_state_path`。
- 需要长期复用同一个 plan 包的登录态时，使用 `use_profile: true`。运行时固定使用当前 plan 包下的 `profiles/browser/`，不支持自定义 profile 目录、profile 名称或全局共享 profile。
- `use_profile: true` 使用 Playwright persistent context。Cookie、localStorage、IndexedDB、Cache Storage、Service Worker 和站点数据会保留在 `profiles/browser/`；sessionStorage 和纯 session cookie 是否跨运行保留取决于浏览器和目标站点。
- `use_profile: true` 仅支持 `browser_type: "chromium"`。需要真实 Chrome 或 Edge 时使用 `channel: "chrome"` 或 `channel: "msedge"`，仍然复用同一个 `profiles/browser/`。
- 同一时间只能打开一个 `use_profile: true` 的浏览器会话。再次打开前先 `close_browser`，再次打开仍复用同一个 `profiles/browser/`。
- `use_profile: true` 不能和 `storage_state_path` 同时使用。
- `storage_state_path` 默认引用当前 plan 包 `resources/...` 或 `output/storage-states/...`。AI 创建 plan 时，用户给出本机 storage state 文件但没有明确要求长期依赖该路径，必须先导入当前包 `resources/`。
- `storage_state_path` 支持绝对路径、共享盘、外部工作目录和越出 plan 包的相对路径；不需要审批字段。
- `profiles/` 是本机浏览器状态目录，必须由 `.gitignore` 过滤，不作为常规提交内容。
- plan JSON 内部路径统一使用 `/`，不要使用 Windows 反斜杠。
- `device` 不会自动切换 `browser_type`；需要指定浏览器内核时显式填写 `browser_type`。
- 多数真实站点调试时，优先显式设置 `viewport`、`locale`、`timezone_id`、`user_agent` 和必要的 `extra_http_headers`。
