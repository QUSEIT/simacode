"""
Universal OCR Tool Core Implementation

The main UniversalOCRTool class that orchestrates OCR operations
using different engines and provides a unified interface.
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, Optional, Type, List

from ..base import Tool, ToolResult, ToolResultType
from .input_models import UniversalOCRInput
from .engines import ClaudeEngine, ExtractionResult, ExtractionStatus
from .config import get_config
from .file_processor import FileProcessor, FileProcessorError


class UniversalOCRTool(Tool):
    """
    Universal OCR Tool main class.
    
    This tool provides intelligent document recognition capabilities
    using multiple OCR engines with template-driven extraction.
    """
    
    def __init__(self):
        super().__init__(
            name="universal_ocr",
            description="Universal OCR and image text recognition tool for extracting text from images, PDFs, invoices, receipts, and documents. Supports intelligent document processing with scene detection.",
            version="1.0.0"
        )
        
        # Load configuration
        self.config = get_config()
        
        # Initialize OCR engines
        self.engines = {}
        self._initialize_engines()
        
        # Initialize file processor
        self.file_processor = FileProcessor()
        
        # Statistics tracking
        self.stats = {
            "total_processed": 0,
            "successful_extractions": 0,
            "failed_extractions": 0,
            "total_processing_time": 0.0,
            "engine_usage": {},
            "file_format_usage": {}
        }
    
    def _initialize_engines(self):
        """Initialize available OCR engines"""
        try:
            # Initialize Claude engine (primary)
            self.engines["claude"] = ClaudeEngine()
        except Exception as e:
            print(f"Warning: Failed to initialize Claude engine: {e}")
        
        # TODO: Initialize other engines in future phases
        # self.engines["paddleocr"] = PaddleOCREngine()
        # self.engines["tesseract"] = TesseractEngine()
    
    def get_input_schema(self) -> Type[UniversalOCRInput]:
        """Return the input schema for this tool"""
        return UniversalOCRInput
    
    async def validate_input(self, input_data: Dict[str, Any]) -> UniversalOCRInput:
        """Validate and parse tool input data"""
        return UniversalOCRInput(**input_data)
    
    async def check_permissions(self, input_data: UniversalOCRInput) -> bool:
        """Check if tool has permission to process the file"""
        try:
            # Use file processor for comprehensive validation
            is_valid, error_msg = self.file_processor.validate_file(
                input_data.file_path, 
                self.config.max_file_size
            )
            
            if not is_valid:
                print(f"File validation failed: {error_msg}")
            
            return is_valid
            
        except Exception as e:
            print(f"Permission check failed: {str(e)}")
            return False
    
    async def execute(self, input_data: UniversalOCRInput) -> AsyncGenerator[ToolResult, None]:
        """Execute OCR extraction"""
        start_time = time.time()
        execution_id = input_data.execution_id
        
        try:
            # Update statistics
            self.stats["total_processed"] += 1
            
            # Process file (convert PDF to images, enhance quality, etc.)
            yield ToolResult(
                type=ToolResultType.INFO,
                content="Processing input file",
                execution_id=execution_id,
                metadata=input_data.get_file_info()
            )
            
            try:
                processed_images = await self.file_processor.process_file(
                    input_data.file_path,
                    enhance_quality=input_data.quality_enhancement
                )
                
                if len(processed_images) > 1:
                    yield ToolResult(
                        type=ToolResultType.INFO,
                        content=f"Document converted to {len(processed_images)} page(s)",
                        execution_id=execution_id
                    )
            
            except FileProcessorError as e:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"File processing failed: {str(e)}",
                    execution_id=execution_id
                )
                return
            
            # Yield initial progress
            yield ToolResult(
                type=ToolResultType.INFO,
                content="Starting OCR extraction",
                execution_id=execution_id,
                metadata={
                    "total_pages": len(processed_images),
                    "file_info": input_data.get_file_info()
                }
            )
            
            # Determine OCR engine to use
            engine_name = self._select_engine(input_data)
            if engine_name not in self.engines:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"OCR engine '{engine_name}' not available",
                    execution_id=execution_id
                )
                return
            
            engine = self.engines[engine_name]
            
            # Update engine usage statistics
            self.stats["engine_usage"][engine_name] = \
                self.stats["engine_usage"].get(engine_name, 0) + 1
            
            # Check engine health
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Using {engine_name} engine for extraction",
                execution_id=execution_id
            )
            
            if not await engine.health_check():
                yield ToolResult(
                    type=ToolResultType.WARNING,
                    content=f"{engine_name} engine health check failed, attempting extraction anyway",
                    execution_id=execution_id
                )
            
            # Perform OCR extraction on processed images
            all_extractions = []
            
            for i, image_path in enumerate(processed_images):
                try:
                    if len(processed_images) > 1:
                        yield ToolResult(
                            type=ToolResultType.INFO,
                            content=f"Processing page {i+1} of {len(processed_images)}",
                            execution_id=execution_id
                        )
                    
                    if input_data.custom_prompt or input_data.scene_hint:
                        # Use custom or scene-specific prompt
                        prompt = input_data.custom_prompt or self._create_scene_prompt(input_data.scene_hint)
                        extraction_result = await engine.extract_text(image_path, prompt)
                    else:
                        # Use default extraction
                        extraction_result = await engine.extract_text(image_path)
                    
                    # Add page information to metadata
                    if len(processed_images) > 1:
                        extraction_result.metadata["page_number"] = i + 1
                        extraction_result.metadata["total_pages"] = len(processed_images)
                    
                    all_extractions.append(extraction_result)
                
                except Exception as e:
                    yield ToolResult(
                        type=ToolResultType.ERROR,
                        content=f"OCR extraction failed for page {i+1}: {str(e)}",
                        execution_id=execution_id,
                        metadata={"error_type": type(e).__name__, "engine": engine_name, "page": i+1}
                    )
                    self.stats["failed_extractions"] += 1
                    return
            
            # Combine results if multiple pages
            if len(all_extractions) == 1:
                # Single page/image
                extraction_result = all_extractions[0]
            else:
                # Multiple pages - combine results
                extraction_result = self._combine_extraction_results(all_extractions)
                
            # Process final extraction result
            async for result in self._process_extraction_result(
                extraction_result, input_data, execution_id, start_time
            ):
                yield result
        
        except Exception as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Unexpected error during OCR processing: {str(e)}",
                execution_id=execution_id,
                metadata={"error_type": type(e).__name__}
            )
            self.stats["failed_extractions"] += 1
        
        finally:
            # Clean up temporary files
            self.file_processor.cleanup_temp_files()
            
            # Update processing time statistics
            processing_time = time.time() - start_time
            self.stats["total_processing_time"] += processing_time
    
    def _select_engine(self, input_data: UniversalOCRInput) -> str:
        """Select the best OCR engine for the given input"""
        # For Phase 1, always use Claude engine
        # TODO: Implement intelligent engine selection in future phases
        
        available_engines = [engine for engine in input_data.engines if engine in self.engines]
        
        if not available_engines:
            # Fallback to any available engine
            if "claude" in self.engines:
                return "claude"
            elif self.engines:
                return list(self.engines.keys())[0]
            else:
                raise RuntimeError("No OCR engines available")
        
        return available_engines[0]
    
    def _combine_extraction_results(self, extractions: List[ExtractionResult]) -> ExtractionResult:
        """Combine multiple extraction results into a single result"""
        if not extractions:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                errors=["No extraction results to combine"],
                engine_name=self.engines.get("claude", {}).name if self.engines else "unknown",
                engine_version="1.0.0"
            )
        
        # Determine overall status
        successful_count = sum(1 for ext in extractions if ext.status == ExtractionStatus.SUCCESS)
        partial_count = sum(1 for ext in extractions if ext.status == ExtractionStatus.PARTIAL)
        
        if successful_count == len(extractions):
            combined_status = ExtractionStatus.SUCCESS
        elif successful_count + partial_count > 0:
            combined_status = ExtractionStatus.PARTIAL
        else:
            combined_status = ExtractionStatus.FAILED
        
        # Combine raw text
        combined_text_parts = []
        for i, ext in enumerate(extractions):
            if ext.raw_text:
                page_header = f"\n--- Page {i+1} ---\n" if len(extractions) > 1 else ""
                combined_text_parts.append(f"{page_header}{ext.raw_text}")
        
        combined_raw_text = "\n".join(combined_text_parts)
        
        # Combine structured data if available
        combined_extracted_data = {}
        if all(ext.extracted_data for ext in extractions):
            # If all pages have structured data, combine them
            for i, ext in enumerate(extractions):
                page_key = f"page_{i+1}" if len(extractions) > 1 else "data"
                combined_extracted_data[page_key] = ext.extracted_data
        
        # Calculate average confidence
        valid_confidences = [ext.confidence_score for ext in extractions if ext.confidence_score > 0]
        avg_confidence = sum(valid_confidences) / len(valid_confidences) if valid_confidences else 0.0
        
        # Combine errors
        all_errors = []
        for i, ext in enumerate(extractions):
            if ext.errors:
                page_errors = [f"Page {i+1}: {error}" for error in ext.errors]
                all_errors.extend(page_errors)
        
        # Calculate total processing time
        total_processing_time = sum(ext.processing_time for ext in extractions)
        
        # Use first extraction's engine info
        first_extraction = extractions[0]
        
        # Combine metadata
        combined_metadata = {
            "total_pages": len(extractions),
            "successful_pages": successful_count,
            "partial_pages": partial_count,
            "failed_pages": len(extractions) - successful_count - partial_count,
            "individual_processing_times": [ext.processing_time for ext in extractions]
        }
        
        # Add individual page metadata if available
        for i, ext in enumerate(extractions):
            if ext.metadata:
                combined_metadata[f"page_{i+1}_metadata"] = ext.metadata
        
        return ExtractionResult(
            status=combined_status,
            extracted_data=combined_extracted_data,
            raw_text=combined_raw_text,
            confidence_score=avg_confidence,
            processing_time=total_processing_time,
            engine_name=first_extraction.engine_name,
            engine_version=first_extraction.engine_version,
            metadata=combined_metadata,
            errors=all_errors
        )
    
    def _create_scene_prompt(self, scene_hint: Optional[str]) -> str:
        """Create a scene-specific extraction prompt"""
        if not scene_hint:
            return None
        
        scene_prompts = {
            "invoice": """Please carefully examine this invoice image and extract the following information:
