@echo off
echo Building Business Application...
echo.

REM Clean previous builds
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "BusinessApp.spec" del "BusinessApp.spec"

echo Cleaned previous builds
echo.

REM Build with PyInstaller
pyinstaller ^
    --onefile ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data ".env;." ^
    --icon "gbt.png" ^
    --hidden-import "flask_sqlalchemy" ^
    --hidden-import "flask_migrate" ^
    --hidden-import "flask_wtf" ^
    --hidden-import "flask_login" ^
    --hidden-import "werkzeug.security" ^
    --hidden-import "sqlalchemy" ^
    --hidden-import "dotenv" ^
    --hidden-import "requests" ^
    --hidden-import "pandas" ^
    --hidden-import "extensions" ^
    --hidden-import "models" ^
    --hidden-import "sync_api" ^
    --hidden-import "env_loader" ^
    --hidden-import "browser_launcher" ^
    --hidden-import "db_initializer" ^
    --name "BusinessApp" ^
    --distpath "dist" ^
    --workpath "build" ^
    app.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ Build completed successfully!
    echo.
    echo 📁 Executable location: dist\BusinessApp.exe
    echo.
    echo 📋 Next steps:
    echo   1. Copy .env file to dist\ directory
    echo   2. Test the application: cd dist ^&^& BusinessApp.exe
    echo.
) else (
    echo.
    echo ❌ Build failed! Check the output above for errors.
    echo.
)

pause