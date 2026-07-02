# detect_challenge

## 用途

检测页面是否进入验证状态，例如验证码、真人验证、多因素认证提示或其他登录阻断页面。

这个组件只负责识别状态并通过 `output.as` 发布结果，不负责绕过真实网站的人机验证。

## 必填字段

- `action`: 固定写成 `detect_challenge`
- `browser`: 浏览器会话名
- `output.as`: 发布检测结果的变量名
- `rules`: 检测规则数组

## 可选字段

- `page`: 指定页面名

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
  "output": {"as": "challenge"},  "rules": [
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
