# keygen-openai-account

这是一个基于 Playwright + Python 的 JSON 编排自动化内核。

你不需要每次改 Python 代码，而是通过编写计划文件来描述动作流程，执行器负责读取 JSON 并按顺序执行。

`handbook/` 是唯一教程来源。
`examples/` 只放可运行示例，不承担教学职责。

## 快速开始

```powershell
python -m pip install -r .\requirements.txt
python -m playwright install chromium
python .\main.py --file .\examples\scenarios\basic\fill_system_account.example.json
```

运行带标签筛选的 suite：

```powershell
python .\main.py --file .\examples\suites\smoke\tagged_projects.example.json --include-tags smoke,login --tag-mode all
```

## 先看哪里

- 组件手册入口：`.\handbook\README.md`
- 计划结构说明：`.\handbook\计划结构.md`
- 第一个示例：`.\handbook\第一个计划示例.md`

## 当前目录

- `main.py`: 命令行入口，负责读取 JSON 计划并执行
- `src/keygen_automation/`: 自动化执行内核
- `handbook/`: 面向人的组件手册，每个动作一个独立文档
- `examples/`: 可运行示例资产，不作为教程入口
- `docs/`: 项目架构、设计、排期、错题本、重构记录

## examples 分层

- `examples/scenarios/basic/`: 基础交互示例
- `examples/scenarios/data-driven/`: 数据驱动与变量流转示例
- `examples/suites/smoke/`: 轻量冒烟套件
- `examples/suites/regression/`: 回归与批量执行套件

## 当前支持的动作组件

- `open_browser`
- `open_new_page`
- `switch_page`
- `close_page`
- `close_browser`
- `goto`
- `refresh`
- `go_back`
- `go_forward`
- `click`
- `hover`
- `fill`
- `clear`
- `type`
- `focus`
- `wait_for_selector`
- `wait`
- `wait_for_url`
- `wait_for_text`
- `wait_for_count`
- `extract_text`
- `extract_value`
- `extract_attribute`
- `extract_html`
- `extract_count`
- `extract_table`
- `extract_nth_text`
- `extract_all_texts`
- `extract_all_values`
- `press`
- `keyboard_press`
- `keyboard_type`
- `keyboard_down`
- `keyboard_up`
- `scroll_into_view`
- `scroll_by`
- `mouse_move`
- `mouse_click_at`
- `mouse_down`
- `mouse_up`
- `mouse_wheel`
- `check`
- `uncheck`
- `select_option`
- `set_input_files`
- `screenshot`
- `save_page_html`
- `save_storage_state`
- `load_storage_state`
- `wait_for_download`
- `wait_for_popup`
- `wait_for_request`
- `wait_for_response`
- `accept_dialog`
- `dismiss_dialog`
- `manual_confirm`
- `print`
- `dump_variables`
- `write_json`
- `write_csv`
- `write_text`
- `append_text`
- `sleep`
- `assert_selector`
- `assert_text`
- `assert_value`
- `assert_url_contains`
- `assert_count`
- `set_variable`
- `set_variables`
- `load_json`
- `load_csv`
- `load_txt`
- `if`
- `foreach`
- `retry`
- `copy_variable`
- `ocr_image`
- `llm_chat`
- `llm_extract_json`

具体字段说明、适用场景和使用方式请直接看 `handbook` 目录，不建议靠阅读原始 JSON 文件学习框架。

## 第三版新增能力

- 失败自动截图
- `result.json` 计划结果文件
- `suite-summary.json` 和 `suite-summary.md` 套件汇总报告
- suite 标签筛选执行

## 当前新增补强

- 新窗口捕获：`wait_for_popup`
- 接口请求/响应等待：`wait_for_request`、`wait_for_response`
- 表格批量提取：`extract_table`
- CSV 输出：`write_csv`
