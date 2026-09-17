# config.json

## 用途

`config.json` 只保存 plan 运行配置，不保存业务变量。业务变量请写在 `plan.json` 的 `variables` 字段。

`config.json` 支持字符串外的 `//` 行注释；运行时会先移除注释再按 JSON 对象读取。不支持 `/* ... */` 块注释。

## 位置

- `<plan-root>/config.json`: 当前 plan 集合级配置，`plan-root` 来自运行根的 `plan.config.plan_roots`。
- `plan-package/config.json`: 当前 plan 包局部配置。

局部配置会覆盖集合级配置。嵌套对象递归合并；数组、字符串、数字、布尔值和 `null` 由局部值整体覆盖。

## 环境变量引用

`config.json` 的任意值可以使用完整值环境变量引用，运行时会解析为环境变量内容：

```json
{
  "connections": {
    "crm_pg": {
      "type": "postgresql",
      "dsn": {
        "env": "CRM_POSTGRES_DSN"
      }
    }
  }
}
```

支持写法：

- `{"env": "NAME"}`
- `{"env": "NAME", "default": "value"}`
- `"env:NAME"`
- `"$env:NAME"`
- `"${NAME}"`

没有设置环境变量且没有 `default` 时解析为空字符串。需要连接数据库的本机真实配置建议放在 `local/database-services.json`，公开示例用环境变量引用。

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
- `prompt`: 字符串。可选，等待用户确认时显示的提示文案；无 AI 命令行运行时只接受 `y` 或 `n`。

失败运行不会触发检查等待，会直接清理浏览器资源。

## failure_capture

控制失败现场是否自动保存截图。默认不保存失败截图；需要截图时必须显式开启配置。

```json
{
  "failure_capture": {
    "browser_screenshot": false,
    "desktop_screenshot": false
  }
}
```

字段：

- `browser_screenshot`: 布尔值。默认 `false`。为 `true` 时，浏览器步骤失败会写入 `output/<run>/failure-screenshots/`。
- `desktop_screenshot`: 布尔值。默认 `false`。为 `true` 时，桌面步骤失败会写入 `output/<run>/failure-desktop-screenshots/`。

无论是否开启截图，浏览器失败仍会保存 `failure-html/` 和 `failure-page-state/`；桌面失败仍会保存 `failure-desktop-state/`。

## desktop.ocr

`desktop.ocr` 已移除。`config.json` 中出现该字段会校验失败，错误为“desktop.ocr 已移除；桌面自动化不再支持 OCR 配置”。

桌面线不支持 `desktop_vision type=locate_text`，也不读取 Tesseract、pytesseract 或语言包配置。需要文字读取时使用控件树、应用接口、文件读取或人工确认。

## desktop.run_mutex

控制同一项目内 desktop plan 的运行互斥。默认启用；同一时间只允许一个 desktop plan 控制当前项目的真实桌面资源。

```json
{
  "desktop": {
    "run_mutex": {
      "enabled": true,
      "scope": "project",
      "on_conflict": "fail",
      "wait_timeout_seconds": 0,
      "stale_after_seconds": 7200
    }
  }
}
```

字段：

- `enabled`: 布尔值。默认 `true`。
- `scope`: `project` 或 `plan_package`。默认 `project`。
- `on_conflict`: `fail` 或 `wait`。默认 `fail`；冲突时直接失败，避免静默等待。
- `wait_timeout_seconds`: 非负整数。`on_conflict=wait` 时最多等待秒数。
- `stale_after_seconds`: 正整数。用于锁文件诊断信息，不绕过有效系统锁。

## desktop.foreground_protection

控制真实键鼠输入前的窗口激活和前台复查。默认启用；plan 通常不需要额外写“把窗口提到最前”的步骤。

```json
{
  "desktop": {
    "foreground_protection": {
      "enabled": true,
      "strict": true,
      "activation_attempts": 3,
      "retry_delay_ms": 80,
      "cache_ttl_ms": 1500
    }
  }
}
```

字段：

- `enabled`: 布尔值。默认 `true`。
- `strict`: 布尔值。默认 `true`；目标窗口无法成为前台时真实输入失败。
- `activation_attempts`: 正整数。默认 `3`。
- `retry_delay_ms`: 非负整数。默认 `80`。
- `cache_ttl_ms`: 非负整数。默认 `1500`。同一目标窗口连续真实输入时，在该时间窗内复用上一次前台校验结果，减少重复 `focus/active-window` 开销；设为 `0` 可关闭缓存。

