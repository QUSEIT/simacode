# 快速开始

## 安装

```bash
# 克隆并进入项目
git clone https://github.com/simacode/simacode.git
cd simacode

# 安装依赖（开发环境可加 --with dev）
poetry install
```

## 终端 AI 助手（CLI）

```bash
# 显示帮助
poetry run simacode --help

# 初始化项目目录（生成 .simacode/ 配置）
poetry run simacode init

# 交互对话（ReAct 智能模式）
poetry run simacode chat --react --interactive

# 单次对话
poetry run simacode chat "创建一个计算斐波那契数列的 Python 函数"
```

## API 服务（FastAPI + Uvicorn）

```bash
# 启动开发服务
poetry run simacode serve --host 0.0.0.0 --port 8000 --reload --debug

# 健康检查
curl http://localhost:8000/health
```

## 质量与校验

```bash
# 运行测试
poetry run pytest -v

# 覆盖率
poetry run pytest --cov=simacode --cov-report=html

# 代码风格与类型
poetry run black . && poetry run isort .
poetry run flake8 src/simacode
poetry run mypy src/simacode
```

