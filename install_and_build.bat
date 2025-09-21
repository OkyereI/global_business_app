@echo off
echo 🚀 Installing PyInstaller and Building Global Business App
echo ================================================================
echo.

echo Step 1: Installing PyInstaller...
pip install pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Failed to install PyInstaller
    echo Trying with upgrade...
    pip install --upgrade pip
    pip install pyinstaller
)

echo.
echo Step 2: Verifying PyInstaller installation...
pyinstaller --version
if %ERRORLEVEL% NEQ 0 (
    echo ❌ PyInstaller installation failed!
    pause
    exit /b 1
)

echo.
echo Step 3: Cleaning previous builds...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "GlobalBusinessApp.spec" del "GlobalBusinessApp.spec"

echo.
echo Step 4: Building the application...
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
    echo.
    echo ✅ Build completed successfully!
    echo.
    echo Step 5: Setting up the executable directory...
    copy .env dist\.env
    echo.
    echo 📁 Your app is ready at: dist\GlobalBusinessApp.exe
    echo.
    echo 🚀 To test your app:
    echo    cd dist
    echo    GlobalBusinessApp.exe
    echo.
    echo 📋 Files in dist directory:
    dir dist
) else (
    echo.
    echo ❌ Build failed! Check the output above for errors.
)

echo.
pause
