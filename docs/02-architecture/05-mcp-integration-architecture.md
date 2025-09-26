# SimaCode MCP Integration Architecture Analysis

## Overview

This document provides a comprehensive analysis of how the SimaCode framework integrates with Model Context Protocol (MCP) tool servers, including the connection establishment process, communication protocols, and tool invocation workflows.

## Architecture Overview

### Layered Architecture

SimaCode's MCP integration adopts a hierarchical layered architecture:

```
┌─────────────────────────────────────────────────┐
│          Application Layer                      │
│        (React Engine, CLI, API)                │
├─────────────────────────────────────────────────┤
│        MCPServerManager                         │
│    (Multi-server management)                    │
├─────────────────────────────────────────────────┤
│           MCPClient                             │
│   (Single server connection)                   │
├─────────────────────────────────────────────────┤
│         MCPProtocol                             │
│    (JSON-RPC 2.0 implementation)              │
├─────────────────────────────────────────────────┤
│        MCPTransport                             │
│     (Stdio/WebSocket transport)                │
└─────────────────────────────────────────────────┘
```

### Core Components

1. **MCPServerManager** (`src/simacode/mcp/server_manager.py:54`)
   - Top-level manager for multiple MCP servers
   - Handles configuration, health monitoring, and tool discovery

2. **MCPClient** (`src/simacode/mcp/client.py:37`)
   - Individual MCP server client
   - Manages connection lifecycle and session state

3. **MCPProtocol** (`src/simacode/mcp/protocol.py:204`)
   - Protocol layer implementing JSON-RPC 2.0
   - Handles message serialization and method calls

4. **MCPTransport** (`src/simacode/mcp/connection.py`)
   - Transport layer supporting stdio and WebSocket
   - Manages process lifecycle and communication channels

## Connection Establishment Workflow

### Phase 1: Configuration and Initialization

#### Step 1: Server Configuration Loading
```python
# MCPServerManager.load_config() - server_manager.py:116
await self.config_manager.load_config()
enabled_servers = self.config.get_enabled_servers()
```

The configuration system loads MCP server definitions from:
- `.simacode/config.yaml` (project-specific)
- `~/.simacode/config.yaml` (user-specific)
- `config/mcp_servers.yaml` (default servers)

#### Step 2: Client Instance Creation
```python
# MCPServerManager.add_server() - server_manager.py:148
client = MCPClient(config)
self.servers[name] = client
```

Each MCP server gets its own dedicated client instance with:
- Server-specific configuration
- Connection locks for thread safety
- Health monitoring integration

### Phase 2: Transport Layer Connection

#### Step 3: Transport Creation and Connection
```python
# MCPClient.connect() - client.py:71
transport = create_transport(self.server_config.type, transport_config)
self.connection = MCPConnection(transport, timeout=self.server_config.timeout)
await self.connection.connect()
```

**For stdio-based tool servers (like `tools/mcp_smtp_send_email.py`)**:

```python
# StdioTransport.connect() - connection.py:38
self.process = await asyncio.create_subprocess_exec(
    *self.command,
    *self.args,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env=process_env,
    limit=10 * 1024 * 1024  # 10MB limit for large responses
)
```

Key features:
- **Subprocess Management**: Automatic process lifecycle management
- **Large Buffer Support**: 10MB limit for handling large email attachments
- **Environment Handling**: Proper environment variable propagation
- **Error Handling**: Graceful process termination and cleanup

### Phase 3: Protocol Handshake

#### Step 4: MCP Session Initialization
```python
# MCPClient._initialize_session() - client.py:166
init_params = {
    "protocolVersion": "2024-11-05",
    "capabilities": {
        "tools": {"listChanged": False},
        "resources": {"subscribe": False, "listChanged": False}
    },
    "clientInfo": {
        "name": "simacode-mcp-client",
        "version": "1.0.0"
    }
}
result = await self.protocol.call_method(MCPMethods.INITIALIZE, init_params)
```

#### Step 5: Server Response Handling
In the MCP tool server (`tools/mcp_smtp_send_email.py`):

