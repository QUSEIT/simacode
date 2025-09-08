"""
File Processing Module for Universal OCR

This module handles file processing, format conversion, and image preprocessing
for the Universal OCR tool.
"""

import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple, Union
import hashlib

try:
    import pdf2image
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

try:
    from PIL import Image, ImageEnhance, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class FileProcessorError(Exception):
    """Custom exception for file processing errors"""
    pass


class FileProcessor:
    """
    File processor for Universal OCR tool.
    
    Handles file format conversion, image preprocessing,
    and file validation operations.
    """
    
    def __init__(self):
        self.supported_image_formats = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}
        self.supported_document_formats = {'.pdf'}
        self.temp_files = []  # Track temporary files for cleanup
    
    def is_supported_format(self, file_path: str) -> bool:
        """Check if file format is supported"""
        suffix = Path(file_path).suffix.lower()
        return suffix in (self.supported_image_formats | self.supported_document_formats)
    
    def get_file_type(self, file_path: str) -> str:
        """Get file type category"""
        suffix = Path(file_path).suffix.lower()
        if suffix in self.supported_image_formats:
            return "image"
        elif suffix in self.supported_document_formats:
            return "document"
        else:
            return "unknown"
    
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of file for caching purposes"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            raise FileProcessorError(f"Failed to calculate file hash: {str(e)}")
    
    def validate_file(self, file_path: str, max_size: int = 10 * 1024 * 1024) -> Tuple[bool, str]:
        """
        Validate file for OCR processing.
        
        Args:
            file_path: Path to the file
            max_size: Maximum file size in bytes
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            path = Path(file_path)
            
            # Check if file exists
            if not path.exists():
                return False, f"File does not exist: {file_path}"
            
            # Check if it's a file
            if not path.is_file():
                return False, f"Path is not a file: {file_path}"
            
            # Check file size
            file_size = path.stat().st_size
            if file_size > max_size:
                size_mb = file_size / (1024 * 1024)
                max_mb = max_size / (1024 * 1024)
                return False, f"File too large: {size_mb:.1f}MB (max: {max_mb:.1f}MB)"
            
            # Check file format
            if not self.is_supported_format(file_path):
                return False, f"Unsupported file format: {path.suffix}"
            
            # Check file readability
            if not os.access(file_path, os.R_OK):
                return False, f"File is not readable: {file_path}"
            
            # Additional format-specific validation
            file_type = self.get_file_type(file_path)
            if file_type == "image":
                return self._validate_image_file(file_path)
            elif file_type == "document":
                return self._validate_document_file(file_path)
            
            return True, ""
            
        except Exception as e:
            return False, f"File validation error: {str(e)}"
    
    def _validate_image_file(self, file_path: str) -> Tuple[bool, str]:
        """Validate image file specifically"""
        if not PIL_AVAILABLE:
            return True, ""  # Skip validation if PIL not available
        
        try:
            with Image.open(file_path) as img:
                # Check image dimensions
                width, height = img.size
                if width < 50 or height < 50:
                    return False, f"Image too small: {width}x{height} (minimum: 50x50)"
                
                if width > 10000 or height > 10000:
                    return False, f"Image too large: {width}x{height} (maximum: 10000x10000)"
                
                # Verify image can be loaded
                img.verify()
                
            return True, ""
            
        except Exception as e:
            return False, f"Invalid image file: {str(e)}"
    
    def _validate_document_file(self, file_path: str) -> Tuple[bool, str]:
        """Validate document file specifically"""
        try:
            # For PDF files, try to get page count
            if file_path.lower().endswith('.pdf'):
                if not PDF2IMAGE_AVAILABLE:
                    return False, "pdf2image package not available. Install with: pip install pdf2image. Also need system dependency: brew install poppler (macOS) or apt-get install poppler-utils (Ubuntu)"
                
                try:
                    # Try to get info about the PDF
                    info = pdf2image.pdfinfo_from_path(file_path)
                    page_count = info.get("Pages", 0)
                    
                    if page_count == 0:
                        return False, "PDF file appears to be empty"
                    
                    if page_count > 50:
                        return False, f"PDF has too many pages: {page_count} (maximum: 50)"
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'poppler' in error_msg or 'pdftoppm' in error_msg:
                        return False, f"Poppler system dependency missing. Install with: brew install poppler (macOS) or apt-get install poppler-utils (Ubuntu). Original error: {str(e)}"
                    else:
                        return False, f"Cannot read PDF file: {str(e)}"
            
            return True, ""
            
        except Exception as e:
            return False, f"Document validation error: {str(e)}"
    
    async def process_file(self, file_path: str, enhance_quality: bool = True) -> List[str]:
        """
        Process file for OCR, converting to image format if needed.
        
        Args:
            file_path: Path to input file
            enhance_quality: Whether to apply quality enhancement
            
        Returns:
            List of image file paths ready for OCR
        """
        file_type = self.get_file_type(file_path)
        
        if file_type == "image":
            # Process image file
            processed_path = await self._process_image_file(file_path, enhance_quality)
            return [processed_path]
        
        elif file_type == "document":
            # Convert document to images
            image_paths = await self._convert_document_to_images(file_path)
            
            if enhance_quality:
                # Enhance each converted image
                enhanced_paths = []
                for img_path in image_paths:
                    enhanced_path = await self._enhance_image_quality(img_path)
                    enhanced_paths.append(enhanced_path)
                return enhanced_paths
            
            return image_paths
        
        else:
            raise FileProcessorError(f"Unsupported file type: {file_type}")
    
    async def _process_image_file(self, file_path: str, enhance_quality: bool) -> str:
        """Process image file"""
        if enhance_quality:
            return await self._enhance_image_quality(file_path)
        else:
            return file_path  # Return original path if no enhancement needed
    
    async def _convert_document_to_images(self, file_path: str) -> List[str]:
        """Convert document (PDF) to image files"""
        if not PDF2IMAGE_AVAILABLE:
            raise FileProcessorError(
                "pdf2image package not available. Install with: pip install pdf2image. Also need system dependency: brew install poppler (macOS) or apt-get install poppler-utils (Ubuntu)"
            )
        
        try:
            # Convert PDF to images
            images = pdf2image.convert_from_path(
                file_path,
                dpi=300,  # High DPI for better OCR quality
                fmt='PNG',
                thread_count=2
            )
            
            image_paths = []
            base_name = Path(file_path).stem
            
            for i, image in enumerate(images):
                # Create temporary file for each page
                temp_file = tempfile.NamedTemporaryFile(
                    suffix=f"_{base_name}_page_{i+1}.png",
                    delete=False,
                    dir=tempfile.gettempdir()
                )
                temp_path = temp_file.name
                temp_file.close()
                
                # Save image
                image.save(temp_path, 'PNG', optimize=True)
                image_paths.append(temp_path)
                self.temp_files.append(temp_path)
            
            return image_paths
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'poppler' in error_msg or 'pdftoppm' in error_msg:
                raise FileProcessorError(f"Poppler system dependency missing. Install with: brew install poppler (macOS) or apt-get install poppler-utils (Ubuntu). Original error: {str(e)}")
            else:
                raise FileProcessorError(f"Failed to convert PDF to images: {str(e)}")
    
    async def _enhance_image_quality(self, image_path: str) -> str:
        """Enhance image quality for better OCR results"""
        if not PIL_AVAILABLE:
            return image_path  # Return original if PIL not available
        
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Apply enhancement filters
                enhanced_img = img
                
                # Sharpen the image
                enhanced_img = enhanced_img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
                
                # Enhance contrast
                enhancer = ImageEnhance.Contrast(enhanced_img)
                enhanced_img = enhancer.enhance(1.2)
                
                # Enhance sharpness
                enhancer = ImageEnhance.Sharpness(enhanced_img)
                enhanced_img = enhancer.enhance(1.1)
                
                # If image is very large, resize for better processing speed
                width, height = enhanced_img.size
                max_dimension = 3000
                
                if width > max_dimension or height > max_dimension:
                    ratio = min(max_dimension / width, max_dimension / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    enhanced_img = enhanced_img.resize((new_width, new_height), Image.LANCZOS)
                
                # Save enhanced image to temporary file
                base_name = Path(image_path).stem
                temp_file = tempfile.NamedTemporaryFile(
                    suffix=f"_{base_name}_enhanced.png",
                    delete=False,
                    dir=tempfile.gettempdir()
                )
                temp_path = temp_file.name
                temp_file.close()
                
                enhanced_img.save(temp_path, 'PNG', optimize=True, quality=95)
                self.temp_files.append(temp_path)
                
                return temp_path
        
        except Exception as e:
            # If enhancement fails, return original image
            print(f"Warning: Image enhancement failed: {e}")
            return image_path
    
    def cleanup_temp_files(self):
        """Clean up temporary files created during processing"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                print(f"Warning: Failed to delete temporary file {temp_file}: {e}")
        
        self.temp_files.clear()
    
    def get_image_info(self, image_path: str) -> dict:
        """Get information about an image file"""
        if not PIL_AVAILABLE:
            return {"error": "PIL not available"}
        
        try:
            with Image.open(image_path) as img:
                return {
                    "format": img.format,
                    "mode": img.mode,
                    "size": img.size,
                    "width": img.width,
                    "height": img.height,
                    "has_transparency": img.mode in ('RGBA', 'LA') or 'transparency' in img.info
                }
        except Exception as e:
            return {"error": str(e)}
    
    def __del__(self):
        """Cleanup temporary files when object is destroyed"""
        self.cleanup_temp_files()