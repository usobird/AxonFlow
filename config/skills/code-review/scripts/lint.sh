#!/bin/bash
# 简单的 lint 检查脚本
# 用法: lint.sh <file_path>

set -e

if [ -z "$1" ]; then
    echo "Usage: lint.sh <file_path>"
    exit 1
fi

FILE="$1"

if [ ! -f "$FILE" ]; then
    echo "Error: File not found: $FILE"
    exit 1
fi

echo "Running lint check on $FILE..."

# 检查 Python 文件
if [[ "$FILE" == *.py ]]; then
    python -m py_compile "$FILE" 2>&1 || echo "Syntax error detected"
    echo "Lint check completed."
else
    echo "Skipping non-Python file."
fi