调参建议：

- 默认值偏保守，适合跨窗口、弹窗多、用户可能中途抢焦点的流程。
- 单窗口连续操作，例如聊天工具搜索联系人、粘贴消息、回车发送，通常可以设为 `8000` 到 `10000`，避免每个键鼠动作都重新做窗口聚焦和 active window 复查。
- 缓存只复用已经成功的目标窗口校验，不跳过首次真实输入前的前台保护。
- 如果计划中有跨窗口点击、系统弹层、文件对话框、付款/删除/发送前确认等高风险动作，不要为了速度盲目拉长缓存；应在跨窗口步骤前重新等待/聚焦/断言目标窗口。
- 优化耗时时先看 `events.jsonl`：`guard_mode=restore_focus_verify` 是完整校验，`guard_mode=cached_restore_focus_verify` 是缓存命中，`guard_cache_age_ms` 能判断 TTL 是否过短。

## desktop_profiles

配置桌面 App/窗口定位预设。plan 中用 `profile` 引用，见 [desktop app profile](../actions/desktop/app_profile.md)。

```json
{
  "desktop_profiles": {
    "chat": {
      "platforms": {
        "windows": {
          "launch": {
            "command": "C:/apps/mock-chat.exe"
          },
          "window_query": {
            "process_name": "mock-chat.exe",
            "title_contains": "Mock Chat"
          },
          "defaults": {
            "wait_for_window": true,
            "focus": true,
            "window_timeout_ms": 10000
          }
        },
        "macos": {
          "launch": {
            "app": "Mock Chat"
          },
          "window_query": {
            "app": "Mock Chat",
            "title_contains": "Mock Chat"
          },
          "defaults": {
            "wait_for_window": true,
            "focus": true,
            "window_timeout_ms": 10000
          }
        }
      }
    }
  }
}
```

字段：

- `launch`: 可选，提供 `app`、`path`、`command`、`args`。
- `window_query`: 可选，提供 `title`、`title_contains`、`title_regex`、`app`、`process`、`process_name`、`class_name`、`window_id`、`match_index`。
- `defaults`: 可选，提供常用默认参数，例如 `wait_for_window`、`focus`、`timeout_ms`、`window_timeout_ms`、`interval_ms`。
- `platforms`: 可选，按平台保存差异配置；平台键支持 `windows`/`win32`/`win64` 和 `macos`/`darwin`/`mac`/`osx`。plan 中仍引用同一个 `profile` 名称。
- `platforms.windows` / `platforms.macos`: 可选，按平台覆盖 profile。

step 上显式字段优先级高于 profile。

## ai_services

专项 AI 组件和 AI 终端使用的模型服务配置。

```json
{
  "ai_services": {
    "default": {
      "protocol": "openai_chat_completions",
      "base_url": "https://your-openai-compatible-endpoint/v1",
      "model": "your-model",
      "api_key_env": "OPENAI_API_KEY",
      "timeout_seconds": 90,
      "max_output_tokens": 2048,
      "response_format": "json_schema"
    }
  }
}
```

`protocol` 是规范协议字段，省略时默认为 `openai_chat_completions`。同一个配置集合可以注册多个服务；专项 `ai` action 通过 `service` 选择服务，AI 终端使用 `ai_services.default`。服务配置按集合级和 plan 局部 `config.json` 合并，局部同名字段覆盖集合级字段。

| `protocol` | 上游协议 | `base_url` 的常见官方根地址 | 适合场景 |
| --- | --- | --- | --- |
| `openai_chat_completions` | OpenAI Chat Completions | `https://api.openai.com/v1` | 默认值；OpenAI-compatible 网关通常优先使用此协议 |
| `openai_responses` | OpenAI Responses API | `https://api.openai.com/v1` | 使用 Responses 专有能力或模型时 |
| `anthropic_messages` | Anthropic Messages API | `https://api.anthropic.com` | Claude 原生服务或兼容服务 |
| `google_generate_content` | Google Gemini GenerateContent API | `https://generativelanguage.googleapis.com` | Gemini 原生服务或兼容服务 |

`base_url` 必须与所选协议匹配。OpenAI 的 URL 通常包含 `/v1`，Anthropic 根地址不包含 `/v1`，Gemini 客户端会自行追加 API 版本和 `models/...:generateContent` 路径。不要把 Chat Completions 的网关地址填给 Anthropic、Gemini 或 Responses，项目不会试探、转换或自动降级。

