# detect_challenge

## 用途

检测页面是否进入验证状态，例如验证码、真人验证、多因素认证提示或其他登录阻断页面。

这个组件只负责识别状态并通过 `output.as` 发布结果，不负责绕过真实网站的人机验证。

## 必填字段

- `action`: 固定写成 `detect_challenge`
- `browser`: 浏览器会话名
- `output.as`: 发布检测结果的变量名

## 可选字段

- `page`: 指定页面名
- `rules`: 检测规则数组，可选。缺省或为空数组时直接输出未命中：`matched` 为 `false`，`labels` 和 `matches` 为空数组

输出结构：`matched`（布尔，是否有任一规则命中）、`labels`（命中规则的 label 数组）、`matches`（命中规则明细数组，每项含 `label`、`type`、`selector`、`text`、`value`，未提供的字段为 `null`）。

## 规则类型

规则是对象数组，`type` 缺省时按 `selector_visible` 处理；不支持的 `type` 会让步骤直接报错。

| rule.type | 必填字段 | 可选字段 | 判断逻辑 |
| --- | --- | --- | --- |
| `selector_visible` | `selector` | `index`（整数，命中多个时取第几个，从 `0` 开始，默认取第一个）、`label` | 元素存在且可见 |
| `selector_exists` | `selector` | `label` | 元素存在即可，不要求可见 |
| `text_contains` | `text` | `selector`（默认 `body`）、`label` | 目标元素的文本包含 `text`；选择器无匹配时按未命中处理 |
| `url_contains` | `value` | `label` | 当前页面 URL 包含 `value` |

`label` 是规则的自定义标识，缺省等于 rule 的 `type`，用于在 `labels` 和 `matches` 里区分是哪条规则命中。

## 示例

```json
{
  "action": "detect_challenge",
  "browser": "demo",
  "output": {"as": "challenge"},
  "rules": [
    {
      "type": "selector_visible",
      "selector": "#verification-panel",
      "label": "verification_panel"
    },
    {
      "type": "text_contains",
      "selector": "body",
      "text": "验证码",
      "label": "captcha_text"
    }
  ]
}
```

## 推荐处理方式

- 在正式站点遇到验证时，优先让自动化正常尝试页面提供的验证流程；需要用户操作时，使用 `open_browser.headed=true` 加 `manual_confirm` 做同一个 Playwright 浏览器窗口内的人工交接。
- 需要长期复用同一个 plan 包的登录态时，优先让 `open_browser.use_profile=true` 使用 plan 包内唯一的 `profiles/browser/`。人工通过后，Cookie、localStorage、IndexedDB 等状态会随 profile 保留。
- 需要把状态导出成文件时，再用 `capture` + `type: storage_state` 保存登录态，后续 plan 可用 `open_browser.storage_state_path` 导入。
