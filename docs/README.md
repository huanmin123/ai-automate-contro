# 文档中心

这个目录用于沉淀项目级知识，而不是只放零散说明。

不要一次性阅读全部文档。先按任务选择最小入口，再继续追对应专题：

- 使用、安装、打包和分发：读 [study/快速使用指南](./study/快速使用指南.md)、[study/分发包使用指南](./study/分发包使用指南.md)、[study/打包发布指南](./study/打包发布指南.md)。
- 创建或修改 plan/action：读 [../handbook/README.md](../handbook/README.md)，再读对应 action 文档。
- 理解架构和模块边界：读 [architecture/架构总览](./architecture/架构总览.md)。
- 修改 `AGENTS.md`、AI 协作规则、资源路径策略或验证矩阵：读 [develop/AI协作开发规范](./develop/AI协作开发规范.md)。
- 修改 AI 终端、上下文、图片附件或调试修复：读 [architecture/AI终端与交互式执行架构](./architecture/AI终端与交互式执行架构.md)、[architecture/AI终端提示词与上下文策略](./architecture/AI终端提示词与上下文策略.md)、[architecture/AI调试修复工作流](./architecture/AI调试修复工作流.md)。
- 修改功能能力或专项 AI 边界：读 [functions/核心功能设计](./functions/核心功能设计.md) 和 [functions/AI能力重构设计](./functions/AI能力重构设计.md)。
- 本地运行、自检和回归：读 [develop/运行说明](./develop/运行说明.md) 和 [develop/测试与验证说明](./develop/测试与验证说明.md)。
- 计划、问题和重构记录：按需进入 [plans](./plans/README.md)、[bug](./bug/README.md)、[refactors](./refactors/README.md)。

教学入口只有 `handbook/`，这里不承担组件教学职责。

## 目录索引

- [architecture](./architecture/README.md): 稳定架构、模块边界、开发与修复原则
- [study](./study/快速使用指南.md): 对外使用、安装、自检、分发包使用、AI 终端、打包发布和上线前检查
- [functions](./functions/README.md): 功能能力、执行模型、配置契约
- [plans](./plans/README.md): 迭代计划、排期、阶段性目标
- [develop](./develop/README.md): 本地开发、AI 协作规范、运行、验证方式
- [bug](./bug/README.md): 问题记录与错题本
- [refactors](./refactors/README.md): 重构记录与架构演进

## 维护规则

- 新增动作组件时，同时更新 `handbook/` 和 `docs/functions/`。
- 修改执行模型时，同时更新 `architecture/架构总览.md`。
- 修改 AI 终端、交互式执行器或专项 AI 边界时，同时更新 `architecture/AI终端与交互式执行架构.md` 和 `functions/AI能力重构设计.md`。
- 修改 AI 调试修复流程时，同时更新 `architecture/AI调试修复工作流.md`。
- 修改根目录 `AGENTS.md`、AI 协作规则、资源路径策略或验证矩阵时，同时更新 `develop/AI协作开发规范.md`。
- 进入新一轮迭代前，在 `plans/` 新建计划文档。
- 遇到线上或调试问题时，在 `bug/` 记录复现、原因和修复。
