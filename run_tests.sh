#!/bin/bash

# Test runner script for Mozaika Core

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Running Mozaika Core Tests${NC}"
echo "================================"

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Warning: Virtual environment not activated${NC}"
    echo "Trying to activate .venv or venv..."

    if [ -d ".venv" ]; then
        source .venv/bin/activate
    elif [ -d "venv" ]; then
        source venv/bin/activate
    else
        echo -e "${RED}No virtual environment found. Please create one first.${NC}"
        exit 1
    fi
fi

# Parse command line arguments
case "$1" in
    "unit")
        echo -e "${GREEN}Running unit tests only...${NC}"
        pytest tests/unit -v
        ;;
    "api")
        echo -e "${GREEN}Running API tests only...${NC}"
        pytest tests/test_api.py tests/test_sqs_consumer.py -v
        ;;
    "functional")
        echo -e "${GREEN}Running functional tests (requires Docker)...${NC}"
        pytest tests/functional -v
        ;;
    "coverage")
        echo -e "${GREEN}Running tests with coverage...${NC}"
        pytest --cov=src --cov-report=term --cov-report=html
        echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    "quick")
        echo -e "${GREEN}Running quick tests (no Docker required)...${NC}"
        pytest tests/unit tests/test_*.py -v
        ;;
    "all")
        echo -e "${GREEN}Running all tests...${NC}"
        pytest -v
        ;;
    "--help"|"-h")
        echo "Usage: ./run_tests.sh [option]"
        echo ""
        echo "Options:"
        echo "  unit       - Run unit tests only"
        echo "  api        - Run API tests only"
        echo "  functional - Run functional tests (requires Docker)"
        echo "  coverage   - Run with coverage report"
        echo "  quick      - Run quick tests (no Docker)"
        echo "  all        - Run all tests (default)"
        echo "  --help     - Show this help"
        ;;
    *)
        echo -e "${GREEN}Running all tests...${NC}"
        pytest -v
        ;;
esac

# Check exit code
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Tests completed successfully!${NC}"
else
    echo -e "${RED}✗ Tests failed!${NC}"
    exit 1
fi