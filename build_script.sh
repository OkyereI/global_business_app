#!/bin/bash

echo "Building Business Application..."
echo

# Clean previous builds
if [ -d "dist" ]; then
    rm -rf "dist"
fi
if [ -d "build" ]; then
    rm -rf "build"
fi
if [ -f "BusinessApp.spec" ]; then
    rm "BusinessApp.spec"
fi

echo "Cleaned previous builds"
echo

# Build with PyInstaller
pyinstaller \
    --onefile \
    --add-data "templates:templates" \
    --add-data "static:static" \
    --add-data ".env:." \
    --icon "gbt.png" \
    --hidden-import "flask_sqlalchemy" \
    --hidden-import "flask_migrate" \
    --hidden-import "flask_wtf" \
    --hidden-import "flask_login" \
    --hidden-import "werkzeug.security" \
    --hidden-import "sqlalchemy" \
    --hidden-import "dotenv" \
    --hidden-import "requests" \
    --hidden-import "pandas" \
    --hidden-import "extensions" \
    --hidden-import "models" \
    --hidden-import "sync_api" \
    --hidden-import "env_loader" \
    --hidden-import "browser_launcher" \
    --hidden-import "db_initializer" \
    --name "BusinessApp" \
    --distpath "dist" \
    --workpath "build" \
    app.py

if [ $? -eq 0 ]; then
    echo
    echo "✅ Build completed successfully!"
    echo
    echo "📁 Executable location: dist/BusinessApp"
    echo
    echo "📋 Next steps:"
    echo "  1. Copy .env file to dist/ directory"
    echo "  2. Test the application: cd dist && ./BusinessApp"
    echo
else
    echo
    echo "❌ Build failed! Check the output above for errors."
    echo
fi