# 组件手册

这个目录是给“编排者”看的，不是给执行器看的。

如果你想自己写 JSON 计划，推荐按照下面顺序阅读：

1. [计划结构](./计划结构.md)
2. [第一个计划示例](./第一个计划示例.md)
3. 下面按组件名称阅读具体文档

## 基础概念

- [计划结构](./计划结构.md)
- [第一个计划示例](./第一个计划示例.md)
- [多项目与标签执行](./多项目与标签执行.md)

## 浏览器会话组件

- [open_browser](./open_browser.md)
- [open_new_page](./open_new_page.md)
- [switch_page](./switch_page.md)
- [close_page](./close_page.md)
- [close_browser](./close_browser.md)
- [save_storage_state](./save_storage_state.md)
- [load_storage_state](./load_storage_state.md)

## 页面跳转与等待组件

- [goto](./goto.md)
- [refresh](./refresh.md)
- [go_back](./go_back.md)
- [go_forward](./go_forward.md)
- [wait_for_selector](./wait_for_selector.md)
- [wait](./wait.md)
- [wait_for_url](./wait_for_url.md)
- [wait_for_text](./wait_for_text.md)
- [wait_for_count](./wait_for_count.md)
- [wait_for_download](./wait_for_download.md)
- [wait_for_popup](./wait_for_popup.md)
- [wait_for_request](./wait_for_request.md)
- [wait_for_response](./wait_for_response.md)
- [assert_selector](./assert_selector.md)
- [assert_text](./assert_text.md)
- [assert_value](./assert_value.md)
- [assert_url_contains](./assert_url_contains.md)
- [assert_count](./assert_count.md)

## 页面交互组件

- [click](./click.md)
- [hover](./hover.md)
- [fill](./fill.md)
- [clear](./clear.md)
- [type](./type.md)
- [focus](./focus.md)
- [press](./press.md)
- [keyboard_press](./keyboard_press.md)
- [keyboard_type](./keyboard_type.md)
- [keyboard_down](./keyboard_down.md)
- [keyboard_up](./keyboard_up.md)
- [scroll_into_view](./scroll_into_view.md)
- [scroll_by](./scroll_by.md)
- [mouse_move](./mouse_move.md)
- [mouse_click_at](./mouse_click_at.md)
- [mouse_down](./mouse_down.md)
- [mouse_up](./mouse_up.md)
- [mouse_wheel](./mouse_wheel.md)
- [check](./check.md)
- [uncheck](./uncheck.md)
- [select_option](./select_option.md)
- [set_input_files](./set_input_files.md)

## 数据提取与变量组件

- [set_variable](./set_variable.md)
- [set_variables](./set_variables.md)
- [copy_variable](./copy_variable.md)
- [extract_text](./extract_text.md)
- [extract_value](./extract_value.md)
- [extract_attribute](./extract_attribute.md)
- [extract_html](./extract_html.md)
- [extract_count](./extract_count.md)
- [extract_table](./extract_table.md)
- [extract_nth_text](./extract_nth_text.md)
- [extract_all_texts](./extract_all_texts.md)
- [extract_all_values](./extract_all_values.md)
- [dump_variables](./dump_variables.md)

## AI 组件

- [ocr_image](./ocr_image.md)
- [llm_chat](./llm_chat.md)
- [llm_extract_json](./llm_extract_json.md)

## 控制流组件

- [if](./if.md)
- [foreach](./foreach.md)
- [retry](./retry.md)

## 数据源组件

- [load_json](./load_json.md)
- [load_csv](./load_csv.md)
- [load_txt](./load_txt.md)

## 辅助组件

- [print](./print.md)
- [manual_confirm](./manual_confirm.md)
- [screenshot](./screenshot.md)
- [save_page_html](./save_page_html.md)
- [accept_dialog](./accept_dialog.md)
- [dismiss_dialog](./dismiss_dialog.md)
- [write_json](./write_json.md)
- [write_csv](./write_csv.md)
- [write_text](./write_text.md)
- [append_text](./append_text.md)
- [sleep](./sleep.md)

## 设计原则

- 一个 JSON `step` 只做一件事。
- 组件名就是 `action` 字段的值。
- 组件文档里的字段名需要和 JSON 里保持一致。
- 变量通过 `{{变量名}}` 进行替换。
- 如果一个流程太长，先用 `print` 和 `manual_confirm` 把调试链路打通，再逐步加复杂动作。