### 参数参考

下表是 `ai_services.<服务名>` 的完整参数参考。统一字段的名字相同，不表示所有协议均支持；未填写的可选字段不会发送给上游，`anthropic_messages` 的 `max_tokens` 例外，见 `max_output_tokens`。

| 字段 | 类型与默认值 | 用途 | 注意事项 |
| --- | --- | --- | --- |
| `protocol` | 字符串；默认 `openai_chat_completions` | 选择请求和响应协议。 | 新配置只使用该字段。选择后固定使用该协议，失败时不切换供应商。 |
| `model` | 非空字符串；必填 | 上游模型 ID。 | 模型能力不是协议能力的一部分；例如某个 reasoning 档位、JSON Schema 或采样参数是否可用，最终由模型决定。 |
| `api_key` | 非空字符串；可选 | 直接提供服务密钥。 | 有值时优先于 `api_key_env`。适合本地临时调试；提交配置前自行决定是否保留。 |
| `api_key_env` | 非空字符串；可选 | 指定承载密钥的环境变量名。 | 仅当没有 `api_key` 时读取。变量缺失或为空会在本地报错，不会发起请求。 |
| `base_url` | 非空 URL 字符串；可选 | 覆盖供应商 SDK 的服务根地址。 | 用于代理、兼容网关或私有部署；路径格式必须符合上表说明。省略时由各 SDK 使用官方默认地址。 |
| `timeout_seconds` | 正数；默认 `60` | 单次 HTTP 请求的超时。 | OpenAI/Anthropic 直接使用秒；Gemini 适配器转换为毫秒。它不限制整个 plan 的执行时间。 |
| `max_retries` | 非负整数；默认由 SDK 决定 | 配置 SDK/LangChain 的传输重试次数。 | `0` 关闭重试；Gemini 适配为总尝试 `1` 次。只处理传输层可重试错误，不会重写提示词、换协议或修复格式错误。 |
| `stream` | 布尔；默认 `false` | 让专项 `ai` action 使用协议原生流式调用。 | AI 终端始终流式渲染，本字段不改变终端行为。上游模型或网关不支持流式时保留原始错误。 |
| `temperature` | 数字；默认不发送 | 控制采样随机性，值越低通常越稳定。 | `anthropic_messages` 当前 SDK 不接受，配置会失败。对 reasoning 模型，供应商可能禁止非默认采样值；项目不静默删除，须按模型文档选择或接受上游错误。 |
| `top_p` | 数字；默认不发送 | 核采样阈值，通常与 `temperature` 二选一调节。 | `anthropic_messages` 当前 SDK 不接受，配置会失败。reasoning 模型可能另有限制。 |
| `max_output_tokens` | 正整数；默认不发送 | 限制生成上限。 | 映射为 Chat Completions 的 `max_completion_tokens`、Responses/Gemini 的 `max_output_tokens`、Anthropic 的 `max_tokens`。Anthropic 要求该字段，省略时适配器发送 `4096`。 |
| `stop` | 非空字符串或非空字符串数组；默认不发送 | 指定生成到达的停止序列。 | 单个字符串会规范化为数组。映射到 Chat 的 `stop`、Anthropic 的 `stop_sequences`、Gemini 的 `stop_sequences`；`openai_responses` 不支持，配置会失败。 |
| `reasoning_effort` | 字符串；默认不发送 | 请求模型使用指定的思考强度。 | 这是跨协议的有限抽象，详见“思考级别”。不是完整的模型推理/预算设置。 |
| `response_format` | `json_schema`、`json_object` 或 `plain`；默认 `json_schema` | 控制专项 AI 的上游输出格式约束。 | 专项 AI 无论取值如何都会解析 JSON 并做本地 schema 校验；`plain` 仅表示不向上游发送格式约束，不表示 action 可以返回任意文本。AI 终端不使用此字段。 |
| `strict_schema` | 布尔；默认 `true` | OpenAI JSON Schema 请求的 strict 标记。 | 仅在 `response_format=json_schema` 时对 OpenAI 两种协议发送。Anthropic/Gemini 不接收该字段，但四协议的专项 AI 返回值都会经过本地 schema 校验。 |
| `provider` | 字符串；兼容校验字段 | 可选地声明服务提供方。 | 新配置不需要填写，`protocol` 已足够。填写时只校验组合是否合法：OpenAI 协议为 `openai`/`openai-compatible`，Anthropic 为 `anthropic`，Gemini 为 `google`/`gemini`。它不改变实际客户端。 |
| `api` | 字符串；旧配置兼容字段 | 兼容旧的 `chat_completions`/`responses`。 | 新配置不要使用；请迁移为 `protocol: openai_chat_completions` 或 `protocol: openai_responses`。同时写入时以 `protocol` 为准。 |

