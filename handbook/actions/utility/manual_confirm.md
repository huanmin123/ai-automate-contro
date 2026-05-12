# manual_confirm

## 用途

让流程暂停，等待用户在管理终端执行 `continue` 后继续。

这个组件适合“人机协作”的场景，比如你要先手动登录、手动滑块验证、手动切换页面，然后再让计划继续。

## 必填字段

- `action`: 固定写成 `manual_confirm`

## 可选字段

- `prompt`: 控制台提示语

## 示例

```json
{
  "action": "manual_confirm",
  "prompt": "请先手动完成前置操作，完成后回到管理终端执行 continue。"
}
```

## 注意事项

- 在管理终端中运行 plan 时，遇到该动作会显示 `[WAIT_USER]`。
- 执行 `continue` 后继续当前 run。
- 执行 `stop` 会让等待中的 run 失败并清理浏览器会话。
