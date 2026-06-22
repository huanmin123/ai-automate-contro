# http-client-request

## 目标

验证 `http` action 和 `command` action 可以在同一个 plan 中连续组合：

- HTTP GET 结果进入后续 JSON 请求。
- 文本、form 和 multipart 上传共享前序变量。
- HTTP 下载响应体落到 `output/http/`。
- `command` action 读取 HTTP 下载文件和变量，输出 JSON。
- command 的 JSON stdout 继续进入后续 HTTP 请求。
- HEAD、DELETE、redirect 和非 2xx 期望状态也在同一条链路中验证。

## 准备本地服务

另开一个 PowerShell 7 终端：

```powershell
node .\test-plans\http\client-request\resources\server.mjs
```

服务固定监听：

```text
http://127.0.0.1:43125
```

## 运行

```powershell
python .\cplan.py validate --file .\test-plans\http\client-request\plan.json
python .\cplan.py run --file .\test-plans\http\client-request\plan.json --run-name http-client
```

## 输出

- `output/http/downloads/http-report.csv`
- `output/commands/combo-process-stdout.json`
- `output/commands/combo-process-stderr.txt`
- `output/variables/http-command-combo-variables.json`