### 思考级别

`reasoning_effort` 只在填写时发送，未填写即保持供应商或模型默认值。允许值和实际映射如下：

| 协议 | 可配置值 | 上游字段 | 重要限制 |
| --- | --- | --- | --- |
| `openai_chat_completions` | `none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max` | `reasoning_effort` | 值集合来自当前 OpenAI SDK；每个模型并不保证支持所有值。 |
| `openai_responses` | `none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max` | `reasoning: {"effort": "..."}` | 不会错误地发送顶层 `reasoning_effort`。模型能力不足时保留上游错误。 |
| `anthropic_messages` | `low`、`medium`、`high`、`xhigh`、`max` | `output_config.effort` | 不等同于 Anthropic 的 `thinking` / `budget_tokens` extended thinking；当前配置没有暴露预算参数。 |
| `google_generate_content` | `minimal`、`low`、`medium`、`high` | `thinking_config.thinking_level`，转换为大写 | Gemini 模型是否支持 thinking level 及档位由上游模型决定。 |

不要因为需要“更强思考”就同时填入供应商私有 `thinking`、`budget_tokens` 或网关自定义字段；这些字段不在统一契约中，会被拒绝或不被发送。需要新增此类能力时，应先扩展配置契约、适配器和 mock 上游验证。

### 协议能力矩阵

| 通用字段 | Chat Completions | Responses | Anthropic Messages | Gemini GenerateContent |
| --- | --- | --- | --- | --- |
| `temperature` / `top_p` | 支持 | 支持 | 本地拒绝 | 支持 |
| `max_output_tokens` | `max_completion_tokens` | `max_output_tokens` | `max_tokens`，默认 `4096` | `max_output_tokens` |
| `stop` | `stop` | 本地拒绝 | `stop_sequences` | `stop_sequences` |
| `reasoning_effort` | `reasoning_effort` | `reasoning.effort` | `output_config.effort` | `thinking_config.thinking_level` |
| `response_format=json_schema` | `response_format.json_schema` | `text.format` | `output_config.format` | `response_mime_type` + `response_json_schema` |
| `response_format=json_object` | `response_format.json_object` | `text.format.json_object` | 空对象 JSON Schema | `application/json` MIME 类型 |
| `stream=true` | Chat Completion SSE | Responses SSE | Messages SSE | GenerateContent SSE |

JSON Schema 的供应商支持范围不同。`strict_schema` 不能把 Anthropic 或 Gemini 变成 OpenAI strict mode；所有专项 AI 结果仍会在本地进行 JSON 解析和 schema 校验。协议选择固定后不会自动切换、手动重试、改写格式或降级到其他协议。

需要启用思考级别时，在最小配置上只增加 `reasoning_effort`，并先不要同时设置 `temperature` 或 `top_p`：

```json
{
  "protocol": "openai_responses",
  "model": "your-reasoning-model",
  "api_key_env": "OPENAI_API_KEY",
  "reasoning_effort": "high"
}
```

待模型文档确认支持采样参数后，再单独增加 `temperature` 或 `top_p`。项目不会为了兼容模型而静默删除用户配置。

需要同时注册多个协议时，可以在同一个 `ai_services` 集合中分别配置服务：

```json
{
  "ai_services": {
    "default": {
      "protocol": "openai_chat_completions",
      "base_url": "https://api.openai.com/v1",
      "model": "your-chat-model",
      "api_key_env": "OPENAI_API_KEY"
    },
    "responses": {
      "protocol": "openai_responses",
      "base_url": "https://api.openai.com/v1",
      "model": "your-responses-model",
      "api_key_env": "OPENAI_API_KEY"
    },
    "anthropic": {
      "protocol": "anthropic_messages",
      "base_url": "https://api.anthropic.com",
      "model": "your-anthropic-model",
      "api_key_env": "ANTHROPIC_API_KEY"
    },
    "gemini": {
      "protocol": "google_generate_content",
      "base_url": "https://generativelanguage.googleapis.com",
      "model": "your-gemini-model",
      "api_key_env": "GEMINI_API_KEY"
    }
  }
}
```
