#!/bin/bash
set -e

echo "--- 1. Formatting (Black) ---"
black .

echo -e "\n--- 2. Linting (Ruff) ---"
ruff check . --fix

echo -e "\n--- 3. Type Checking (Mypy) ---"
mypy scripts

echo -e "\n--- 4. Testing (Pytest) ---"
pytest -q

echo -e "\n\033[0;32mAll checks passed! Your code is clean.\033[0m"
