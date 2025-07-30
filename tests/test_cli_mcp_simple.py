#!/usr/bin/env python3
"""
Simple CLI test for MCP tool execution
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from simacode.mcp.integration import SimaCodeToolRegistry, initialize_mcp_integration


async def test_cli_simple():
    """Simple CLI test"""
    print("Initializing MCP...")
    await initialize_mcp_integration()
    
    registry = SimaCodeToolRegistry()
    
    # Wait a bit for initialization
    import time
    time.sleep(2)
    
    # List tools to verify
    tools = await registry.list_tools()
    print(f"Available tools: {tools}")
    
    print("Executing tool...")
    
    results = []
    try:
        async for result in registry.execute_tool('system_monitor:get_cpu_usage', {}):
            results.append(result)
            print(f"Got result: {result.type} - {result.content[:100]}...")
    except Exception as e:
        print(f"Exception during execution: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\nTotal results: {len(results)}")
    
    # Simulate CLI display logic
    for i, result in enumerate(results, 1):
        result_type = result.type.value if hasattr(result.type, 'value') else result.type
        print(f"Result {i}: {result_type} - {result.content}")
        
        # Check for errors (this might be where the problem is)
        if result_type == 'error':
            print(f"Found error result: {result.content}")


if __name__ == "__main__":
    asyncio.run(test_cli_simple())