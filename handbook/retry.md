# retry

## 用途

对一组步骤增加失败重试能力。

## 必填字段

- `action`: 固定写成 `retry`
- `steps`: 要重试的步骤数组

## 可选字段

- `attempts`: 最大尝试次数，默认 `3`
- `wait_seconds`: 每次失败后的等待秒数，默认 `1`

## 示例

```json
{
  "action": "retry",
  "attempts": 3,
  "wait_seconds": 1,
  "steps": [
    {
      "action": "wait_for_selector",
      "browser": "main",
      "selector": "input[autocomplete='username']"
    },
    {
      "action": "fill",
      "browser": "main",
      "selector": "input[autocomplete='username']",
      "value": "{{email}}"
    }
  ]
}
```
