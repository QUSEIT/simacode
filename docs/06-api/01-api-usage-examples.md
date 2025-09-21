# SimaCode API 使用示例

本文档提供SimaCode API服务模式的详细使用示例。

## 🚀 快速开始

### 1. 安装和启动

```bash
# 安装API依赖
pip install 'simacode[api]'

# 启动API服务
simacode serve --host 0.0.0.0 --port 8000

# 验证服务状态
curl http://localhost:8000/health
```

### 2. 基础API调用

```python
import httpx
import asyncio

# 同步调用示例
def basic_chat():
    response = httpx.post("http://localhost:8000/api/v1/chat/", json={
        "message": "Hello, SimaCode API!",
        "session_id": "demo-session"
    })
    
    if response.status_code == 200:
        data = response.json()
        print(f"Assistant: {data['content']}")
        print(f"Session ID: {data['session_id']}")
    else:
        print(f"Error: {response.status_code} - {response.text}")

basic_chat()
```

## 💬 聊天API示例

### 单次对话

```python
import httpx

def single_chat(message: str, session_id: str = None):
    """单次聊天对话"""
    payload = {
        "message": message,
        "session_id": session_id,
        "context": {},
        "stream": False
    }
    
    response = httpx.post("http://localhost:8000/api/v1/chat/", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        return result['content'], result['session_id']
    else:
        raise Exception(f"API Error: {response.status_code} - {response.text}")

# 使用示例
answer, session = single_chat("什么是Python?")
print(f"回答: {answer}")
print(f"会话ID: {session}")

# 继续对话
follow_up, _ = single_chat("能给个代码示例吗?", session_id=session)
print(f"后续回答: {follow_up}")
```

### 流式聊天

```python
import httpx

def streaming_chat(message: str, session_id: str = None):
    """流式聊天响应"""
    payload = {
        "message": message,
        "session_id": session_id,
        "stream": True
    }
    
    with httpx.stream("POST", "http://localhost:8000/api/v1/chat/stream", json=payload) as response:
        if response.status_code == 200:
            print("Assistant: ", end="", flush=True)
            for line in response.iter_lines():
                if line.startswith("data: "):
                    import json
                    data = json.loads(line[6:])  # Remove "data: " prefix
                    print(data['chunk'], end="", flush=True)
                    if data['finished']:
                        print()  # New line at end
                        return data['session_id']
        else:
            print(f"Error: {response.status_code}")

# 使用示例
session = streaming_chat("请解释机器学习的基本概念")
```

### WebSocket聊天

```python
import asyncio
import websockets
import json

async def websocket_chat():
    """WebSocket实时聊天"""
    uri = "ws://localhost:8000/api/v1/chat/ws"
    
    async with websockets.connect(uri) as websocket:
        print("WebSocket连接已建立")
        
        # 发送第一条消息
        await websocket.send(json.dumps({
            "message": "Hello via WebSocket!",
            "session_id": "ws-demo"
        }))
        
        # 接收响应
        response = await websocket.recv()
        data = json.loads(response)
        
        if data.get('type') == 'response':
            print(f"Assistant: {data['content']}")
            session_id = data['session_id']
            
            # 继续对话
            await websocket.send(json.dumps({
                "message": "Can you help me with coding?",
                "session_id": session_id
            }))
            
            response = await websocket.recv()
            data = json.loads(response)
            print(f"Assistant: {data['content']}")
        else:
            print(f"Error: {data.get('error')}")

# 运行WebSocket示例
asyncio.run(websocket_chat())
```

## 🤖 ReAct API示例

### 任务执行

```python
import httpx
import time

def execute_react_task(task: str, session_id: str = None):
    """执行ReAct任务"""
    payload = {
        "task": task,
        "session_id": session_id,
        "context": {},
        "execution_mode": "adaptive"
    }
    
    response = httpx.post("http://localhost:8000/api/v1/react/execute", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"任务结果: {result['result']}")
        print(f"执行步骤: {len(result['steps'])} 步")
        print(f"会话ID: {result['session_id']}")
        
        # 显示执行步骤
        for i, step in enumerate(result['steps'], 1):
            print(f"  步骤 {i}: {step.get('content', 'Unknown step')}")
            
        return result['session_id']
    else:
        print(f"任务执行失败: {response.status_code} - {response.text}")

# 使用示例
session = execute_react_task("创建一个Python文件，包含hello world程序")
```

