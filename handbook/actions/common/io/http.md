# http

## 用途

在计划执行器内直接发起 HTTP(S) 请求，适合接口自动化、文件上传、表单提交和响应落盘。

## 必填字段

- `action`: 固定写成 `http`
- `type`: 固定写成 `request`
- `method`: HTTP 方法
- `url`: 请求 URL

## 支持方法

- `GET`
- `POST`
- `PUT`
- `PATCH`
- `DELETE`
- `HEAD`
- `OPTIONS`

## 参数表

### 请求

- `headers`: 对象，默认空；键值都会转成字符串。`auth` 和 body 自动添加的 `Content-Type`、`Authorization` 不会覆盖显式写入的 `headers` 同名项。
- `query`: 对象；按表单编码追加到 URL，与 URL 里已有的 query 合并，数组值展开为重复参数。
- `json`: 任意 JSON 值；自动设置 `Content-Type: application/json`，按 UTF-8 编码发送。
- `body`: 字符串；用 `encoding` 编码，配合 `content_type` 设置请求头。
- `body_path`: 本地文件路径，默认相对当前 plan 包根；按原始字节发送，配合 `content_type` 设置请求头；文件不存在时报错。
- `form`: 对象；按 `application/x-www-form-urlencoded` 编码。
- `multipart`: `multipart/form-data` 对象；`fields` 是字符串字段对象，`files` 是 `{field, path, filename?, content_type?}` 数组；`filename` 默认取文件名，`content_type` 默认按扩展名推断，推断不出用 `application/octet-stream`。
- `content_type`: 字符串；仅在 `body` 或 `body_path` 时设置 `Content-Type`；`json`/`form`/`multipart` 自动设置，不需要写。
- `encoding`: 字符串，默认 `utf-8`；仅用于把 `body` 字符串编码成请求字节，不影响响应解码；响应文本按响应头 charset 解码，缺失时按 UTF-8。
- `auth`: 认证对象；`{"type": "basic", "username": "...", "password": "..."}` 生成 Basic Authorization，`{"type": "bearer", "token": "..."}` 生成 Bearer Authorization；`type` 不支持时报错；`headers` 里已有 `Authorization` 时不覆盖。
- `allow_body`: 布尔，默认 `false`；`GET`/`HEAD` 携带 `json`、`body`、`body_path`、`form`、`multipart` 之一时，必须显式写 `allow_body: true` 才放行，否则步骤报错。

### 行为

- `timeout_ms`: 正整数，默认 `30000`；请求超时毫秒数。
- `follow_redirects`: 布尔，默认 `true`；是否自动跟随重定向；关闭时 3xx 响应直接作为本次结果返回，不再跟随。
- `max_redirects`: 非负整数，默认 `10`；跟随重定向上限，超过时步骤报错。
- `verify_tls`: 布尔，默认 `true`；是否校验 HTTPS 证书；`false` 时跳过证书校验，仅用于明确接受风险的内网或自建证书场景。
- `expect_status`: 单个整数或整数数组；响应状态码不在期望集合内时步骤失败，例如 `200`、`[200, 204]`、`[200, 201, 202]`。

### 响应

- `include_headers`: 布尔，默认 `true`；响应头是否进入输出变量（小写键名）。
- `include_body`: 布尔；未提供 `response_body_path` 时默认 `true`，提供了 `response_body_path` 时默认 `false`。显式写 `true` 可以在落盘的同时把 body 也放进变量；显式写 `false` 可以只留 `body_path` 不进变量。
- `body_type`: `text`、`json`、`bytes`；默认按响应 `Content-Type` 推断，包含 `json` 时按 `json` 解析，否则按 `text`。`json` 解析空响应体得到 `null`；`bytes` 输出字节值数组。
- `max_body_bytes`: 正整数，默认 `262144`（256 KB），上限 `1048576`（1 MB）；超过上限的配置值会被压到上限。body 进入变量时超过限制即报错，此时应改用 `response_body_path` 落盘；落盘本身不受该限制。
- `response_body_path`: 响应体按原始字节写入当前 plan 包 `output/http/`；适合大响应、二进制和文件下载。落盘成功后输出里的 `body_path` 是产物路径；`include_body` 默认变 `false`，body 不再进入变量。
- `output`: 发布给后续步骤的 JSON-safe 输出；`output.as` 是变量名。输出包含 `url`、`final_url`、`method`、`status`、`ok`、`headers`、`body_path`、`elapsed_ms`，以及按 `include_body` 决定的 `body`。

## 约束

- `json`、`body`、`body_path`、`form`、`multipart` 只能选一种。
- 要把响应体字段传给后续节点时，必须使用 `body_type: "json"`，再用 `output.from` 从响应 payload 中选择结构化片段。
- `GET` 和 `HEAD` 默认不允许 body；确需发送时显式写 `allow_body: true`。
- `expect_status` 校验失败时步骤立即失败，并给出期望值和实际状态码。
- body 进入变量时受 `max_body_bytes` 限制，默认 256 KB、上限 1 MB；更大响应必须用 `response_body_path` 落盘。
- 请求 body 文件和上传文件默认放当前 plan 包 `resources/`，例如 `resources/payload.json`、`resources/upload.txt`。
- AI 创建 plan 时，用户没有指定固定本机上传路径时，推荐把文件导入当前包 `resources/`，再写 `resources/...`。
- `body_path` 或 `multipart.files[].path` 支持绝对路径、共享盘、外部工作目录和越出 plan 包的相对路径；不需要审批字段。
- plan JSON 内部路径统一使用 `/`，不要使用 Windows 反斜杠。
- 只支持 `http://` 和 `https://`。
- HTTP 变量、响应落盘和产物按原始响应和配置写入，不自动改写请求头、响应体、表单字段、认证信息和文件路径。
- 大响应使用 `response_body_path`，不要直接放入变量。

## 示例

```json
{
  "action": "http",
  "type": "request",
  "method": "GET",
  "url": "http://127.0.0.1:3000/echo",
  "output": {
    "as": "echo_response"
  }
}
```

用 `output` 发布下游真正需要的字段：

```json
{
  "action": "http",
  "type": "request",
  "method": "POST",
  "url": "http://127.0.0.1:3000/login",
  "json": {
    "username": "{{username}}",
    "password": "{{password}}"
  },
  "body_type": "json",
  "output": {
    "as": "login",
    "from": "body.data",
    "type": "object!",
    "fields": {
      "token": "string!",
      "user_id": "string!"
    }
  }
}
```

```json
{
  "action": "http",
  "type": "request",
  "method": "POST",
  "url": "http://127.0.0.1:3000/upload",
  "multipart": {
    "fields": {
      "name": "demo"
    },
    "files": [
      {
        "field": "file",
        "path": "resources/upload.txt"
      }
    ]
  },
  "output": {
    "as": "upload_response"
  }
}
```

带认证、状态码断言和响应落盘：

```json
{
  "action": "http",
  "type": "request",
  "method": "GET",
  "url": "https://api.example.com/reports/2026-09",
  "auth": {
    "type": "bearer",
    "token": "{{api_token}}"
  },
  "timeout_ms": 60000,
  "max_redirects": 5,
  "expect_status": [200, 204],
  "response_body_path": "reports/2026-09.xlsx",
  "output": {
    "as": "report_download"
  }
}
```

提供了 `response_body_path` 时响应体写入 `output/http/reports/2026-09.xlsx`，输出变量里 `body_path` 指向该产物，`body` 默认不再进入变量；需要同时保留时显式加 `"include_body": true`（仍受 `max_body_bytes` 限制）。
