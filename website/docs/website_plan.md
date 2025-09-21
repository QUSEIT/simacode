# 思码 (SimaCode) 官网建设方案

## 目标与受众
- 以开发者为核心，清晰传达价值主张：ReAct 工作流编排 + MCP 工具集成 + 双模式（CLI 与 API）。
- 降低上手门槛：一屏完成安装与最小可运行示例；提供可复制命令与 API 片段。

## 可参考网站
- LangChain、Microsoft AutoGen、CrewAI、Cursor、Continue、GitHub Copilot、OpenAI Assistants、LangGraph、AutoGPT。
- 可借鉴：首屏清晰 CTA、结构化示例、架构图与对比/可信背书。

## 信息架构（IA）
- 首页：一句话价值主张 + 主要 CTA（开始使用 / 查看示例）。
- 快速开始：安装与最小示例（CLI 与 API 各一段）。
- 功能：ReAct 工作流编排、多智能体/MCP、权限与会话管理、双模式运行。
- 示例：CLI 命令片段、API 路由示例、MCP 执行片段（均可复制）。
- 架构：核心层与接口层（CLI/API）分层图；模块说明（`src/simacode/*`）。
- 文档：配置、命令参考、MCP 故障排查（代理/WS）。
- 贡献：测试/提交规范、PR 要求、Roadmap。
- 下载/部署：PyPI/源码、（后续）Docker。

## 内容要点与示例
- 安装与环境（Poetry）：`poetry install`（开发：`poetry install --with dev`）。
- CLI：`poetry run simacode chat --react --interactive`；`poetry run simacode --help`。
- API：`poetry run simacode serve --reload --debug`（FastAPI+Uvicorn）。
- 测试/质量：`poetry run pytest -v`，`poetry run black . && isort . && flake8 src/simacode`，`poetry run mypy src/simacode`。
- MCP：指向 README 的用法与代理问题处理（`no_proxy`）。

## 技术选型与目录结构
- 首选：MkDocs + Material（轻量、上线快、与现有 docs 一致）。
  - 本地预览：`pip install mkdocs-material && mkdocs serve`。
- 站点结构建议（网站侧）：
  - `website/docs/index.md`（首页/价值主张）
  - `website/docs/quickstart.md`（快速开始）
  - `website/docs/features.md`（功能）
  - `website/docs/examples.md`（示例：CLI/API/MCP）
  - `website/docs/architecture.md`（架构与目录）
  - `website/docs/troubleshooting.md`（MCP/网络代理）
  - `website/docs/contributing.md`（贡献与规范）
  - `website/docs/roadmap.md`（路线图）

## 上线步骤（里程碑）
1) v0 草案：Quickstart/Features/Examples 三页 + 首页 CTA；
2) v0.1：补充 Architecture/Contributing/Troubleshooting；
3) v1：添加对比与案例、完善图片与架构图、启用搜索；
4) 部署：GitHub Pages 或 Vercel（CI：构建并发布）。

## 后续动作（To‑Do）
- 生成首页与 Quickstart 初稿；
- 从 README 抽取示例和命令片段；
- 绘制分层架构图（占位图先行）。
