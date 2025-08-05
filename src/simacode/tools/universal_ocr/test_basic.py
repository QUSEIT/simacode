#!/usr/bin/env python3
"""
Basic test script for Universal OCR Tool Phase 1
This script validates core OCR functionality with minimal dependencies.
"""

import asyncio
import tempfile
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from .core import UniversalOCRTool
from .input_models import UniversalOCRInput


async def create_test_image() -> str:
    """Create a simple test image with text for OCR testing"""
    # Create a simple image with text
    width, height = 800, 400
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    # Try to use a system font, fallback to default if not available
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 36)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except (OSError, IOError):
            font = ImageFont.load_default()
    
    # Draw test text
    test_text = """Invoice #12345
Date: 2024-08-05
Customer: Test Company
Amount: $299.99
Description: OCR Testing Service"""
    
    draw.text((50, 50), test_text, fill='black', font=font)
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    image.save(temp_file.name, 'PNG')
    temp_file.close()
    
    return temp_file.name


async def test_basic_ocr():
    """Test basic OCR functionality"""
    print("🧪 Testing Universal OCR Tool - Phase 1")
    print("=" * 50)
    
    # Create test image
    print("📸 Creating test image...")
    test_image_path = await create_test_image()
    print(f"✅ Test image created: {test_image_path}")
    
    try:
        # Initialize OCR tool
        print("\n🔧 Initializing Universal OCR Tool...")
        ocr_tool = UniversalOCRTool()
        print(f"✅ Tool initialized: {ocr_tool.name} v{ocr_tool.version}")
        
        # Check tool health
        print("\n🏥 Checking tool health...")
        health_status = await ocr_tool.health_check()
        print(f"Health Status: {health_status['tool_status']}")
        
        for engine_name, engine_info in health_status['engines'].items():
            print(f"  - {engine_name}: {engine_info['status']}")
        
        # Create input parameters
        print("\n📝 Creating OCR input parameters...")
        input_data = UniversalOCRInput(
            file_path=test_image_path,
            output_format="json",
            scene_hint="invoice",
            confidence_threshold=0.7
        )
        print(f"✅ Input validated: {input_data.file_path}")
        
        # Test permission check
        print("\n🔐 Checking file permissions...")
        has_permission = await ocr_tool.check_permissions(input_data)
        print(f"Permission check: {'✅ PASSED' if has_permission else '❌ FAILED'}")
        
        if not has_permission:
            print("❌ Cannot proceed without file permissions")
            return
        
        # Execute OCR
        print("\n🔍 Executing OCR extraction...")
        results = []
        async for result in ocr_tool.execute(input_data):
            print(f"📄 {result.type.value}: {result.content[:100]}...")
            results.append(result)
        
        # Analyze results
        print(f"\n📊 OCR completed with {len(results)} results")
        
        success_results = [r for r in results if r.type.value == "success"]
        if success_results:
            print("✅ OCR extraction successful!")
            final_result = success_results[-1]
            
            # Print metadata
            if final_result.metadata:
                print(f"Engine used: {final_result.metadata.get('engine_used', 'unknown')}")
                print(f"Processing time: {final_result.metadata.get('processing_time', 0):.2f}s")
                print(f"Confidence: {final_result.metadata.get('confidence_score', 0):.1%}")
            
            # Show extracted content preview
            content_preview = final_result.content[:500]
            print(f"\n📄 Extracted content preview:\n{content_preview}")
            if len(final_result.content) > 500:
                print("... (truncated)")
                
        else:
            print("❌ OCR extraction failed")
            error_results = [r for r in results if r.type.value == "error"]
            for error in error_results:
                print(f"Error: {error.content}")
        
        # Show tool statistics
        print(f"\n📈 Tool Statistics:")
        stats = ocr_tool.get_statistics()
        for key, value in stats.items():
            print(f"  {key}: {value}")
            
    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup test image
        try:
            os.unlink(test_image_path)
            print(f"\n🧹 Cleaned up test image: {test_image_path}")
        except Exception as e:
            print(f"⚠️  Failed to cleanup test image: {e}")


async def test_config_loading():
    """Test configuration loading"""
    print("\n🔧 Testing configuration loading...")
    
    try:
        from .config import get_config, get_claude_config
        
        # Test main config
        config = get_config()
        print(f"✅ Main config loaded: max_file_size={config.max_file_size}")
        
        # Test Claude config
        claude_config = get_claude_config()
        print(f"✅ Claude config loaded: model={claude_config.model}")
        
        return True
        
    except Exception as e:
        print(f"❌ Config loading failed: {str(e)}")
        return False


async def main():
    """Main test function"""
    print("🚀 Universal OCR Tool - Phase 1 Basic Test")
    print("=" * 60)
    
    # Test configuration first
    config_ok = await test_config_loading()
    if not config_ok:
        print("❌ Configuration test failed, skipping OCR test")
        return
    
    # Test basic OCR functionality
    await test_basic_ocr()
    
    print("\n" + "=" * 60)
    print("🎯 Phase 1 basic test completed!")


if __name__ == "__main__":
    asyncio.run(main())