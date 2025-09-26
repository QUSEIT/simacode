# SimaCode MCP工具调用路线跟踪分析

## 📊 当前日志记录情况评估

### ✅ 优秀的地方

#### 1. **全面的日志覆盖**
- **连接层面**: 54个日志点覆盖connection.py的关键流程
- **客户端层面**: 22个日志点覆盖client.py的核心操作
- **管理器层面**: 20个日志点覆盖server_manager.py的服务器管理

#### 2. **关键流程日志完整**
```python
# 连接建立流程
logger.info(f"Connecting to MCP server '{self.server_name}' (attempt {self.connection_attempts})")
logger.info(f"Connected to MCP server '{self.server_name}'")
logger.info(f"MCP server '{self.server_name}' is ready")

# PyInstaller自动转换
logger.info("PyInstaller detected: auto-switching stdio to embedded mode")
logger.info(f"Converting stdio config to embedded: {script_path} -> {module_path}")

# 嵌入式传输
logger.info(f"PyInstaller environment detected - using embedded mode for {module_path}")
logger.info(f"Starting embedded MCP server: {self.module_path}")
logger.info(f"Detected custom protocol server: {custom_server_class.__name__}")
```

#### 3. **良好的错误跟踪**
```python
# 详细的错误信息
logger.error(f"Failed to connect to MCP server '{self.server_name}': {str(e)}")
logger.error(f"Failed to start embedded MCP server: {str(e)}")
logger.error(f"Error processing message in embedded server: {str(e)}")
```

#### 4. **工具调用追踪**
```python
# 工具发现和调用
logger.info(f"Discovered {len(self.tools_cache)} tools from '{self.server_name}'")
logger.info(f"Calling tool '{tool_name}' on server '{self.server_name}'")
logger.info(f"Starting async call for tool '{tool_name}' on server '{self.server_name}'")
```

### ⚠️ 需要改进的地方

#### 1. **缺少调用链ID**
- **问题**: 无法跟踪单个请求的完整生命周期
- **影响**: 在并发环境下难以区分不同请求的日志

#### 2. **关键节点日志缺失**
```python
# 在 create_transport 中缺少关键决策日志
def create_transport(transport_type: str, config: Dict[str, Any]):
    if transport_type == "stdio":
        # 🚨 缺少: 记录决策过程
        if hasattr(sys, '_MEIPASS') and config["command"] and config["command"][0] in ["python", "python3"]:
            # 有日志 ✅
            logger.info("PyInstaller detected: auto-switching stdio to embedded mode")
        # 🚨 缺少: else分支的日志
```

#### 3. **配置加载追踪不足**
- **缺少**: 配置文件读取过程的详细日志
- **缺少**: 环境变量解析的跟踪信息

#### 4. **性能指标缺失**
- **缺少**: 连接建立耗时
- **缺少**: 工具调用响应时间
- **缺少**: 模块加载时间

## 🎯 建议的改进方案

### 1. **引入调用链追踪**

#### 添加调用链ID生成器
```python
import uuid
from contextvars import ContextVar

# 全局调用链ID上下文
call_chain_id: ContextVar[str] = ContextVar('call_chain_id', default=None)

def generate_call_chain_id() -> str:
    """生成唯一的调用链ID"""
    return str(uuid.uuid4())[:8]

def with_call_chain(func):
    """装饰器：为函数调用添加调用链ID"""
    def wrapper(*args, **kwargs):
        if call_chain_id.get() is None:
            call_chain_id.set(generate_call_chain_id())
        return func(*args, **kwargs)
    return wrapper
```

#### 改进日志格式
```python
# 当前格式
logger.info(f"Starting embedded MCP server: {self.module_path}")

# 建议格式
logger.info(f"[{call_chain_id.get()}] Starting embedded MCP server: {self.module_path}")
```

### 2. **增加关键决策点日志**

