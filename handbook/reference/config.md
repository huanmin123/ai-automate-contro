# config.json

## 用途

`config.json` 只保存 plan 运行配置，不保存业务变量。业务变量请写在 `plan.json` 的 `variables` 字段。

## 位置

- `<plan-root>/config.json`: 当前 plan 集合级配置，`plan-root` 来自运行根的 `plan.config.plan_roots`。
- `plan-package/config.json`: 当前 plan 包局部配置。

局部配置会覆盖集合级配置。嵌套对象递归合并；数组、字符串、数字、布尔值和 `null` 由局部值整体覆盖。

## post_run_inspection

控制 plan 正常执行完步骤后是否保留浏览器给用户检查。

```json
{
  "post_run_inspection": {
    "enabled": true,
    "prompt": "检查完毕后输入 y 继续/确认，输入 n 停止/拒绝: "
  }
}
```

字段：

- `enabled`: 布尔值。为 `true` 时，正常执行完毕且仍有浏览器会话打开，会先等待用户确认，再关闭浏览器并写出最终结果。
- `prompt`: 字符串。可选，等待用户确认时显示的提示文案；`cplan run` 仍只接受 `y` 或 `n`。

失败运行不会触发检查等待，会直接清理浏览器资源。

## ai_services

专项 AI 组件和 AI 终端使用的模型服务配置。

```json
{
  "ai_services": {
    "default": {
      "provider": "openai-compatible",
      "api": "chat_completions",
      "base_url": "https://your-openai-compatible-endpoint/v1",
      "model": "your-model",
      "api_key_env": "OPENAI_API_KEY",
      "stream": true,
      "timeout_seconds": 90,
      "strict_schema": true,
      "response_format": "json_schema"
    }
  }
}
```

配置可以直接写 `api_key` 或通过 `api_key_env` 读取环境变量。项目按本地调试原文优先处理，不因真实密钥字段自动脱敏、拒写或强制改成环境变量。
