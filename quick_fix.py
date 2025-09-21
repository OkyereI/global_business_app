#!/usr/bin/env python3
"""
Quick fix script for PyInstaller Flask app issues
Run this to identify and fix common problems with your current build
"""

import os
import sys
import shutil
from pathlib import Path

def check_current_setup():
    """Check the current project setup for common issues"""
    print("🔍 CHECKING YOUR CURRENT SETUP")
    print("=" * 50)
    
    issues = []
    warnings = []
    
    # Check for bundled database in dist
    dist_dir = Path("dist")
    if dist_dir.exists():
        db_files = list(dist_dir.glob("**/*.db"))
        if db_files:
            issues.append(f"❌ Database file bundled in dist: {db_files}")
            issues.append("   This will cause write permission errors!")
    
    # Check for .env in dist
    env_in_dist = dist_dir / ".env"
    if dist_dir.exists() and not env_in_dist.exists():
        issues.append("❌ No .env file in dist directory")
        issues.append("   App won't be able to load configuration!")
    
    # Check for templates directory
    templates_dir = Path("templates")
    if not templates_dir.exists():
        warnings.append("⚠️  No templates directory found")
    
    # Check for static directory  
    static_dir = Path("static")
    if not static_dir.exists():
        warnings.append("⚠️  No static directory found")
    
    # Check for .env file
    env_file = Path(".env")
    if not env_file.exists():
        issues.append("❌ No .env file in project root")
        issues.append("   Create .env file with your configuration")
    
    # Check for app.py
    app_file = Path("app.py")
    if not app_file.exists():
        issues.append("❌ No app.py file found")
    
    # Check for the fixed files
    fixed_files = ["fixed_app.py", "improved_env_loader.py", "improved_db_initializer.py"]
    available_fixes = []
    for file in fixed_files:
        if Path(file).exists():
            available_fixes.append(file)
    
    # Report results
    if issues:
        print("🚨 CRITICAL ISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
        print()
    
    if warnings:
        print("⚠️  WARNINGS:")
        for warning in warnings:
            print(f"  {warning}")
        print()
    
    if available_fixes:
        print("✅ AVAILABLE FIXES:")
        for fix in available_fixes:
            print(f"  📁 {fix}")
        print()
    
    if not issues and not warnings:
        print("✅ No obvious issues found with current setup!")
    
    return len(issues) == 0, available_fixes

def clean_build():
    """Clean previous build artifacts"""
    print("🧹 CLEANING BUILD ARTIFACTS")
    print("=" * 50)
    
    dirs_to_clean = ["dist", "build", "__pycache__"]
    files_to_clean = ["*.spec"]
    
    cleaned = []
    
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            cleaned.append(f"📁 {dir_name}/")
    
    import glob
    for pattern in files_to_clean:
        for file in glob.glob(pattern):
            os.remove(file)
            cleaned.append(f"📄 {file}")
    
    if cleaned:
        print("Cleaned:")
        for item in cleaned:
            print(f"  ✅ {item}")
    else:
        print("✅ Nothing to clean")
    
    print()

def apply_fixes(available_fixes):
    """Apply available fixes to the current project"""
    print("🔧 APPLYING FIXES")
    print("=" * 50)
    
    if "fixed_app.py" in available_fixes:
        try:
            # Backup original
            if os.path.exists("app.py"):
                shutil.copy2("app.py", "app_backup.py")
                print("✅ Backed up original app.py to app_backup.py")
            
            # Replace with fixed version
            shutil.copy2("fixed_app.py", "app.py")
            print("✅ Replaced app.py with fixed version")
        except Exception as e:
            print(f"❌ Error applying app.py fix: {e}")
    
    if "improved_env_loader.py" in available_fixes:
        try:
            if os.path.exists("env_loader.py"):
                shutil.copy2("env_loader.py", "env_loader_backup.py")
                print("✅ Backed up original env_loader.py")
            
            shutil.copy2("improved_env_loader.py", "env_loader.py")
            print("✅ Replaced env_loader.py with improved version")
        except Exception as e:
            print(f"❌ Error applying env_loader.py fix: {e}")
    
    if "improved_db_initializer.py" in available_fixes:
        try:
            if os.path.exists("db_initializer.py"):
                shutil.copy2("db_initializer.py", "db_initializer_backup.py")
                print("✅ Backed up original db_initializer.py")
            
            shutil.copy2("improved_db_initializer.py", "db_initializer.py")
            print("✅ Replaced db_initializer.py with improved version")
        except Exception as e:
            print(f"❌ Error applying db_initializer.py fix: {e}")
    
    print()

def create_corrected_build_command():
    """Create a corrected build command for the user's platform"""
    print("📝 CORRECTED BUILD COMMAND")
    print("=" * 50)
    
    # Detect platform
    is_windows = sys.platform.startswith('win')
    separator = ";" if is_windows else ":"
    
    # Base command
    base_cmd = [
        "pyinstaller",
        "--onefile",
        f"--add-data \"templates{separator}templates\"",
        f"--add-data \"static{separator}static\"",
        f"--add-data \".env{separator}.\"",
        "--icon \"gbt.png\"",
        "--hidden-import \"flask_sqlalchemy\"",
        "--hidden-import \"flask_migrate\"",
        "--hidden-import \"flask_wtf\"",
        "--hidden-import \"flask_login\"",
        "--hidden-import \"extensions\"",
        "--hidden-import \"models\"",
        "--hidden-import \"sync_api\"",
        "--hidden-import \"env_loader\"",
        "--hidden-import \"browser_launcher\"",
        "--hidden-import \"db_initializer\"",
        "--name \"BusinessApp\"",
        "app.py"
    ]
    
    if is_windows:
        cmd_file = "corrected_build.bat"
        content = "@echo off\n"
        content += "echo Building with corrected command...\n"
        content += " ^\n    ".join(base_cmd) + "\n"
        content += "echo.\n"
        content += "echo Build complete! Next steps:\n"
        content += "echo 1. copy .env dist\\.env\n"
        content += "echo 2. cd dist\n"
        content += "echo 3. BusinessApp.exe\n"
        content += "pause\n"
    else:
        cmd_file = "corrected_build.sh"
        content = "#!/bin/bash\n"
        content += "echo 'Building with corrected command...'\n"
        content += " \\\n    ".join(base_cmd) + "\n"
        content += "echo\n"
        content += "echo 'Build complete! Next steps:'\n"
        content += "echo '1. cp .env dist/.env'\n"
        content += "echo '2. cd dist'\n"
        content += "echo '3. ./BusinessApp'\n"
    
    with open(cmd_file, 'w') as f:
        f.write(content)
    
    if not is_windows:
        os.chmod(cmd_file, 0o755)
    
    print(f"✅ Created corrected build script: {cmd_file}")
    print(f"📋 Run this command to build your app correctly")
    print()
    
    # Also show the command
    print("Command:")
    print(" \\\n    ".join(base_cmd) if not is_windows else " ^\n    ".join(base_cmd))
    print()

def main():
    """Main function to run all checks and fixes"""
    print("🚀 PYINSTALLER FLASK APP QUICK FIX")
    print("=" * 70)
    print("This script will identify and fix common PyInstaller issues")
    print("=" * 70)
    print()
    
    # Check current setup
    is_healthy, available_fixes = check_current_setup()
    
    # Clean build artifacts
    clean_build()
    
    # Apply fixes if available
    if available_fixes:
        response = input("🔧 Apply available fixes? (y/n): ").lower().strip()
        if response in ['y', 'yes']:
            apply_fixes(available_fixes)
        else:
            print("⏭️  Skipping fixes")
            print()
    
    # Create corrected build command
    create_corrected_build_command()
    
    # Final recommendations
    print("🎯 NEXT STEPS:")
    print("=" * 50)
    print("1. ✅ Run the corrected build script")
    print("2. ✅ Copy .env file to dist directory")
    print("3. ✅ Test your application")
    print("4. ✅ Check that database is created in dist/instance/")
    print()
    
    if not is_healthy:
        print("⚠️  IMPORTANT: Address the critical issues above before building!")
    else:
        print("🎉 Your setup looks good! Try the corrected build command.")
    
    print()
    print("📚 For detailed troubleshooting, see TROUBLESHOOTING.md")
    print("📋 For build guide, see PYINSTALLER_GUIDE.md")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {e}")
        sys.exit(1)
