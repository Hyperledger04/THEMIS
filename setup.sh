#!/usr/bin/env bash
set -e

echo ""
echo "Setting up LexAgent..."
echo ""

# Install uv if not present
if ! command -v uv &>/dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Install dependencies into .venv
echo "Installing dependencies (this may take a minute)..."
uv sync

# Symlink lex to ~/.local/bin
mkdir -p "$HOME/.local/bin"
ln -sf "$(pwd)/.venv/bin/lex" "$HOME/.local/bin/lex"

# Verify ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
  echo ""
  echo "Adding ~/.local/bin to your PATH..."
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
  export PATH="$HOME/.local/bin:$PATH"
fi

echo ""
echo "Done! LexAgent is ready."
echo ""
echo "Run 'lex setup' to create your lawyer profile."
echo "Run 'lex draft \"your matter brief\"' to generate your first draft."
echo ""
echo "If 'lex' is not found, restart your terminal or run: source ~/.zshrc"
