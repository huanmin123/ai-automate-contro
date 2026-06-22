# HTTP客户端请求Action设计

## 背景

当前浏览器网络能力只覆盖页面触发的请求观测、拦截、mock 和 HAR 回放。它适合验证“点击按钮后页面是否调用接口”，但不适合作为 plan 内的通用 HTTP 客户端。

新增 HTTP 客户端能力后，plan 可以在不打开浏览器的情况下调用接口、上传本地文件、提交表单、读取响应并把结果保存到变量或 `output/`，再与后续浏览器步骤、断言、AI 数据处理和文件写出组合。

## 定位

新增独立 `http` action。

不把它并入 `network`，原因是：

- `network` 是 Playwright 浏览器上下文级能力，依赖浏览器会话。
- `http` 是执行器级 I/O 能力，不依赖页面、上下文或 selector。
- 请求方法、body 类型、文件上传、响应落盘、重试和超时属于 HTTP 客户端生命周期。

## 目标

- 支持常见 HTTP 方法：`GET`、`POST`、`PUT`、`PATCH`、`DELETE`、`HEAD`、`OPTIONS`。
- 支持 request body：JSON、文本、二进制文件、`application/x-www-form-urlencoded`、`multipart/form-data`。
- 支持本地文件上传；默认把上传文件放入当前 plan 包 `resources/`，plan 中使用 `resources/...`。
- 支持 headers、query、basic auth、bearer token 变量注入、超时、重定向、TLS 验证开关。
- 支持把响应摘要保存为变量，把响应体保存到 `output/http/`。
- 支持断言状态码、响应头和响应 JSON 字段的基础门禁。
- 支持完整本地回归，测试用 Node.js 自建 HTTP 服务覆盖方法、表单、上传和错误场景。

## 非目标

- 不支持直接执行本地命令，不复用远期 `command` action。
- 不支持 FTP、SFTP、SMTP、WebSocket、gRPC 或裸 TCP。这些不是 HTTP 客户端能力。
- 不支持把响应体写到源码、`resources/`、`docs/` 或仓库其他目录。
- 不做浏览器 cookie jar 自动共享；如需登录态，先通过 `capture.type=storage_state` 或后续专门设计显式导入。
- 不做自动降级、自动改协议或服务兼容兜底。

## Action Schema

最小 GET：

```json
{
  "action": "http",
  "type": "request",
  "method": "GET",
  "url": "http://127.0.0.1:3000/api/profile",
  "save_as": "profile_response"
}
```

JSON POST：

```json
{
  "action": "http",
  "type": "request",
  "method": "POST",
  "url": "{{api_base_url}}/accounts",
  "headers": {
    "Authorization": "Bearer {{api_token}}"
  },
  "json": {
    "name": "{{account_name}}"
  },
  "save_as": "create_account_response"
}
```

URL encoded form：

```json
{
  "action": "http",
  "type": "request",
  "method": "POST",
  "url": "{{api_base_url}}/login",
  "form": {
    "username": "{{login_username}}",
    "password": "{{login_password}}"
  },
  "save_as": "login_response"
}
```

Multipart 文件上传：

```json
{
  "action": "http",
  "type": "request",
  "method": "PUT",
  "url": "{{api_base_url}}/files/avatar",
  "multipart": {
    "fields": {
      "owner": "{{account_name}}"
    },
    "files": [
      {
        "field": "file",
        "path": "resources/avatar.png",
        "filename": "avatar.png",
        "content_type": "image/png"
      }
    ]
  },
  "save_as": "upload_response"
}
```

响应体落盘：

```json
{
  "action": "http",
  "type": "request",
  "method": "GET",
  "url": "{{api_base_url}}/report.csv",
  "response_body_path": "reports/latest.csv",
  "save_as": "download_response"
}
```

## 字段

必填字段：

- `action`: 固定为 `http`
- `type`: 固定为 `request`
- `method`: HTTP 方法
- `url`: `http://` 或 `https://` URL

常用可选字段：

- `headers`: 请求头对象，值支持变量渲染。
- `query`: query 参数对象，值支持字符串、数字、布尔、数组。
- `json`: JSON body。
- `body`: 文本 body。
- `body_path`: 二进制或文本 body 文件路径，默认使用当前 plan 包 `resources/...`。
- `form`: `application/x-www-form-urlencoded` 表单对象。
- `multipart`: multipart 表单对象，包含 `fields` 和 `files`。
- `auth`: 认证对象，第一版支持 `basic` 和 `bearer`。
- `timeout_ms`: 单请求超时，默认 `30000`。
- `follow_redirects`: 是否跟随重定向，默认 `true`。
- `max_redirects`: 最大重定向次数，默认 `10`。
- `verify_tls`: 是否校验证书，默认 `true`。
- `expect_status`: 期望状态码，支持单个数字或数字数组。
- `include_headers`: 是否把响应头保存到变量，默认 `true`。
- `include_body`: 是否把响应体保存到变量，默认 `true`，大响应应改用 `response_body_path`。
- `body_type`: 响应体解析方式，`text`、`json`、`bytes`，默认按 Content-Type 推断，推断失败为 `text`。
- `response_body_path`: 响应体写入路径，相对于当前 plan 包 `output/http/`。
- `save_as`: 响应摘要保存变量名。

