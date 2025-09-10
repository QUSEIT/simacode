"""
MCP Message Content Extractor Tool for SimaCode.

This tool extracts pure tool execution content from MCP protocol messages,
removing the MCP message wrapper and returning only the actual tool data.
"""

import base64
import json
import logging
import os
import urllib.parse
import yaml
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, Union

from pydantic import BaseModel, Field, validator

from .base import Tool, ToolInput, ToolResult, ToolResultType
from ..permissions import PermissionManager

logger = logging.getLogger(__name__)


class MCPContentExtractionInput(ToolInput):
    """Input model for MCP Content Extraction tool."""
    
    mcp_message: Optional[Union[str, Dict[str, Any]]] = Field(
        None, 
        description="MCP message content to extract (JSON string or dict)"
    )
    content: Optional[Union[str, Dict[str, Any]]] = Field(
        None,
        description="Alternative parameter name for content to extract"
    )
    data: Optional[Union[str, Dict[str, Any]]] = Field(
        None,
        description="Alternative parameter name for data to extract"
    )
    extract_type: str = Field(
        "auto",
        description="Type of extraction: 'content' (default), 'text', 'json', 'auto'"
    )
    pretty_print: bool = Field(
        True,
        description="Whether to format JSON output with indentation"
    )
    validate_json: bool = Field(
        True,
        description="Whether to validate extracted content as JSON"
    )
    
    @validator('extract_type')
    def validate_extract_type(cls, v):
        allowed_types = ['content', 'text', 'json', 'auto']
        if v not in allowed_types:
            raise ValueError(f"extract_type must be one of {allowed_types}")
        return v
    
    @validator('mcp_message', 'content', 'data', pre=True)
    def validate_input_content(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            try:
                json.loads(v)
            except json.JSONDecodeError:
                # If it's not valid JSON, that's still okay - might be plain text
                pass
        elif not isinstance(v, (dict, list)):
            # Convert other types to string
            v = str(v)
        return v
    
    def get_content_to_extract(self) -> Union[str, Dict[str, Any]]:
        """Get the content to extract from any of the possible input fields."""
        # Priority order: mcp_message > content > data
        if self.mcp_message is not None:
            return self.mcp_message
        elif self.content is not None:
            return self.content
        elif self.data is not None:
            return self.data
        else:
            # Check if there are additional fields that might contain content
            additional_fields = {k: v for k, v in self.dict().items() 
                               if k not in ['execution_id', 'metadata', 'extract_type', 'pretty_print', 'validate_json', 'mcp_message', 'content', 'data']}
            
            if additional_fields:
                # Use the first additional field as content
                field_name, field_value = next(iter(additional_fields.items()))
                logger.info(f"Using additional field '{field_name}' as content source")
                return field_value
            
            raise ValueError("No content provided. Please provide one of 'mcp_message', 'content', 'data', or any other field containing the data to extract")


class ContentForwardURLInput(ToolInput):
    """Input model for Content Forward URL tool."""
    
    content: Union[str, Dict[str, Any]] = Field(
        ...,
        description="Content to encode and forward via URL (can be string or JSON object)"
    )
    forward_url_base: Optional[str] = Field(
        None,
        description="Base URL for content forwarding (overrides default configuration)"
    )
    encoding: str = Field(
        "base64",
        description="Encoding method for content (currently only supports 'base64')"
    )
    
    @validator('encoding')
    def validate_encoding(cls, v):
        allowed_encodings = ['base64']
        if v not in allowed_encodings:
            raise ValueError(f"encoding must be one of {allowed_encodings}")
        return v


class ContentForwardURL(Tool):
    """
    Tool for generating content forwarding URLs.
    
    This tool encodes content as base64 and generates a forwarding URL
    in the format: FORWARD_URL<base64_encoded_content>
    """
    
    def __init__(self, permission_manager: Optional[PermissionManager] = None, session_manager=None):
        """Initialize Content Forward URL tool."""
        super().__init__(
            name="content_forward_url",
            description="Generate forwarding URLs with base64-encoded content. Converts any content to a URL format for easy sharing and forwarding.",
            version="1.0.0",
            session_manager=session_manager
        )
        self.permission_manager = permission_manager or PermissionManager()
        
        # Load forward URL from config file, environment, or use default
        self.default_forward_url = self._load_forward_url()
    
    def _load_forward_url(self) -> str:
        """Load forward URL from .simacode/config.yaml or fallback to environment/default."""
        try:
            # First try to load from .simacode/config.yaml
            config_path = Path(".simacode/config.yaml")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    forward_url = config.get("forward_url")
                    if forward_url:
                        logger.info(f"Loaded forward URL from config: {forward_url}")
                        return forward_url
            
            # Fallback to environment variable
            env_url = os.getenv("FORWARD_URL")
            if env_url:
                logger.info("Using forward URL from environment variable")
                return env_url
            
            # Final fallback to default
            default_url = "http://localhost/smc_forward"
            logger.info(f"Using default forward URL: {default_url}")
            return default_url
            
        except Exception as e:
            logger.warning(f"Failed to load forward URL from config: {str(e)}, using default")
            return "http://localhost/smc_forward"
    
    def get_input_schema(self) -> Type[ToolInput]:
        """Return the input schema for this tool."""
        return ContentForwardURLInput
    
    async def validate_input(self, input_data: Dict[str, Any]) -> ContentForwardURLInput:
        """Validate tool input data."""
        try:
            return ContentForwardURLInput(**input_data)
        except Exception as e:
            logger.error(f"Input validation failed for content forward URL: {str(e)}")
            raise ValueError(f"Invalid input for content_forward_url: {str(e)}")
    
    async def check_permissions(self, input_data: ToolInput) -> bool:
        """Check permissions for content forward URL generation."""
        try:
            return await self.permission_manager.check_tool_permission(
                self.name,
                input_data.dict()
            )
        except Exception as e:
            logger.warning(f"Permission check failed for {self.name}: {str(e)}")
            return True  # Default to allow
    
    async def execute(self, input_data: ContentForwardURLInput) -> AsyncGenerator[ToolResult, None]:
        """
        Execute content forward URL generation.
        
        Args:
            input_data: Validated input data
            
        Yields:
            ToolResult: Generated forwarding URL (simplified output)
        """
        try:
            # Prepare content for encoding
            content = input_data.content
            if isinstance(content, (dict, list)):
                # Convert to JSON string
                content_str = json.dumps(content, ensure_ascii=False, separators=(',', ':'))
            else:
                content_str = str(content)
            
            # Encode content as base64
            try:
                content_bytes = content_str.encode('utf-8')
                base64_content = base64.b64encode(content_bytes).decode('ascii')
            except Exception as e:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"编码失败: {str(e)}",
                    tool_name=self.name,
                    execution_id=input_data.execution_id
                )
                return
            
            # Determine forward URL base
            forward_url_base = input_data.forward_url_base or self.default_forward_url
            
            # Generate the forwarding URL
            try:
                # URL encode the base64 content to handle any special characters
                encoded_param = urllib.parse.quote(base64_content, safe='')
                forwarding_url = f"{forward_url_base}{encoded_param}"
                
                # First show the original content before encoding
                yield ToolResult(
                    type=ToolResultType.SUCCESS,
                    content=f"原始内容: {content_str}",
                    tool_name=self.name,
                    execution_id=input_data.execution_id
                )
                
                # Then return the forwarding URL
                yield ToolResult(
                    type=ToolResultType.SUCCESS,
                    content=f"转发链接: {forwarding_url}",
                    tool_name=self.name,
                    execution_id=input_data.execution_id
                )
                
            except Exception as e:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"生成链接失败: {str(e)}",
                    tool_name=self.name,
                    execution_id=input_data.execution_id
                )
                return
            
        except Exception as e:
            logger.error(f"Content forward URL generation failed: {str(e)}")
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"转发链接生成失败: {str(e)}",
                tool_name=self.name,
                execution_id=input_data.execution_id
            )


