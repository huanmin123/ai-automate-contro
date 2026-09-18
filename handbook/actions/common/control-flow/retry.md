# retry

## 用途

对一组步骤增加失败重试能力。

## 必填字段

- `action`: 固定写成 `retry`
- `steps`: 要重试的步骤数组

## 可选字段

- `attempts`: 最大尝试次数，默认 `3`。
- `wait_seconds`: 每次失败后到下一次尝试前的等待秒数，默认 `1`。传 `0` 或负数时不等待，直接开始下一次尝试。

## 边界

- `attempts` 为 `0` 或负数时，步骤体一次都不会执行，`retry` 直接成功返回，不报错。当前校验不拦截这种写法，写 `attempts` 时应使用大于等于 `1` 的整数。
- 某一次尝试成功后立即结束 `retry`，剩余次数不再执行。
- 所有尝试都失败时，`retry` 把最后一次失败的原始错误重新抛出，plan 按该错误失败；等待只发生在两次尝试之间，最后一次失败后不再等待。

## 示例

```json
{
  "action": "retry",
  "attempts": 3,
  "wait_seconds": 1,
  "steps": [
    {
      "action": "wait",
      "type": "selector",
      "browser": "main",
      "selector": "input[autocomplete='username']"
    },
    {
      "action": "element",
      "type": "fill",
      "browser": "main",
      "selector": "input[autocomplete='username']",
      "value": "{{email}}"
    }
  ]
}
```
