# 计划-0015-SQL复制分批Stream处理落地

## 背景

`sql.copy` 第一版已经能从一个 SQL 连接查询数据并写入另一个 SQL 连接，但默认 buffered 模式会先把本次查询结果放入内存，再批量写入目标库。对于更大的数据复制任务，需要在不引入新依赖的前提下支持分批读取、分批写入和 JSONL 分批落盘。

本阶段目标不是实现长期同步系统或无限 CDC，而是让单次自动化 plan 可以更稳地处理较大批量数据。

## 目标

- 为 `sql.copy` 增加 `stream: true`。
- 增加 `fetch_size` 控制源游标每批读取行数。
- 目标写入继续复用 `batch_size`。
- `rows_path` 在 stream 模式下只支持 `.jsonl`，逐批追加写入。
- stream 模式不支持 `include_rows`，避免把完整 rows 放入变量池。
- SQLite 默认自检覆盖 buffered copy 和 stream copy。

## 范围

- 运行时：
  - `sql.copy` 按 `stream` 分流。
  - `stream=true` 时使用 cursor `fetchmany` 分批读取。
  - 每批转换 `column_map` 后写入目标连接。
  - 失败时回滚目标连接，并尽力删除半截 JSONL 文件。
- 校验：
  - `stream` 必须是布尔值。
  - `fetch_size` 必须是正整数。
  - `stream=true` 不允许 `include_rows=true`。
  - `stream=true` 的 `rows_path` 只允许 `.jsonl`。
- 自检：
  - SQLite 文件到 SQLite 文件的 stream copy。
  - 验证 `fetch_size`、`batch_count`、JSONL 行数和目标表计数。

## 不做

- 不实现后台同步、定时同步或 CDC。
- 不自动建目标表或自动迁移 schema。
- 不绕过 `max_rows`；stream 仍然受 `max_rows` 保护。
- 不支持 stream 模式下写 `.json` 或 `.csv` rows_path。

## 设计方向

示例：

```json
{
  "action": "sql",
  "type": "copy",
  "connection": "crm_pg",
  "target_connection": "local_sqlite",
  "sql": "select id, status, total from orders order by id",
  "table": "orders_snapshot",
  "column_map": {
    "order_id": "id",
    "status": "status",
    "total": "total"
  },
  "stream": true,
  "fetch_size": 1000,
  "batch_size": 500,
  "rows_path": "orders-copy.jsonl",
  "result_path": "orders-copy.json",
  "output": {
    "as": "orders_copy"
  }
}
```

返回摘要增加：

- `stream: true`
- `fetch_size`
- `source_row_count`
- `input_rows`
- `affected_rows`
- `batch_count`

## 风险

- 目标数据库单批写入失败时，本次目标事务会回滚；如果数据库驱动不支持完整事务语义，仍以驱动行为为准。
- JSONL 文件在失败时会尽力删除，但如果系统文件锁定或权限异常，仍可能留下失败现场。
- `affected_rows=-1` 表示驱动无法可靠返回影响行数，此时 `expect_affected_rows` 可能不适合使用。

## 验收标准

- `python .\cplan.py self-check database-components` 中 `stream_copy_*` 证据全部通过。
- `python -m compileall -q src main.py cplan.py` 通过。
- `python .\cplan.py self-check release-matrix --only database_components,compileall,handbook,workspace_clean --fail-fast` 通过。
- handbook 和功能设计说明 `stream`、`fetch_size`、`.jsonl` 限制和 `include_rows` 限制。

## 文档同步

- [数据库连接 Action 设计](../functions/数据库连接Action设计.md)
- [测试与验证说明](../develop/测试与验证说明.md)
- `handbook/actions/common/io/sql.md`
- `test-plans/database/README.md`