class MCPContentExtraction(Tool):
    """
    Tool for extracting pure content from MCP protocol messages.
    
    This tool processes MCP message formats and extracts the actual tool execution
    content, removing protocol wrappers and returning clean tool data.
    """
    
    def __init__(self, permission_manager: Optional[PermissionManager] = None, session_manager=None):
        """Initialize MCP Content Extraction tool."""
        super().__init__(
            name="mcp_content_extraction",
            description="Intelligent deep content extraction from complex nested data structures. Automatically skips metadata, execution logs, and protocol wrappers to extract core data content. Works with MCP messages, JSON responses, and any multi-layer data format. Returns only the most valuable data payload.",
            version="1.0.0",
            session_manager=session_manager
        )
        self.permission_manager = permission_manager or PermissionManager()
    
    def get_input_schema(self) -> Type[ToolInput]:
        """Return the input schema for this tool."""
        return MCPContentExtractionInput
    
    async def validate_input(self, input_data: Dict[str, Any]) -> MCPContentExtractionInput:
        """Validate tool input data."""
        try:
            return MCPContentExtractionInput(**input_data)
        except Exception as e:
            logger.error(f"Input validation failed for MCP content extraction: {str(e)}")
            raise ValueError(f"Invalid input for mcp_content_extraction: {str(e)}")
    
    async def check_permissions(self, input_data: ToolInput) -> bool:
        """Check permissions for MCP extractor execution."""
        try:
            # Basic permission check - this tool doesn't access sensitive resources
            return await self.permission_manager.check_tool_permission(
                self.name,
                input_data.dict()
            )
        except Exception as e:
            logger.error(f"Permission check failed for {self.name}: {str(e)}")
            return False
    
    async def execute(self, input_data: MCPContentExtractionInput) -> AsyncGenerator[ToolResult, None]:
        """
        Execute MCP content extraction.
        
        Args:
            input_data: Validated input data
            
        Yields:
            ToolResult: Extraction results
        """
        try:
            # Progress indicator
            yield ToolResult(
                type=ToolResultType.PROGRESS,
                content="Extracting content from MCP message",
                tool_name=self.name,
                execution_id=input_data.execution_id
            )
            
            # Get content to extract from input
            try:
                content_to_extract = input_data.get_content_to_extract()
            except ValueError as e:
                # If no content is provided, try to extract from metadata or provide a helpful error
                if hasattr(input_data, 'metadata') and input_data.metadata:
                    # Check if metadata contains previous task output
                    metadata = input_data.metadata
                    if 'previous_output' in metadata or 'task_output' in metadata:
                        content_to_extract = metadata.get('previous_output') or metadata.get('task_output')
                        logger.info("Using content from metadata")
                    else:
                        yield ToolResult(
                            type=ToolResultType.WARNING,
                            content=f"No direct content provided. Available metadata keys: {list(metadata.keys())}",
                            tool_name=self.name,
                            execution_id=input_data.execution_id
                        )
                        yield ToolResult(
                            type=ToolResultType.ERROR,
                            content="No content to extract. This tool requires MCP message content from a previous task.",
                            tool_name=self.name,
                            execution_id=input_data.execution_id
                        )
                        return
                else:
                    # Last resort: try to read from hello.json if it exists
                    import os
                    hello_json_path = "hello.json"
                    if os.path.exists(hello_json_path):
                        try:
                            yield ToolResult(
                                type=ToolResultType.INFO,
                                content=f"No direct content provided, attempting to read from {hello_json_path}",
                                tool_name=self.name,
                                execution_id=input_data.execution_id
                            )
                            
                            with open(hello_json_path, 'r', encoding='utf-8') as f:
                                content_to_extract = f.read()
                                logger.info("Using content from hello.json file")
                        except Exception as file_error:
                            yield ToolResult(
                                type=ToolResultType.ERROR,
                                content=f"Failed to read {hello_json_path}: {str(file_error)}",
                                tool_name=self.name,
                                execution_id=input_data.execution_id
                            )
                            return
                    else:
                        yield ToolResult(
                            type=ToolResultType.ERROR,
                            content="No content to extract. This tool requires MCP message content. Please provide 'content', 'data', or 'mcp_message' parameter, ensure previous tasks provide data, or place data in hello.json file.",
                            tool_name=self.name,
                            execution_id=input_data.execution_id
                        )
                        return
            
            # Parse content if it's a string
            if isinstance(content_to_extract, str):
                try:
                    mcp_data = json.loads(content_to_extract)
                except json.JSONDecodeError:
                    # If it's not JSON, treat as plain text for extraction
                    mcp_data = {"text_content": content_to_extract}
            else:
                mcp_data = content_to_extract
            
            # Extract content based on extraction type
            extracted_content = await self._extract_content(
                mcp_data, 
                input_data.extract_type,
                input_data.validate_json
            )
            
            if extracted_content is None:
                yield ToolResult(
                    type=ToolResultType.WARNING,
                    content="No extractable content found in MCP message",
                    tool_name=self.name,
                    execution_id=input_data.execution_id
                )
                return
            
            # Format output for proper serialization
            # Ensure content is always JSON-serializable
            if isinstance(extracted_content, (dict, list)):
                try:
                    # Test JSON serialization to ensure compatibility
                    json.dumps(extracted_content, ensure_ascii=False)
                    if input_data.pretty_print:
                        formatted_content = json.dumps(extracted_content, indent=2, ensure_ascii=False)
                    else:
                        formatted_content = json.dumps(extracted_content, ensure_ascii=False)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Content not JSON serializable: {str(e)}, converting to string")
                    formatted_content = str(extracted_content)
            else:
                formatted_content = str(extracted_content)
            
            # Success result - return formatted string content to avoid serialization issues
            yield ToolResult(
                type=ToolResultType.SUCCESS,
                content=formatted_content,  # Return serializable string content
                tool_name=self.name,
                execution_id=input_data.execution_id,
                metadata={
                    "extraction_type": input_data.extract_type,
                    "content_type": type(extracted_content).__name__,
                    "content_size": len(formatted_content),
                    "is_json": isinstance(extracted_content, (dict, list)),
                    "mcp_result_extracted": "result" in (mcp_data if isinstance(content_to_extract, dict) else {}),
                    "raw_content": extracted_content if isinstance(extracted_content, (str, int, float, bool, type(None))) else None
                }
            )
            
        except Exception as e:
            logger.error(f"MCP extraction failed: {str(e)}")
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"MCP content extraction failed: {str(e)}",
                tool_name=self.name,
                execution_id=input_data.execution_id,
                metadata={"error_type": "extraction_error"}
            )
    
    async def _extract_content(
        self, 
        mcp_data: Dict[str, Any], 
        extract_type: str,
        validate_json: bool
    ) -> Optional[Any]:
        """
        Extract content from MCP message based on extraction type.
        Core logic: Extract MCPMessage.result as ToolResult.content
        
        Args:
            mcp_data: Parsed MCP message data
            extract_type: Type of extraction to perform
            validate_json: Whether to validate JSON content
            
        Returns:
            Extracted content or None if extraction fails
        """
        try:
            # 使用深度提取逻辑，智能识别和提取核心内容
            logger.info("使用智能深度提取逻辑")
            
            # 首先尝试超级提取（专门解决你的问题）
            super_extracted = await self._super_extract_innermost_data(mcp_data)
            if super_extracted is not None:
                logger.info("超级提取成功，获得最内层数据")
                return super_extracted
            
            # 然后尝试最终数据提取（专门处理复杂嵌套情况）
            final_extracted = await self._extract_final_data(mcp_data)
            if final_extracted is not None:
                logger.info("最终数据提取成功")
                return final_extracted
            
            # 其次尝试通用深度提取
            deep_extracted = await self._deep_extract_core_content(mcp_data)
            if deep_extracted is not None:
                logger.info("深度提取成功，获得核心内容")
                return deep_extracted
            
            # 如果深度提取没有结果，使用原有的回退逻辑
            logger.info("深度提取无结果，使用回退逻辑")
            
            if extract_type == "auto":
                return await self._auto_extract_content(mcp_data, validate_json)
            elif extract_type == "content":
                return await self._extract_from_content_array(mcp_data, validate_json)
            elif extract_type == "text":
                return await self._extract_text_content(mcp_data)
            elif extract_type == "json":
                return await self._extract_json_content(mcp_data, validate_json)
            else:
                raise ValueError(f"Unknown extraction type: {extract_type}")
                
        except Exception as e:
            logger.error(f"Content extraction failed: {str(e)}")
            return None
    
    async def _auto_extract_content(self, mcp_data: Dict[str, Any], validate_json: bool) -> Optional[Any]:
        """Auto-detect and extract content using the best method."""
        # Priority 1: Direct result field (MCPMessage.result)
        if "result" in mcp_data and mcp_data["result"] is not None:
            logger.info("Auto-extraction: Using MCP result field")
            return mcp_data["result"]
        
        # Priority 2: Content array extraction (common MCP format)
        content = await self._extract_from_content_array(mcp_data, validate_json)
        if content is not None:
            logger.info("Auto-extraction: Using content array")
            return content
        
        # Priority 3: Text extraction
        text_content = await self._extract_text_content(mcp_data)
        if text_content is not None:
            logger.info("Auto-extraction: Using text content")
            return text_content
        
        # Fallback: Return the entire data if nothing else works
        logger.warning("Auto-extraction: Using entire data as fallback")
        return mcp_data
    
    async def _extract_from_content_array(self, mcp_data: Dict[str, Any], validate_json: bool) -> Optional[Any]:
        """Extract JSON content from MCP content array format."""
        # Look for content array in result or root
        content_array = None
        
        if "result" in mcp_data and isinstance(mcp_data["result"], dict):
            if "content" in mcp_data["result"]:
                content_array = mcp_data["result"]["content"]
        elif "content" in mcp_data:
            content_array = mcp_data["content"]
        
        if not content_array or not isinstance(content_array, list):
            return None
        
        logger.info(f"Found content array with {len(content_array)} items")
        
        # Extract and parse JSON from text fields
        for item in content_array:
            if isinstance(item, dict) and "text" in item:
                text_content = item["text"]
                logger.info(f"Processing text content, length: {len(text_content)}")
                
                # Try to parse the text content as JSON
                try:
                    parsed_json = json.loads(text_content)
                    logger.info(f"Successfully parsed JSON: {type(parsed_json)}")
                    return parsed_json
                except json.JSONDecodeError as e:
                    logger.debug(f"JSON parse failed: {e}, trying as string")
                    # If not valid JSON, return as string
                    return text_content
        
        logger.warning("No text content found in content array")
        return None
    
    async def _extract_text_content(self, mcp_data: Dict[str, Any]) -> Optional[str]:
        """Extract plain text content from MCP message."""
        # Look for text in various locations
        text_contents = []
        
        def extract_text_recursive(obj):
            if isinstance(obj, dict):
                if "text" in obj:
                    text_contents.append(obj["text"])
                for value in obj.values():
                    extract_text_recursive(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_text_recursive(item)
        
        extract_text_recursive(mcp_data)
        
        if text_contents:
            return "\n".join(text_contents) if len(text_contents) > 1 else text_contents[0]
        
        return None
    
    async def _extract_json_content(self, mcp_data: Dict[str, Any], validate_json: bool) -> Optional[Any]:
        """Extract and parse JSON content from MCP message."""
        # First try content array extraction
        content = await self._extract_from_content_array(mcp_data, validate_json=True)
        if content is not None and isinstance(content, (dict, list)):
            return content
        
        # Try text extraction and JSON parsing
        text_content = await self._extract_text_content(mcp_data)
        if text_content:
            try:
                return json.loads(text_content)
            except json.JSONDecodeError:
                if validate_json:
                    return None
                else:
                    return text_content
        
        return None
    
    
    
    
    async def _extract_from_raw_text(self, raw_text: str) -> Optional[Any]:
        """Extract JSON content from raw text (like hello.json file)."""
        try:
            logger.info(f"Extracting from raw text, length: {len(raw_text)}")
            
            # Try to parse the entire content as JSON first
            try:
                mcp_data = json.loads(raw_text)
                logger.info("Successfully parsed raw text as JSON")
                return await self._extract_from_content_array(mcp_data, validate_json=True)
            except json.JSONDecodeError:
                pass
            
            # Try to find MCP JSON structure in the raw text
            # Look for the JSON part (skip the tool execution logs)
            lines = raw_text.split('\n')
            json_start = -1
            json_end = -1
            brace_count = 0
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('{') and json_start == -1:
                    json_start = i
                    brace_count = 1
                elif json_start != -1:
                    brace_count += stripped.count('{') - stripped.count('}')
                    if brace_count == 0:
                        json_end = i
                        break
            
            if json_start == -1 or json_end == -1:
                logger.warning("No JSON structure found in raw text")
                return raw_text  # Return as plain text if no JSON found
            
            # Extract and parse the JSON part
            json_lines = lines[json_start:json_end+1]
            json_text = '\n'.join(json_lines)
            
            try:
                mcp_data = json.loads(json_text)
                logger.info("Successfully parsed MCP JSON structure")
                return await self._extract_from_content_array(mcp_data, validate_json=True)
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse MCP JSON: {e}")
                return raw_text  # Return as plain text if JSON parsing fails
            
        except Exception as e:
            logger.error(f"Raw text extraction failed: {str(e)}")
            return None
    
    async def _extract_mcp_result(self, mcp_data: Dict[str, Any]) -> Optional[Any]:
        """
        Extract result field from MCPMessage structure.
        
        This method specifically handles the MCPMessage protocol format
        and extracts the result field as defined in SimaCode architecture.
        
        Args:
            mcp_data: Parsed MCP message data
            
        Returns:
            Content from MCPMessage.result field or None if not found
        """
        try:
            # Check for standard MCPMessage structure
            if isinstance(mcp_data, dict) and "jsonrpc" in mcp_data:
                logger.info("Detected standard MCPMessage format")
                
                # Extract result field directly
                if "result" in mcp_data and mcp_data["result"] is not None:
                    result = mcp_data["result"]
                    logger.info(f"Extracted MCP result: {type(result).__name__}")
                    return result
                
                # Handle error responses
                if "error" in mcp_data and mcp_data["error"] is not None:
                    logger.warning("MCP message contains error")
                    return mcp_data["error"]
            
            # Fallback: check for result field in any dictionary
            if isinstance(mcp_data, dict) and "result" in mcp_data:
                logger.info("Found result field in data structure")
                return mcp_data["result"]
                
            logger.debug("No result field found in MCP data")
            return None
            
        except Exception as e:
            logger.error(f"MCP result extraction failed: {str(e)}")
            return None
    
    async def _deep_extract_core_content(self, data: Any) -> Optional[Any]:
        """
        深度提取核心内容，跳过工具执行信息和多层包装。
        
        这个方法会智能地识别并提取嵌套数据中的核心内容，
        跳过诸如 "Starting execution"、"execution finished" 等执行信息。
        
        Args:
            data: 需要提取的数据（可能是多层嵌套的）
            
        Returns:
            提取出的核心内容，如果没找到则返回 None
        """
        try:
            logger.info("开始深度提取核心内容")
            
            # 如果是字符串，尝试从中解析JSON并继续提取
            if isinstance(data, str):
                return await self._extract_from_text_content(data)
            
            # 如果是字典，递归查找核心内容
            elif isinstance(data, dict):
                # 优先查找已知的核心字段
                core_fields = ['text', 'content', 'data', 'emails', 'result']
                
                for field in core_fields:
                    if field in data and data[field] is not None:
                        # 递归提取
                        result = await self._deep_extract_core_content(data[field])
                        if result is not None:
                            logger.info(f"在字段 '{field}' 中找到核心内容")
                            return result
                
                # 如果没找到核心字段，尝试所有字段
                for key, value in data.items():
                    if key not in ['jsonrpc', 'id', 'method', 'error'] and value is not None:
                        result = await self._deep_extract_core_content(value)
                        if result is not None:
                            return result
            
            # 如果是列表，递归处理每个元素
            elif isinstance(data, list):
                for item in data:
                    result = await self._deep_extract_core_content(item)
                    if result is not None:
                        return result
            
            # 基本类型直接返回
            else:
                return data
            
            return None
            
        except Exception as e:
            logger.error(f"深度提取失败: {str(e)}")
            return None
    
    async def _extract_from_text_content(self, text_content: str) -> Optional[Any]:
        """
        从包含执行信息的文本中提取核心内容。
        
        智能识别并跳过执行日志，提取最终的数据内容。
        
        Args:
            text_content: 包含执行信息的文本内容
            
        Returns:
            提取的核心内容
        """
        try:
            logger.info(f"分析文本内容，长度: {len(text_content)}")
            
            # 首先尝试直接解析为JSON
            try:
                parsed = json.loads(text_content)
                logger.info("文本内容是纯JSON格式")
                return await self._deep_extract_core_content(parsed)
            except json.JSONDecodeError:
                pass
            
            # 如果包含执行信息，进行智能清理
            import re
            
            # 移除执行开始和结束的标记行
            lines = text_content.split('\\n')
            clean_lines = []
            
            for line in lines:
                stripped = line.strip()
                # 跳过明显的执行信息行
                if re.match(r'.*(?:starting|execution|finished|completed).*(?:execution|in \\d+\\.\\d+s).*', stripped.lower()):
                    continue
                clean_lines.append(line)
            
            if clean_lines:
                cleaned_text = '\\n'.join(clean_lines).strip()
                
                # 尝试解析清理后的内容
                try:
                    parsed = json.loads(cleaned_text)
                    logger.info("成功解析清理后的JSON内容")
                    return await self._deep_extract_core_content(parsed)
                except json.JSONDecodeError:
                    pass
            
            # 尝试处理多层转义的JSON字符串
            deeply_nested = await self._extract_deeply_nested_json(text_content)
            if deeply_nested is not None:
                return deeply_nested
            
            # 如果还是不行，尝试提取引用的JSON字符串
            extracted = await self._extract_quoted_json(text_content)
            if extracted is not None:
                return extracted
            
            # 如果都没有成功，返回清理后的文本
            if clean_lines and len('\\n'.join(clean_lines).strip()) < len(text_content) * 0.8:
                cleaned = '\\n'.join(clean_lines).strip()
                logger.info("返回清理后的文本内容")
                return cleaned
            
            logger.warning("无法从文本中提取有效内容")
            return None
            
        except Exception as e:
            logger.error(f"文本内容提取失败: {str(e)}")
            return None
    
    async def _extract_quoted_json(self, text: str) -> Optional[Any]:
        """
        从文本中提取被引号包围的JSON字符串。
        
        处理格式如：\"text\": \"[{...}]\" 或 \"text\": \"{...}\"
        
        Args:
            text: 包含引用JSON的文本
            
        Returns:
            解析后的JSON内容
        """
        try:
            # 查找 "text": "..." 模式
            import re
            
            # 匹配 "text": "..." 格式，支持转义字符
            text_pattern = r'\\"text\\":\\s*\\"([^"]*(?:\\\\.[^"]*)*)\\"'
            matches = re.findall(text_pattern, text)
            
            for match in matches:
                # 清理转义字符
                cleaned = match.replace('\\\\"', '"').replace('\\\\n', '\\n')
                
                try:
                    # 尝试解析为JSON
                    parsed = json.loads(cleaned)
                    logger.info(f"从引用字符串中解析出JSON: {type(parsed).__name__}")
                    return parsed
                except json.JSONDecodeError:
                    # 如果不是JSON，返回原始字符串
                    if cleaned.strip():
                        logger.info("返回原始文本内容")
                        return cleaned
            
            # 如果没找到，尝试更宽泛的模式
            broader_pattern = r'\\"([^"]*(?:\\\\.[^"]*)*)\\"'
            all_matches = re.findall(broader_pattern, text)
            
            for match in all_matches:
                cleaned = match.replace('\\\\"', '"').replace('\\\\n', '\\n')
                
                # 检查是否像是邮件数据（包含常见字段）
                if any(keyword in cleaned.lower() for keyword in 
                      ['uid', 'subject', 'sender', 'email', '[{', '{"']):
                    try:
                        parsed = json.loads(cleaned)
                        logger.info("找到邮件数据JSON")
                        return parsed
                    except json.JSONDecodeError:
                        if len(cleaned) > 50:  # 足够长的字符串可能是数据
                            logger.info("返回疑似邮件数据字符串")
                            return cleaned
            
            return None
            
        except Exception as e:
            logger.error(f"引用JSON提取失败: {str(e)}")
            return None
    
    async def _extract_deeply_nested_json(self, text: str) -> Optional[Any]:
        """
        处理深度嵌套和多重转义的JSON字符串。
        
        专门处理像 \"text\": \"[{\\\\\\\"key\\\\\\\":\\\\\\\"value\\\\\\\"}]\" 这样的复杂格式。
        
        Args:
            text: 包含深度嵌套JSON的文本
            
        Returns:
            解析后的最终数据
        """
        try:
            import re
            
            # 查找 "text": "..." 模式，处理多层转义
            text_value_pattern = r'\"text\":\\s*\"([^\"]*(?:\\\\.[^\"]*)*?)\"'
            matches = re.findall(text_value_pattern, text)
            
            for match in matches:
                # 逐步清理转义字符
                cleaned = match
                
                # 处理多层转义
                for _ in range(5):  # 最多处理5层转义
                    old_cleaned = cleaned
                    cleaned = cleaned.replace('\\\\\\\\\"', '\"')  # 4个反斜杠 + 引号
                    cleaned = cleaned.replace('\\\\\"', '\"')      # 2个反斜杠 + 引号
                    cleaned = cleaned.replace('\\\\n', '\\n')      # 换行符转义
                    cleaned = cleaned.replace('\\\\r', '\\r')      # 回车符转义
                    cleaned = cleaned.replace('\\\\t', '\\t')      # 制表符转义
                    
                    if cleaned == old_cleaned:  # 没有更多变化，停止
                        break
                
                logger.info(f"清理后的内容长度: {len(cleaned)}")
                
                # 尝试解析为JSON
                if cleaned.strip():
                    try:
                        parsed = json.loads(cleaned)
                        logger.info(f"成功解析深度嵌套JSON: {type(parsed).__name__}")
                        
                        # 如果是列表或字典，直接返回
                        if isinstance(parsed, (list, dict)):
                            return parsed
                        else:
                            return cleaned
                            
                    except json.JSONDecodeError as e:
                        logger.debug(f"JSON解析失败: {str(e)}")
                        
                        # 如果JSON解析失败但内容看起来有价值，返回清理后的字符串
                        if len(cleaned.strip()) > 10 and any(c in cleaned for c in ['{', '[', ':']):
                            logger.info("返回清理后但未解析的内容")
                            return cleaned.strip()
            
            # 如果"text"模式没找到，尝试查找任何看起来像JSON的内容
            # 使用更简单的正则表达式避免嵌套集合警告
            json_like_patterns = [
                r'\\[\\{.*?\\}\\]',      # 数组格式
                r'\\{.*?\\}',           # 对象格式
            ]
            
            for pattern in json_like_patterns:
                matches = re.findall(pattern, text, re.DOTALL)
                for match in matches:
                    # 尝试多层转义清理
                    cleaned = match
                    for _ in range(3):
                        old_cleaned = cleaned
                        cleaned = cleaned.replace('\\\\\"', '\"')
                        cleaned = cleaned.replace('\\\\\\\\\"', '\"')
                        if cleaned == old_cleaned:
                            break
                    
                    try:
                        parsed = json.loads(cleaned)
                        logger.info(f"通过模式匹配找到JSON: {type(parsed).__name__}")
                        return parsed
                    except json.JSONDecodeError:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"深度嵌套JSON提取失败: {str(e)}")
            return None
    
    async def _extract_final_data(self, mcp_data: Any) -> Optional[Any]:
        """
        最终数据提取方法，专门处理你描述的复杂嵌套格式。
        
        直接定位到最内层的实际数据，跳过所有包装层。
        
        Args:
            mcp_data: MCP消息数据
            
        Returns:
            最终的核心数据
        """
        try:
            logger.info("开始最终数据提取")
            
            # 转换为字符串进行模式匹配
            if isinstance(mcp_data, dict):
                content_str = json.dumps(mcp_data, ensure_ascii=False)
            elif isinstance(mcp_data, str):
                content_str = mcp_data
            else:
                content_str = str(mcp_data)
            
            import re
            
            # 直接查找最内层的数据模式
            # 匹配 \"text\": \"[{...}]\" 或类似模式，处理所有可能的转义层级
            patterns = [
                # 最常见：匹配 \"text\": \"[...]\" 格式
                r'\"text\":\\s*\"(\\[.*?\\])\"',
                # 匹配 \"text\": \"{...}\" 格式  
                r'\"text\":\\s*\"(\\{.*?\\})\"',
                # 更深层的转义：\\\"text\\\": \\\"[...]\\\"
                r'\\\\\"text\\\\\":\\\\s*\\\\\"(\\\\[.*?\\\\])\\\\\"',
                # 极深层转义
                r'\\\\\\\\\"text\\\\\\\\\":\\\\\\\\s*\\\\\\\\\"(.*?)\\\\\\\\\"',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content_str, re.DOTALL)
                
                for match in matches:
                    # 逐步清理多层转义
                    cleaned = match
                    
                    # 最多清理8层转义
                    for i in range(8):
                        old_cleaned = cleaned
                        # 处理各种转义组合
                        cleaned = cleaned.replace('\\\\\\\\\\\\\\\\\"', '\"')  # 8个反斜杠
                        cleaned = cleaned.replace('\\\\\\\\\\\\\"', '\"')      # 6个反斜杠  
                        cleaned = cleaned.replace('\\\\\\\\\"', '\"')          # 4个反斜杠
                        cleaned = cleaned.replace('\\\\\"', '\"')              # 2个反斜杠
                        cleaned = cleaned.replace('\\\\n', '\\n')
                        cleaned = cleaned.replace('\\\\r', '\\r')
                        cleaned = cleaned.replace('\\\\t', '\\t')
                        
                        if cleaned == old_cleaned:
                            break
                    
                    logger.info(f"尝试解析清理后内容，长度: {len(cleaned)}")
                    
                    # 尝试解析
                    if cleaned.strip():
                        try:
                            parsed = json.loads(cleaned)
                            logger.info(f"✅ 成功解析最终数据: {type(parsed).__name__}")
                            
                            # 如果解析出来是列表或字典，直接返回
                            if isinstance(parsed, (list, dict)):
                                return parsed
                                
                        except json.JSONDecodeError as e:
                            logger.debug(f"JSON解析失败: {str(e)}")
                            
                            # 即使JSON解析失败，如果内容看起来有价值就返回
                            if (len(cleaned.strip()) > 20 and 
                                any(indicator in cleaned for indicator in ['[{', '":', 'uid', 'subject'])):
                                logger.info("返回清理后的文本内容")
                                return cleaned.strip()
            
            # 如果上述模式都没匹配，尝试更宽泛的搜索
            # 查找任何看起来像邮件数据的JSON数组
            broad_patterns = [
                r'(\\[\\{[^\\[\\]]*?"uid"[^\\[\\]]*?\\}\\])',  # 包含uid的JSON数组
                r'(\\{[^{}]*?"subject"[^{}]*?\\})',            # 包含subject的JSON对象
            ]
            
            for pattern in broad_patterns:
                matches = re.findall(pattern, content_str, re.DOTALL)
                for match in matches:
                    cleaned = match
                    # 清理转义
                    for _ in range(5):
                        old_cleaned = cleaned
                        cleaned = cleaned.replace('\\\\\"', '\"')
                        cleaned = cleaned.replace('\\\\\\\\\"', '\"')
                        if cleaned == old_cleaned:
                            break
                    
                    try:
                        parsed = json.loads(cleaned)
                        logger.info(f"通过宽泛匹配找到数据: {type(parsed).__name__}")
                        return parsed
                    except json.JSONDecodeError:
                        continue
            
            logger.info("最终数据提取未找到匹配模式")
            return None
            
        except Exception as e:
            logger.error(f"最终数据提取失败: {str(e)}")
            return None
    
    async def _super_extract_innermost_data(self, mcp_data: Any) -> Optional[Any]:
        """
        超级提取方法，专门解决复杂嵌套数据的问题。
        
        使用逐步拆解的方法，直接定位到最内层的实际数据。
        
        Args:
            mcp_data: MCP消息数据
            
        Returns:
            最内层的实际数据
        """
        try:
            logger.info("开始超级提取最内层数据")
            
            # 将数据转换为字符串进行处理
            if isinstance(mcp_data, dict):
                data_str = json.dumps(mcp_data, ensure_ascii=False)
            elif isinstance(mcp_data, str):
                data_str = mcp_data
            else:
                data_str = str(mcp_data)
            
            # 第一步：找到最内层的 "text": "..." 部分
            import re
            
            # 使用更精确的模式匹配，处理多层嵌套
            # 匹配模式：寻找 "text": 后面跟着的内容
            text_patterns = [
                r'"text":\s*"([^"]*(?:\\.[^"]*)*)"',  # 基本模式
                r'\\"text\\":\s*\\"([^"]*(?:\\.[^"]*)*)\\"',  # 一层转义
                r'\\\\\\"text\\\\\\":\s*\\\\\\"([^"]*(?:\\.[^"]*)*)\\\\\\"',  # 两层转义
            ]
            
            extracted_text = None
            for pattern in text_patterns:
                matches = re.findall(pattern, data_str)
                if matches:
                    # 取最后一个匹配（通常是最内层的）
                    extracted_text = matches[-1]
                    logger.info(f"通过模式匹配找到文本，长度: {len(extracted_text)}")
                    break
            
            if not extracted_text:
                logger.info("未找到text字段内容")
                return None
            
            # 第二步：清理多层转义字符（增强版）
            cleaned_text = extracted_text
            cleanup_rounds = 0
            
            while cleanup_rounds < 15:  # 最多清理15轮，确保彻底清理
                old_text = cleaned_text
                
                # 从最深层的转义开始清理
                cleaned_text = cleaned_text.replace('\\\\\\\\\\\\\\\\', '\\\\\\\\')    # 8个->4个
                cleaned_text = cleaned_text.replace('\\\\\\\\\\\\', '\\\\\\\\')        # 6个->4个  
                cleaned_text = cleaned_text.replace('\\\\\\\\', '\\\\')              # 4个->2个
                cleaned_text = cleaned_text.replace('\\\\', '')                    # 2个->0个（完全清除转义）
                
                # 清理引号转义
                cleaned_text = cleaned_text.replace('\\"', '"')
                
                # 清理其他转义字符
                cleaned_text = cleaned_text.replace('\\n', '\\n')
                cleaned_text = cleaned_text.replace('\\r', '\\r') 
                cleaned_text = cleaned_text.replace('\\t', '\\t')
                
                # 如果没有变化，停止清理
                if cleaned_text == old_text:
                    break
                    
                cleanup_rounds += 1
            
            # 额外的最终清理：移除可能残留的转义序列和多余内容
            final_cleanup_patterns = [
                (r'\\"\n\s*}', ''),          # 移除结尾的转义引号和大括号
                (r'\\n\s*', ''),             # 移除转义换行符
                (r'\s*\"$', ''),             # 移除结尾的引号
                (r'^\s*\"', ''),             # 移除开头的引号
            ]
            
            for pattern, replacement in final_cleanup_patterns:
                import re
                cleaned_text = re.sub(pattern, replacement, cleaned_text)
            
            cleaned_text = cleaned_text.strip()
            
            logger.info(f"经过 {cleanup_rounds} 轮清理，文本长度: {len(cleaned_text)}")
            
            # 第三步：智能提取JSON部分
            # 首先尝试直接解析整个清理后的文本
            try:
                parsed_data = json.loads(cleaned_text)
                logger.info(f"成功解析完整文本为JSON: {type(parsed_data).__name__}")
                return parsed_data
            except json.JSONDecodeError:
                pass
            
            # 如果直接解析失败，尝试提取JSON部分
            import re
            
            # 查找JSON数组或对象的边界
            json_patterns = [
                r'^(\\[[^\\]]+\\])',          # 匹配开头的JSON数组
                r'^(\\{[^\\}]+\\})',          # 匹配开头的JSON对象
                r'(\\[[^\\]]+\\])',           # 匹配任意位置的JSON数组
                r'(\\{[^\\}]+\\})',           # 匹配任意位置的JSON对象
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, cleaned_text, re.DOTALL)
                for match in matches:
                    try:
                        parsed_data = json.loads(match)
                        logger.info(f"成功提取并解析JSON片段: {type(parsed_data).__name__}")
                        return parsed_data
                    except json.JSONDecodeError:
                        continue
            
            # 如果模式匹配也失败，尝试更精确的边界检测
            # 查找最长的有效JSON字符串
            for end_pos in range(len(cleaned_text), 0, -1):
                candidate = cleaned_text[:end_pos].strip()
                if candidate.endswith((']', '}')):  # 只考虑以合适字符结尾的候选
                    try:
                        parsed_data = json.loads(candidate)
                        logger.info(f"通过边界检测找到有效JSON: {type(parsed_data).__name__}")
                        return parsed_data
                    except json.JSONDecodeError:
                        continue
            
            # 最后尝试：返回看起来有价值的清理后文本
            if len(cleaned_text.strip()) > 10:
                if any(indicator in cleaned_text for indicator in ['{', '[', ':', 'uid', 'subject']):
                    logger.info("返回清理后的结构化文本")
                    return cleaned_text.strip()
                elif len(cleaned_text.strip()) > 50:
                    logger.info("返回清理后的长文本")
                    return cleaned_text.strip()
            
            logger.info("超级提取未找到有价值的内容")
            return None
            
        except Exception as e:
            logger.error(f"超级提取失败: {str(e)}")
            return None


