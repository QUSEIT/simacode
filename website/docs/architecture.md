# 架构

## 分层设计（双模式）
- 核心服务层：ReAct 引擎、工具系统、AI 客户端、配置与会话、安全权限。
- 接口层：
  - CLI：基于 Click（`src/simacode/cli.py`）。
  - API：基于 FastAPI（`src/simacode/api/`）。

## 目录概览

```
src/simacode/
├── cli.py              # CLI 入口
├── api/                # FastAPI 应用与路由
├── react/              # ReAct 引擎
├── tools/              # 工具系统（含 MCP 集成）
├── permissions/        # 权限与校验
├── session/            # 会话管理
├── services/           # 服务封装
└── config.py           # 配置加载与校验
```

## 设计要点
- 统一业务逻辑：CLI 与 API 共享核心能力，降低重复实现。
- 可扩展的工具注册表：支持发现、命名空间、热更新。
- 安全与隔离：受控的外部命令与文件访问，审计友好。

