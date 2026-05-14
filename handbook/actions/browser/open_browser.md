# open_browser

## 用途

创建一个新的浏览器会话，供后续步骤使用。

这是大多数计划里的第一步。后面的 `navigate`、`element`、`wait` 等动作，都需要先绑定到一个已经打开的浏览器会话。

## 必填字段

- `action`: 固定写成 `open_browser`
- `name`: 浏览器会话名称，自定义即可，后续通过 `browser` 字段引用

## 可选字段

- `headed`: 是否显示浏览器窗口，默认 `false`
- `slow_mo_ms`: 每个 Playwright 动作之间增加的延迟，默认 `0`
- `timeout_ms`: 当前浏览器会话的默认超时时间，默认 `15000`
- `browser_type`: 浏览器类型，支持 `chromium`、`firefox`、`webkit`，默认 `chromium`
- `channel`: Chromium 渠道，例如 `chrome`、`msedge`
- `args`: 浏览器启动参数数组
- `device`: Playwright 设备预设名，例如 `iPhone 12`；预设会填充 viewport、user_agent、device_scale_factor、is_mobile、has_touch
- `proxy`: 代理配置对象
- `storage_state_path`: 从文件加载登录态或上下文状态
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

## 什么时候用

- 你需要启动第一个浏览器窗口
- 你需要多个浏览器并行工作
- 你要给不同站点分配不同的会话

## 注意事项

- `name` 不能重复。
- 如果你后面要写 `browser: "main"`，这里的 `name` 就必须叫 `main`。
- 默认新建一个空白上下文；需要继承状态时使用 `storage_state_path`。
- `device` 不会自动切换 `browser_type`；需要指定浏览器内核时显式填写 `browser_type`。
- 多数真实站点调试时，优先显式设置 `viewport`、`locale`、`timezone_id`、`user_agent` 和必要的 `extra_http_headers`。
