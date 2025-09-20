# 贡献指南（简要）

## 开发流程
1. 安装依赖：`poetry install --with dev`
2. 代码变更：遵循 PEP 8、类型注解与模块化设计。
3. 校验与测试：
   ```bash
   poetry run black . && poetry run isort .
   poetry run flake8 src/simacode
   poetry run mypy src/simacode
   poetry run pytest -v
   ```
4. 提交信息：Conventional Commits（如 `feat: ...`, `fix: ...`）。
5. 发起 PR：描述变更、附测试/截图、关联 Issue。

## 测试规范
- 框架：pytest（含 `pytest-asyncio`）。
- 目录：`tests/`，文件命名 `test_*.py` 或 `*_test.py`。
- 覆盖率：建议为新增/修改代码提供测试。

