# 计划-0016 摘要

本轮目标是补齐数据库生态常见能力：

- `sql` 支持 SQL Server、`inspect` schema 探测和真实服务到 SQLite 的流式 copy 回归。
- `sql` 增加 `import`/`export`，支持 CSV/JSON/JSONL/Excel 与 SQL 表之间的导入导出。
- 新增 `mongo` common action，支持 MongoDB CRUD、aggregate 和 command。
- 新增 MongoDB 示例 plan。
- `database-components` 输出可选驱动安装状态和配置 inventory。
- 文档、handbook、测试说明同步更新，源码默认安装仍不包含服务型数据库驱动；发行包按支持能力打入数据库驱动。
