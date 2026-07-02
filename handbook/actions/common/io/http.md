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

## 常用字段

- `headers`: 请求头
- `query`: query 参数
- `json`: JSON body
- `body`: 文本 body
- `body_path`: 本地 body 文件，默认使用当前 plan 包 `resources/...`
- `form`: `application/x-www-form-urlencoded`
- `multipart`: `multipart/form-data`，支持本地文件上传
- `auth`: `basic` 或 `bearer`
- `timeout_ms`: 超时毫秒
- `follow_redirects`: 是否跟随重定向
- `max_redirects`: 最大重定向次数
- `verify_tls`: 是否校验证书
- `expect_status`: 期望状态码
- `include_headers`: 是否保存响应头
- `include_body`: 是否保存响应体
- `body_type`: `text`、`json`、`bytes`
- `response_body_path`: 把响应体写到当前 plan 包 `output/http/`
- `output`: 发布给后续步骤的 JSON-safe 输出；`output.as` 是变量名

## 约束

- `json`、`body`、`body_path`、`form`、`multipart` 只能选一种。
- 要把响应体字段传给后续节点时，必须使用 `body_type: "json"`，再用 `output.from` 从响应 payload 中选择结构化片段。
- `GET` 和 `HEAD` 默认不允许 body，除非显式开放。
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