#### 在connection.py中增加
```python
def create_transport(transport_type: str, config: Dict[str, Any]) -> MCPTransport:
    chain_id = call_chain_id.get() or generate_call_chain_id()
    logger.debug(f"[{chain_id}] Creating transport: type={transport_type}, command={config.get('command', 'N/A')}")

    if transport_type == "stdio":
        # 记录环境检测过程
        is_pyinstaller = hasattr(sys, '_MEIPASS')
        uses_python = config["command"] and config["command"][0] in ["python", "python3"]

        logger.debug(f"[{chain_id}] Environment check: PyInstaller={is_pyinstaller}, Python_cmd={uses_python}")

        if is_pyinstaller and uses_python:
            logger.info(f"[{chain_id}] PyInstaller detected: auto-switching stdio to embedded mode")
            return create_embedded_transport_from_stdio_config(config)
        else:
            logger.debug(f"[{chain_id}] Using standard stdio transport")
            return StdioTransport(...)
```

### 3. **添加性能监控**

#### 连接性能跟踪
```python
import time
from datetime import datetime

async def connect(self) -> bool:
    start_time = time.time()
    chain_id = call_chain_id.get()

    logger.info(f"[{chain_id}] Connecting to MCP server '{self.server_name}' (attempt {self.connection_attempts})")

    try:
        # ... 连接逻辑

        elapsed = time.time() - start_time
        logger.info(f"[{chain_id}] Connected to MCP server '{self.server_name}' in {elapsed:.3f}s")

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{chain_id}] Connection failed after {elapsed:.3f}s: {str(e)}")
```

### 4. **工具调用详细追踪**

#### 增强工具调用日志
```python
async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPResult:
    chain_id = call_chain_id.get() or generate_call_chain_id()
    call_chain_id.set(chain_id)

    start_time = time.time()
    logger.info(f"[{chain_id}] Calling tool '{tool_name}' on server '{self.server_name}'")
    logger.debug(f"[{chain_id}] Tool arguments: {arguments}")

    try:
        # ... 调用逻辑

        elapsed = time.time() - start_time
        logger.info(f"[{chain_id}] Tool '{tool_name}' completed in {elapsed:.3f}s")

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{chain_id}] Tool '{tool_name}' failed after {elapsed:.3f}s: {str(e)}")
```

### 5. **配置加载跟踪**

#### 在config.py中添加
```python
def load_mcp_config(config_path: Path) -> MCPConfig:
    logger.info(f"Loading MCP configuration from: {config_path}")

    try:
        with open(config_path, 'r') as f:
            raw_config = yaml.safe_load(f)

        logger.debug(f"Loaded {len(raw_config.get('servers', {}))} server configurations")

        # 记录启用的服务器
        enabled_servers = [name for name, cfg in raw_config.get('servers', {}).items()
                          if cfg.get('enabled', True)]
        logger.info(f"Enabled servers: {', '.join(enabled_servers)}")

        return MCPConfig(**raw_config)

    except Exception as e:
        logger.error(f"Failed to load MCP configuration from {config_path}: {str(e)}")
        raise
```

## 🔧 实现建议的优先级

### 高优先级 (立即实施)
1. ✅ **增加关键决策点日志** - 在create_transport中添加环境检测日志
2. ✅ **改进错误日志格式** - 包含更多上下文信息
3. ✅ **添加配置加载跟踪** - 记录配置文件读取过程

### 中优先级 (下个版本)
1. 🔄 **引入调用链追踪** - 需要架构调整
2. 🔄 **添加性能监控** - 需要性能基准测试

### 低优先级 (后续优化)
1. 📊 **集成APM工具** - 如OpenTelemetry
2. 📊 **可视化调用链** - Web界面展示

## 🎯 总结

**当前状态**: SimaCode已经具备了良好的日志基础，关键流程都有适当的日志记录。

**主要优势**:
- ✅ 全面的错误处理和记录
- ✅ 关键节点的信息日志
- ✅ PyInstaller自动转换的透明日志

**改进空间**:
- 🔧 缺少统一的调用链追踪
- 🔧 部分决策节点日志不够详细
- 🔧 性能指标监控有待完善

**建议**: 优先实施高优先级改进，可以显著提升调试体验和问题排查效率。