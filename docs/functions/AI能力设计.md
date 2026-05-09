# AI 能力设计

## 当前第一版能力

- OCR 服务调用
- OpenAI 兼容 LLM 调用
- LLM 结构化 JSON 提取
- 结果写回变量
- 配置化模型别名

## 当前动作

- `ocr_image`
- `llm_chat`
- `llm_extract_json`

## 当前推荐编排链路

### 页面图片识别链路

- `extract_attribute`
- `ocr_image`
- `fill`
- `assert_value`

### 文本结构化链路

- `extract_text` 或 `ocr_image`
- `llm_extract_json`
- `if` / `fill` / `write_json`

## 配置入口

推荐在项目根目录维护：

- `config/ai-services.example.json`
- `config/ai-services.local.json`

其中：

- `example` 用来示范结构
- `local` 用来放你自己机器或内网服务的真实配置

## 配置设计

### OCR

- `base_url`
- `timeout_seconds`
- `token_env`

### LLM

- `provider`
- `base_url`
- `model`
- `api_key_env`
- `timeout_seconds`

## 安全边界

- API key 不直接写进仓库文档或示例计划
- 真实密钥通过环境变量注入
- OCR 图片原文和大块 base64 不建议长期写入日志

## 后续演进

- 结构化 JSON 抽取节点
- 视觉页面理解节点
- AI 决策建议节点
- AI 错误解释节点
