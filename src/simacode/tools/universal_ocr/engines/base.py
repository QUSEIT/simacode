"""
Base OCR Engine Interface

This module defines the abstract base class for all OCR engines,
providing a consistent interface for different OCR implementations.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum


class ExtractionStatus(Enum):
    """Extraction status enumeration"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class ExtractionResult:
    """Result of OCR extraction"""
    status: ExtractionStatus
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence_score: float = 0.0
    processing_time: float = 0.0
    engine_name: str = ""
    engine_version: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        return {
            "status": self.status.value,
            "extracted_data": self.extracted_data,
            "raw_text": self.raw_text,
            "confidence_score": self.confidence_score,
            "processing_time": self.processing_time,
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "metadata": self.metadata,
            "errors": self.errors,
            "timestamp": self.timestamp.isoformat()
        }
    
    def is_successful(self) -> bool:
        """Check if extraction was successful"""
        return self.status == ExtractionStatus.SUCCESS
    
    def has_errors(self) -> bool:
        """Check if there are any errors"""
        return len(self.errors) > 0


@dataclass
class EngineInfo:
    """Information about an OCR engine"""
    name: str
    version: str
    description: str
    supported_formats: List[str]
    capabilities: List[str]
    config: Dict[str, Any] = field(default_factory=dict)


class OCREngine(ABC):
    """
    Abstract base class for all OCR engines.
    
    This class defines the interface that all OCR engines must implement,
    providing a consistent way to extract text and structured data from images.
    """
    
    def __init__(self, name: str, version: str = "1.0.0"):
        """Initialize the OCR engine"""
        self.name = name
        self.version = version
        self._total_extractions = 0
        self._successful_extractions = 0
        self._total_processing_time = 0.0
    
    @abstractmethod
    async def extract_text(self, image_path: str, prompt: Optional[str] = None) -> ExtractionResult:
        """
        Extract text from an image file.
        
        Args:
            image_path: Path to the image file
            prompt: Optional extraction prompt for guided extraction
            
        Returns:
            ExtractionResult: The extraction result
        """
        pass
    
    @abstractmethod
    async def extract_structured_data(
        self, 
        image_path: str, 
        schema: Dict[str, Any],
        prompt: Optional[str] = None
    ) -> ExtractionResult:
        """
        Extract structured data from an image according to a schema.
        
        Args:
            image_path: Path to the image file
            schema: Schema defining the structure of data to extract
            prompt: Optional extraction prompt
            
        Returns:
            ExtractionResult: The extraction result with structured data
        """
        pass
    
    @abstractmethod
    def get_engine_info(self) -> EngineInfo:
        """
        Get information about this engine.
        
        Returns:
            EngineInfo: Engine information and capabilities
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the engine is healthy and ready to process requests.
        
        Returns:
            bool: True if engine is healthy, False otherwise
        """
        pass
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get engine usage statistics"""
        success_rate = (
            self._successful_extractions / self._total_extractions 
            if self._total_extractions > 0 else 0.0
        )
        
        avg_processing_time = (
            self._total_processing_time / self._total_extractions
            if self._total_extractions > 0 else 0.0
        )
        
        return {
            "total_extractions": self._total_extractions,
            "successful_extractions": self._successful_extractions,
            "success_rate": success_rate,
            "average_processing_time": avg_processing_time
        }
    
    def _record_extraction(self, result: ExtractionResult):
        """Record extraction statistics"""
        self._total_extractions += 1
        self._total_processing_time += result.processing_time
        
        if result.is_successful():
            self._successful_extractions += 1
    
    async def extract_with_retry(
        self, 
        image_path: str, 
        prompt: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> ExtractionResult:
        """
        Extract text with retry mechanism.
        
        Args:
            image_path: Path to the image file
            prompt: Optional extraction prompt
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            ExtractionResult: The extraction result
        """
        import asyncio
        
        last_result = None
        
        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                result = await self.extract_text(image_path, prompt)
                result.processing_time = time.time() - start_time
                result.engine_name = self.name
                result.engine_version = self.version
                
                # Record statistics
                self._record_extraction(result)
                
                if result.is_successful():
                    return result
                
                last_result = result
                
            except Exception as e:
                error_result = ExtractionResult(
                    status=ExtractionStatus.FAILED,
                    engine_name=self.name,
                    engine_version=self.version,
                    errors=[f"Attempt {attempt + 1}: {str(e)}"],
                    processing_time=time.time() - start_time if 'start_time' in locals() else 0.0
                )
                
                self._record_extraction(error_result)
                last_result = error_result
            
            # Wait before retry (except on last attempt)
            if attempt < max_retries:
                await asyncio.sleep(retry_delay)
        
        return last_result or ExtractionResult(
            status=ExtractionStatus.FAILED,
            engine_name=self.name,
            engine_version=self.version,
            errors=["All retry attempts failed"]
        )
    
    def __str__(self) -> str:
        """String representation of the engine"""
        return f"{self.name} v{self.version}"
    
    def __repr__(self) -> str:
        """Detailed representation of the engine"""
        return f"OCREngine(name='{self.name}', version='{self.version}')"


class MockOCREngine(OCREngine):
    """
    Mock OCR engine for testing purposes.
    
    This engine returns predefined responses and can be used for testing
    without requiring actual OCR service connections.
    """
    
    def __init__(self):
        super().__init__("mock", "1.0.0")
        self.mock_responses: Dict[str, ExtractionResult] = {}
        self.default_response = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            raw_text="Mock extracted text",
            confidence_score=0.95,
            engine_name="mock",
            engine_version="1.0.0"
        )
    
    def set_mock_response(self, image_path: str, response: ExtractionResult):
        """Set mock response for a specific image path"""
        self.mock_responses[image_path] = response
    
    async def extract_text(self, image_path: str, prompt: Optional[str] = None) -> ExtractionResult:
        """Return mock extraction result"""
        import asyncio
        await asyncio.sleep(0.1)  # Simulate processing time
        
        if image_path in self.mock_responses:
            return self.mock_responses[image_path]
        
        return self.default_response
    
    async def extract_structured_data(
        self, 
        image_path: str, 
        schema: Dict[str, Any],
        prompt: Optional[str] = None
    ) -> ExtractionResult:
        """Return mock structured data extraction result"""
        import asyncio
        await asyncio.sleep(0.2)  # Simulate processing time
        
        # Generate mock structured data based on schema
        mock_data = {}
        for field_name, field_info in schema.items():
            if isinstance(field_info, dict) and "type" in field_info:
                field_type = field_info["type"]
                if field_type == "string":
                    mock_data[field_name] = f"mock_{field_name}"
                elif field_type == "number":
                    mock_data[field_name] = 123.45
                elif field_type == "date":
                    mock_data[field_name] = "2024-08-05"
                elif field_type == "boolean":
                    mock_data[field_name] = True
                else:
                    mock_data[field_name] = f"mock_{field_name}"
        
        return ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            extracted_data=mock_data,
            raw_text="Mock extracted text with structured data",
            confidence_score=0.90,
            engine_name="mock",
            engine_version="1.0.0"
        )
    
    def get_engine_info(self) -> EngineInfo:
        """Get mock engine information"""
        return EngineInfo(
            name="mock",
            version="1.0.0",
            description="Mock OCR engine for testing",
            supported_formats=[".jpg", ".png", ".pdf"],
            capabilities=["text_extraction", "structured_extraction", "multilingual"]
        )
    
    async def health_check(self) -> bool:
        """Mock engine is always healthy"""
        return True