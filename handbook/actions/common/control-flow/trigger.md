# trigger

## 用途

`trigger` 是父级控制流 action，用于在同一个 plan run 内，按固定间隔周期执行一组子步骤或同包子计划。

它必须直接写在 `steps` 数组中。执行器运行到这个节点时进入触发器循环，满足 `max_runs`、`duration_seconds`、`stop_condition` 或错误处理规则后退出，然后父 plan 继续执行后续步骤。

不要再使用顶层 `routines` 或 `triggers`。plan 中的可执行行为都应该从 `steps` 进入；周期执行体写在 `trigger.steps`，或者通过 `trigger.path` 引用 `sub-plans/*-plan.json`。

## 内联步骤示例

```json
{
  "action": "trigger",
  "type": "interval",
  "name": "poller",
  "every_seconds": 1,
  "run_immediately": true,
  "max_runs": 3,
  "steps": [
    {
      "action": "print",
      "message": "poll {{trigger_run_index}}"
    }
  ],
  "output": {"as": "poller_status"}
}
```

## 子计划示例

```json
{
  "action": "trigger",
  "type": "interval",
  "name": "check_status",
  "every_seconds": 300,
  "run_immediately": true,
  "max_runs": 12,
  "path": "sub-plans/check-status-plan.json",
  "output": {"as": "check_status_result"}
}
```

## 必填字段

- `action`: 固定写成 `trigger`
- `type`: 固定写成 `interval`
- `every_seconds`: 间隔秒数，必须大于 0
- `steps` 或 `path`: 二选一，作为周期执行体

## 可选字段

- `name`: 触发器名称，用于日志和状态；不填时使用当前 step 的 `name` 或 `trigger`。
- `run_immediately`: 是否在进入 trigger 后立刻执行第一次，默认 `false`。
- `max_runs`: 最大执行次数。
- `duration_seconds`: 最大运行秒数。
- `allow_infinite`: 显式允许无限运行，默认 `false`。
- `stop_condition`: 条件对象，满足后结束。
- `overlap`: 执行体耗时超过间隔时的处理，支持 `skip`、`queue`、`fail`，默认 `skip`。三种取值的精确语义见下文"overlap 语义"。
- `on_error`: 执行体失败时的处理，支持 `fail_plan`、`stop_trigger`，默认 `fail_plan`。
- `output.as`: trigger 结束后把状态对象保存到变量。

没有 `max_runs` 或 `duration_seconds` 时，必须显式设置 `allow_infinite: true`，否则校验失败。无限 trigger 会阻塞父 plan 后续步骤，通常只适合由 `stop_condition` 或外部中断结束的场景。

## overlap 语义

`overlap` 只在执行体结束时间晚于下一个计划触发点时生效。执行体不超时时，三种取值行为一致，都按 `every_seconds` 固定节奏触发。

以 `every_seconds=10`、第 0 秒触发、执行体运行 12 秒（第 12 秒结束，原计划第 10 秒应触发下一次）为例：

- `skip`（默认）: 错过的计划触发点直接跳过，下一次触发时间改为"执行体结束时间 + every_seconds"，即第 22 秒。适合允许节奏漂移、不需要补跑的任务。
- `queue`: 保留原计划时间表，下一次触发时间仍是原计划的第 10 秒；由于当前已是第 12 秒，执行体结束后回到触发器循环会立即再次执行一次执行体（相当于补跑被推迟的那次）。如果每次执行体都超时，会连续追赶执行，不额外排队上限。适合需要按计划补齐次数的任务。
- `fail`: 执行体一结束就抛出 `RuntimeError`（`trigger body 执行时间超过间隔`），trigger 失败，plan 失败。适合把"执行体必须短于间隔"作为硬约束的任务。

时间线对比：

```text
every_seconds=10，执行体运行 12s：

计划点:   0s ---- 10s ---- 20s ---- 30s
实际运行: [==== 12s ====]
skip:     第 0s 执行(0-12s)      下一次 22s
queue:    第 0s 执行(0-12s) 立即补跑下一次(12s 起)
fail:     第 0s 执行(0-12s) 12s 时抛 RuntimeError
```

## 运行变量

每次执行体运行前会写入：

- `trigger_name`
- `trigger_run_index`
- `trigger_started_at`
- `trigger_last_run_at`
- `trigger_next_run_at`

这些变量属于当前 run，后续 trigger 执行可能覆盖同名值。`trigger.steps` 和 `trigger.path` 指向的子计划都可以使用这些变量。

## 状态对象

`output.as` 保存的状态对象包含：

- `name`
- `status`: `completed` 或 `failed`
- `started_at`
- `run_count`
- `next_run_at`
- `last_run_at`
- `last_finished_at`
- `finished_at`
- `finish_reason`
- `last_error`
- `last_error_type`

## 边界

- `trigger` 是阻塞式父 action，不创建后台线程。
- 执行体单线程运行，避免共享当前执行线 runtime 状态时出现并发污染。
- `trigger.steps` 和 `trigger.path` 只能提供一种。
- `trigger.path` 必须引用当前 plan 包内的 `sub-plans/*-plan.json`，不能引用另一个主 `plan.json`。
