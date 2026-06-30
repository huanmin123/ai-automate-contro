# 计划-0017 摘要

本轮目标是补齐数据库自动化中更常见的批量进出库和 MongoDB 索引能力：

- `mongo` 增加 `list_indexes`、`create_index`、`drop_index`。
- `sql.import stream=true` 支持 CSV/JSONL 分批导入。
- `sql.import` 增加 `required_columns`、`unique_columns` 和 `column_types`。
- `sql.export stream=true` 支持 CSV/JSONL 分批导出。
- SQLite 动态自检覆盖流式导入/导出和字段校验，MongoDB 示例覆盖索引动作。
- 文档、handbook、测试说明同步更新，默认安装仍不包含服务型数据库驱动。
