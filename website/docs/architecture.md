# 架构

## 分层设计（双模式工作流架构）
- 核心工作流服务层：ReAct 工作流引擎、工作流工具系统、AI 编排客户端、配置与会话、安全权限。
- 工作流接口层：
  - CLI：基于 Click 的工作流命令行界面（`src/simacode/cli.py`）。
  - API：基于 FastAPI 的工作流编排服务（`src/simacode/api/`）。

## 目录概览

```
src/simacode/
├── cli.py              # CLI 入口
├── api/                # FastAPI 应用与路由
├── react/              # ReAct 工作流引擎
├── tools/              # 工作流工具系统（含 MCP 集成）
├── permissions/        # 权限与校验
├── session/            # 会话管理
├── services/           # 服务封装
└── config.py           # 配置加载与校验
```

## 设计要点
- 统一工作流逻辑：CLI 与 API 共享核心工作流编排能力，降低重复实现。
- 可扩展的工作流工具注册表：支持工具发现、命名空间、热更新。
- 安全与隔离：受控的外部命令与文件访问，工作流执行审计友好。