- Invoice number
- Invoice date
- Vendor/seller information (name, address)
- Customer/buyer information (name, address)
- Line items with descriptions, quantities, unit prices, and totals
- Subtotal, tax amounts, and final total
- Payment terms or due date

Provide the extracted information in a clear, structured format.""",
            
            "receipt": """Please examine this receipt and extract:
- Store/vendor name
- Purchase date and time
- Items purchased with prices
- Subtotal, tax, and total amount
- Payment method
- Transaction ID or receipt number

Format the information clearly and completely.""",
            
            "transcript": """Please extract information from this academic transcript:
- Student name and ID
- Institution name
- Academic period/semester
- Course listings with course codes, names, credits, and grades
- GPA or grade point average
- Degree information

Present the information in an organized format.""",
            
            "bank_statement": """Please extract data from this bank statement:
- Account holder name
- Account number
- Statement period
- Beginning and ending balance
- Transaction details (date, description, amount, balance)
- Bank information

Organize the extracted information clearly."""
        }
        
        return scene_prompts.get(scene_hint.lower()) or f"""Please examine this {scene_hint} document and extract all relevant information in a structured format."""
    
    async def _process_extraction_result(
        self, 
        extraction_result: ExtractionResult,
        input_data: UniversalOCRInput,
        execution_id: str,
        start_time: float
    ) -> AsyncGenerator[ToolResult, None]:
        """Process and format extraction results"""
        
        if extraction_result.status == ExtractionStatus.SUCCESS:
            self.stats["successful_extractions"] += 1
            
            # Check confidence threshold
            if extraction_result.confidence_score < input_data.confidence_threshold:
                yield ToolResult(
                    type=ToolResultType.WARNING,
                    content=f"Extraction confidence ({extraction_result.confidence_score:.2f}) "
                           f"below threshold ({input_data.confidence_threshold:.2f})",
                    execution_id=execution_id
                )
            
            # Format output according to requested format
            formatted_output = await self._format_output(extraction_result, input_data)
            
            # Create output result for task chaining
            yield ToolResult(
                type=ToolResultType.OUTPUT,
                content=formatted_output,
                execution_id=execution_id,
                metadata={
                    "file_path": input_data.file_path,
                    "engine_used": extraction_result.engine_name,
                    "processing_time": extraction_result.processing_time,
                    "confidence_score": extraction_result.confidence_score,
                    "output_format": input_data.output_format,
                    "total_processing_time": time.time() - start_time
                }
            )
            
            # Also create success result for completion status
            yield ToolResult(
                type=ToolResultType.SUCCESS,
                content=f"Successfully extracted text from {input_data.file_path}",
                execution_id=execution_id
            )
            
        elif extraction_result.status == ExtractionStatus.PARTIAL:
            self.stats["successful_extractions"] += 1  # Count as success with warnings
            
            yield ToolResult(
                type=ToolResultType.WARNING,
                content=f"Partial extraction completed with errors: {'; '.join(extraction_result.errors)}",
                execution_id=execution_id
            )
            
            # Still provide partial results for task chaining
            formatted_output = await self._format_output(extraction_result, input_data)
            yield ToolResult(
                type=ToolResultType.OUTPUT,
                content=formatted_output,
                execution_id=execution_id,
                metadata={
                    "file_path": input_data.file_path,
                    "engine_used": extraction_result.engine_name,
                    "processing_time": extraction_result.processing_time,
                    "confidence_score": extraction_result.confidence_score,
                    "output_format": input_data.output_format,
                    "partial_extraction": True,
                    "errors": extraction_result.errors
                }
            )
            
        else:  # FAILED
            self.stats["failed_extractions"] += 1
            
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"OCR extraction failed: {'; '.join(extraction_result.errors)}",
                execution_id=execution_id,
                metadata={
                    "file_path": input_data.file_path,
                    "engine_used": extraction_result.engine_name,
                    "processing_time": extraction_result.processing_time,
                    "errors": extraction_result.errors
                }
            )
    
    async def _format_output(self, extraction_result: ExtractionResult, input_data: UniversalOCRInput) -> str:
        """Format extraction results according to requested output format"""
        
        if input_data.output_format == "raw":
            return extraction_result.raw_text
        
        elif input_data.output_format == "structured":
            return self._format_structured_output(extraction_result, input_data)
        
        else:  # json format (default)
            return self._format_json_output(extraction_result, input_data)
    
    def _format_json_output(self, extraction_result: ExtractionResult, input_data: UniversalOCRInput) -> str:
        """Format output as JSON"""
        output_data = {
            "meta": {
                "file_path": input_data.file_path,
                "file_info": input_data.get_file_info(),
                "processing_time": extraction_result.processing_time,
                "engine_used": extraction_result.engine_name,
                "confidence_score": extraction_result.confidence_score,
                "output_format": input_data.output_format,
                "scene_hint": input_data.scene_hint,
                "timestamp": extraction_result.timestamp.isoformat()
            },
            "extracted_data": extraction_result.extracted_data if extraction_result.extracted_data else {
                "raw_text": extraction_result.raw_text
            },
            "raw_text": extraction_result.raw_text if input_data.output_format != "raw" else None
        }
        
        # Add confidence scores if requested
        if input_data.extract_confidence and hasattr(extraction_result, 'field_confidence'):
            output_data["confidence_scores"] = getattr(extraction_result, 'field_confidence', {})
        
        # Add errors if any
        if extraction_result.errors:
            output_data["errors"] = extraction_result.errors
        
        return json.dumps(output_data, ensure_ascii=False, indent=2)
    
    def _format_structured_output(self, extraction_result: ExtractionResult, input_data: UniversalOCRInput) -> str:
        """Format output as structured text"""
        lines = []
        lines.append("=== OCR Extraction Results ===")
        lines.append("")
        
        # Meta information
        lines.append("📋 Processing Information:")
        lines.append(f"  File: {Path(input_data.file_path).name}")
        lines.append(f"  Engine: {extraction_result.engine_name}")
        lines.append(f"  Processing Time: {extraction_result.processing_time:.2f}s")
        lines.append(f"  Confidence: {extraction_result.confidence_score:.1%}")
        if input_data.scene_hint:
            lines.append(f"  Scene: {input_data.scene_hint}")
        lines.append("")
        
        # Structured data if available
        if extraction_result.extracted_data:
            lines.append("📊 Extracted Data:")
            for key, value in extraction_result.extracted_data.items():
                if isinstance(value, dict):
                    lines.append(f"  {key}:")
                    for sub_key, sub_value in value.items():
                        lines.append(f"    {sub_key}: {sub_value}")
                elif isinstance(value, list):
                    lines.append(f"  {key}:")
                    for i, item in enumerate(value, 1):
                        if isinstance(item, dict):
                            lines.append(f"    {i}. {item}")
                        else:
                            lines.append(f"    {i}. {item}")
                else:
                    lines.append(f"  {key}: {value}")
            lines.append("")
        
        # Raw text
        if extraction_result.raw_text:
            lines.append("📝 Raw Extracted Text:")
            lines.append(extraction_result.raw_text)
            lines.append("")
        
        # Errors if any
        if extraction_result.errors:
            lines.append("⚠️ Errors/Warnings:")
            for error in extraction_result.errors:
                lines.append(f"  - {error}")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tool usage statistics"""
        total_processed = self.stats["total_processed"]
        
        if total_processed > 0:
            success_rate = self.stats["successful_extractions"] / total_processed
            avg_processing_time = self.stats["total_processing_time"] / total_processed
        else:
            success_rate = 0.0
            avg_processing_time = 0.0
        
        return {
            "total_processed": total_processed,
            "successful_extractions": self.stats["successful_extractions"],
            "failed_extractions": self.stats["failed_extractions"],
            "success_rate": f"{success_rate:.1%}",
            "average_processing_time": f"{avg_processing_time:.2f}s",
            "engine_usage": self.stats["engine_usage"],
            "file_format_usage": self.stats["file_format_usage"]
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health status of the tool and its engines"""
        health_status = {
            "tool_status": "healthy",
            "engines": {},
            "configuration": "loaded"
        }
        
        # Check each engine
        for engine_name, engine in self.engines.items():
            try:
                engine_healthy = await engine.health_check()
                health_status["engines"][engine_name] = {
                    "status": "healthy" if engine_healthy else "unhealthy",
                    "info": engine.get_engine_info().to_dict() if hasattr(engine.get_engine_info(), 'to_dict') else str(engine.get_engine_info())
                }
            except Exception as e:
                health_status["engines"][engine_name] = {
                    "status": "error",
                    "error": str(e)
                }
        
        # Overall health
        if not health_status["engines"] or not any(
            engine_info["status"] == "healthy" 
            for engine_info in health_status["engines"].values()
        ):
            health_status["tool_status"] = "unhealthy"
        
        return health_status


# Register the Universal OCR Tool
from ..base import ToolRegistry
universal_ocr_tool = UniversalOCRTool()
ToolRegistry.register(universal_ocr_tool)