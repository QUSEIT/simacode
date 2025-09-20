# Repository Guidelines

## Project Structure & Module Organization
- Source code lives in `src/simacode` (CLI in `src/simacode/cli.py`, API in `src/simacode/api/`).
- Tests are in `tests/` following `test_*.py` or `*_test.py` patterns.
- Docs in `docs/`; scripts and utilities in `scripts/` and `tools/`.
- Config: project `.simacode/config.yaml` (created by `simacode init`); sample env in `.env.mcp.sample`.

## Build, Test, and Development Commands
- Install: `poetry install` (add `--with dev` for dev tools).
- CLI help: `poetry run simacode --help`.
- Run chat: `poetry run simacode chat --interactive` (add `--react` for ReAct mode).
- Run API (dev): `poetry run simacode serve --reload --debug`.
- Tests: `poetry run pytest -v` (coverage enabled via config).
- Lint/format: `poetry run black . && poetry run isort . && poetry run flake8 src/simacode`.
- Types: `poetry run mypy src/simacode`.

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, PEP 8/PEP 257.
- Formatting: Black (line length 88) + isort (profile "black").
- Linting: flake8; Typing: mypy (strict settings in `pyproject.toml`).
- Names: modules/packages `snake_case`, functions/vars `snake_case`, classes `CamelCase`.
- Public APIs must include type hints; prefer small, focused modules under `src/simacode/*`.

## Testing Guidelines
- Framework: pytest (+ pytest-asyncio). Default discovery uses `tests/` with `Test*` classes and `test_*` functions.
- Coverage: collected for `simacode` with term, HTML, and XML reports. Aim to cover new/changed code.
- Examples:
  - File: `tests/test_cli.py`
  - Run specific: `poetry run pytest tests/test_cli.py -q`

## Commit & Pull Request Guidelines
- Use Conventional Commits: `feat: ...`, `fix: ...`, `docs: ...`, `chore: ...`, `refactor: ...`, `test: ...`.
- Keep commits focused; include rationale when behavior changes.
- Before PR: ensure `poetry run black .`, `isort .`, `flake8`, `mypy`, and `pytest` all pass. Run `poetry run pre-commit run -a` if hooks are installed.
- PRs should include: clear description, linked issues, test evidence (logs or screenshots), and notes on configuration changes.

## Security & Configuration Tips
- Do not commit secrets. Prefer env vars (`SIMACODE_API_KEY`, `OPENAI_API_KEY`) and project config in `.simacode/config.yaml`.
- When working with MCP, consult `.env.mcp.sample` and `README.md` MCP sections; avoid proxy issues by setting `no_proxy` for localhost.

