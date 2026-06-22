# browser-site-http-command-combo

这个 plan 启动轻量 HTML 网站后，验证浏览器自动化、HTTP 客户端、本地命令、文件读写、循环和子计划之间的混合编排。

覆盖点：

- 浏览器填写账号、密码、token 并由页面 JS 调用本地 API。
- 页面显示原始 token，plan 断言原文可见。
- 从 HTML 表格提取结构化数据并写入 `output/json/`。
- 本地 command 从 `output/json/` 读取数据并计算汇总。
- foreach 基于 command 输出逐项调用 HTTP API，并把结果写入 `output/text/`。
- HTTP audit 请求携带 Authorization、session、password 等原文字段。
- 子计划读取主流程产物，继续调用 HTTP API，并做最终 if 断言。
