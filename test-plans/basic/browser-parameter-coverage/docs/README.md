# browser-parameter-coverage

## 目标

补充验证浏览器增强组件的参数分支：HAR、video、上下文布尔/数组/尺寸参数、`network.set_extra_http_headers`、`network.unroute`、cookies、storage 清理、事件清理、JS 条件等待和元素状态等待。

## 运行方式

```powershell
python .\main.py plan run --file .\test-plans\basic\browser-parameter-coverage\plan.json
```
