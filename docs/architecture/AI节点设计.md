# AI 节点设计

## 目标

在现有 JSON 自动化引擎之上，增加一层可配置、可复用、可扩展的 AI 节点能力。

这一层不替代 Playwright 动作引擎，而是补充：

- 数据处理
- OCR
- 文本理解
- 后续的页面理解与动作建议

## 设计原则

- AI 能力通过独立动作暴露，不把站点逻辑硬编码到模型调用里。
- 模型与服务通过配置文件注册，不在计划里直接写死地址和密钥。
- OCR、LLM、后续视觉能力都使用“服务别名”调用。
- AI 节点输出一律回写到变量，继续参与普通 JSON 编排。

## 当前分层

### 1. AI 服务注册层

- `src/keygen_automation/ai_registry.py`
- `config/ai-services.json`
- `config/ai-services.local.json`

职责：

- 加载 OCR / LLM 服务配置
- 管理服务别名
- 创建 OpenAI 兼容客户端
- 统一处理超时和环境变量密钥

### 2. AI 动作层

当前已规划/落地：

- `ocr_image`
- `llm_chat`

后续可扩展：

- `llm_extract_json`
- `vision_understand_page`
- `ai_decide_next_step`
- `ai_validate_form`

### 3. 编排层

AI 节点只是普通 `step`，可以自然参与：

- `if`
- `foreach`
- `retry`
- `suite`

## 为什么现在不直接全量换成 LangGraph

LangGraph 更适合：

- 长状态工作流
- 复杂 agent 分支
- 人工介入恢复
- 多轮推理图

但当前项目已经有一套稳定的 JSON 自动化执行内核，直接替换成本高、风险大。

当前更合适的策略是：

- 先保留现有 JSON 执行器
- 把 AI 节点做成可插拔层
- 等后续出现复杂推理子流程时，再把 LangGraph 放到 AI 子系统内部

## LangChain / LangGraph 建议落点

### LangChain

更适合放在 AI 节点实现层，用来做：

- Prompt 模板
- 模型路由封装
- 结构化输出辅助
- 后续工具调用包装

### LangGraph

更适合放在复杂 AI 子流程层，用来做：

- 多轮推理图
- 人工介入恢复
- 条件化 agent 子流程
- “识别 -> 判断 -> 生成建议 -> 等待人工确认 -> 再继续” 这种长状态流程

### 当前结论

现阶段不建议让 LangGraph 直接接管整个浏览器自动化执行器。

更稳的方式是：

- Playwright JSON 动作继续负责确定性执行
- AI 节点只在需要智能判断时调用
- 真正复杂的 AI 推理流程，再在 AI 节点内部逐步引入 LangGraph

## 当前建议

- 页面控制仍以显式 JSON 动作为主
- AI 负责识别、理解、提炼、建议
- 真正执行点击、输入、等待的仍然是框架原子动作

这能避免“全靠模型直接控制页面”带来的不稳定性。
