"""
Claude Vision OCR Engine

This module implements the Claude Vision API integration for OCR functionality.
It uses Anthropic's Claude-3.5 Sonnet model for intelligent text extraction.
"""

import base64
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from .base import OCREngine, ExtractionResult, ExtractionStatus, EngineInfo
from ..config import get_claude_config


class ClaudeEngineError(Exception):
    """Custom exception for Claude engine errors"""
    pass


class ClaudeEngine(OCREngine):
    """
    Claude Vision OCR Engine implementation.
    
    This engine uses Anthropic's Claude-3.5 Sonnet Vision model to extract
    text and structured data from images with high accuracy.
    """
    
    def __init__(self):
        super().__init__("claude", "1.0.0")
        self.client: Optional[anthropic.AsyncAnthropic] = None
        self.config = get_claude_config()
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Anthropic client"""
        if not ANTHROPIC_AVAILABLE:
            raise ClaudeEngineError(
                "Anthropic package not available. Install with: pip install anthropic"
            )
        
        if not self.config.api_key:
            raise ClaudeEngineError(
                "Claude API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or configure ocr_claudeai.api_key in .simacode/config.yaml"
            )
        
        try:
            self.client = anthropic.AsyncAnthropic(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout
            )
        except Exception as e:
            raise ClaudeEngineError(f"Failed to initialize Claude client: {str(e)}")
    
    def _encode_image(self, image_path: str) -> tuple[str, str]:
        """
        Encode image to base64 for Claude API.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Tuple of (base64_data, media_type)
        """
        path = Path(image_path)
        
        if not path.exists():
            raise ClaudeEngineError(f"Image file not found: {image_path}")
        
        # Determine media type
        suffix = path.suffix.lower()
        media_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        
        if suffix not in media_type_map:
            raise ClaudeEngineError(f"Unsupported image format: {suffix}")
        
        media_type = media_type_map[suffix]
        
        # Read and encode image
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            base64_data = base64.b64encode(image_data).decode('utf-8')
            return base64_data, media_type
            
        except Exception as e:
            raise ClaudeEngineError(f"Failed to read image file: {str(e)}")
    
    def _create_default_prompt(self, prompt: Optional[str] = None) -> str:
        """Create default extraction prompt"""
        if prompt:
            return prompt
        
        return """Please carefully examine this image and extract all visible text content.

Provide the extracted text in a clear, structured format. If the document contains:
- Structured data (like forms, tables, invoices), organize the information logically
- Lists or bullet points, maintain the formatting
- Multiple sections, clearly separate them

Focus on accuracy and completeness. If any text is unclear or partially obscured, indicate this in your response."""
    
    def _create_structured_prompt(self, schema: Dict[str, Any], base_prompt: Optional[str] = None) -> str:
        """Create prompt for structured data extraction"""
        # Build field descriptions from schema
        field_descriptions = []
        for field_name, field_info in schema.items():
            if isinstance(field_info, dict):
                field_type = field_info.get("type", "string")
                description = field_info.get("description", "")
                required = field_info.get("required", False)
                
                desc = f"- {field_name} ({field_type})"
                if description:
                    desc += f": {description}"
                if required:
                    desc += " [REQUIRED]"
                
                field_descriptions.append(desc)
        
        fields_text = "\n".join(field_descriptions)
        
        base_instruction = base_prompt or "Please carefully examine this image and extract the following information:"
        
        return f"""{base_instruction}

Extract the following fields:
{fields_text}

Return the result as a JSON object with the exact field names specified above. 
If a field cannot be found or is unclear, use null as the value.
Ensure the JSON is valid and properly formatted.

