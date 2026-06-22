# schedule

## 用途

`schedule` 是 `cplan` 的长期定时计划管理能力，用于按时间启动完整 plan run。它不属于普通 plan action，也不会在 `plan.json.steps` 中出现。

运行期“登录后每隔一段时间触发动作”请使用 `steps` 中的父级 `trigger` action，并把周期执行体写入 `trigger.steps` 或通过 `trigger.path` 引用同包子计划。

## 配置文件

当前运行根下：

```text
schedules.json
.keygen/schedules-state.json
```

- `schedules.json`: 用户可读、可编辑的定时计划配置。
- `.keygen/schedules-state.json`: 最近运行状态、错误和输出目录。

删除最后一个 schedule 时，空的 `schedules.json` 和空的 `.keygen/schedules-state.json` 会自动移除，避免项目根目录残留无意义配置。

## 常用命令

```powershell
python .\cplan.py schedule list
python .\cplan.py schedule add --id daily-demo --file .\plans\demo\plan.json --daily-at 09:05
python .\cplan.py schedule add --id poll-demo --file .\plans\demo\plan.json --every-seconds 300 --run-immediately
python .\cplan.py schedule enable daily-demo
python .\cplan.py schedule disable daily-demo
python .\cplan.py schedule run-now daily-demo
python .\cplan.py schedule daemon
python .\cplan.py schedule daemon --once
python .\cplan.py schedule remove daily-demo
```

## trigger 类型

### daily

```json
{
  "type": "daily",
  "at": "09:05"
}
```

### interval

```json
{
  "type": "interval",
  "every_seconds": 300,
  "run_immediately": true
}
```

## 边界

- `daemon` 是常驻进程；`--once` 只扫描一次后退出，适合测试或系统任务计划程序。
- 初版只支持单进程顺序运行，`concurrency` 固定为 `skip`。
- Windows 上 `Asia/Shanghai` 有内置 UTC+8 兜底，不依赖系统 tzdata。