### WebSocket ReAct

```python
import asyncio
import websockets
import json

async def websocket_react():
    """WebSocket ReAct任务执行"""
    uri = "ws://localhost:8000/api/v1/react/ws"
    
    async with websockets.connect(uri) as websocket:
        print("ReAct WebSocket连接已建立")
        
        # 发送任务
        task = {
            "task": "分析当前目录下的Python文件并生成报告",
            "session_id": "react-ws-demo",
            "execution_mode": "adaptive"
        }
        
        await websocket.send(json.dumps(task))
        
        # 接收实时更新
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                
                if data['type'] == 'task_started':
                    print(f"🚀 任务开始: {data['task']}")
                    
                elif data['type'] == 'step_update':
                    step = data['step']
                    print(f"⚙️  执行步骤: {step.get('content', 'Processing...')}")
                    
                elif data['type'] == 'task_completed':
                    print(f"✅ 任务完成: {data['result']}")
                    print(f"📊 总步骤数: {len(data['steps'])}")
                    break
                    
                elif data['type'] == 'error':
                    print(f"❌ 错误: {data['error']}")
                    break
                    
            except websockets.exceptions.ConnectionClosed:
                print("连接已关闭")
                break

# 运行ReAct WebSocket示例
asyncio.run(websocket_react())
```

## 📊 会话管理API

### 会话操作

```python
import httpx

def session_management_demo():
    """会话管理示例"""
    base_url = "http://localhost:8000/api/v1"
    
    # 1. 创建几个会话
    sessions = []
    for i in range(3):
        # 通过聊天创建会话
        response = httpx.post(f"{base_url}/chat/", json={
            "message": f"Hello from session {i+1}",
            "session_id": f"demo-session-{i+1}"
        })
        if response.status_code == 200:
            sessions.append(response.json()['session_id'])
    
    # 2. 列出所有会话
    response = httpx.get(f"{base_url}/sessions/")
    if response.status_code == 200:
        session_list = response.json()
        print(f"找到 {len(session_list)} 个会话:")
        for session in session_list:
            print(f"  - {session['session_id']} ({session['status']})")
    
    # 3. 获取特定会话信息
    if sessions:
        session_id = sessions[0]
        response = httpx.get(f"{base_url}/sessions/{session_id}")
        if response.status_code == 200:
            info = response.json()
            print(f"\n会话详情:")
            print(f"  ID: {info['session_id']}")
            print(f"  消息数: {info['message_count']}")
            print(f"  状态: {info['status']}")
    
    # 4. 删除会话
    if len(sessions) > 1:
        session_to_delete = sessions[-1]
        response = httpx.delete(f"{base_url}/sessions/{session_to_delete}")
        if response.status_code == 200:
            print(f"\n✅ 成功删除会话: {session_to_delete}")

session_management_demo()
```

## 🏥 健康检查和监控

### 健康状态检查

```python
import httpx
import json

def health_check_demo():
    """健康检查示例"""
    
    # 基础健康检查
    response = httpx.get("http://localhost:8000/health")
    if response.status_code == 200:
        health = response.json()
        print("🏥 服务健康状态:")
        print(f"  状态: {health['status']}")
        print(f"  版本: {health['version']}")
        print(f"  组件状态:")
        for component, status in health['components'].items():
            emoji = "✅" if status == "healthy" else "❌"
            print(f"    {emoji} {component}: {status}")
    
    # 就绪检查
    response = httpx.get("http://localhost:8000/health/ready")
    if response.status_code == 200:
        ready = response.json()
        print(f"\n🚦 服务就绪状态: {'✅ Ready' if ready['ready'] else '❌ Not Ready'}")
    
    # 存活检查
    response = httpx.get("http://localhost:8000/health/live")
    if response.status_code == 200:
        live = response.json()
        print(f"💓 服务存活状态: {'✅ Alive' if live['alive'] else '❌ Dead'}")

health_check_demo()
```

## 🔧 高级用法

### 批量操作

