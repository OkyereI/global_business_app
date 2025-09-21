#!/bin/bash
# Build script for Global Business App
# This script creates a standalone executable using PyInstaller

echo "🚀 Building Global Business App..."
echo "📁 Cleaning previous builds..."
rm -rf build/ dist/ *.spec

echo "🔨 Running PyInstaller..."
python -m PyInstaller \
  --onefile \
  --add-data "templates;templates" \
  --add-data "static;static" \
  --add-data ".env;." \
  --icon "gbt.png" \
  --hidden-import "flask_sqlalchemy" \
  --hidden-import "flask_migrate" \
  --hidden-import "flask_wtf" \
  --hidden-import "flask_login" \
  --hidden-import "extensions" \
  --hidden-import "models" \
  --hidden-import "sync_api" \
  --hidden-import "env_loader" \
  --hidden-import "browser_launcher" \
  --hidden-import "db_initializer" \
  --name "GlobalBusinessApp" \
  app.py

if [ $? -eq 0 ]; then
    echo "✅ Build completed successfully!"
    echo "📦 Executable location: dist/GlobalBusinessApp"
    echo "💡 Remember to place your .env file in the same directory as the executable"
else
    echo "❌ Build failed. Check the error messages above."
    exit 1
fi
