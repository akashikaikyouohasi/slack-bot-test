#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROCESSOR_DIR="$PROJECT_ROOT/lambda/processor"
PACKAGE_DIR="$PROCESSOR_DIR/package"

echo "=== Packaging Processor Lambda ==="

# Clean previous package
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"

# Install dependencies
pip install -r "$PROCESSOR_DIR/requirements.txt" -t "$PACKAGE_DIR" --quiet

# Copy source files
cp "$PROCESSOR_DIR/handler.py" "$PROCESSOR_DIR/system_prompt.py" "$PACKAGE_DIR/"

echo "=== Package ready at $PACKAGE_DIR ==="
echo "Run 'terraform apply' in terraform/ directory next."
