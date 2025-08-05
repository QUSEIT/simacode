"""
Input Models for Universal OCR Tool

This module defines Pydantic models for validating and parsing
input parameters for the Universal OCR tool.
"""

import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator, model_validator

from ..base import ToolInput


class UniversalOCRInput(ToolInput):
    """
    Input model for Universal OCR tool.
    
    This model validates and parses all input parameters for OCR operations,
    ensuring data integrity and providing helpful error messages.
    """
    
    # Required parameters
    file_path: str = Field(
        ..., 
        description="Path to the image or document file to process (supports JPG, PNG, PDF, etc.). Can also be referred to as image_path.",
        example="/path/to/document.jpg"
    )
    
    # Output configuration
    output_format: str = Field(
        "json",
        description="Output format for extracted data",
        pattern="^(json|structured|raw)$"
    )
    
    # OCR configuration
    confidence_threshold: float = Field(
        0.8,
        description="Minimum confidence threshold for extraction results",
        ge=0.0,
        le=1.0
    )
    
    # Scene and template configuration
    scene_hint: Optional[str] = Field(
        None,
        description="Hint about document type to improve recognition",
        example="invoice"
    )
    
    template_override: Optional[str] = Field(
        None,
        description="Force use of specific template by ID",
        example="builtin/invoice"
    )
    
    # Engine configuration
    engines: List[str] = Field(
        default_factory=lambda: ["claude", "paddleocr"],
        description="List of OCR engines to use in priority order"
    )
    
    # Processing options
    use_cache: bool = Field(
        True,
        description="Whether to use cached results for identical files"
    )
    
    quality_enhancement: bool = Field(
        True,
        description="Whether to apply image quality enhancement preprocessing"
    )
    
    extract_confidence: bool = Field(
        False,
        description="Whether to return field-level confidence scores"
    )
    
    # Advanced options
    max_retries: int = Field(
        3,
        description="Maximum number of retry attempts for failed extractions",
        ge=0,
        le=10
    )
    
    timeout: Optional[int] = Field(
        None,
        description="Timeout in seconds for OCR operation",
        ge=1,
        le=300
    )
    
    custom_prompt: Optional[str] = Field(
        None,
        description="Custom extraction prompt to override default behavior"
    )
    
    # Model-level validation for parameter aliases
    @model_validator(mode='before')
    @classmethod
    def handle_parameter_aliases(cls, data):
        """Handle parameter aliases like image_path -> file_path"""
        if isinstance(data, dict):
            # Handle image_path alias
            if 'image_path' in data and 'file_path' not in data:
                data['file_path'] = data.pop('image_path')
            
            # Handle other potential aliases
            aliases = {
                'path': 'file_path',
                'document_path': 'file_path',
                'img_path': 'file_path'
            }
            
            for alias, target in aliases.items():
                if alias in data and target not in data:
                    data[target] = data.pop(alias)
        
        return data
    
    # Validation methods
    @validator('file_path')
    def validate_file_path(cls, v):
        """Validate file path exists and is accessible"""
        if not v or not v.strip():
            raise ValueError("File path cannot be empty")
        
        path = Path(v.strip())
        
        # Check if file exists
        if not path.exists():
            raise ValueError(f"File does not exist: {v}")
        
        # Check if it's a file (not directory)
        if not path.is_file():
            raise ValueError(f"Path is not a file: {v}")
        
        # Check file permissions
        if not os.access(path, os.R_OK):
            raise ValueError(f"File is not readable: {v}")
        
        return str(path.absolute())
    
    @validator('output_format')
    def validate_output_format(cls, v):
        """Validate output format"""
        valid_formats = {"json", "structured", "raw"}
        if v not in valid_formats:
            raise ValueError(f"Invalid output format. Must be one of: {', '.join(valid_formats)}")
        return v
    
    @validator('engines')
    def validate_engines(cls, v):
        """Validate engine list"""
        if not v:
            raise ValueError("At least one engine must be specified")
        
        valid_engines = {"claude", "paddleocr", "tesseract", "openai"}
        invalid_engines = set(v) - valid_engines
        
        if invalid_engines:
            raise ValueError(f"Invalid engines: {', '.join(invalid_engines)}. "
                           f"Valid engines: {', '.join(valid_engines)}")
        
        return v
    
    @validator('scene_hint')
    def validate_scene_hint(cls, v):
        """Validate scene hint"""
        if v is not None:
            v = v.strip().lower()
            if not v:
                return None
            
            # Define valid scene hints (can be extended)
            valid_scenes = {
                "invoice", "receipt", "transcript", "bank_statement",
                "order", "waybill", "contract", "form", "table",
                "handwritten", "printed", "mixed"
            }
            
            # Allow custom scene hints, just provide warning for unknown ones
            if v not in valid_scenes:
                # This is just a warning, not an error
                pass
            
            return v
        return v
    
    @validator('template_override')
    def validate_template_override(cls, v):
        """Validate template override format"""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            
            # Template ID should follow pattern: category/name or user_id/name
            if '/' not in v:
                raise ValueError("Template ID must be in format 'category/name' or 'user_id/name'")
            
            return v
        return v
    
    @validator('custom_prompt')
    def validate_custom_prompt(cls, v):
        """Validate custom prompt"""
        if v is not None:
            v = v.strip()
            if len(v) > 5000:
                raise ValueError("Custom prompt cannot exceed 5000 characters")
            if len(v) < 10:
                raise ValueError("Custom prompt must be at least 10 characters")
            return v
        return v
    
    def get_file_info(self) -> Dict[str, Any]:
        """Get information about the input file"""
        path = Path(self.file_path)
        stat = path.stat()
        
        return {
            "file_name": path.name,
            "file_size": stat.st_size,
            "file_extension": path.suffix.lower(),
            "modified_time": stat.st_mtime,
            "absolute_path": str(path.absolute())
        }
    
    def is_image_file(self) -> bool:
        """Check if the file is an image"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}
        return Path(self.file_path).suffix.lower() in image_extensions
    
    def is_pdf_file(self) -> bool:
        """Check if the file is a PDF"""
        return Path(self.file_path).suffix.lower() == '.pdf'
    
    def get_primary_engine(self) -> str:
        """Get the primary (first) engine from the list"""
        return self.engines[0] if self.engines else "claude"
    
    def has_custom_configuration(self) -> bool:
        """Check if any custom configuration options are set"""
        return bool(
            self.scene_hint or 
            self.template_override or 
            self.custom_prompt or
            self.confidence_threshold != 0.8 or
            not self.use_cache or
            not self.quality_enhancement
        )


class BatchOCRInput(BaseModel):
    """
    Input model for batch OCR processing.
    
    This model handles validation for processing multiple documents
    in a single operation.
    """
    
    documents: List[UniversalOCRInput] = Field(
        ...,
        description="List of documents to process",
        min_items=1,
        max_items=100
    )
    
    batch_settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Batch processing settings"
    )
    
    max_concurrent: int = Field(
        5,
        description="Maximum number of concurrent processing tasks",
        ge=1,
        le=20
    )
    
    fail_fast: bool = Field(
        False,
        description="Whether to stop processing on first failure"
    )
    
    progress_callback: Optional[str] = Field(
        None,
        description="Callback URL for progress updates"
    )
    
    @validator('documents')
    def validate_documents(cls, v):
        """Validate document list"""
        if not v:
            raise ValueError("At least one document must be provided")
        
        # Check for duplicate file paths
        file_paths = [doc.file_path for doc in v]
        if len(file_paths) != len(set(file_paths)):
            raise ValueError("Duplicate file paths found in document list")
        
        return v
    
    def get_total_size(self) -> int:
        """Get total size of all files in bytes"""
        total_size = 0
        for doc in self.documents:
            try:
                total_size += Path(doc.file_path).stat().st_size
            except (OSError, FileNotFoundError):
                pass  # Skip files that can't be accessed
        return total_size
    
    def get_file_types_summary(self) -> Dict[str, int]:
        """Get summary of file types in the batch"""
        types = {}
        for doc in self.documents:
            ext = Path(doc.file_path).suffix.lower()
            types[ext] = types.get(ext, 0) + 1
        return types


class TemplateTestInput(BaseModel):
    """
    Input model for testing templates against sample documents.
    """
    
    template_id: str = Field(
        ...,
        description="ID of the template to test"
    )
    
    test_images: List[str] = Field(
        ...,
        description="List of test image paths",
        min_items=1,
        max_items=20
    )
    
    expected_results: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Expected extraction results for validation"
    )
    
    generate_report: bool = Field(
        True,
        description="Whether to generate a detailed test report"
    )
    
    @validator('test_images')
    def validate_test_images(cls, v):
        """Validate test image paths"""
        for image_path in v:
            path = Path(image_path)
            if not path.exists():
                raise ValueError(f"Test image does not exist: {image_path}")
            if not path.is_file():
                raise ValueError(f"Test image path is not a file: {image_path}")
        return v