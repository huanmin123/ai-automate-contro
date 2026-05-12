# config.json

## 用途

`config.json` 只保存 plan 运行配置，不保存业务变量。业务变量请写在 `plan.json` 的 `variables` 字段。

## 位置

- `plans/config.json`: 公开示例 plan 集合级配置。
- `test-plans/config.json`: 测试 plan 集合级配置。
- `plan-package/config.json`: 当前 plan 包局部配置。

局部配置会覆盖集合级配置。嵌套对象递归合并；数组、字符串、数字、布尔值和 `null` 由局部值整体覆盖。

## post_run_inspection

控制 plan 正常执行完步骤后是否保留浏览器给用户检查。

```json
{
  "post_run_inspection": {
    "enabled": true,
    "prompt": "检查完毕后按回车关闭浏览器并结束: "
  }
}
```

字段：

- `enabled`: 布尔值。为 `true` 时，正常执行完毕且仍有浏览器会话打开，会先等待用户确认，再关闭浏览器并写出最终结果。
- `prompt`: 字符串。可选，等待用户确认时显示的提示文案。

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
      "api_key": "sk-your-key",
      "stream": true,
      "timeout_seconds": 90,
      "strict_schema": true,
      "response_format": "json_schema"
    }
  }
}
```

公开示例配置不要保存真实密钥。项目测试集合中的临时真实服务由用户主动提供时，可以保留在本机测试配置中。
