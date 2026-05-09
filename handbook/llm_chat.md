# llm_chat

## 用途

调用已配置的大模型服务，执行一次标准聊天补全。

这是 AI 编排层的基础模型节点，适合做：

- 数据清洗
- 文本分类
- OCR 结果二次结构化
- 页面下一步动作建议

## 必填字段

- `action`: 固定写成 `llm_chat`
- `service`: 模型服务别名
- `messages`: 标准消息数组
- `save_as`: 保存完整响应的变量名

## 可选字段

- `model`: 覆盖服务默认模型
- `temperature`: 默认 `0`
- `save_text_as`: 单独保存首个回答文本

## 示例

```json
{
  "action": "llm_chat",
  "service": "local_gateway",
  "messages": [
    {
      "role": "system",
      "content": "你是一个结构化提取助手。"
    },
    {
      "role": "user",
      "content": "把这段文本压缩成一句话：{{ocr_text}}"
    }
  ],
  "save_as": "llm_result",
  "save_text_as": "llm_text"
}
```
