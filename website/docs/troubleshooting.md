# 故障排查

## MCP 与网络代理

症状：`simacode mcp init` WebSocket 连接失败，或提示需要 `python-socks`。

解决：

```bash
# 暂时关闭代理并初始化
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
poetry run simacode mcp init

# 如需代理，安装依赖并加入 no_proxy
pip install python-socks
export no_proxy="localhost,127.0.0.1,*.local"
```

## API 启动失败
- 端口占用：更换 `--port`。
- 依赖缺失：确保 `poetry install` 已完成（含 `uvicorn`, `fastapi`）。

## CLI 无法运行
- 检查 Python 版本（3.10+）。
- 执行 `poetry run simacode --help` 验证可用性。

