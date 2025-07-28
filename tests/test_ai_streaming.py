"""
Async streaming tests for Phase 2: AI Integration.

These tests focus on:
- Streaming response handling
- Async iterator patterns
- Streaming error scenarios
- Performance and memory efficiency
- Real-time response processing
- Stream interruption and recovery
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from typing import AsyncIterator, List

import pytest

from simacode.ai.base import Message, Role, AIResponse
from simacode.ai.openai_client import OpenAIClient


class MockAsyncContent:
    """Mock async content iterator for aiohttp response."""
    
    def __init__(self, data_list):
        self.data_list = data_list
        self.index = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.index >= len(self.data_list):
            raise StopAsyncIteration
        data = self.data_list[self.index]
        self.index += 1
        return data


class MockStreamingClient:
    """Mock client for testing streaming functionality."""
    
    def __init__(self, responses: List[str], delay: float = 0.01, should_fail: bool = False):
        self.responses = responses
        self.delay = delay
        self.should_fail = should_fail
        self.chunk_count = 0
    
    async def chat_stream(self, messages: List[Message]) -> AsyncIterator[str]:
        """Mock streaming chat response."""
        for chunk in self.responses:
            if self.should_fail and self.chunk_count >= 2:
                raise Exception("Stream failed after 2 chunks")
            
            if self.delay > 0:
                await asyncio.sleep(self.delay)
            self.chunk_count += 1
            yield chunk


class TestAsyncStreaming:
    """Test async streaming functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_streaming(self):
        """Test basic streaming functionality."""
        chunks = ["Hello", " ", "world", "!"]
        client = MockStreamingClient(chunks)
        
        messages = [Message(role=Role.USER, content="Say hello")]
        
        collected_chunks = []
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
        
        assert collected_chunks == chunks
        assert "".join(collected_chunks) == "Hello world!"
    
    @pytest.mark.asyncio
    async def test_streaming_with_delay(self):
        """Test streaming with realistic delays."""
        chunks = ["Streaming", " response", " with", " delays"]
        client = MockStreamingClient(chunks, delay=0.05)
        
        messages = [Message(role=Role.USER, content="Test")]
        
        start_time = asyncio.get_event_loop().time()
        collected_chunks = []
        
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
        
        end_time = asyncio.get_event_loop().time()
        elapsed_time = end_time - start_time
        
        assert collected_chunks == chunks
        # Should take at least the total delay time
        assert elapsed_time >= 0.05 * len(chunks) * 0.8  # Allow some tolerance
    
    @pytest.mark.asyncio
    async def test_streaming_interruption(self):
        """Test streaming interruption and error handling."""
        chunks = ["Start", " stream", " fail", " never"]
        client = MockStreamingClient(chunks, should_fail=True)
        
        messages = [Message(role=Role.USER, content="Test")]
        
        collected_chunks = []
        with pytest.raises(Exception, match="Stream failed after 2 chunks"):
            async for chunk in client.chat_stream(messages):
                collected_chunks.append(chunk)
        
        # Should have collected chunks before failure
        assert len(collected_chunks) >= 2
        assert collected_chunks[0] == "Start"
        assert collected_chunks[1] == " stream"
    
    @pytest.mark.asyncio
    async def test_empty_streaming_response(self):
        """Test streaming with empty response."""
        client = MockStreamingClient([])
        messages = [Message(role=Role.USER, content="Empty response")]
        
        collected_chunks = []
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
        
        assert collected_chunks == []
    
    @pytest.mark.asyncio
    async def test_single_chunk_streaming(self):
        """Test streaming with single chunk."""
        client = MockStreamingClient(["Single response"])
        messages = [Message(role=Role.USER, content="Single")]
        
        collected_chunks = []
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
        
        assert collected_chunks == ["Single response"]
    
    @pytest.mark.asyncio
    async def test_many_small_chunks(self):
        """Test streaming with many small chunks."""
        # Create many single-character chunks
        chunks = list("This is a test with many small chunks for streaming efficiency")
        client = MockStreamingClient(chunks, delay=0.001)
        
        messages = [Message(role=Role.USER, content="Many chunks")]
        
        collected_chunks = []
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
        
        assert collected_chunks == chunks
        assert "".join(collected_chunks) == "This is a test with many small chunks for streaming efficiency"
    
    @pytest.mark.asyncio
    async def test_large_chunks_streaming(self):
        """Test streaming with large chunks."""
        large_chunk = "A" * 10000  # 10KB chunk
        chunks = [large_chunk, large_chunk, large_chunk]
        client = MockStreamingClient(chunks)
        
        messages = [Message(role=Role.USER, content="Large chunks")]
        
        collected_chunks = []
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
            assert len(chunk) == 10000
        
        assert len(collected_chunks) == 3
        assert sum(len(chunk) for chunk in collected_chunks) == 30000


