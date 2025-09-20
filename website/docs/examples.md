# 示例

=== "CLI"

    ```bash
    poetry run simacode chat --react --interactive

    # 示例对话：
    # 你：请生成一个读取 CSV 并统计字段均值的脚本
    # 助手：将自动规划步骤与工具执行，并返回代码与运行建议
    ```

=== "MCP"

    ```bash
    # 初始化与查看工具
    poetry run simacode mcp init
    poetry run simacode mcp list

    # 执行工具
    poetry run simacode mcp run file_tools:read_file --param file_path=config.yaml
    ```

=== "API"

    ```bash
    # 启动服务
    poetry run simacode serve --host 0.0.0.0 --port 8000

    # 健康检查
    curl http://localhost:8000/health

    # Chat 接口（示例）
    curl -X POST http://localhost:8000/api/v1/chat/ \
      -H 'Content-Type: application/json' \
      -d '{"message": "创建一个 Python 斐波那契函数"}'
    ```
