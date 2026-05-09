# detect_challenge

## 用途

检测页面是否进入验证状态，例如验证码、真人验证、多因素认证提示或其他登录阻断页面。

这个组件只负责识别状态并保存变量，不负责绕过真实网站的人机验证。

## 必填字段

- `action`: 固定写成 `detect_challenge`
- `browser`: 浏览器会话名
- `save_as`: 保存检测结果的变量名
- `rules`: 检测规则数组

## 可选字段

- `page`: 指定页面名
- `save_detected_as`: 单独保存布尔值，表示是否命中任意规则
- `save_label_as`: 单独保存第一个命中的标签

## 规则类型

- `selector_visible`: 元素存在并可见
- `selector_exists`: 元素存在
- `text_contains`: 指定元素文本包含目标文本
- `url_contains`: 当前 URL 包含目标文本

## 示例

```json
{
  "action": "detect_challenge",
  "browser": "demo",
  "save_as": "challenge",
  "save_detected_as": "challenge_detected",
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

- 在正式站点遇到验证时，使用 `manual_confirm` 做人工交接。
- 人工通过后，用 `capture` + `type: storage_state` 保存登录态，后续回归用 `open_browser.storage_state_path` 复用。
- 在测试环境中，优先使用本地 fixture 或后端测试开关模拟验证流程。
