# 计划-0017-数据库导入导出与 Mongo 索引增强

## 背景

数据库 common action 已支持关系型数据库、MongoDB、Redis、本地 SQLite、SQL Server、schema 探测和基础文件导入导出。自动化链路里仍有两个高频缺口：大 CSV/JSONL 进出库不应一次性占用内存，MongoDB collection 常需要在写入或查询前后管理索引。

## 范围

- MongoDB: `mongo` 增加 `list_indexes`、`create_index`、`drop_index`。
- SQL import: 支持 `stream=true` 的 CSV/JSONL 分批导入。
- SQL import: 增加 `required_columns`、`unique_columns` 和 `column_types`。
- SQL export: 支持 `stream=true` 的 CSV/JSONL 分批导出。
- 示例与自检: SQLite 动态自检覆盖流式导入/导出和字段校验；MongoDB 示例 plan 覆盖索引动作。
- 文档: handbook、功能设计、测试说明和数据库示例 README 同步更新。

## 设计约束

- 默认安装不新增数据库驱动。
- JSON/Excel 导入导出继续使用普通模式；流式模式只承诺 CSV/JSONL。
- `column_types` 只用于自动建表类型覆盖，不做跨数据库类型抽象。
- MongoDB 索引参数使用 JSON 形态，尽量贴近 PyMongo，同时保持 plan 校验可读。

## 验证

- `python -m compileall -q src main.py cplan.py`
- `python .\cplan.py validate --file .\test-plans\database\mongodb-basic\plan.json`
- `python .\cplan.py self-check database-components`
- `python .\cplan.py self-check release-matrix --only database_components,compileall,handbook --fail-fast`
