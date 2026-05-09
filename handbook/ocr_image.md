# ocr_image

## 用途

调用已配置的 OCR 服务识别图片文本，并把完整结果保存到变量。

这是一种通用 AI 节点，适合识别：

- 本地图片文件
- 页面元素截图
- `data:image/...;base64,...` 形式的数据

## 必填字段

- `action`: 固定写成 `ocr_image`
- `service`: OCR 服务别名
- `save_as`: 保存完整 OCR 结果的变量名

## 三种输入方式

三选一：

- `path`: 本地图片路径
- `data_url`: base64 data URL
- `selector`: 页面元素选择器，执行器会先截图再识别

## 可选字段

- `browser`: 当使用 `selector` 时需要
- `page`: 当使用 `selector` 时可指定页面
- `capture_path`: 当使用 `selector` 时，截图临时保存路径，最终写入 `output/ocr-captures/`
- `save_text_as`: 只把 `text` 字段单独保存到另一个变量

## 结果结构

当前 OCR sidecar 会返回类似结构：

- `text`
- `blocks`
- `meta`
- `errors`

## 示例

```json
{
  "action": "ocr_image",
  "service": "local_ocr",
  "path": "resources/sample-ocr.png",
  "save_as": "ocr_result",
  "save_text_as": "ocr_text"
}
```

## 常见组合

页面图片 OCR 后回填输入框的典型链路：

1. `extract` + `type: attribute` 取出图片 `src`
2. `ocr_image` 识别 `data_url`
3. `element` + `type: fill` 把 `{{ocr_text}}` 回填到输入框

如果图片不是 `src` 形式，而是页面中的可见元素，也可以直接对 `selector` 截图识别。
