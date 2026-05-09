# examples

这个目录只放可运行示例，不承担教学职责。

真正学习组件用法时，请先看：

- `handbook/README.md`

## 目录说明

- `scenarios/basic/`: 基础动作与最小交互链路
- `scenarios/data-driven/`: 数据读取、变量传递、循环
- `scenarios/regression/`: 失败捕获、重试、回归辅助场景
- `suites/smoke/`: 轻量冒烟套件
- `suites/regression/`: 顺序/并发回归套件
- `data/`: 示例数据源

## 使用建议

- 学习动作语义：看 `handbook/`
- 需要跑一个最小用例：从 `scenarios/basic/` 开始
- 需要练多项目编排：看 `suites/`

## 当前新增示例

- `scenarios/basic/wait_for_popup.example.json`
- `scenarios/basic/wait_for_network.example.json`
- `scenarios/basic/extract_table.example.json`
- `scenarios/basic/write_csv.example.json`
- `scenarios/basic/ocr_data_url.example.json`
- `scenarios/basic/llm_chat_local_gateway.example.json`
- `scenarios/basic/ocr_selector_capture.example.json`
- `scenarios/basic/ocr_fill_input.example.json`
- `scenarios/basic/llm_extract_json_remote.example.json`
