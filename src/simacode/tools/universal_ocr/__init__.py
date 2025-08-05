"""
Universal OCR Tool for SimaCode

A universal OCR recognition tool that supports multiple document types
through a template-driven, extensible architecture.
"""

from .core import UniversalOCRTool
from .input_models import UniversalOCRInput

__version__ = "1.0.0"
__all__ = ["UniversalOCRTool", "UniversalOCRInput"]