#!/usr/bin/env python3
"""
Test script for TICMaker Async MCP Server

This script tests the async task enhancement features of the TICMaker async server.
"""

import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TICMakerAsyncTester:
    """Test client for TICMaker Async MCP Server"""

    def __init__(self):
        self.server_process: Optional[subprocess.Popen] = None
        self.request_id_counter = 0

    def generate_request_id(self) -> str:
        """Generate unique request ID"""
        self.request_id_counter += 1
        return f"test_req_{self.request_id_counter}"

    async def start_server(self) -> bool:
        """Start the TICMaker async server"""
        try:
            server_path = Path(__file__).parent / "mcp_ticmaker_async_stdio_server.py"

            logger.info(f"Starting TICMaker async server: {server_path}")

            # Start server process
            self.server_process = subprocess.Popen(
                [sys.executable, str(server_path), "--debug"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0
            )

            # Give server time to start
            await asyncio.sleep(2)

            if self.server_process.poll() is None:
                logger.info("✅ TICMaker async server started successfully")
                return True
            else:
                stderr_output = self.server_process.stderr.read()
                logger.error(f"❌ Server failed to start: {stderr_output}")
                return False

        except Exception as e:
            logger.error(f"❌ Error starting server: {e}")
            return False

    async def stop_server(self):
        """Stop the server"""
        if self.server_process:
            try:
                self.server_process.terminate()
                await asyncio.sleep(1)
                if self.server_process.poll() is None:
                    self.server_process.kill()
                logger.info("🛑 Server stopped")
            except Exception as e:
                logger.error(f"Error stopping server: {e}")

    async def send_message(self, message: dict) -> Optional[dict]:
        """Send message to server and get response"""
        if not self.server_process:
            logger.error("Server not running")
            return None

        try:
            # Send message
            message_json = json.dumps(message) + "\n"
            self.server_process.stdin.write(message_json)
            self.server_process.stdin.flush()

            logger.debug(f"📤 Sent: {message_json.strip()}")

            # Read response
            response_line = self.server_process.stdout.readline()
            if response_line:
                response = json.loads(response_line.strip())
                logger.debug(f"📥 Received: {response}")
                return response
            else:
                logger.error("No response from server")
                return None

        except Exception as e:
            logger.error(f"Error communicating with server: {e}")
            return None

    async def test_initialization(self) -> bool:
        """Test server initialization"""
        logger.info("🔧 Testing server initialization...")

        init_request = {
            "jsonrpc": "2.0",
            "id": self.generate_request_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "ticmaker-async-test-client",
                    "version": "1.0.0"
                }
            }
        }

        response = await self.send_message(init_request)

        if response and response.get("result"):
            result = response["result"]
            server_info = result.get("serverInfo", {})
            capabilities = result.get("capabilities", {})

            logger.info(f"✅ Server initialized: {server_info.get('name', 'Unknown')}")
            logger.info(f"   Version: {server_info.get('version', 'Unknown')}")
            logger.info(f"   Async support: {capabilities.get('async_support', False)}")
            logger.info(f"   Progress reporting: {capabilities.get('progress_reporting', False)}")

            return True
        else:
            logger.error("❌ Initialization failed")
            return False

    async def test_tools_list(self) -> bool:
        """Test tools listing"""
        logger.info("🛠️ Testing tools list...")

        tools_request = {
            "jsonrpc": "2.0",
            "id": self.generate_request_id(),
            "method": "tools/list",
            "params": {}
        }

        response = await self.send_message(tools_request)

        if response and response.get("result"):
            tools = response["result"].get("tools", [])
            logger.info(f"✅ Found {len(tools)} async tools:")

            for tool in tools:
                logger.info(f"   - {tool.get('name', 'Unknown')}: {tool.get('description', 'No description')[:80]}...")

            # Check for async tools
            async_tools = [tool for tool in tools if "async" in tool.get("name", "").lower()]
            if async_tools:
                logger.info(f"✅ Found {len(async_tools)} async-enhanced tools")
                return True
            else:
                logger.warning("⚠️ No async tools found")
                return False
        else:
            logger.error("❌ Tools list failed")
            return False

    async def test_simple_task(self) -> bool:
        """Test simple task execution (should be sync)"""
        logger.info("📄 Testing simple task execution...")

        simple_request = {
            "jsonrpc": "2.0",
            "id": self.generate_request_id(),
            "method": "tools/call",
            "params": {
                "name": "create_interactive_course_async",
                "arguments": {
                    "user_input": "创建一个简单的数学课程介绍页面",
                    "course_title": "数学基础",
                    "content_type": "course"
                }
            }
        }

        start_time = time.time()
        response = await self.send_message(simple_request)
        execution_time = time.time() - start_time

        if response and response.get("result"):
            content = response["result"].get("content", [])
            if content and len(content) > 0:
                result_text = content[0].get("text", "")
                result_data = json.loads(result_text)

                logger.info(f"✅ Simple task completed in {execution_time:.2f}s")
                logger.info(f"   Success: {result_data.get('success', False)}")
                logger.info(f"   Task complexity: {result_data.get('task_complexity', 'Unknown')}")
                logger.info(f"   Was async: {result_data.get('was_async_execution', False)}")
                logger.info(f"   Progress updates: {result_data.get('progress_updates_count', 0)}")

                if result_data.get("metadata", {}).get("file_path"):
                    logger.info(f"   File created: {result_data['metadata']['file_path']}")

                return result_data.get("success", False)
            else:
                logger.error("❌ No content in response")
                return False
        else:
            logger.error("❌ Simple task failed")
            return False

    async def test_complex_task(self) -> bool:
        """Test complex task execution (should be async)"""
        logger.info("🚀 Testing complex task execution...")

        complex_request = {
            "jsonrpc": "2.0",
            "id": self.generate_request_id(),
            "method": "tools/call",
            "params": {
                "name": "create_interactive_course_async",
                "arguments": {
                    "user_input": "创建一个详细的、复杂的高级数据科学课程，包含多个交互式练习、AI增强的内容生成、完整的课程结构、实战项目案例、综合性评估系统，以及与当前技术趋势紧密结合的前沿知识点。课程需要涵盖机器学习、深度学习、数据可视化、统计分析等多个领域，并提供丰富的实践机会。",
                    "course_title": "高级数据科学与AI应用综合课程",
                    "content_type": "workshop",
                    "template_style": "modern",
                    "force_async": True,
                    "_session_context": {
                        "session_state": "active_task_execution",
                        "current_task": "complex_course_generation",
                        "user_input": "comprehensive data science course creation"
                    }
                }
            }
        }

        start_time = time.time()
        response = await self.send_message(complex_request)
        execution_time = time.time() - start_time

        if response and response.get("result"):
            content = response["result"].get("content", [])
            if content and len(content) > 0:
                result_text = content[0].get("text", "")
                result_data = json.loads(result_text)

                logger.info(f"✅ Complex task completed in {execution_time:.2f}s")
                logger.info(f"   Success: {result_data.get('success', False)}")
                logger.info(f"   Task complexity: {result_data.get('task_complexity', 'Unknown')}")
                logger.info(f"   Was async: {result_data.get('was_async_execution', False)}")
                logger.info(f"   Progress updates: {result_data.get('progress_updates_count', 0)}")
                logger.info(f"   Execution time: {result_data.get('execution_time', 0):.2f}s")

                if result_data.get("metadata", {}).get("file_path"):
                    logger.info(f"   File created: {result_data['metadata']['file_path']}")

                # Verify async execution for complex task
                expected_async = True  # Complex task should use async
                actual_async = result_data.get('was_async_execution', False)

                if expected_async and actual_async:
                    logger.info("✅ Async execution correctly detected for complex task")
                elif not expected_async and not actual_async:
                    logger.info("✅ Sync execution correctly used for simple task")
                else:
                    logger.warning(f"⚠️ Async detection mismatch: expected {expected_async}, got {actual_async}")

                return result_data.get("success", False)
            else:
                logger.error("❌ No content in response")
                return False
        else:
            logger.error("❌ Complex task failed")
            return False

    async def test_modification_task(self) -> bool:
        """Test content modification"""
        logger.info("🔧 Testing content modification...")

        # First, create a file to modify
        create_request = {
            "jsonrpc": "2.0",
            "id": self.generate_request_id(),
            "method": "tools/call",
            "params": {
                "name": "create_interactive_course_async",
                "arguments": {
                    "user_input": "创建基础测试页面",
                    "file_path": "test_modification_page.html"
                }
            }
        }

        create_response = await self.send_message(create_request)

        if not (create_response and create_response.get("result")):
            logger.error("❌ Failed to create file for modification test")
            return False

        # Now modify the file
        modify_request = {
            "jsonrpc": "2.0",
            "id": self.generate_request_id(),
            "method": "tools/call",
            "params": {
                "name": "modify_interactive_course_async",
                "arguments": {
                    "user_input": "添加异步任务增强特性的演示内容和新的交互元素",
                    "file_path": "test_modification_page.html",
                    "_session_context": {
                        "session_state": "content_modification",
                        "current_task": "async_enhancement_demo",
                        "user_input": "add async task features demo"
                    }
                }
            }
        }

        start_time = time.time()
        response = await self.send_message(modify_request)
        execution_time = time.time() - start_time

        if response and response.get("result"):
            content = response["result"].get("content", [])
            if content and len(content) > 0:
                result_text = content[0].get("text", "")
                result_data = json.loads(result_text)

                logger.info(f"✅ Modification task completed in {execution_time:.2f}s")
                logger.info(f"   Success: {result_data.get('success', False)}")
                logger.info(f"   Task complexity: {result_data.get('task_complexity', 'Unknown')}")
                logger.info(f"   Was async: {result_data.get('was_async_execution', False)}")

                return result_data.get("success", False)
            else:
                logger.error("❌ No content in modification response")
                return False
        else:
            logger.error("❌ Modification task failed")
            return False

    async def run_all_tests(self) -> bool:
        """Run all test cases"""
        logger.info("🧪 Starting TICMaker Async MCP Server tests...")

        results = []

        try:
            # Start server
            if not await self.start_server():
                logger.error("❌ Failed to start server")
                return False

            # Test initialization
            results.append(("Initialization", await self.test_initialization()))

            # Test tools list
            results.append(("Tools List", await self.test_tools_list()))

            # Test simple task
            results.append(("Simple Task", await self.test_simple_task()))

            # Test complex task
            results.append(("Complex Task", await self.test_complex_task()))

            # Test modification
            results.append(("Modification Task", await self.test_modification_task()))

        finally:
            # Stop server
            await self.stop_server()

        # Report results
        logger.info("\n📊 Test Results Summary:")
        logger.info("=" * 50)

        passed = 0
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"{test_name:20} | {status}")
            if result:
                passed += 1

        logger.info("=" * 50)
        logger.info(f"Total: {passed}/{len(results)} tests passed")

        all_passed = passed == len(results)
        if all_passed:
            logger.info("🎉 All tests passed! TICMaker Async MCP Server is working correctly.")
        else:
            logger.error(f"💥 {len(results) - passed} tests failed.")

        return all_passed


async def main():
    """Main test function"""
    tester = TICMakerAsyncTester()
    success = await tester.run_all_tests()

    if success:
        print("\n🎉 TICMaker Async MCP Server tests completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())