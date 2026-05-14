# browser-observability

## 目标

覆盖最后一批浏览器补齐能力：按 frame name、URL 和 index 定位，提取 frame 列表，采集 WebRTC 和 Service Worker 事件。

## 前置条件

确保已安装 Playwright Chromium：

```powershell
python -m playwright install chromium
```

## 运行方式

```powershell
python .\main.py plan run --file .\test-plans\basic\browser-observability\plan.json
```

## 预期产物

- `output/json/browser-observability-events.json`
- `output/json/browser-observability-summary.json`
