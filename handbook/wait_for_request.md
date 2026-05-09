# wait_for_request

## 用途

等待一次指定请求发出，并可把请求信息保存到变量。

适合校验某个点击、输入或提交动作是否真正触发了目标接口。

## 必填字段

- `action`: 固定写成 `wait_for_request`
- `browser`: 浏览器会话名
- `url`: 要等待的请求地址或可匹配的 URL
- `trigger`: 触发请求的单个动作对象

## 可选字段

- `page`: 从哪个页面触发，默认当前页
- `save_as`: 把请求信息保存成变量

## 保存结果

如果填写了 `save_as`，变量里会保存：

- `url`
- `method`
- `resource_type`

## 示例

```json
{
  "action": "wait_for_request",
  "browser": "demo",
  "url": "https://httpbin.org/get?case=request-demo",
  "save_as": "request_info",
  "trigger": {
    "action": "click",
    "browser": "demo",
    "selector": "#request-btn"
  }
}
```
