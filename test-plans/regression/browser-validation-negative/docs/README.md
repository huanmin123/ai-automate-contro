# browser-validation-negative

## 目标

保存浏览器组件参数校验的负向用例。这里的用例不直接作为 plan 运行，而是由浏览器组件自检命令读取，确认错误参数会被 validator 拒绝。

## 运行方式

```powershell
python .\main.py self-check browser-components
```

## 覆盖范围

- frame 定位字段互斥
- coverage 采集目标不能为空
- WebSocket mock 参数类型和关闭码
- event 观测布尔字段
- swipe 数值边界
- ARIA snapshot mode 枚举
- 设备预设字段类型
- HAR 回放 scope 枚举
