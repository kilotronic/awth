#!/bin/bash
set -e

echo "Running tests with coverage..."
python3 -m pytest -v --cov=. --cov-report=term-missing --cov-report=html

echo ""
echo "Test coverage report generated in htmlcov/index.html"
