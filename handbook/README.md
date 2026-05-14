# AI 编排手册入口

这个目录是 AI 创建、运行和修复 JSON plan 时的权威手册。根目录只保留核心入口，避免一次性读取过多动作细节。

## 读取顺序

1. 先读 [计划结构](./计划结构.md)，确认 plan 包、配置、变量、输出和子计划边界。
2. 需要一个最小可运行样例时，读 [第一个计划示例](./第一个计划示例.md)。
3. 只有在要写某个 `action` 时，才进入下方对应子目录读取具体组件字段。

## 决策规则

- 创建或修改 plan 前，先确认目标 plan 包位置；未指定目录时使用当前运行根的第一个 `plan_roots`。
- 真实网页流程不能凭描述猜 selector；先用页面证据，再写浏览器步骤。
- 所有运行产物都写入当前 plan 包的 `output/`，输出动作的 `path` 不要以 `output/` 开头。
- 主 `plan.json` 是唯一入口；复用流程时只调用同包 `sub-plans/*-plan.json`。
- 需要人工登录、验证码、二次验证或权限确认时，使用 `open_browser.headed=true` 的自动化浏览器加 `manual_confirm` 交接；用户必须在同一个 Playwright 浏览器窗口里操作，不要让用户另开本机浏览器。
- 修改已有 plan 时优先做最小 JSON 路径修改；调试修复先进入调试工作区，再生成补丁。
- 不要把完整日志、大型产物或整本手册塞进上下文；先看目录，再按 action 精确读取。

## 按需读取地图

- `reference/config.md`: `config.json`、AI 服务、运行后检查等配置字段。
- `actions/browser/`: 浏览器会话、页面对象和关闭浏览器。
- `actions/navigation/`: 跳转、等待、断言、弹窗/下载/网络等待、文件选择器和网络拦截。
- `actions/interaction/`: 元素、键盘、鼠标和滚动。
- `actions/data/`: 变量、提取、浏览器存储和验证状态检测。
- `actions/ai/`: 受控专项 AI action。
- `actions/control-flow/`: 子计划、条件、循环和重试。
- `actions/io/`: 读取和写入文件。
- `actions/utility/`: 打印、人工确认、截图/HTML 捕获、浏览器 dialog、脚本、事件采集、coverage、trace 和睡眠。

## 写作约束

- 组件名就是 step 的 `action`。
- 参数结构一致的能力用同一 action 的 `type` 区分，例如 `navigate`、`element`、`wait`、`extract`、`assert`、`read`、`write`。
- 生命周期独立的能力保留独立 action，例如 `open_browser`、`run_sub_plan`、`foreach`、`retry`、`wait_for_popup`、`wait_for_download`。
- 专项 AI 统一使用 `ai` action，并通过 `type` 区分连通性、抽取、分类、转换和摘要。
- 变量使用 `{{变量名}}` 引用；业务变量放在 `plan.json.variables`，运行配置放在 `config.json`。
