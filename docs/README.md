# 文档中心

这个目录用于沉淀项目级知识，而不是只放零散说明。

如果你是第一次进入项目，建议按下面顺序阅读：

1. [文档架构示例](./文档架构示例.md)
2. [architecture/架构总览](./architecture/架构总览.md)
3. [functions/核心功能设计](./functions/核心功能设计.md)
4. [develop/运行说明](./develop/运行说明.md)
5. [plans/计划-0001-框架第二版建设.md](./plans/计划-0001-框架第二版建设.md)

教学入口只有 `handbook/`，这里不承担组件教学职责。

## 目录索引

- [architecture](./architecture/README.md): 稳定架构、模块边界、开发与修复原则
- [functions](./functions/README.md): 功能能力、执行模型、配置契约
- [plans](./plans/README.md): 迭代计划、排期、阶段性目标
- [develop](./develop/README.md): 本地开发、运行、验证方式
- [bug](./bug/README.md): 问题记录与错题本
- [refactors](./refactors/README.md): 重构记录与架构演进

## 维护规则

- 新增动作组件时，同时更新 `handbook/` 和 `docs/functions/`。
- 修改执行模型时，同时更新 `architecture/架构总览.md`。
- 进入新一轮迭代前，在 `plans/` 新建计划文档。
- 遇到线上或调试问题时，在 `bug/` 记录复现、原因和修复。