```python
# EmailSMTPMCPServer._process_mcp_message() - mcp_smtp_send_email.py:709
if message.method == MCPMethods.INITIALIZE:
    return MCPMessage(
        id=message.id,
        result={
            "serverInfo": self.server_info,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False}
            }
        }
    )
```

#### Step 6: Capability Discovery
```python
# MCPClient._discover_tools() - client.py:225
result = await self.protocol.call_method(MCPMethods.TOOLS_LIST)
tools_data = result.get("tools", [])

for tool_data in tools_data:
    tool = MCPTool(
        name=tool_data["name"],
        description=tool_data.get("description", ""),
        server_name=self.server_name,
        input_schema=tool_data.get("input_schema")
    )
    self.tools_cache[tool.name] = tool
```

## Tool Invocation Workflow

### Request Flow

#### Step 7: Tool Call Initiation
```python
# MCPServerManager.call_tool() - server_manager.py:387
if not client.is_connected():
    success = await self.connect_server(server_name)
    if not success:
        raise MCPConnectionError("Reconnection failed")

async with self.executor:  # Concurrency control
    result = await client.call_tool(tool_name, arguments)
```

#### Step 8: Protocol Message Creation
```python
# MCPProtocol.call_method() - protocol.py:240
request_id = self._generate_request_id()
request = MCPMessage(
    id=request_id,
    method=method,  # "tools/call"
    params=params   # {"name": "send_email", "arguments": {...}}
)
await self.send_message(request)
```

#### Step 9: Transport Layer Transmission
```python
# StdioTransport.send() - connection.py:109
async with self._write_lock:
    self.process.stdin.write(message + b'\n')
    await self.process.stdin.drain()
```

### Server-Side Processing

#### Step 10: Message Reception and Parsing
```python
# EmailSMTPMCPServer.run_stdio() - mcp_smtp_send_email.py:946
line = await asyncio.to_thread(sys.stdin.readline)
request_data = json.loads(line)
mcp_message = MCPMessage.from_dict(request_data)
response = await self._process_mcp_message(mcp_message)
```

#### Step 11: Tool Execution
```python
# EmailSMTPMCPServer._execute_tool() - mcp_smtp_send_email.py:794
if tool_name == "send_email":
    result = await self._send_email(arguments)

# EmailSMTPMCPServer._send_email() - mcp_smtp_send_email.py:872
return await self.email_client.send_email(
    to=to,
    subject=subject,
    body=body,
    content_type=content_type,
    # ... other parameters
)
```

### Response Flow

#### Step 12: Response Generation
```python
# EmailSMTPMCPServer._execute_tool() - mcp_smtp_send_email.py:825
response_content = {
    "success": result.success,
    "message": result.message if result.success else result.error,
    "execution_time": result.execution_time,
    "timestamp": datetime.now().isoformat()
}

return MCPMessage(
    id=message.id,
    result={
        "content": [{"type": "text", "text": json_text}],
        "isError": not result.success,
        "metadata": {
            "execution_time": execution_time,
            "tool": tool_name
        }
    }
)
```

## Communication Protocol Details

### JSON-RPC Message Format

**Client Request** (SimaCode → MCP Tool Server):
```json
{
    "jsonrpc": "2.0",
    "id": "req_1",
    "method": "tools/call",
    "params": {
        "name": "send_email",
        "arguments": {
            "to": "user@example.com",
            "subject": "Test Email",
            "body": "Hello World",
            "content_type": "text"
        }
    }
}
```

**Server Response** (MCP Tool Server → SimaCode):
```json
{
    "jsonrpc": "2.0",
    "id": "req_1",
    "result": {
        "content": [
            {
                "type": "text",
                "text": "{\"success\": true, \"message\": \"Email sent successfully to 1 recipient(s)\", \"execution_time\": 2.34}"
            }
        ],
        "isError": false,
        "metadata": {
            "execution_time": 0.05,
            "tool": "send_email",
            "response_size_bytes": 156
        }
    }
}
```

### Standard MCP Methods

```python
class MCPMethods:
    # Core protocol methods
    INITIALIZE = "initialize"
    PING = "ping"

    # Tool methods
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"

    # Resource methods
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"

    # Notification methods
    NOTIFICATIONS_INITIALIZED = "notifications/initialized"
```

