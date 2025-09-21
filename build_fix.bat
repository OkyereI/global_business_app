@echo off
echo 🔧 PyInstaller Virtual Environment Fix
echo ========================================
echo.

echo Checking Python and PyInstaller availability...
echo.

echo Option 1: Installing PyInstaller in virtual environment...
python -m pip install pyinstaller
echo.

echo Option 2: Building with python -m PyInstaller...
python -m PyInstaller ^
    --onefile ^
    --add-data "templates;templates" ^
    --add-data ".env;." ^
    --icon "gbt.png" ^
    --hidden-import "flask_sqlalchemy" ^
    --hidden-import "flask_migrate" ^
    --hidden-import "flask_wtf" ^
    --hidden-import "flask_login" ^
    --hidden-import "extensions" ^
    --hidden-import "models" ^
    --hidden-import "sync_api" ^
    --hidden-import "env_loader" ^
    --hidden-import "browser_launcher" ^
    --hidden-import "db_initializer" ^
    --name "GlobalBusinessApp" ^
    app.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ Build successful!
    echo Copying .env file...
    copy .env dist\.env
    echo.
    echo 📁 Your app: dist\GlobalBusinessApp.exe
    echo.
    echo Test your app:
    echo cd dist
    echo GlobalBusinessApp.exe
) else (
    echo.
    echo ❌ Build failed. Trying alternative method...
    echo.
    echo Deactivating virtual environment and trying global PyInstaller...
    call deactivate
    
    pyinstaller ^
        --onefile ^
        --add-data "templates;templates" ^
        --add-data ".env;." ^
        --icon "gbt.png" ^
        --hidden-import "flask_sqlalchemy" ^
        --hidden-import "flask_migrate" ^
        --hidden-import "flask_wtf" ^
        --hidden-import "flask_login" ^
        --hidden-import "extensions" ^
        --hidden-import "models" ^
        --hidden-import "sync_api" ^
        --hidden-import "env_loader" ^
        --hidden-import "browser_launcher" ^
        --hidden-import "db_initializer" ^
        --name "GlobalBusinessApp" ^
        app.py
    
    if %ERRORLEVEL% EQU 0 (
        echo ✅ Build successful with global PyInstaller!
        copy .env dist\.env
    ) else (
        echo ❌ Build failed with both methods
    )
)

pause
