#!/usr/bin/env python3
"""
Phase 3 MCP Integration Test Runner

This script runs all Phase 3 integration tests and provides comprehensive
reporting on the MCP tool integration and registration system.
"""

import sys
import os
import subprocess
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

def run_test_suite(test_file: Path, test_name: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Run a specific test suite and return results.
    
    Args:
        test_file: Path to test file
        test_name: Name of test suite
        
    Returns:
        Tuple[bool, Dict[str, Any]]: (success, results)
    """
    print(f"\n{'='*60}")
    print(f"Running {test_name}")
    print(f"{'='*60}")
    
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_file),
        "-v",
        "--tb=short",
        "--json-report",
        "--json-report-file=/tmp/pytest_report.json"
    ]
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Read JSON report if available
        report_data = {}
        try:
            with open('/tmp/pytest_report.json', 'r') as f:
                report_data = json.load(f)
        except:
            pass
        
        success = result.returncode == 0
        
        # Print output
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        # Extract key metrics
        test_results = {
            "success": success,
            "duration": duration,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "report_data": report_data
        }
        
        # Parse pytest output for test counts
        if "collected" in result.stdout:
            lines = result.stdout.split('\n')
            for line in lines:
                if "passed" in line and ("failed" in line or "error" in line):
                    test_results["summary_line"] = line.strip()
                    break
        
        print(f"\n{test_name} Results:")
        print(f"Success: {success}")
        print(f"Duration: {duration:.2f}s")
        if "summary_line" in test_results:
            print(f"Summary: {test_results['summary_line']}")
        
        return success, test_results
        
    except subprocess.TimeoutExpired:
        print(f"❌ {test_name} timed out after 5 minutes")
        return False, {
            "success": False,
            "duration": 300,
            "error": "timeout",
            "return_code": -1
        }
    except Exception as e:
        print(f"❌ {test_name} failed with exception: {str(e)}")
        return False, {
            "success": False,
            "duration": 0,
            "error": str(e),
            "return_code": -1
        }


def check_test_dependencies() -> bool:
    """Check if required test dependencies are available."""
    
    print("Checking test dependencies...")
    
    required_packages = [
        "pytest",
        "pytest-asyncio",
        "pytest-json-report"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("Install with: pip install " + " ".join(missing_packages))
        return False
    
    print("✅ All test dependencies are available")
    return True


def validate_test_files(test_files: List[Path]) -> bool:
    """Validate that all test files exist and are readable."""
    
    print("Validating test files...")
    
    for test_file in test_files:
        if not test_file.exists():
            print(f"❌ Test file not found: {test_file}")
            return False
        
        if not test_file.is_file():
            print(f"❌ Not a file: {test_file}")
            return False
        
        try:
            with open(test_file, 'r') as f:
                content = f.read()
                if len(content) < 100:  # Basic sanity check
                    print(f"❌ Test file appears to be empty or too small: {test_file}")
                    return False
        except Exception as e:
            print(f"❌ Cannot read test file {test_file}: {str(e)}")
            return False
    
    print("✅ All test files are valid")
    return True


def generate_test_report(results: Dict[str, Tuple[bool, Dict[str, Any]]]) -> None:
    """Generate a comprehensive test report."""
    
    print(f"\n{'='*80}")
    print("PHASE 3 MCP INTEGRATION TEST REPORT")
    print(f"{'='*80}")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Overall summary
    total_suites = len(results)
    successful_suites = sum(1 for success, _ in results.values() if success)
    failed_suites = total_suites - successful_suites
    total_duration = sum(data["duration"] for _, data in results.values())
    
    print(f"\nOVERALL SUMMARY:")
    print(f"  Total test suites: {total_suites}")
    print(f"  Successful suites: {successful_suites}")
    print(f"  Failed suites: {failed_suites}")
    print(f"  Total duration: {total_duration:.2f}s")
    print(f"  Success rate: {(successful_suites/total_suites)*100:.1f}%")
    
    # Individual suite results
    print(f"\nINDIVIDUAL SUITE RESULTS:")
    print(f"{'Suite':<40} {'Status':<10} {'Duration':<10} {'Details'}")
    print("-" * 80)
    
    for suite_name, (success, data) in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        duration = f"{data['duration']:.2f}s"
        
        details = ""
        if "summary_line" in data:
            details = data["summary_line"]
        elif "error" in data:
            details = f"Error: {data['error']}"
        elif not success:
            details = f"Return code: {data.get('return_code', 'unknown')}"
        
        print(f"{suite_name:<40} {status:<10} {duration:<10} {details}")
    
    # Failed tests details
    failed_results = {name: data for name, (success, data) in results.items() if not success}
    
    if failed_results:
        print(f"\nFAILED TESTS DETAILS:")
        print("-" * 80)
        
        for suite_name, (_, data) in failed_results.items():
            print(f"\n{suite_name}:")
            if data.get("stderr"):
                print("Error output:")
                print(data["stderr"][:500] + "..." if len(data["stderr"]) > 500 else data["stderr"])
    
    # Test coverage analysis
    print(f"\nTEST COVERAGE ANALYSIS:")
    print("-" * 40)
    
    coverage_areas = {
        "Tool Wrapper": "test_mcp_phase3_integration.py",
        "Tool Registry": "test_mcp_phase3_integration.py", 
        "Integration": "test_mcp_phase3_integration.py",
        "Auto Discovery": "test_mcp_phase3_integration.py",
        "Namespace Management": "test_mcp_phase3_integration.py",
        "Dynamic Updates": "test_mcp_phase3_integration.py",
        "End-to-End Workflows": "test_mcp_e2e_workflow.py",
        "Real-world Scenarios": "test_mcp_e2e_workflow.py"
    }
    
    for area, test_file in coverage_areas.items():
        test_name = test_file.replace('.py', '').replace('_', ' ').title()
        if test_name in results:
            success, _ = results[test_name]
            status = "✅ Covered" if success else "❌ Failed"
        else:
            status = "❓ Unknown"
        
        print(f"  {area:<25}: {status}")
    
    # Recommendations
    print(f"\nRECOMMENDATIONS:")
    print("-" * 20)
    
    if failed_suites == 0:
        print("🎉 Excellent! All tests are passing.")
        print("   Phase 3 MCP integration is ready for production.")
    elif failed_suites <= 1:
        print("⚠️  Most tests are passing, but there are some issues to address.")
        print("   Review failed tests and fix issues before deployment.")
    else:
        print("🚨 Multiple test suites are failing.")
        print("   Phase 3 implementation needs significant fixes.")
        print("   Do not deploy until all critical tests pass.")
    
    if total_duration > 60:
        print("⏱️  Tests are taking a long time to run.")
        print("   Consider optimizing test performance or running in parallel.")
    
    # Success criteria
    print(f"\nSUCCESS CRITERIA:")
    print("-" * 20)
    
    criteria = [
        ("All core functionality tests pass", successful_suites >= total_suites * 0.8),
        ("End-to-end workflows work", "Test Mcp E2E Workflow" in [name for name, (success, _) in results.items() if success]),
        ("Performance is acceptable", total_duration < 120),
        ("No critical errors", failed_suites <= 1)
    ]
    
    for criterion, met in criteria:
        status = "✅" if met else "❌"
        print(f"  {status} {criterion}")
    
    overall_success = all(met for _, met in criteria)
    
    print(f"\nOVERALL PHASE 3 STATUS: {'✅ READY' if overall_success else '❌ NOT READY'}")


def main():
    """Main test runner function."""
    
    print("Phase 3 MCP Integration Test Runner")
    print("=" * 50)
    
    # Set up paths
    script_dir = Path(__file__).parent
    integration_dir = script_dir / "integration"
    
    # Define test suites
    test_suites = [
        (integration_dir / "test_mcp_phase3_integration.py", "Test MCP Phase3 Integration"),
        (integration_dir / "test_mcp_e2e_workflow.py", "Test MCP E2E Workflow")
    ]
    
    # Pre-flight checks
    if not check_test_dependencies():
        sys.exit(1)
    
    test_files = [test_file for test_file, _ in test_suites]
    if not validate_test_files(test_files):
        sys.exit(1)
    
    # Run test suites
    results = {}
    start_time = time.time()
    
    for test_file, test_name in test_suites:
        success, data = run_test_suite(test_file, test_name)
        results[test_name] = (success, data)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Generate report
    generate_test_report(results)
    
    print(f"\nTotal execution time: {total_time:.2f}s")
    
    # Exit with appropriate code
    all_passed = all(success for success, _ in results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()