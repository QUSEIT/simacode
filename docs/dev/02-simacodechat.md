# ReAct模式的对话
- 在ReAct模式的对话中，将AI 使用对应工具或者MCP的 来执行任务的 状态也作为一条 type 为 task_init 的回复提示用户。提示包括：
Task initialized: <任务目标> 将会通过调用 <工具列表> 来完成

# chat-stream接口
在simacode serve启动提供API服务的/api/v1/chat/stream接口中，再回复status信息时，返回的response都加一个message_type
