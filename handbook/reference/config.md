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
      "stream": true,
      "timeout_seconds": 90,
      "max_retries": 2,
      "temperature": 0.2,
      "top_p": 0.9,
      "max_output_tokens": 2048,
      "stop": ["\\n\\n"],
      "reasoning_effort": "medium",
      "strict_schema": true,
      "response_format": "json_schema"
    }
  }
}
```

`protocol` 是服务配置的规范协议字段，省略时默认为 `openai_chat_completions`。当前支持：

| `protocol` | 对应协议 |
| --- | --- |
| `openai_chat_completions` | OpenAI Chat Completions |
| `openai_responses` | OpenAI Responses API |
| `anthropic_messages` | Anthropic Messages API |
| `google_generate_content` | Google Gemini GenerateContent API |

除 `protocol` 外，服务配置使用统一字段：`model`、`api_key`、`api_key_env`、`base_url`、`timeout_seconds`、`max_retries`、`stream`、`temperature`、`top_p`、`max_output_tokens`、`stop`、`reasoning_effort`、`response_format` 和 `strict_schema`。字段统一命名不代表每个协议都接受全部字段；未填写的可选字段不发送给上游。

`reasoning_effort` 默认不设置。OpenAI 两种协议支持 `none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max`；Anthropic 支持 `low`、`medium`、`high`、`xhigh`、`max`；Gemini 支持 `minimal`、`low`、`medium`、`high`。模型不支持所选级别时保留并报告上游原始错误。

`response_format` 可选 `json_schema`、`json_object` 或 `plain`，四种协议都会进行对应适配，但具体模型能力仍可能拒绝该配置。`strict_schema` 是 OpenAI JSON Schema 请求的严格模式；Anthropic/Gemini 由返回后的本地 schema 校验保证输出形状。协议选择固定后不会自动切换或降级到其他协议。配置可以直接写 `api_key`，也可以通过 `api_key_env` 读取环境变量。

| 字段 | 不可用的协议 | 行为 |
| --- | --- | --- |
| `stop` | `openai_responses` | 配置校验失败 |
| `temperature`、`top_p` | `anthropic_messages` | 配置校验失败 |

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