body 互斥规则：

- `json`、`body`、`body_path`、`form`、`multipart` 同一请求只能使用一个。
- `GET`、`HEAD` 默认不允许 body；如确有需要，必须显式 `allow_body: true`。

## 响应变量结构

保存到 `save_as` 的变量固定为对象：

```json
{
  "url": "http://127.0.0.1:3000/api/profile",
  "final_url": "http://127.0.0.1:3000/api/profile",
  "method": "GET",
  "status": 200,
  "ok": true,
  "headers": {
    "content-type": "application/json"
  },
  "body": {
    "name": "Demo"
  },
  "body_path": "",
  "elapsed_ms": 12
}
```

规则：

- headers 统一保存为小写 key。
- `body_type=json` 成功时 `body` 是 JSON 值。
- `body_type=text` 成功时 `body` 是字符串。
- `body_type=bytes` 时 `body` 是整数数组；仅用于小型二进制回归。
- 指定 `response_body_path` 后，变量里写 `body_path`，默认不再把完整响应体放入 `body`。
- 响应体变量大小需要限幅，超过限制时报错并提示使用 `response_body_path`。

## 路径与输出

- `body_path` 和 multipart 文件路径默认使用当前 plan 包 `resources/...`，读取已生成产物时才使用 `output/...`。
- AI 创建 plan 时，用户给出本机 body 或上传文件但没有明确要求长期依赖该路径，必须先导入当前 plan 包 `resources/`。
- `body_path` 和 `multipart.files[].path` 支持绝对路径、共享盘、外部工作目录和越出 plan 包的相对路径；不需要任何额外审批字段。
- plan JSON 内部路径统一使用 `/`，不要使用 Windows 反斜杠。
- `response_body_path` 只能写入当前 plan 包 `output/http/` 下的相对路径，不能以 `output/` 开头。
- HTTP 变量、响应落盘和调试产物保留请求头、响应体、表单字段、认证信息和文件路径原文，不自动脱敏。

## 协议和本地调试边界

- 第一版只允许 `http` 和 `https` URL。
- 禁止 `file://`、`data:`、`ftp:`、`sftp:`、`ws:`、`wss:`、裸 TCP 等协议。
- `verify_tls=false` 必须显式配置，并在日志里记录该事实。
- 不提供自动读取浏览器 storage state 转 cookie 的隐式行为；如果需要登录态，应由 plan 显式传入 Cookie 或 Authorization 等请求头。

## 实现建议

优先使用 Python 标准库实现第一版，避免新增长期依赖：

- `urllib.request` 负责基础请求、headers、超时和 TLS。
- `urllib.parse.urlencode` 负责 query 和 urlencoded form。
- `email.mime` 或手写边界生成负责 multipart。
- `ssl` 负责 TLS 验证开关。

如果标准库实现导致 multipart、重定向或错误处理复杂度过高，再评估引入 `httpx`，但需要把依赖、打包和离线运行影响写入计划。

## 校验规则

validator 需要覆盖：

- `http.type` 只允许 `request`。
- `method` 必须是允许的方法。
- `url` 必须是 `http://` 或 `https://`，模板值可以延迟运行期检查。
- body 字段互斥。
- `multipart.files` 每项必须有 `field` 和 `path`。
- `timeout_ms`、`max_redirects` 必须是非负整数。
- `follow_redirects`、`verify_tls`、`include_headers`、`include_body` 必须是布尔。
- `body_type` 只允许 `text`、`json`、`bytes`。
- `response_body_path` 走 output 路径规则，不能写到源码目录。

## 测试策略

新增 `test-plans/http/client-request/`，配套 `resources/server.mjs` 和上传夹具文件。回归测试启动 Node.js 本地 HTTP 服务，plan 通过变量拿到 `http://127.0.0.1:<port>`。

服务端需要覆盖：

- `GET /echo`：返回 method、query、headers。
- `POST /json`：校验 JSON body。
- `PUT /text`：返回文本 body 长度。
- `PATCH /form`：校验 urlencoded form。
- `POST /upload`：解析 multipart，返回字段、文件名、content type、大小和 sha256。
- `GET /download`：返回 CSV 或二进制内容。
- `GET /redirect`：跳转到 `/echo`。
- `GET /status/:code`：返回指定状态码。
- `HEAD /head`：返回 headers，无 body。

验证命令：

```powershell
node .\test-plans\http\client-request\resources\server.mjs
python .\cplan.py validate --file .\test-plans\http\client-request\plan.json
python .\cplan.py run --file .\test-plans\http\client-request\plan.json --run-name http-client
python .\cplan.py self-check runtime
```

如果最终把服务启动自动化放入 Python self-check，仍要保留 Node.js 服务作为清晰的独立夹具，方便人工复现。

## 文档同步

后续维护 HTTP action 时，需要同步检查：

- `src/ai_automate_contro/engine/actions/http_client.py` 和 action 注册出口。
- `src/ai_automate_contro/plans/validation_rules.py` 和 `validation_fields.py`。
- `handbook/actions/io/http.md`。
- `handbook/README.md` action 索引。
- `test-plans/http/client-request/` 示例和 README。
- `docs/functions/核心功能设计.md` 当前能力列表。
- `docs/develop/测试与验证说明.md` 测试说明。
