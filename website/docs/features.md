# 功能

## :material-robot: ReAct 智能任务规划
- 从对话到执行，AI编排工具，自动完成目标。
- 结合上下文会话，持续改进与重试。

## :material-progress-clock: 异步任务
- 基于 async/await 的非阻塞执行，提升吞吐与响应速度。
- 支持并发调度（批量请求/工具调用），并可配置最大并发度与队列策略。
- 提供超时、取消、重试与退避等控制，确保稳定性。
- 兼容 CLI 与 API：CLI 流式输出，API 可异步返回长任务结果。

=== "示例：Python 并发请求 API"

    ```python
    import asyncio
    import httpx

    API_BASE = "http://localhost:8000/api/v1"

    async def run_chat(client: httpx.AsyncClient, message: str) -> dict:
        resp = await client.post(
            f"{API_BASE}/chat/",
            json={"message": message},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    async def main():
        prompts = [
            "写一个计算斐波那契的 Python 函数",
            "把下列列表去重并排序: [3,1,2,3,2]",
            "给我一个简单的 FastAPI 健康检查示例",
        ]
        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(*[run_chat(client, p) for p in prompts])
        for r in results:
            print(r)

    if __name__ == "__main__":
        asyncio.run(main())
    ```

=== "示例：Shell 并发(进程级)"

    ```bash
    # 依赖 GNU parallel 或 xargs 并发执行 curl 示例
    export API=http://localhost:8000/api/v1/chat/
    printf '%s\n' \
      '写一个快速排序的 Python 版本' \
      '使用 curl 做一个 POST 示例' \
      'JSON 与 YAML 的区别是什么' \
    | xargs -I{} -P 4 sh -c \
      'curl -s -X POST "$API" -H "Content-Type: application/json" -d "{\"message\": \"{}\"}"'
    ```

## :material-puzzle: MCP 工具集成
- 通过 `simacode mcp` 指令进行工具发现/执行。
- 支持 AI 自动调用与用户直连调用两种模式。

## :material-toolbox: 内嵌工具
- 内置常用工具（文件、命令执行、HTTP、MCP 适配器等），可即用可扩展。
- 统一工具接口与权限边界，防止越权访问与危险操作。
- 通过项目配置（如 `.simacode/config.yaml`）启用/禁用、配置凭据或注入自定义工具。
- 同时支持 AI 自动编排调用与命令行手动调用，便于组合与编排。

=== "示例：CLI 调用工具"

    ```bash
    # 查看可用工具
    poetry run simacode mcp list

    # 执行文件读取工具
    poetry run simacode mcp run file_tools:read_file --param file_path=README.md

    # 执行 HTTP GET 工具
    poetry run simacode mcp run http:get --param url=https://httpbin.org/get
    ```

=== "配置示例：启用/配置工具(.simacode/config.yaml)"

    ```yaml
    tools:
      enabled:
        - file_tools
        - shell
        - http
      http:
        timeout: 30s
        headers:
          User-Agent: SimaCode-Docs-Demo

    mcp:
      servers:
        - id: local_files
          command: python
          args: ["-m", "my_mcp.local_files"]
          env:
            ROOT: ./data
    ```

=== "示例：自定义工具（最小实现，按实际 API 调整）"

    ```python
    # my_project/tools/my_tools.py
    from collections import Counter
    import re
    from typing import Iterable

    def word_count(text: str, topk: int = 5) -> dict:
        """统计总词数与 Top-K 词频。
        参数:
          - text: 待统计文本
          - topk: 返回的高频词个数
        返回: {"total": int, "top": list[tuple[str, int]]}
        """
        words = re.findall(r"\w+", text.lower())
        cnt = Counter(words)
        return {"total": len(words), "top": cnt.most_common(topk)}

    # 伪代码：按你的项目实际注册 API 调整
    # from simacode.tools import register_tool
    # register_tool(name="text:word_count", func=word_count)
    ```

=== "示例：作为 MCP 服务器导出（与 tools/mcp_* 一致风格）"

    ```python
    # my_mcp/filesystem_stdio_server.py
    # 依赖：pip install mcp psutil  （按需）
    import asyncio
    from pathlib import Path
    from typing import Any, Dict, List, Optional
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp import types
    from mcp.server.stdio import stdio_server

    class FilesystemMCPServer:
        def __init__(self, root: str = "/tmp"):
            self.root = Path(root).resolve()
            self.server = Server("filesystem-server")
            self._setup_tools()

        def _setup_tools(self):
            @self.server.list_tools()
            async def list_tools(params: Optional[types.PaginatedRequestParams] = None) -> List[types.Tool]:
                return [
                    types.Tool(
                        name="read_file",
                        description="Read contents of a file",
                        inputSchema={
                            "type": "object",
                            "properties": {"file_path": {"type": "string"}},
                            "required": ["file_path"],
                        },
                    )
                ]

            @self.server.call_tool()
            async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
                if name == "read_file":
                    p = self._validate(arguments["file_path"])
                    content = p.read_text(encoding="utf-8")
                    return [types.TextContent(type="text", text=content)]
                raise ValueError(f"Unknown tool: {name}")

        def _validate(self, path: str) -> Path:
            p = Path(path)
            if not p.is_absolute():
                p = self.root / p
            p = p.resolve()
            p.relative_to(self.root)  # 防越界
            return p

    async def main():
        server = FilesystemMCPServer("/tmp")
        async with stdio_server() as (r, w):
            init = InitializationOptions(
                server_name="filesystem-server",
                server_version="1.0.0",
                capabilities=types.ServerCapabilities(tools=types.ToolsCapability(), logging={}),
            )
            await server.server.run(r, w, init)

    if __name__ == "__main__":
        asyncio.run(main())
    ```

=== "示例：在配置中挂载 tools/mcp_* 服务器并调用"

    ```yaml
    # .simacode/config.yaml （节选）
    mcp:
      servers:
        - id: file_tools
          command: python
          args: ["tools/mcp_filesystem_server.py", "--root", "/tmp"]
        - id: sys_tools
          command: python
          args: ["tools/mcp_system_monitor_stdio_server.py"]
    ```

    ```bash
    # 初始化并查看工具
    poetry run simacode mcp init
    poetry run simacode mcp list | sed -n '1,120p'

    # 文件工具（来自 tools/mcp_filesystem_server.py）
    poetry run simacode mcp run file_tools:read_file --param file_path=/tmp/hello.txt

    # 系统监控工具（来自 tools/mcp_system_monitor_stdio_server.py）
    poetry run simacode mcp run sys_tools:get_cpu_usage --param interval=0.5
    ```

## :material-sync: 双模式运行
- CLI：适合个人开发与实验；提供交互和流式输出。
- API：FastAPI 服务，便于对外集成与自动化。

## :material-shield-check: 工程化与安全
- Black/isort/flake8/mypy 全家桶；pytest+覆盖率。
- 权限与会话管理，控制外部命令与文件系统访问范围。