Example format:
{{
    "field1": "extracted_value",
    "field2": 123.45,
    "field3": null
}}"""
    
    async def extract_text(self, image_path: str, prompt: Optional[str] = None) -> ExtractionResult:
        """Extract text from image using Claude Vision"""
        start_time = time.time()
        
        try:
            # Encode image
            base64_data, media_type = self._encode_image(image_path)
            
            # Prepare prompt
            extraction_prompt = self._create_default_prompt(prompt)
            
            # Create message
            message = {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_data
                        }
                    },
                    {
                        "type": "text",
                        "text": extraction_prompt
                    }
                ]
            }
            
            # Call Claude API
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[message]
            )
            
            # Extract response content
            if response.content and len(response.content) > 0:
                extracted_text = response.content[0].text
                
                # Calculate confidence based on response quality indicators
                confidence = self._calculate_confidence(extracted_text, response)
                
                return ExtractionResult(
                    status=ExtractionStatus.SUCCESS,
                    raw_text=extracted_text,
                    confidence_score=confidence,
                    processing_time=time.time() - start_time,
                    engine_name=self.name,
                    engine_version=self.version,
                    metadata={
                        "model": self.config.model,
                        "usage": {
                            "input_tokens": response.usage.input_tokens if response.usage else 0,
                            "output_tokens": response.usage.output_tokens if response.usage else 0
                        }
                    }
                )
            else:
                return ExtractionResult(
                    status=ExtractionStatus.FAILED,
                    errors=["No content in Claude response"],
                    processing_time=time.time() - start_time,
                    engine_name=self.name,
                    engine_version=self.version
                )
        
        except Exception as e:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                errors=[f"Claude extraction failed: {str(e)}"],
                processing_time=time.time() - start_time,
                engine_name=self.name,
                engine_version=self.version
            )
    
    async def extract_structured_data(
        self, 
        image_path: str, 
        schema: Dict[str, Any],
        prompt: Optional[str] = None
    ) -> ExtractionResult:
        """Extract structured data from image using Claude Vision"""
        start_time = time.time()
        
        try:
            # Encode image
            base64_data, media_type = self._encode_image(image_path)
            
            # Create structured extraction prompt
            extraction_prompt = self._create_structured_prompt(schema, prompt)
            
            # Create message
            message = {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_data
                        }
                    },
                    {
                        "type": "text",
                        "text": extraction_prompt
                    }
                ]
            }
            
            # Call Claude API
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[message]
            )
            
            # Parse response
            if response.content and len(response.content) > 0:
                response_text = response.content[0].text
                
                # Try to parse JSON from response
                try:
                    # Extract JSON from response (handle cases where Claude adds explanation)
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1
                    
                    if json_start >= 0 and json_end > json_start:
                        json_text = response_text[json_start:json_end]
                        structured_data = json.loads(json_text)
                    else:
                        # Fallback: try to parse entire response as JSON
                        structured_data = json.loads(response_text)
                    
                    # Validate extracted data against schema
                    validated_data = self._validate_against_schema(structured_data, schema)
                    
                    # Calculate confidence
                    confidence = self._calculate_structured_confidence(validated_data, schema, response)
                    
                    return ExtractionResult(
                        status=ExtractionStatus.SUCCESS,
                        extracted_data=validated_data,
                        raw_text=response_text,
                        confidence_score=confidence,
                        processing_time=time.time() - start_time,
                        engine_name=self.name,
                        engine_version=self.version,
                        metadata={
                            "model": self.config.model,
                            "schema_fields": list(schema.keys()),
                            "extracted_fields": list(validated_data.keys()),
                            "usage": {
                                "input_tokens": response.usage.input_tokens if response.usage else 0,
                                "output_tokens": response.usage.output_tokens if response.usage else 0
                            }
                        }
                    )
                
                except json.JSONDecodeError as e:
                    return ExtractionResult(
                        status=ExtractionStatus.PARTIAL,
                        raw_text=response_text,
                        errors=[f"Failed to parse JSON response: {str(e)}"],
                        processing_time=time.time() - start_time,
                        engine_name=self.name,
                        engine_version=self.version
                    )
            else:
                return ExtractionResult(
                    status=ExtractionStatus.FAILED,
                    errors=["No content in Claude response"],
                    processing_time=time.time() - start_time,
                    engine_name=self.name,
                    engine_version=self.version
                )
        
        except Exception as e:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                errors=[f"Claude structured extraction failed: {str(e)}"],
                processing_time=time.time() - start_time,
                engine_name=self.name,
                engine_version=self.version
            )
    
    def _validate_against_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean extracted data against schema"""
        validated_data = {}
        
        for field_name, field_info in schema.items():
            if field_name in data:
                value = data[field_name]
                
                # Skip null values
                if value is None:
                    validated_data[field_name] = None
                    continue
                
                # Type validation and conversion
                if isinstance(field_info, dict) and "type" in field_info:
                    field_type = field_info["type"]
                    
                    try:
                        if field_type == "string":
                            validated_data[field_name] = str(value) if value is not None else None
                        elif field_type == "number":
                            validated_data[field_name] = float(value) if value is not None else None
                        elif field_type == "integer":
                            validated_data[field_name] = int(float(value)) if value is not None else None
                        elif field_type == "boolean":
                            if isinstance(value, bool):
                                validated_data[field_name] = value
                            elif isinstance(value, str):
                                validated_data[field_name] = value.lower() in ['true', '1', 'yes', 'on']
                            else:
                                validated_data[field_name] = bool(value)
                        else:
                            validated_data[field_name] = value
                    except (ValueError, TypeError):
                        validated_data[field_name] = None
                else:
                    validated_data[field_name] = value
            else:
                # Field not found in extracted data
                validated_data[field_name] = None
        
        return validated_data
    
    def _calculate_confidence(self, text: str, response: Any) -> float:
        """Calculate confidence score for text extraction"""
        base_confidence = 0.8
        
        # Boost confidence if text is substantial
        if len(text) > 100:
            base_confidence += 0.1
        
        # Reduce confidence if text is very short
        if len(text) < 20:
            base_confidence -= 0.2
        
        # Boost confidence if response contains structured patterns
        if any(pattern in text.lower() for pattern in ['invoice', 'date:', 'amount:', 'number:', 'total:']):
            base_confidence += 0.05
        
        return min(max(base_confidence, 0.0), 1.0)
    
    def _calculate_structured_confidence(
        self, 
        data: Dict[str, Any], 
        schema: Dict[str, Any], 
        response: Any
    ) -> float:
        """Calculate confidence score for structured extraction"""
        if not data:
            return 0.0
        
        # Calculate field completion rate
        required_fields = [
            name for name, info in schema.items() 
            if isinstance(info, dict) and info.get("required", False)
        ]
        
        if required_fields:
            completed_required = sum(
                1 for field in required_fields 
                if field in data and data[field] is not None
            )
            required_completion = completed_required / len(required_fields)
        else:
            required_completion = 1.0
        
        # Calculate overall field completion
        total_completion = sum(
            1 for value in data.values() if value is not None
        ) / len(data) if data else 0.0
        
        # Base confidence from Claude's structured understanding
        base_confidence = 0.85
        
        # Adjust based on completion rates
        completion_score = (required_completion * 0.7) + (total_completion * 0.3)
        final_confidence = base_confidence * completion_score
        
        return min(max(final_confidence, 0.0), 1.0)
    
    def get_engine_info(self) -> EngineInfo:
        """Get Claude engine information"""
        return EngineInfo(
            name="claude",
            version="1.0.0",
            description="Claude-3.5 Sonnet Vision OCR Engine",
            supported_formats=[".jpg", ".jpeg", ".png", ".gif", ".webp"],
            capabilities=[
                "text_extraction",
                "structured_extraction", 
                "multilingual_support",
                "handwriting_recognition",
                "layout_understanding",
                "context_awareness"
            ],
            config={
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature
            }
        )
    
    async def health_check(self) -> bool:
        """Check if Claude engine is healthy and ready"""
        if not self.client:
            return False
        
        try:
            # Simple API call to check connectivity
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hello"}]
            )
            return response is not None
        
        except Exception:
            return False