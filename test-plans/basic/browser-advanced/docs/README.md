# browser-advanced

## 目标

覆盖高价值浏览器增强能力：浏览器上下文配置、语义定位、iframe、文件选择器、增强元素操作、JS 执行、localStorage/sessionStorage、网络 mock、响应体捕获、事件采集、增强断言、HAR 和 trace。

## 前置条件

确保已安装 Playwright Chromium：

```powershell
python -m playwright install chromium
```

## 运行方式

```powershell
python .\main.py plan run --file .\test-plans\basic\browser-advanced\plan.json
```

## 预期产物

- `output/json/browser-advanced-summary.json`
- `output/json/browser-events.json`
- `output/har/browser-advanced.har`
- `output/traces/browser-advanced.zip`
