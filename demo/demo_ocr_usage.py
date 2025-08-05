#!/usr/bin/env python3
"""
Universal OCR Tool 使用演示
演示如何在 SimaCode 中调用 OCR 工具
"""

import asyncio
import sys
import os

# 添加 src 目录到路径
sys.path.insert(0, 'src')

async def demo_ocr_usage():
    """演示 OCR 工具的使用方法"""
    
    print("🚀 Universal OCR Tool 使用演示")
    print("=" * 50)
    
    try:
        # 导入 OCR 工具
        from simacode.tools.universal_ocr import UniversalOCRTool, UniversalOCRInput
        
        print("✅ OCR 工具导入成功")
        
        # 检查测试文件
        test_file = "test_invoice.png"
        if not os.path.exists(test_file):
            print(f"❌ 测试文件不存在: {test_file}")
            return
        
        print(f"✅ 测试文件存在: {test_file}")
        
        print("\n" + "="*60)
        print("📋 模拟 SimaCode Chat 调用过程")
        print("="*60)
        
        print("\n👤 用户输入: '请帮我识别这个发票图片中的内容：test_invoice.png'")
        print("\n🤖 AI 分析: 这是一个文档识别任务，我将调用 universal_ocr 工具")
        
        # 步骤 1: 初始化工具
        print("\n🔧 步骤 1: 初始化 OCR 工具...")
        ocr_tool = UniversalOCRTool()
        print(f"   ✅ 工具初始化成功: {ocr_tool.name} v{ocr_tool.version}")
        
        # 步骤 2: 创建输入参数
        print("\n📝 步骤 2: 创建输入参数...")
        input_data = UniversalOCRInput(
            file_path=test_file,
            output_format="structured",  # 结构化输出
            scene_hint="invoice",        # 发票场景
            confidence_threshold=0.7,    # 置信度阈值
            quality_enhancement=True     # 启用质量增强
        )
        print("   ✅ 输入参数配置:")
        print(f"      - 文件: {input_data.file_path}")
        print(f"      - 格式: {input_data.output_format}")
        print(f"      - 场景: {input_data.scene_hint}")
        print(f"      - 置信度阈值: {input_data.confidence_threshold}")
        
        # 步骤 3: 权限检查
        print("\n🔐 步骤 3: 检查文件权限...")
        has_permission = await ocr_tool.check_permissions(input_data)
        if has_permission:
            print("   ✅ 权限检查通过")
        else:
            print("   ❌ 权限检查失败")
            return
        
        # 步骤 4: 执行 OCR
        print("\n🔍 步骤 4: 执行 OCR 识别...")
        print("-" * 40)
        
        results = []
        async for result in ocr_tool.execute(input_data):
            # 显示实时进度
            status_icon = {
                'info': '📄', 
                'success': '✅', 
                'error': '❌', 
                'warning': '⚠️'
            }.get(result.type.value, '📝')
            
            print(f"{status_icon} {result.type.value.upper()}: {result.content[:80]}...")
            results.append(result)
        
        print("-" * 40)
        
        # 步骤 5: 分析结果
        print("\n📊 步骤 5: 分析处理结果...")
        
        success_results = [r for r in results if r.type.value == 'success']
        error_results = [r for r in results if r.type.value == 'error']
        
        if success_results:
            print("✅ OCR 识别成功!")
            final_result = success_results[-1]
            
            print("\n🤖 AI 响应给用户:")
            print("=" * 50)
            print("我已成功识别了您的发票图片，以下是提取的信息：")
            print()
            
            # 显示部分结果内容
            content_preview = final_result.content[:800]
            print(content_preview)
            if len(final_result.content) > 800:
                print("\n... (内容较长，已截取部分显示)")
            
            print("=" * 50)
            
        elif error_results:
            print("❌ OCR 识别失败")
            for error in error_results[-2:]:  # 显示最后2个错误
                print(f"   错误: {error.content}")
        
        # 步骤 6: 显示统计
        print(f"\n📈 工具使用统计:")
        stats = ocr_tool.get_statistics()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        print(f"\n🎯 演示完成!")
        print(f"\n💡 在实际使用中，您只需要在 SimaCode Chat 中说：")
        print(f"   '请识别这个文档：{test_file}'")
        print(f"   AI 就会自动执行上述整个流程！")
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保 Universal OCR Tool 已正确安装")
    except Exception as e:
        print(f"❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主程序"""
    print("=" * 60)
    print("Universal OCR Tool - SimaCode 使用演示")
    print("=" * 60)
    print()
    print("这个演示展示了如何在 SimaCode Chat 中使用 OCR 工具")
    print("实际使用时，只需在聊天中输入识别请求即可")
    print()
    
    # 运行异步演示
    asyncio.run(demo_ocr_usage())

if __name__ == "__main__":
    main()