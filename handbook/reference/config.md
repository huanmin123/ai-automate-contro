# config.json

## 用途

`config.json` 只保存 plan 运行配置，不保存业务变量。业务变量请写在 `plan.json` 的 `variables` 字段。

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

## desktop.ocr

配置桌面 OCR 运行时。只影响 `automation_type: "desktop"` 且使用 `desktop_vision type=locate_text` 的 plan。

```json
{
  "desktop": {
    "ocr": {
      "tesseract_path": "C:/path/to/tesseract.exe",
      "tessdata_dir": "C:/path/to/tessdata",
      "default_language": "eng"
    }
  }
}
```

字段：

- `tesseract_path`: 字符串。可选，Tesseract 可执行文件路径或安装目录。
- `tessdata_dir`: 字符串。可选，`.traineddata` 语言包目录。
- `default_language`: 字符串。可选，默认 OCR 语言标记；plan action 上的 `language` 仍可显式覆盖。

解析顺序：plan 包 `config.json` 覆盖集合级 `<plan-root>/config.json`；没有配置时运行时再尝试环境变量和系统路径。AI 写需要 OCR 的 desktop plan 前，先确认 `capability_matrix.dependencies.tesseract` 和所需 `tessdata.*` 为 `true`。

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
      "retry_delay_ms": 80
    }
  }
}
```

字段：

- `enabled`: 布尔值。默认 `true`。
- `strict`: 布尔值。默认 `true`；目标窗口无法成为前台时真实输入失败。
- `activation_attempts`: 正整数。默认 `3`。
- `retry_delay_ms`: 非负整数。默认 `80`。

## desktop_profiles

配置桌面 App/窗口定位预设。plan 中用 `profile` 引用，见 [desktop app profile](../actions/desktop/app_profile.md)。

```json
{
  "desktop_profiles": {
    "mock-chat": {
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
- `platforms.windows` / `platforms.macos`: 可选，按平台覆盖 profile。

step 上显式字段优先级高于 profile。

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

配置可以直接写 `api_key`，也可以通过 `api_key_env` 读取环境变量。
