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

# Install dependencies (Python 3.12 / Linux x86_64 for Lambda runtime)
uv pip install -r "$PROCESSOR_DIR/requirements.txt" --target "$PACKAGE_DIR" --python 3.12 --python-platform x86_64-manylinux2014 --quiet

# Copy source files
cp "$PROCESSOR_DIR/handler.py" "$PROCESSOR_DIR/system_prompt.py" "$PROCESSOR_DIR/cloudwatch_tools.py" "$PROCESSOR_DIR/mcp_servers.py" "$PACKAGE_DIR/"

# Clone Terraform repository
TERRAFORM_REPO_URL="${TERRAFORM_REPO_URL:-git@github.com:akashikaikyouohasi/slack-bot-test.git}"  # TODO: 実際のリポジトリURLに変更
if [ -n "$TERRAFORM_REPO_URL" ]; then
  echo "=== Cloning Terraform repository ==="
  TERRAFORM_DEST="$PACKAGE_DIR/terraform_repo"
  rm -rf "$TERRAFORM_DEST"
  git clone --depth 1 "$TERRAFORM_REPO_URL" "$TERRAFORM_DEST"
  # Remove unnecessary files
  rm -rf "$TERRAFORM_DEST/.git" "$TERRAFORM_DEST/.terraform"
  find "$TERRAFORM_DEST" -name "*.tfstate" -o -name "*.tfstate.backup" -o -name ".terraform.lock.hcl" | xargs rm -f 2>/dev/null || true
  echo "Terraform repo cloned to $TERRAFORM_DEST"
else
  echo "=== Skipping Terraform repo (TERRAFORM_REPO_URL not set) ==="
fi

echo "=== Package ready at $PACKAGE_DIR ==="
echo "Run 'terraform apply' in terraform/ directory next."
