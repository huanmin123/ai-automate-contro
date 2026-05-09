# 组件手册

这个目录是给“编排者”看的，不是给执行器看的。

如果你想自己写 JSON 计划，推荐按照下面顺序阅读：

1. [计划结构](./计划结构.md)
2. [第一个计划示例](./第一个计划示例.md)
3. 下面按组件名称阅读具体文档

## 基础概念

- [计划结构](./计划结构.md)
- [第一个计划示例](./第一个计划示例.md)

## 浏览器会话组件

- [open_browser](./open_browser.md)
- [page](./page.md)
- [close_browser](./close_browser.md)

## 页面跳转与等待组件

- [navigate](./navigate.md)
- [wait](./wait.md)
- [wait_for_download](./wait_for_download.md)
- [wait_for_popup](./wait_for_popup.md)
- [wait_for_network](./wait_for_network.md)
- [assert](./assert.md)

## 页面交互组件

- [element](./element.md)
- [keyboard](./keyboard.md)
- [mouse](./mouse.md)
- [scroll](./scroll.md)

## 数据提取与变量组件

- [variable](./variable.md)
- [extract](./extract.md)

## AI 组件

- [detect_challenge](./detect_challenge.md)
- [ocr_image](./ocr_image.md)
- [llm_chat](./llm_chat.md)
- [llm_extract_json](./llm_extract_json.md)

## 控制流组件

- [run_sub_plan](./run_sub_plan.md)
- [if](./if.md)
- [foreach](./foreach.md)
- [retry](./retry.md)

## 文件 IO 组件

- [read](./read.md)
- [write](./write.md)

## 辅助组件

- [print](./print.md)
- [manual_confirm](./manual_confirm.md)
- [capture](./capture.md)
- [dialog](./dialog.md)
- [sleep](./sleep.md)

## 设计原则

- 一个 JSON `step` 只做一件事。
- 组件名就是 `action` 字段的值。
- 参数结构一致的能力合并到同一个组件，用 `type` 控制具体操作，例如 `navigate`、`element`、`wait`、`extract`、`assert`、`read`、`write`。
- 参数生命周期不同的能力继续保留独立组件，例如 `open_browser`、`run_sub_plan`、`foreach`、`retry`、`wait_for_popup`、`wait_for_download`、AI 节点。
- 组件文档里的字段名需要和 JSON 里保持一致。
- 变量通过 `{{变量名}}` 进行替换。
- 如果一个流程太长，先用 `print` 和 `manual_confirm` 把调试链路打通，再逐步加复杂动作。
