# http-command-component-combo

这个 plan 用本地 Node HTTP 服务验证 HTTP、command、read、write、foreach、retry 和 run_sub_plan 的组合行为。

覆盖点：

- command 创建本机临时 JSON 文件，read 通过绝对路径读取。
- foreach 对读取出的数组逐项发 HTTP 请求。
- retry 包裹首次失败、第二次成功的 HTTP 请求。
- command 通过 stdin 处理 HTTP JSON 结果。
- HTTP POST 把 command 处理结果回传给服务。
- write 追加输出文本，子计划 read 读取 output 产物。
- 子计划继续 command + HTTP，并用 if 做最终断言。