# Register the tool
def create_mcp_content_extraction(permission_manager: Optional[PermissionManager] = None) -> MCPContentExtraction:
    """
    Factory function to create an MCP content extraction tool.
    
    Args:
        permission_manager: Optional permission manager instance
        
    Returns:
        MCPContentExtraction: Configured tool instance
    """
    return MCPContentExtraction(permission_manager=permission_manager)


# Factory function for content forward URL tool
def create_content_forward_url(permission_manager: Optional[PermissionManager] = None) -> ContentForwardURL:
    """
    Factory function to create a content forward URL tool.
    
    Args:
        permission_manager: Optional permission manager instance
        
    Returns:
        ContentForwardURL: Configured tool instance
    """
    return ContentForwardURL(permission_manager=permission_manager)


# Auto-register the tools
try:
    from .base import ToolRegistry
    
    # Unregister if already exists
    if 'mcp_content_extraction' in ToolRegistry.list_tools():
        ToolRegistry.unregister('mcp_content_extraction')
    if 'content_forward_url' in ToolRegistry.list_tools():
        ToolRegistry.unregister('content_forward_url')
    
    # Register new instances
    mcp_content_extraction_tool = MCPContentExtraction()
    ToolRegistry.register(mcp_content_extraction_tool)
    
    content_forward_url_tool = ContentForwardURL()
    ToolRegistry.register(content_forward_url_tool)
    
except Exception as e:
    logger.error(f"Failed to register tools: {str(e)}")