## Advanced Features

### Asynchronous Tool Execution

SimaCode supports asynchronous tool execution with progress callbacks:

```python
# MCPProtocol.call_tool_async() - protocol.py:323
async def call_tool_async(
    self,
    tool_name: str,
    arguments: Dict[str, Any],
    progress_callback: Optional[Callable] = None,
    timeout: Optional[float] = None
) -> AsyncGenerator[MCPResult, None]:
```

This enables:
- **Long-running tasks**: Tools that take significant time to complete
- **Progress updates**: Real-time progress reporting
- **Streaming results**: Incremental result delivery

### Connection Management

#### Health Monitoring
```python
# MCPHealthMonitor - health.py
- Periodic health checks (30-second intervals)
- Automatic reconnection on failure
- Performance metrics collection
- Alert callbacks for health issues
```

#### Connection Pooling
```python
# MCPServerManager - server_manager.py:75
self.executor = asyncio.Semaphore(10)  # Limit concurrent operations
```

### Error Handling and Recovery

#### Connection Errors
- Automatic reconnection with exponential backoff
- Graceful degradation when servers are unavailable
- Connection state tracking and recovery

#### Protocol Errors
- JSON-RPC 2.0 compliant error codes
- Detailed error propagation and logging
- Timeout handling with configurable limits

## Configuration System

### Hierarchical Configuration

1. **Runtime configuration** (CLI arguments)
2. **Project configuration** (`.simacode/config.yaml`)
3. **User configuration** (`~/.simacode/config.yaml`)
4. **Default configuration** (`config/default.yaml`)

### MCP Server Configuration Example

```yaml
mcp:
  enabled: true
  health_check_interval: 30
  servers:
    smtp_email:
      type: stdio
      command: ["python", "tools/mcp_smtp_send_email.py"]
      args: ["--config", ".simacode/config.yaml"]
      enabled: true
      timeout: 300
      max_retries: 3
      environment:
        PYTHONPATH: "src"
```

## Performance Optimizations

### Caching Strategy
- **Tool Discovery Cache**: 5-minute TTL for tool lists
- **Result Cache**: 5-minute TTL for frequently accessed results
- **Connection Pooling**: Reuse established connections

### Concurrency Control
- **Semaphore Limiting**: Maximum 10 concurrent tool calls
- **Connection Locks**: Thread-safe connection management
- **Async Operations**: Non-blocking I/O throughout

## Security Considerations

### Process Isolation
- Each MCP server runs in its own subprocess
- Limited environment variable exposure
- Controlled stdin/stdout communication

### Input Validation
- JSON schema validation for tool arguments
- Rate limiting and size restrictions
- Safe process termination procedures

## Troubleshooting

### Common Issues

1. **Connection Failures**
   - Check process permissions and Python PATH
   - Verify configuration file syntax
   - Review server logs in stderr

2. **Performance Issues**
   - Monitor connection pool utilization
   - Check for stuck processes
   - Review timeout configurations

3. **Protocol Errors**
   - Validate JSON-RPC message format
   - Check method name compatibility
   - Verify parameter schemas

### Debugging Tools

```bash
# Enable debug logging
simacode chat --debug

# Check MCP server status
simacode mcp status

# Test tool directly
simacode mcp run smtp_email:send_email --param to=test@example.com
```

## Future Enhancements

### Planned Features
- WebSocket transport support for better performance
- Distributed MCP server support
- Enhanced monitoring and metrics
- Plugin system for custom transports

### Protocol Extensions
- Streaming tool results
- Binary data support
- Multi-step tool workflows
- Resource subscription model

## Conclusion

SimaCode's MCP integration provides a robust, scalable architecture for integrating external tools through the Model Context Protocol. The layered design ensures clean separation of concerns while providing enterprise-grade features like health monitoring, automatic recovery, and performance optimization.

The stdio-based transport mechanism, exemplified by the `mcp_smtp_send_email.py` server, demonstrates how external tools can be seamlessly integrated into the SimaCode workflow system while maintaining process isolation and robust error handling.