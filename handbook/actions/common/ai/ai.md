# ai

`ai` 是受控专项 AI 组件，用于在 plan 执行中处理明确的数据任务。

它不是 AI 终端，也不是开放聊天节点。`ai` 组件不能创建、运行、调试或修复 plan；这些属于 plan 级 AI 终端能力，不能写进普通 plan `steps`。

## 支持类型

| type | 用途 |
| --- | --- |
| `connectivity` | 检查模型服务是否可用 |
| `extract_data` | 从文本中抽取结构化数据 |
| `classify_text` | 在固定标签中分类 |
| `transform_data` | 按指令转换数据 |
| `summarize_text` | 生成摘要 |

## 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `action` | 是 | 固定为 `ai` |
| `type` | 是 | AI 任务类型 |
| `service` | 否 | `config.ai_services` 中的服务名，默认 `default` |
| `input` | 是 | 输入数据，可以使用变量 |
| `instruction` | 否 | 当前任务的补充指令 |
| `schema` | 部分类型必填 | 输出 JSON Schema；`extract_data` 必填 |
| `labels` | 分类必填 | `classify_text` 的候选标签；如果已提供 `schema` 可省略 |
| `output` | 是 | 发布解析结果的声明；`output.as` 是变量名 |
| `path` | 否 | 输出产物路径，相对于 `output/ai/` |

## 配置

AI 服务注册在集合级或局部 `config.json`：

```json
{
  "ai_services": {
    "default": {
      "protocol": "openai_chat_completions",
      "base_url": "https://example.com/v1",
      "model": "model-name",
      "api_key_env": "AI_TEST_API_KEY",
      "timeout_seconds": 90,
      "max_output_tokens": 2048,
      "response_format": "json_schema"
    }
  }
}
```

`protocol` 省略时默认为 `openai_chat_completions`。可选协议为 `openai_chat_completions`（OpenAI Chat Completions）、`openai_responses`（OpenAI Responses API）、`anthropic_messages`（Anthropic Messages API）和 `google_generate_content`（Google Gemini GenerateContent API）。`service` 固定选择其中一个服务，不会在失败时改用另一个协议。

服务配置属于跨 action 的运行配置，而不是本 action 的字段。`model`、密钥、URL、超时、重试、流式、采样、输出上限、停止序列、思考级别和结构化输出的完整用途、默认值、字段映射、模型限制及不可用组合，请以 [配置参考的 ai_services](../../../reference/config.md#ai_services) 为准。尤其注意：

- `stream` 只控制专项 `ai` action；AI 终端始终流式渲染。
- `response_format` 仅控制专项 action 的上游格式约束；本 action 最终仍必须解析为 JSON 并通过 `schema` 校验。
- `openai_responses` 不能设置 `stop`；`anthropic_messages` 不能设置 `temperature` 或 `top_p`，都会在请求前失败。
- `reasoning_effort` 是有限统一抽象，模型不支持某一档位时会保留上游错误，不做自动降级。

配置可以直接写真实密钥，也可以通过 `api_key_env` 引用环境变量。plan 会按配置调用模型服务。

## 输出

所有 `ai` 输出产物必须写入当前 plan 包：

```text
output/ai/
  connectivity/
  extract-data/
  classify-text/
  transform-data/
  summarize-text/
```

`path` 是相对于 `output/ai/` 的路径，不能以 `output/`、`resources/`、`docs/` 或 `sub-plans/` 开头。

## 示例

```json
{
  "action": "ai",
  "type": "extract_data",
  "service": "default",
  "instruction": "从客服工单中抽取联系人姓名、邮箱和问题。",
  "input": "{{ticket_text}}",
  "schema": {
    "contact_name": "string",
    "email": "string",
    "issue": "string"
  },
  "output": {
    "as": "ticket_fields",
    "type": "object!"
  },
  "path": "extract-data/ticket-fields.json"
}
```

执行后：

- 解析后的 JSON 发布到变量 `ticket_fields`。
- 输出产物保存到 `output/ai/extract-data/ticket-fields.json`。
