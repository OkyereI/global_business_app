#!/usr/bin/env python3
"""
Diagnostic Test Script for Flask App Issues
Run this script to identify common problems with your Flask application setup
"""

import os
import sys
from pathlib import Path
import sqlite3
import tempfile

def test_environment():
    """Test environment variable loading"""
    print("🔍 TESTING ENVIRONMENT VARIABLES")
    print("=" * 50)
    
    # Test if we're in a frozen environment
    is_frozen = getattr(sys, 'frozen', False)
    print(f"Running as packaged app: {is_frozen}")
    
    if is_frozen:
        print(f"Executable path: {sys.executable}")
        print(f"Bundle directory: {getattr(sys, '_MEIPASS', 'Not available')}")
    
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script directory: {Path(__file__).parent}")
    
    # Look for .env files
    print("\n📁 SEARCHING FOR .ENV FILES")
    print("-" * 30)
    
    search_paths = [
        Path.cwd() / '.env',
        Path(__file__).parent / '.env'
    ]
    
    if is_frozen:
        search_paths.extend([
            Path(sys.executable).parent / '.env',
            Path(getattr(sys, '_MEIPASS', '')) / '.env'
        ])
    
    env_found = False
    for path in search_paths:
        if path.exists():
            print(f"✅ Found .env file: {path}")
            env_found = True
            
            # Check if readable
            try:
                with open(path, 'r') as f:
                    content = f.read()
                    lines = len(content.splitlines())
                    print(f"   📄 File has {lines} lines")
                    
                    # Check for key variables
                    if 'FLASK_SECRET_KEY' in content:
                        print("   🔑 FLASK_SECRET_KEY found")
                    if 'DB_TYPE' in content:
                        print("   🗄️  DB_TYPE found")
                    if 'ENTERPRISE_NAME' in content:
                        print("   🏢 ENTERPRISE_NAME found")
                        
            except Exception as e:
                print(f"   ❌ Cannot read .env file: {e}")
        else:
            print(f"❌ No .env file at: {path}")
    
    if not env_found:
        print("\n⚠️  No .env file found in any location!")
        return False
    
    return True

def test_database_creation():
    """Test database creation and access"""
    print("\n🗄️  TESTING DATABASE CREATION")
    print("=" * 50)
    
    # Test in temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        test_db_path = Path(temp_dir) / 'test.db'
        print(f"Testing database creation at: {test_db_path}")
        
        try:
            # Test SQLite connection
            conn = sqlite3.connect(str(test_db_path))
            cursor = conn.cursor()
            
            # Create a test table
            cursor.execute('''
                CREATE TABLE test_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                )
            ''')
            
            # Insert test data
            cursor.execute("INSERT INTO test_table (name) VALUES (?)", ("test",))
            conn.commit()
            
            # Query test data
            cursor.execute("SELECT * FROM test_table")
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                print("✅ Database creation and operations: OK")
                print(f"   📊 Test record: {result}")
                return True
            else:
                print("❌ Database query failed")
                return False
                
        except Exception as e:
            print(f"❌ Database test failed: {e}")
            return False

def test_file_permissions():
    """Test file and directory permissions"""
    print("\n🔒 TESTING FILE PERMISSIONS")
    print("=" * 50)
    
    current_dir = Path.cwd()
    
    # Test current directory write access
    test_file = current_dir / 'permission_test.txt'
    
    try:
        with open(test_file, 'w') as f:
            f.write('permission test')
        
        if test_file.exists():
            print("✅ Current directory is writable")
            test_file.unlink()  # Clean up
        
        # Test subdirectory creation
        test_dir = current_dir / 'test_instance'
        test_dir.mkdir(exist_ok=True)
        
        if test_dir.exists():
            print("✅ Can create subdirectories")
            test_dir.rmdir()  # Clean up
        
        return True
        
    except PermissionError as e:
        print(f"❌ Permission denied: {e}")
        print("   💡 Try running as administrator")
        return False
    except Exception as e:
        print(f"❌ File permission test failed: {e}")
        return False

def test_imports():
    """Test critical imports"""
    print("\n📦 TESTING IMPORTS")
    print("=" * 50)
    
    imports_to_test = [
        ('flask', 'Flask'),
        ('flask_sqlalchemy', 'SQLAlchemy'),
        ('flask_migrate', 'Migrate'),
        ('werkzeug.security', 'generate_password_hash'),
        ('sqlalchemy', 'create_engine'),
        ('dotenv', 'load_dotenv')
    ]
    
    all_imports_ok = True
    
    for module_name, item_name in imports_to_test:
        try:
            module = __import__(module_name, fromlist=[item_name])
            getattr(module, item_name)
            print(f"✅ {module_name}.{item_name}: OK")
        except ImportError as e:
            print(f"❌ {module_name}.{item_name}: FAILED - {e}")
            all_imports_ok = False
        except AttributeError as e:
            print(f"❌ {module_name}.{item_name}: FAILED - {e}")
            all_imports_ok = False
    
    return all_imports_ok

def test_flask_app_creation():
    """Test minimal Flask app creation"""
    print("\n🌐 TESTING FLASK APP CREATION")
    print("=" * 50)
    
    try:
        from flask import Flask
        
        # Create minimal app
        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'test-secret-key'
        app.config['TESTING'] = True
        
        @app.route('/')
        def hello():
            return 'Hello, World!'
        
        # Test app context
        with app.app_context():
            print("✅ Flask app creation: OK")
            print(f"   🔧 App name: {app.name}")
            print(f"   🔧 Debug mode: {app.debug}")
            
        return True
        
    except Exception as e:
        print(f"❌ Flask app creation failed: {e}")
        return False

def run_comprehensive_test():
    """Run all tests and provide summary"""
    print("🧪 FLASK APP DIAGNOSTIC TEST")
    print("=" * 70)
    print(f"Python version: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Frozen: {getattr(sys, 'frozen', False)}")
    print("=" * 70)
    
    tests = [
        ("Environment Variables", test_environment),
        ("Database Creation", test_database_creation),
        ("File Permissions", test_file_permissions),
        ("Module Imports", test_imports),
        ("Flask App Creation", test_flask_app_creation)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📊 TEST SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:.<30} {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Your environment should work.")
    else:
        print("\n⚠️  Some tests failed. Check the output above for issues.")
        print("\n💡 RECOMMENDATIONS:")
        
        failed_tests = [name for name, result in results if not result]
        
        if "Environment Variables" in failed_tests:
            print("   • Create or fix your .env file")
            print("   • Place .env file in the same directory as your executable")
        
        if "Database Creation" in failed_tests:
            print("   • Check database directory permissions")
            print("   • Try running as administrator")
        
        if "File Permissions" in failed_tests:
            print("   • Run as administrator")
            print("   • Check antivirus settings")
            print("   • Use a different directory for data files")
        
        if "Module Imports" in failed_tests:
            print("   • Install missing Python packages")
            print("   • Add hidden imports to PyInstaller spec")
        
        if "Flask App Creation" in failed_tests:
            print("   • Check Flask installation")
            print("   • Verify Python environment")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = run_comprehensive_test()
        
        print("\n" + "=" * 70)
        if success:
            print("🎯 All tests completed successfully!")
            exit_code = 0
        else:
            print("⚠️  Some issues were found. Please address them before packaging.")
            exit_code = 1
        
        # Keep window open in frozen mode
        if getattr(sys, 'frozen', False):
            print("\nPress Enter to exit...")
            input()
        
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error during testing: {e}")
        if getattr(sys, 'frozen', False):
            print("\nPress Enter to exit...")
            input()
        sys.exit(1)
