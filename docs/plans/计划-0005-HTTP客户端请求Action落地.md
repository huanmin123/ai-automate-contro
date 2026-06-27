# 计划-0005-HTTP客户端请求Action落地

## 背景

当前 `network` 和 `wait_for_network` 只能处理浏览器上下文中的网络行为。用户需要在 plan 里直接发起 HTTP 请求，覆盖 GET、PUT、表单、本地文件上传、响应保存和断言等接口自动化场景。

该能力应作为执行器级 `http` action 落地，不依赖 Playwright 浏览器。

## 目标

- 新增 `http` action，第一版只提供 `type: request`。
- 支持 `GET`、`POST`、`PUT`、`PATCH`、`DELETE`、`HEAD`、`OPTIONS`。
- 支持 query、headers、JSON body、文本 body、文件 body、urlencoded form、multipart 本地文件上传。
- 支持响应变量保存、响应体写入当前 plan 包 `output/http/`。
- 支持状态码断言、超时、重定向和 TLS 验证开关。
- 使用 Node.js 本地 HTTP 服务构建完整回归测试。

## 范围

- 新增 HTTP action 执行模块。
- 新增 plan 校验规则。
- 新增 handbook 文档。
- 新增 `test-plans/http/client-request/` plan 包。
- 新增 Node.js 测试服务和上传夹具。
- 更新 docs、handbook README 和必要的测试说明。

## 不做

- 不支持系统命令执行。
- 不支持 FTP、SFTP、SMTP、WebSocket、gRPC、裸 TCP。
- 不把浏览器 cookie/storage state 隐式注入 HTTP 客户端。
- 不把响应或下载写到 `resources/`、`docs/`、源码目录或仓库其他位置。

## 关键设计

- Action 名称：`http`。
- 类型：`type: request`。
- 输出分类：`response_body_path` 固定进入 `output/http/`。
- 保存变量：`save_as` 保存 `url`、`final_url`、`method`、`status`、`ok`、`headers`、`body`、`body_path`、`elapsed_ms`。
- 请求 body 字段互斥：`json`、`body`、`body_path`、`form`、`multipart` 同时最多一个。
- 上传路径：`multipart.files[].path` 推荐使用当前 plan 包 `resources/...`；也支持用户要求的本机绝对路径、共享盘或越出 plan 包的相对路径。
- 协议：第一版只接受 `http://` 和 `https://`。
- 日志和产物：按本地调试原文优先处理，不脱敏 Authorization、Cookie、Set-Cookie、X-API-Key 等请求头。

## 实施步骤

1. 更新验证规则：在 `ACTION_TYPES`、`REQUIRED_FIELDS`、输出分类和字段校验中登记 `http.request`。
2. 新增 `src/ai_automate_contro/engine/actions/http_client.py`，实现请求构建、body 编码、multipart、响应解析和输出落盘。
3. 把 `http_client` 加入 action executor 注册。
4. 新增 handbook：说明 schema、字段互斥、上传、响应体落盘和本地调试边界。
5. 新增测试 plan 包：`test-plans/http/client-request/`。
6. 新增 Node.js 测试服务：覆盖方法、query、headers、JSON、文本、form、multipart、下载、重定向、错误状态和 HEAD。
7. 更新 README 索引和功能设计文档。
8. 执行完整验证命令并记录结果。

## 测试矩阵

| 场景 | 覆盖点 | 预期 |
| --- | --- | --- |
| GET query | query 编码、headers | 响应变量包含 query 和 method |
| POST JSON | JSON 序列化、Content-Type | 服务端收到 JSON 对象 |
| PUT text | 文本 body | 服务端返回 body 长度和内容摘要 |
| PATCH form | urlencoded form | 服务端收到字段和值 |
| POST multipart | 本地文件上传、字段混合 | 服务端返回文件名、类型、大小、sha256 |
| GET download | 响应体写入 `output/http/` | 输出文件存在且内容正确 |
| GET redirect | `follow_redirects=true` | `final_url` 为跳转后地址 |
| HEAD | 无 body 响应 | status 和 headers 可保存 |
| DELETE | 无 body 方法 | 服务端收到 DELETE |
| status 409 | `expect_status` | 配置包含 409 时通过，不包含时失败 |
| timeout | 超时错误 | run 失败并写出明确错误 |
| invalid protocol | `file://` 或 `ftp://` | validate 或运行期拒绝 |
| body conflict | 同时写 `json` 和 `form` | validate 失败 |
| local upload path | 上传本机文件 | 支持当前 plan 包 `resources/`、本机绝对路径、共享盘和越出 plan 包的相对路径 |

## 本地 Node 服务

测试服务放在：

```text
test-plans/http/client-request/resources/server.mjs
```

服务启动后输出 JSON，例如：

```json
{"baseUrl":"http://127.0.0.1:43125"}
```

人工回归可分两个终端执行：

```powershell
node .\test-plans\http\client-request\resources\server.mjs
python .\cplan.py run --file .\test-plans\http\client-request\plan.json --run-name http-client
```

如需自动化回归，后续可以在 `self-check runtime` 内用 Python 启动 Node 子进程，读取 `baseUrl` 后通过变量覆盖传给 plan。

## 验收标准

- `python .\cplan.py validate --file .\test-plans\http\client-request\plan.json` 通过。
- `python .\cplan.py run --file .\test-plans\http\client-request\plan.json --run-name http-client` 通过。
- `python .\cplan.py self-check runtime` 通过。
- `python .\cplan.py self-check cli` 通过。
- `python .\main.py self-check ai-tools` 通过，确认 AI 工具写 plan 时仍使用同一 validator。
- 负向校验覆盖 body 字段互斥、非法协议、非法 body_type 和非法输出路径；包外本机上传路径不作为错误处理。
- 所有运行产物只出现在当前 plan 包 `output/` 下。

## 风险

- 标准库实现 multipart 和重定向细节较繁琐，需要用测试服务覆盖真实解析。
- 文件上传默认导入 `resources/`；固定依赖任意本机路径会降低可复现性，必须由用户明确要求并在 plan 包 `docs/` 下记录风险。
- 响应体如果直接塞入变量，可能造成 `state.json` 或后续 AI 上下文过大。
- `verify_tls=false` 需要显式字段和日志提示，便于排查 TLS 相关问题。

## 文档同步

- [HTTP客户端请求Action设计](../functions/HTTP客户端请求Action设计.md)
- `handbook/actions/common/io/http.md`
- `handbook/README.md`
- `docs/functions/核心功能设计.md`
- `docs/develop/测试与验证说明.md`
- `test-plans/http/client-request/docs/README.md`
