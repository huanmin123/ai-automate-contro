# 计划-0014-Excel 文件与表格处理落地

## 背景

当前 plan 的通用文件 IO 支持 JSON、文本、CSV 和 storage state，不支持直接读取或写入 Excel。实际企业自动化场景中，人员名单、财务流水、排班、客户清单和报表模板常以 `.xlsx` 形式交付。

需要在不破坏现有 JSON plan 风格的前提下补齐 Excel 能力，并保持语法简单。

## 目标

- 增加 `read.type=excel`，把 `.xlsx` / `.xlsm` 工作表读取为变量。
- 增加 `write.type=excel`，把行数组、矩阵或模板单元格写到 `output/excel/`。
- 落地 `table` common action，用于行数组的筛选、选列、排序、去重、分组、连接和派生列等常见处理。
- 让 Excel、CSV、JSON 的表格数据在 plan 内统一为行数组，便于和浏览器、桌面、SQL、AI action 组合。
- 更新 handbook、功能文档和回归示例。

## 范围

第一阶段：

- 默认依赖增加 `openpyxl>=3.1,<4.0`。
- `read.type=excel` 支持 `sheet`、`range`、`header_row`、`headers`、`mode`、`skip_blank_rows`、`formula_mode`、`save_meta_as`。
- `write.type=excel` 支持新建工作簿、模板工作簿、替换 sheet、追加行、单元格填充、多工作表、冻结表头和自动筛选。
- 新增 `output/excel/` 输出分区。
- 新增 `test-plans/basic/write-excel/` 和 `test-plans/data-driven/load-excel/`。

第二阶段：

- 新增 `table` action，支持 `filter`、`select`、`sort`、`dedupe`、`group`、`join`、`add_column`。
- 新增 `test-plans/data-driven/table-transform/`。
- 在 AI plan 生成规则中优先使用 `read excel -> table -> write excel/csv/json` 的组合。
- 新增 `python .\cplan.py self-check data-components`，统一覆盖 Excel/table 正向和负向回归。

暂不覆盖：

- `.xls`、`.xlsb`。
- 宏执行、VBA 编辑、外部链接刷新。
- Excel 公式计算引擎。
- 透视表、图表、复杂样式编辑。

## 实施步骤

1. 更新依赖和 IO 输出分区。
2. 在 `files.py` 实现 Excel 读取、写入、模板复制和 JSON 安全值转换。
3. 在 `basic.py` 接入 `read/write type=excel`。
4. 更新校验规则，覆盖 `excel` 类型、输出路径、模板输入路径、字段枚举和 `value/cells/sheets` 至少一项规则。
5. 更新 handbook 中 `read`、`write` 和 common action 索引。
6. 新增 Excel 回归 plan 和资源工作簿。
7. 落地 `table` action 的纯 Python 行数组处理。
8. 新增 table 回归 plan，覆盖行数组的筛选、排序、去重、选列、连接、派生列、分组汇总和多工作表写入。
9. 新增 data-components 自检，覆盖静态示例、模板样式保留和负向校验。
10. 更新测试与验证说明。

## 风险

- Excel 表头重复会导致字典 key 冲突；第一版应直接报错，避免静默覆盖数据。
- 公式缓存值依赖文件是否被 Excel/WPS 保存过；文档必须说明 `formula_mode=cached` 不负责重新计算公式。
- 大文件读取可能占用较多内存；需要 `max_rows` 兜底，后续再设计流式读取。
- 模板写入要避免覆盖非目标 sheet 和样式；实现时优先复制模板到输出路径，再在输出副本上修改。
- `.xls` 用户需求可能很快出现；第一版先明确不支持，后续用单独计划评估格式转换或额外依赖。

## 验收标准

- `read.type=excel` 能读取中文表头、日期、数字、空白行和指定 sheet/range。
- `write.type=excel` 能创建新工作簿，并能从模板生成输出工作簿。
- `write.type=excel` 能在一个 workbook 内写多个 sheet，并保留模板 overlay 未覆盖区域和基础样式。
- `write.type=excel` 的输出固定落在 `output/excel/`。
- Excel 读出的行数组可以直接接 `write.type=json`、`write.type=csv` 和后续 `table` action。
- `python .\cplan.py self-check handbook` 通过。
- `python .\cplan.py self-check data-components` 通过。
- Excel 示例 plan validate/run 通过。

## 文档同步

- [Excel 文件与表格处理 Action 设计](../functions/Excel文件与表格处理Action设计.md)
- `handbook/actions/common/io/read.md`
- `handbook/actions/common/io/write.md`
- `handbook/actions/common/README.md`
- `handbook/actions/common/data/table.md`
- `docs/develop/测试与验证说明.md`
- `test-plans/basic/write-excel/docs/README.md`
- `test-plans/data-driven/load-excel/docs/README.md`
- `test-plans/data-driven/table-transform/plan.json`
