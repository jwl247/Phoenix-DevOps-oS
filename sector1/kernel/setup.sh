#!/usr/bin/env bash
echo "🚀 Building Phoenix Universal Kernel..."

python3 -m venv venv 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

pip install pyinstaller --quiet

python -m PyInstaller --onefile --name phoenix_kernel --clean main_kernel.py

echo "✅ Build finished!"
echo "Binary ready → ./dist/phoenix_kernel"
echo "Run it: ./dist/phoenix_kernel  (7701-7704 are Helix-I stage intake, not a shell)"
