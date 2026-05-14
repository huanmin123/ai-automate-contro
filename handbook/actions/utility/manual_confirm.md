# manual_confirm

## 用途

让流程暂停，等待用户在管理终端执行 `continue` 后继续。

这个组件适合“人机协作”的场景，比如自动化浏览器已经打开并停在登录、验证码、滑块验证、二次验证或人工判断页面，需要用户在同一个 Playwright 浏览器窗口里完成操作，然后再让计划继续。

## 必填字段

- `action`: 固定写成 `manual_confirm`

## 可选字段

- `prompt`: 控制台提示语

## 示例

```json
{
  "action": "manual_confirm",
  "prompt": "请在当前自动化浏览器窗口中完成验证码或二次验证，完成后回到终端执行 continue。"
}
```

## 注意事项

- 需要用户操作页面时，前面通常要用 `open_browser` 且设置 `headed: true`，否则用户看不到自动化浏览器。
- 在管理终端中运行 plan 时，遇到该动作会显示 `[WAIT_USER]`。
- 执行 `continue` 后继续当前 run。
- 执行 `stop` 会让等待中的 run 失败并清理浏览器会话。