```python
import httpx
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def batch_chat_demo():
    """批量聊天示例"""
    
    messages = [
        "What is Python?",
        "Explain machine learning",
        "How to write a REST API?",
        "What is Docker?",
        "Explain database indexing"
    ]
    
    def send_chat(message):
        response = httpx.post("http://localhost:8000/api/v1/chat/", json={
            "message": message,
            "session_id": f"batch-{hash(message) % 1000}"
        })
        return response.json() if response.status_code == 200 else None
    
    # 并发执行
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(send_chat, messages))
    
    # 显示结果
    for i, result in enumerate(results):
        if result:
            print(f"Q{i+1}: {messages[i]}")
            print(f"A{i+1}: {result['content'][:100]}...")
            print(f"Session: {result['session_id']}\n")

asyncio.run(batch_chat_demo())
```

### 错误处理

```python
import httpx
from typing import Optional

class SimaCodeAPIClient:
    """SimaCode API客户端封装"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.Client()
    
    def chat(self, message: str, session_id: Optional[str] = None) -> dict:
        """安全的聊天调用"""
        try:
            response = self.client.post(f"{self.base_url}/api/v1/chat/", json={
                "message": message,
                "session_id": session_id
            }, timeout=30.0)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 500:
                error_data = response.json()
                raise Exception(f"Server Error: {error_data.get('detail', 'Unknown error')}")
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except httpx.TimeoutException:
            raise Exception("Request timeout - server may be overloaded")
        except httpx.ConnectError:
            raise Exception("Cannot connect to SimaCode API server")
        except httpx.RequestError as e:
            raise Exception(f"Request error: {str(e)}")
    
    def health_check(self) -> bool:
        """检查服务健康状态"""
        try:
            response = self.client.get(f"{self.base_url}/health", timeout=5.0)
            return response.status_code == 200 and response.json().get('status') == 'healthy'
        except:
            return False
    
    def close(self):
        """关闭客户端"""
        self.client.close()

# 使用示例
client = SimaCodeAPIClient()

try:
    if client.health_check():
        print("✅ 服务健康")
        result = client.chat("Hello API!")
        print(f"Response: {result['content']}")
    else:
        print("❌ 服务不健康")
except Exception as e:
    print(f"Error: {e}")
finally:
    client.close()
```

## 🐳 Docker部署示例

### Dockerfile

```dockerfile
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY . .

# 安装依赖
RUN pip install --no-cache-dir 'simacode[api]'

# 创建非root用户
RUN useradd --create-home --shell /bin/bash simacode
USER simacode

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["simacode", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  simacode-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SIMACODE_API_KEY=${SIMACODE_API_KEY}
      - LOG_LEVEL=INFO
    volumes:
      - ./config:/app/config:ro
      - simacode_sessions:/app/.simacode/sessions
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

volumes:
  simacode_sessions:
```

## 📝 最佳实践

### 1. 性能优化

```python
# 使用连接池
import httpx

class OptimizedClient:
    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

# 使用异步客户端获得更好性能
async with httpx.AsyncClient() as client:
    tasks = [
        client.post("http://localhost:8000/api/v1/chat/", json={"message": f"Question {i}"})
        for i in range(10)
    ]
    responses = await asyncio.gather(*tasks)
```

### 2. 错误重试

```python
import time
import random

def retry_request(func, max_retries=3, backoff_factor=1.5):
    """带重试的请求函数"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            
            wait_time = backoff_factor ** attempt + random.uniform(0, 1)
            print(f"Attempt {attempt + 1} failed, retrying in {wait_time:.2f}s...")
            time.sleep(wait_time)

# 使用示例
def make_request():
    return httpx.post("http://localhost:8000/api/v1/chat/", json={
        "message": "Hello with retry logic"
    })

result = retry_request(make_request)
```

### 3. 认证和安全

```python
# 如果API需要认证（未来版本）
class AuthenticatedClient:
    def __init__(self, api_key: str):
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}
        )
    
    def chat(self, message: str):
        return self.client.post("/api/v1/chat/", json={"message": message})

# 使用环境变量管理敏感信息
import os
api_key = os.getenv("SIMACODE_API_KEY")
if api_key:
    client = AuthenticatedClient(api_key)
```

---

**这些示例涵盖了SimaCode API的主要使用场景，从基础的聊天对话到高级的批量处理和部署配置。**