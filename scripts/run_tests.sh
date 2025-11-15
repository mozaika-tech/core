#!/bin/bash

# Script to run tests for Mozaika Core Service

set -e

echo "🧪 Running Mozaika Core Service Tests"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Warning: Virtual environment is not activated${NC}"
    echo "Activating virtual environment..."
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        echo -e "${RED}Error: Virtual environment not found. Please create it first.${NC}"
        exit 1
    fi
fi

# Install test dependencies if needed
echo "📦 Checking dependencies..."
pip install -q pytest pytest-asyncio pytest-cov testcontainers[postgresql] pytest-mock

# Run different test suites based on argument
case ${1:-all} in
    unit)
        echo -e "\n${GREEN}Running Unit Tests...${NC}"
        pytest tests/unit -v --tb=short
        ;;
    functional)
        echo -e "\n${GREEN}Running Functional Tests (requires Docker)...${NC}"
        pytest tests/functional -v --tb=short
        ;;
    coverage)
        echo -e "\n${GREEN}Running All Tests with Coverage...${NC}"
        pytest tests --cov=src --cov-report=html --cov-report=term
        echo -e "\n${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    quick)
        echo -e "\n${GREEN}Running Quick Tests (unit only, no coverage)...${NC}"
        pytest tests/unit -v --tb=line
        ;;
    all)
        echo -e "\n${GREEN}Running All Tests...${NC}"
        pytest tests -v --tb=short
        ;;
    *)
        echo "Usage: $0 [unit|functional|coverage|quick|all]"
        echo "  unit       - Run only unit tests"
        echo "  functional - Run only functional tests (requires Docker)"
        echo "  coverage   - Run all tests with coverage report"
        echo "  quick      - Run quick unit tests only"
        echo "  all        - Run all tests (default)"
        exit 1
        ;;
esac

# Check test results
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✅ All tests passed!${NC}"
else
    echo -e "\n${RED}❌ Some tests failed${NC}"
    exit 1
fi