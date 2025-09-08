"""
事件循环安全的 MCP 客户端管理器
解决 FastAPI 与 MCP 协议的事件循环冲突问题
"""

import asyncio
import logging
import threading
import weakref
from typing import Any, Dict, Optional, List
import concurrent.futures
from dataclasses import dataclass

from .client import MCPClient
from .protocol import MCPResult
from .integration import SimaCodeToolRegistry
from ..tools.base import ToolInput

logger = logging.getLogger(__name__)


@dataclass
class LoopSafeMCPResult:
    """事件循环安全的 MCP 结果"""
    success: bool
    content: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def to_mcp_result(self) -> MCPResult:
        """转换为标准 MCPResult"""
        return MCPResult(
            success=self.success,
            content=self.content,
            error=self.error,
            metadata=self.metadata or {}
        )


class EventLoopSafeMCPManager:
    """
    事件循环安全的 MCP 管理器
    
    这个管理器解决了以下问题：
    1. FastAPI 在主事件循环中运行
    2. MCP 客户端需要在一致的事件循环中运行
    3. Future 对象不能跨事件循环使用
    """
    
    def __init__(self):
        self._mcp_loop: Optional[asyncio.AbstractEventLoop] = None
        self._mcp_thread: Optional[threading.Thread] = None
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._clients: Dict[str, MCPClient] = {}
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()
        
    def start(self):
        """启动专用的 MCP 事件循环"""
        with self._lock:
            if self._mcp_thread is None or not self._mcp_thread.is_alive():
                logger.info("🚀 启动事件循环安全的 MCP 管理器")
                self._shutdown_event.clear()
                self._mcp_thread = threading.Thread(
                    target=self._run_mcp_loop, 
                    name="MCPEventLoop",
                    daemon=True
                )
                self._mcp_thread.start()
                
                # 等待事件循环启动（最多等待5秒）
                wait_count = 0
                while self._mcp_loop is None and wait_count < 500:
                    threading.Event().wait(0.01)
                    wait_count += 1
                
                if self._mcp_loop is None:
                    raise RuntimeError("MCP 事件循环启动超时")
                    
                logger.info(f"✅ MCP 事件循环已启动: {self._mcp_loop} (线程: {self._mcp_thread.name})")
    
    def _run_mcp_loop(self):
        """运行专用的 MCP 事件循环"""
        asyncio.set_event_loop(asyncio.new_event_loop())
        self._mcp_loop = asyncio.get_event_loop()
        
        logger.info(f"🔄 MCP 事件循环线程启动: {threading.current_thread().name}")
        
        try:
            self._mcp_loop.run_until_complete(self._mcp_loop_main())
        except Exception as e:
            logger.error(f"❌ MCP 事件循环异常: {e}")
        finally:
            logger.info("🏁 MCP 事件循环结束")
    
    async def _mcp_loop_main(self):
        """MCP 事件循环主函数"""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
    
    async def call_tool_safe(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> LoopSafeMCPResult:
        """
        事件循环安全的工具调用
        
        这个方法可以从任何事件循环中安全调用
        """
        if self._mcp_loop is None:
            self.start()
        
        # 在专用的 MCP 事件循环中执行调用
        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_in_mcp_loop(tool_name, arguments),
            self._mcp_loop
        )
        
        try:
            # 等待结果，设置合理的超时
            result = future.result(timeout=60.0)
            return result
        except concurrent.futures.TimeoutError:
            logger.error(f"❌ 工具调用超时: {tool_name}")
            return LoopSafeMCPResult(
                success=False,
                error=f"Tool call timeout: {tool_name}",
                metadata={"tool_name": tool_name, "error_type": "timeout"}
            )
        except Exception as e:
            logger.error(f"❌ 工具调用异常: {e}")
            return LoopSafeMCPResult(
                success=False,
                error=str(e),
                metadata={"tool_name": tool_name, "error_type": type(e).__name__}
            )
    
    async def _call_tool_in_mcp_loop(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> LoopSafeMCPResult:
        """在 MCP 事件循环中执行工具调用"""
        try:
            current_loop = asyncio.get_running_loop()
            logger.debug(f"🔧 在 MCP 循环中调用工具: {tool_name}, 循环: {current_loop}")
            
            # 获取工具注册表
            registry = SimaCodeToolRegistry()
            
            # 确保 MCP 已初始化
            await registry._ensure_mcp_initialized()
            
            # 获取工具
            tool = registry.get_tool(tool_name)
            if not tool:
                return LoopSafeMCPResult(
                    success=False,
                    error=f"Tool not found: {tool_name}",
                    metadata={"tool_name": tool_name, "error_type": "not_found"}
                )
            
            # 创建正确的 ToolInput 对象
            tool_input = ToolInput(**arguments)
            
            # 调用工具并收集结果
            results = []
            async for result in tool.execute(tool_input):
                results.append(result)
            
            # 处理结果
            if results:
                # 取最后一个结果作为主结果
                last_result = results[-1]
                if last_result.type == "error":
                    return LoopSafeMCPResult(
                        success=False,
                        error=last_result.content,
                        metadata={"tool_name": tool_name, "error_type": "execution_error"}
                    )
                else:
                    # 合并所有结果内容
                    all_content = []
                    for r in results:
                        if hasattr(r, 'content') and r.content:
                            all_content.append(str(r.content))
                    
                    combined_content = "\n".join(all_content) if all_content else last_result.content
                    
                    return LoopSafeMCPResult(
                        success=True,
                        content=combined_content,
                        metadata={"tool_name": tool_name, "results_count": len(results)}
                    )
            else:
                return LoopSafeMCPResult(
                    success=False,
                    error="No results returned from tool execution",
                    metadata={"tool_name": tool_name, "error_type": "no_results"}
                )
            
        except Exception as e:
            logger.error(f"❌ MCP 循环中工具调用失败: {e}")
            return LoopSafeMCPResult(
                success=False,
                error=str(e),
                metadata={"tool_name": tool_name, "error_type": type(e).__name__}
            )
    
    def shutdown(self):
        """关闭 MCP 管理器"""
        with self._lock:
            logger.info("🛑 关闭事件循环安全的 MCP 管理器")
            self._shutdown_event.set()
            
            if self._mcp_loop and not self._mcp_loop.is_closed():
                # 安全关闭事件循环
                asyncio.run_coroutine_threadsafe(
                    self._shutdown_mcp_loop(), self._mcp_loop
                )
            
            if self._mcp_thread and self._mcp_thread.is_alive():
                self._mcp_thread.join(timeout=5.0)
                
    async def _shutdown_mcp_loop(self):
        """关闭 MCP 事件循环"""
        try:
            # 关闭所有客户端
            for client in self._clients.values():
                if hasattr(client, 'shutdown'):
                    await client.shutdown()
                    
            # 停止事件循环
            loop = asyncio.get_running_loop()
            loop.stop()
        except Exception as e:
            logger.error(f"❌ 关闭 MCP 循环时出错: {e}")


# 全局单例实例
_mcp_manager: Optional[EventLoopSafeMCPManager] = None
_manager_lock = threading.Lock()


def get_mcp_manager() -> EventLoopSafeMCPManager:
    """获取全局 MCP 管理器实例"""
    global _mcp_manager
    
    with _manager_lock:
        if _mcp_manager is None:
            _mcp_manager = EventLoopSafeMCPManager()
            _mcp_manager.start()
    
    return _mcp_manager


async def safe_call_mcp_tool(
    tool_name: str, 
    arguments: Dict[str, Any]
) -> MCPResult:
    """
    事件循环安全的 MCP 工具调用入口
    
    这是主要的公共接口，可以从任何事件循环中安全调用
    """
    manager = get_mcp_manager()
    
    # 添加调试日志
    current_loop = None
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = "No event loop"
    
    logger.debug(f"🌐 安全调用 MCP 工具: {tool_name}, 当前循环: {current_loop}")
    
    result = await manager.call_tool_safe(tool_name, arguments)
    return result.to_mcp_result()