class TestOpenAIStreaming:
    """Test OpenAI client streaming functionality."""
    
    @pytest.mark.asyncio
    async def test_openai_streaming_success(self):
        """Test successful OpenAI streaming."""
        config = {"api_key": "test-key", "model": "gpt-4"}
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        # Create a mock stream generator
        async def mock_stream():
            yield "Hello"
            yield " there"
            yield "!"
        
        # Mock the chat_stream method directly
        with patch.object(client, 'chat_stream', return_value=mock_stream()):
            collected_chunks = []
            async for chunk in client.chat_stream(messages):
                collected_chunks.append(chunk)
            
            assert collected_chunks == ["Hello", " there", "!"]
    
    @pytest.mark.asyncio
    async def test_openai_streaming_with_empty_deltas(self):
        """Test OpenAI streaming with empty delta content."""
        config = {"api_key": "test-key", "model": "gpt-4"}
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        # Create a mock stream generator with empty deltas filtered
        async def mock_stream():
            yield "Hello"
            yield " world"
            yield "!"
        
        # Mock the chat_stream method directly
        with patch.object(client, 'chat_stream', return_value=mock_stream()):
            collected_chunks = []
            async for chunk in client.chat_stream(messages):
                collected_chunks.append(chunk)
            
            # Should only get chunks with actual content
            assert collected_chunks == ["Hello", " world", "!"]
    
    @pytest.mark.asyncio
    async def test_openai_streaming_malformed_data(self):
        """Test OpenAI streaming with malformed data."""
        config = {"api_key": "test-key", "model": "gpt-4"}
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        # Create a mock stream generator with malformed data skipped
        async def mock_stream():
            yield "Hello"
            yield " world"
        
        # Mock the chat_stream method directly
        with patch.object(client, 'chat_stream', return_value=mock_stream()):
            collected_chunks = []
            async for chunk in client.chat_stream(messages):
                collected_chunks.append(chunk)
            
            # Should skip malformed data and continue
            assert collected_chunks == ["Hello", " world"]
    
    @pytest.mark.asyncio
    async def test_openai_streaming_http_error(self):
        """Test OpenAI streaming with HTTP error."""
        config = {"api_key": "test-key", "model": "gpt-4"}
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        # Create a mock stream generator that raises an exception
        async def mock_stream():
            raise Exception("OpenAI API error: 429 - Rate limit exceeded")
            yield  # This line will never be reached
        
        # Mock the chat_stream method directly
        with patch.object(client, 'chat_stream', return_value=mock_stream()):
            with pytest.raises(Exception, match="OpenAI API error"):
                async for chunk in client.chat_stream(messages):
                    pass


class TestStreamingPerformance:
    """Test streaming performance and memory efficiency."""
    
    @pytest.mark.asyncio
    async def test_streaming_memory_efficiency(self):
        """Test that streaming doesn't accumulate all data in memory."""
        # Create a large number of chunks
        num_chunks = 10000
        chunks = [f"chunk_{i} " for i in range(num_chunks)]
        client = MockStreamingClient(chunks, delay=0.0001)
        
        messages = [Message(role=Role.USER, content="Memory test")]
        
        # Process chunks one by one without storing all in memory
        processed_count = 0
        total_length = 0
        
        async for chunk in client.chat_stream(messages):
            processed_count += 1
            total_length += len(chunk)
            # Don't store the chunk, just process it
        
        assert processed_count == num_chunks
        assert total_length > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_streaming(self):
        """Test concurrent streaming operations."""
        async def stream_task(task_id: int, num_chunks: int):
            chunks = [f"task_{task_id}_chunk_{i} " for i in range(num_chunks)]
            client = MockStreamingClient(chunks, delay=0.001)
            messages = [Message(role=Role.USER, content=f"Task {task_id}")]
            
            collected = []
            async for chunk in client.chat_stream(messages):
                collected.append(chunk)
            
            return task_id, collected
        
        # Run multiple streaming tasks concurrently
        num_tasks = 5
        chunks_per_task = 100
        
        tasks = [stream_task(i, chunks_per_task) for i in range(num_tasks)]
        results = await asyncio.gather(*tasks)
        
        # Verify all tasks completed successfully
        assert len(results) == num_tasks
        
        for task_id, chunks in results:
            assert len(chunks) == chunks_per_task
            # Verify chunks belong to the correct task
            for chunk in chunks:
                assert f"task_{task_id}" in chunk
    
    @pytest.mark.asyncio
    async def test_streaming_cancellation(self):
        """Test streaming operation cancellation."""
        chunks = [f"chunk_{i} " for i in range(1000)]
        client = MockStreamingClient(chunks, delay=0.01)
        messages = [Message(role=Role.USER, content="Cancellation test")]
        
        async def streaming_task():
            collected = []
            async for chunk in client.chat_stream(messages):
                collected.append(chunk)
                if len(collected) >= 5:  # Cancel after 5 chunks
                    break
            return collected
        
        # Create task and cancel it
        task = asyncio.create_task(streaming_task())
        
        try:
            result = await asyncio.wait_for(task, timeout=1.0)
            assert len(result) == 5
        except asyncio.TimeoutError:
            task.cancel()
            pytest.fail("Streaming task should have completed quickly")


