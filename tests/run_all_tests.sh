#!/bin/bash
# SimaCode Test Runner - Run all tests for the project
# Usage: ./tests/run_all_tests.sh [options]

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default options
VERBOSE=false
COVERAGE=true
FAIL_FAST=false
SPECIFIC_TEST=""
PARALLEL=false
HTML_REPORT=false
QUIET=false
CONFIG_FILE="" # Use Config.load default behavior unless explicitly specified

# Function to print colored output
print_color() {
    printf "${1}%s${NC}\n" "$2"
}

# Function to print usage
print_usage() {
    echo "SimaCode Test Runner"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -v, --verbose          Enable verbose output"
    echo "  -q, --quiet            Suppress output (only show summary)"
    echo "  --no-cov               Disable coverage reporting"
    echo "  -f, --fail-fast        Stop on first test failure"
    echo "  -t, --test TEST        Run specific test file or pattern"
    echo "  -p, --parallel         Run tests in parallel"
    echo "  --html                 Generate HTML coverage report"
    echo "  -c, --config FILE      Specify config file (default: use Config.load standard paths)"
    echo "  -h, --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                     Run all tests with coverage"
    echo "  $0 -v --html           Run with verbose output and HTML report"
    echo "  $0 -t test_ai.py       Run only AI tests"
    echo "  $0 -f -q               Run quietly, stop on first failure"
    echo "  $0 --no-cov -p         Run without coverage, in parallel"
    echo "  $0 -c config/config.yaml Use custom config file"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        --no-cov)
            COVERAGE=false
            shift
            ;;
        -f|--fail-fast)
            FAIL_FAST=true
            shift
            ;;
        -t|--test)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        --html)
            HTML_REPORT=true
            shift
            ;;
        -c|--config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]]; then
    print_color $RED "Error: pyproject.toml not found. Please run this script from the project root."
    exit 1
fi

# Check if config file exists (only if explicitly provided)
if [[ -n "$CONFIG_FILE" && ! -f "$CONFIG_FILE" ]]; then
    print_color $RED "Error: Config file '$CONFIG_FILE' not found."
    print_color $YELLOW "Available config files:"
    find config/ -name "*.yaml" -o -name "*.yml" 2>/dev/null | sed 's/^/  /' || echo "  No config files found in config/ directory"
    exit 1
fi

# Check if poetry is available
if ! command -v poetry &> /dev/null; then
    print_color $RED "Error: Poetry is not installed or not in PATH."
    print_color $YELLOW "Please install Poetry: https://python-poetry.org/docs/#installation"
    exit 1
fi

# Print header
if [[ $QUIET != true ]]; then
    print_color $CYAN "=========================================="
    print_color $CYAN "       SimaCode Test Suite Runner        "
    print_color $CYAN "=========================================="
    echo
fi

# Check if virtual environment is activated
if [[ $QUIET != true ]]; then
    if [[ -n "$VIRTUAL_ENV" ]]; then
        print_color $GREEN "✓ Virtual environment detected: $(basename $VIRTUAL_ENV)"
    else
        print_color $YELLOW "⚠ No virtual environment detected, using Poetry environment"
    fi
    echo
fi

# Build pytest command with config file
PYTEST_CMD="poetry run pytest"

# Add config file to environment for tests that need it (only if specified)
if [[ -n "$CONFIG_FILE" ]]; then
    export SIMACODE_TEST_CONFIG="$CONFIG_FILE"
fi

# Add test path
if [[ -n "$SPECIFIC_TEST" ]]; then
    if [[ -f "tests/$SPECIFIC_TEST" ]]; then
        PYTEST_CMD="$PYTEST_CMD tests/$SPECIFIC_TEST"
    elif [[ -f "$SPECIFIC_TEST" ]]; then
        PYTEST_CMD="$PYTEST_CMD $SPECIFIC_TEST"
    else
        PYTEST_CMD="$PYTEST_CMD -k $SPECIFIC_TEST"
    fi
else
    PYTEST_CMD="$PYTEST_CMD tests/"
fi

# Add coverage options
if [[ $COVERAGE == true ]]; then
    PYTEST_CMD="$PYTEST_CMD --cov=src/simacode --cov-report=term-missing"
    if [[ $HTML_REPORT == true ]]; then
        PYTEST_CMD="$PYTEST_CMD --cov-report=html"
    fi
fi

# Add verbosity options
if [[ $VERBOSE == true ]]; then
    PYTEST_CMD="$PYTEST_CMD -v"
elif [[ $QUIET == true ]]; then
    PYTEST_CMD="$PYTEST_CMD -q"
