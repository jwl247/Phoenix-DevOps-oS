#!/bin/bash
echo "🚀 Building Phoenix Universal Kernel..."

python3 -m venv venv 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

pip install pyinstaller --quiet

python -m PyInstaller --onefile --name phoenix_kernel --clean main_kernel.py

echo "✅ Build finished!"
echo "Binary ready → ./dist/phoenix_kernel"
echo "Run it and test with: echo 'ls -la' | nc localhost 7701"
