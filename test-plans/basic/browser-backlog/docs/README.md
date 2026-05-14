# browser-backlog

## 目标

覆盖本轮后续补齐的浏览器能力：HAR 回放、coverage 采集、WebSocket mock 和帧观测、SSE 事件观测、移动设备预设、元素 tap、触控 swipe、ARIA snapshot。

## 前置条件

确保已安装 Playwright Chromium：

```powershell
python -m playwright install chromium
```

## 运行方式

```powershell
python .\main.py plan run --file .\test-plans\basic\browser-backlog\plan.json
```

## 预期产物

- `output/json/browser-backlog-coverage.json`
- `output/json/browser-backlog-events.json`
- `output/json/browser-backlog-summary.json`