fi

# Add fail-fast option
if [[ $FAIL_FAST == true ]]; then
    PYTEST_CMD="$PYTEST_CMD -x"
fi

# Add parallel option
if [[ $PARALLEL == true ]]; then
    PYTEST_CMD="$PYTEST_CMD -n auto"
fi

# Print configuration
if [[ $QUIET != true ]]; then
    print_color $BLUE "Test Configuration:"
    if [[ -n "$CONFIG_FILE" ]]; then
        echo "  Config File: $CONFIG_FILE"
    else
        echo "  Config File: Using Config.load default paths"
    fi
    echo "  Coverage: $([ $COVERAGE == true ] && echo "✓ Enabled" || echo "✗ Disabled")"
    echo "  Verbose: $([ $VERBOSE == true ] && echo "✓ Enabled" || echo "✗ Disabled")"
    echo "  Fail Fast: $([ $FAIL_FAST == true ] && echo "✓ Enabled" || echo "✗ Disabled")"
    echo "  Parallel: $([ $PARALLEL == true ] && echo "✓ Enabled" || echo "✗ Disabled")"
    echo "  HTML Report: $([ $HTML_REPORT == true ] && echo "✓ Enabled" || echo "✗ Disabled")"
    if [[ -n "$SPECIFIC_TEST" ]]; then
        echo "  Target: $SPECIFIC_TEST"
    else
        echo "  Target: All tests"
    fi
    echo
    
    # Show brief config file info if available and config file is specified
    if [[ -n "$CONFIG_FILE" ]] && command -v yq &> /dev/null; then
        print_color $CYAN "Config Summary:"
        echo "  Project: $(yq '.project_name // "N/A"' "$CONFIG_FILE" 2>/dev/null || echo "N/A")"
        echo "  AI Provider: $(yq '.ai.provider // "N/A"' "$CONFIG_FILE" 2>/dev/null || echo "N/A")"
        echo "  Log Level: $(yq '.logging.level // "N/A"' "$CONFIG_FILE" 2>/dev/null || echo "N/A")"
        echo
    fi
    
    print_color $YELLOW "Running command: $PYTEST_CMD"
    echo
fi

# Record start time
START_TIME=$(date +%s)

# Run the tests
if [[ $QUIET == true ]]; then
    print_color $BLUE "Running tests..."
fi

set +e  # Don't exit on test failures
$PYTEST_CMD
TEST_EXIT_CODE=$?
set -e

# Record end time and calculate duration
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Print results
echo
print_color $CYAN "=========================================="
print_color $CYAN "              Test Results                "
print_color $CYAN "=========================================="

if [[ $TEST_EXIT_CODE -eq 0 ]]; then
    print_color $GREEN "✓ All tests passed!"
    print_color $GREEN "  Duration: ${DURATION}s"
else
    print_color $RED "✗ Some tests failed (exit code: $TEST_EXIT_CODE)"
    print_color $RED "  Duration: ${DURATION}s"
fi

# Show coverage report location if HTML was generated
if [[ $COVERAGE == true && $HTML_REPORT == true && $TEST_EXIT_CODE -eq 0 ]]; then
    echo
    print_color $PURPLE "📊 Coverage Reports:"
    echo "  HTML: htmlcov/index.html"
    echo "  XML: coverage.xml"
fi

# Show additional information
if [[ $QUIET != true ]]; then
    echo
    print_color $BLUE "📁 Test Files:"
    find tests/ -name "test_*.py" | sort | sed 's/^/  /'
    
    echo
    print_color $BLUE "🔧 Available Test Categories:"
    echo "  • test_ai.py                 - Core AI functionality tests"
    echo "  • test_ai_integration.py     - AI integration tests"
    echo "  • test_cli_ai.py             - CLI and AI interaction tests"
    echo "  • test_ai_factory_extended.py - AI factory pattern tests"
    echo "  • test_ai_error_handling.py  - Error handling tests"
    echo "  • test_ai_streaming.py       - Async streaming tests"
    echo "  • test_cli.py                - CLI functionality tests"
    echo "  • test_config.py             - Configuration tests"
    echo "  • test_logging.py            - Logging tests"
    
    echo
    print_color $BLUE "💡 Tips:"
    echo "  • Use -t <pattern> to run specific tests"
    echo "  • Use -f to stop on first failure"
    echo "  • Use --html for detailed coverage report"
    echo "  • Use -p for faster parallel execution"
fi

# Exit with the same code as pytest
exit $TEST_EXIT_CODE