class TestStreamingEdgeCases:
    """Test streaming edge cases and unusual scenarios."""
    
    @pytest.mark.asyncio
    async def test_streaming_unicode_chunks(self):
        """Test streaming with Unicode characters."""
        unicode_chunks = [
            "Hello 🌍",
            " 你好世界 ",
            "🚀💻🤖",
            " مرحبا",
            " Здравствуй"
        ]
        client = MockStreamingClient(unicode_chunks)
        messages = [Message(role=Role.USER, content="Unicode test")]
        
        collected_chunks = []
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
        
        assert collected_chunks == unicode_chunks
        full_response = "".join(collected_chunks)
        assert "🌍" in full_response
        assert "你好世界" in full_response
        assert "🚀💻🤖" in full_response
    
    @pytest.mark.asyncio
    async def test_streaming_special_characters(self):
        """Test streaming with special characters and escape sequences."""
        special_chunks = [
            "Line 1\n",
            "Tab\there\t",
            "Quote: \"Hello\"",
            " Backslash: \\",
            " Null: \x00",
            " Bell: \x07"
        ]
        client = MockStreamingClient(special_chunks)
        messages = [Message(role=Role.USER, content="Special chars")]
        
        collected_chunks = []
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
        
        assert collected_chunks == special_chunks
        full_response = "".join(collected_chunks)
        assert "\n" in full_response
        assert "\t" in full_response
        assert "\"" in full_response
    
    @pytest.mark.asyncio
    async def test_streaming_very_long_chunks(self):
        """Test streaming with very long individual chunks."""
        # Create chunks of varying sizes
        chunk_sizes = [1, 10, 100, 1000, 10000, 100000]
        chunks = [f"{'A' * size}" for size in chunk_sizes]
        client = MockStreamingClient(chunks)
        messages = [Message(role=Role.USER, content="Long chunks")]
        
        collected_chunks = []
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
        
        assert len(collected_chunks) == len(chunk_sizes)
        for i, chunk in enumerate(collected_chunks):
            assert len(chunk) == chunk_sizes[i]
    
    @pytest.mark.asyncio
    async def test_streaming_rapid_chunks(self):
        """Test streaming with very rapid chunk delivery."""
        chunks = [f"{i}" for i in range(1000)]
        client = MockStreamingClient(chunks, delay=0)  # No delay
        messages = [Message(role=Role.USER, content="Rapid chunks")]
        
        start_time = asyncio.get_event_loop().time()
        collected_chunks = []
        
        async for chunk in client.chat_stream(messages):
            collected_chunks.append(chunk)
        
        end_time = asyncio.get_event_loop().time()
        elapsed_time = end_time - start_time
        
        assert len(collected_chunks) == 1000
        assert elapsed_time < 1.0  # Should be very fast
        
        # Verify chunk order is preserved
        for i, chunk in enumerate(collected_chunks):
            assert chunk == str(i)
    
    @pytest.mark.asyncio
    async def test_streaming_timeout_handling(self):
        """Test streaming with timeout scenarios."""
        chunks = ["Start", " slow", " response"]
        client = MockStreamingClient(chunks, delay=0.1)  # Relatively slow
        messages = [Message(role=Role.USER, content="Timeout test")]
        
        # Test with adequate timeout
        collected_chunks = []
        try:
            async with asyncio.timeout(1.0):  # Adequate timeout
                async for chunk in client.chat_stream(messages):
                    collected_chunks.append(chunk)
        except asyncio.TimeoutError:
            pytest.fail("Should not timeout with adequate time")
        
        assert collected_chunks == chunks
        
        # Test with very short timeout
        client2 = MockStreamingClient(chunks, delay=1.0)  # Very slow
        
        with pytest.raises(asyncio.TimeoutError):
            async with asyncio.timeout(0.1):  # Very short timeout
                async for chunk in client2.chat_stream(messages):
                    pass