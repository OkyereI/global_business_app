"""
Improved environment variable loader for PyInstaller bundles
Handles .env file loading both in development and bundled executables
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import logging

def load_environment_variables():
    """
    Load environment variables with proper handling for PyInstaller bundles.
    This function tries multiple locations to find and load the .env file.
    """
    env_loaded = False
    env_locations = []
    
    try:
        if getattr(sys, 'frozen', False):
            # Running as PyInstaller bundle
            print("📦 Detected PyInstaller bundle - searching for .env file...")
            
            # 1. Try to load from the executable's directory (most common)
            executable_dir = Path(sys.executable).parent
            env_file_exe = executable_dir / '.env'
            env_locations.append(str(env_file_exe))
            
            if env_file_exe.exists():
                load_dotenv(env_file_exe)
                env_loaded = True
                print(f"✅ Loaded .env from executable directory: {env_file_exe}")
            
            # 2. Try to load from the bundle's temporary directory (_MEIPASS)
            try:
                bundle_dir = Path(sys._MEIPASS)
                env_file_bundle = bundle_dir / '.env'
                env_locations.append(str(env_file_bundle))
                
                if env_file_bundle.exists():
                    load_dotenv(env_file_bundle)
                    env_loaded = True
                    print(f"✅ Loaded .env from bundle: {env_file_bundle}")
            except AttributeError:
                print("⚠️  sys._MEIPASS not available")
            
            # 3. Try current working directory
            current_dir = Path.cwd()
            env_file_cwd = current_dir / '.env'
            env_locations.append(str(env_file_cwd))
            
            if env_file_cwd.exists():
                load_dotenv(env_file_cwd)
                env_loaded = True
                print(f"✅ Loaded .env from current directory: {env_file_cwd}")
                
        else:
            # Running in development mode
            print("🐍 Running in development mode - loading .env...")
            current_dir = Path.cwd()
            env_file_dev = current_dir / '.env'
            env_locations.append(str(env_file_dev))
            
            if env_file_dev.exists():
                load_dotenv(env_file_dev)
                env_loaded = True
                print(f"✅ Loaded .env from development directory: {env_file_dev}")
            
            # Also try the script's directory
            script_dir = Path(__file__).parent
            env_file_script = script_dir / '.env'
            env_locations.append(str(env_file_script))
            
            if env_file_script.exists() and script_dir != current_dir:
                load_dotenv(env_file_script)
                env_loaded = True
                print(f"✅ Loaded .env from script directory: {env_file_script}")
        
        # Log attempted locations for debugging
        print(f"🔍 Environment file search locations: {env_locations}")
        
        if not env_loaded:
            print("⚠️  No .env file found in any expected location!")
            print("🔧 Using default/system environment variables only")
            print("📝 Tip: Place .env file in the same directory as the executable")
        
        # Verify critical environment variables
        verify_environment_variables()
        
        return env_loaded
        
    except Exception as e:
        print(f"❌ Error loading environment variables: {e}")
        logging.error(f"Environment loading failed: {e}")
        return False

def verify_environment_variables():
    """
    Verify that critical environment variables are loaded and log their status.
    """
    critical_vars = [
        'ONLINE_FLASK_APP_BASE_URL',
        'FLASK_SECRET_KEY',
        'REMOTE_ADMIN_API_KEY',
        'ENTERPRISE_NAME',
        'DB_TYPE'
    ]
    
    print("🔍 Environment Variables Status:")
    
    missing_vars = []
    
    for var in critical_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values for logging
            if 'KEY' in var or 'SECRET' in var:
                masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '***'
                print(f"  ✅ {var}: {masked_value}")
            elif 'URL' in var:
                print(f"  ✅ {var}: {value}")
            else:
                print(f"  ✅ {var}: {value}")
        else:
            print(f"  ❌ {var}: NOT SET")
            missing_vars.append(var)
    
    # Special checks
    online_url = os.getenv('ONLINE_FLASK_APP_BASE_URL')
    if online_url:
        if 'localhost' in online_url:
            print(f"⚠️  ONLINE_FLASK_APP_BASE_URL is set to localhost: {online_url}")
            print("   This might cause issues in production!")
        else:
            print(f"✅ ONLINE_FLASK_APP_BASE_URL is properly configured: {online_url}")
    
    # Set defaults for missing critical variables
    if missing_vars:
        print(f"🔧 Setting defaults for missing variables: {missing_vars}")
        
        if 'DB_TYPE' not in os.environ:
            os.environ['DB_TYPE'] = 'sqlite'
            print("  ⚙️  Set DB_TYPE to 'sqlite'")
        
        if 'FLASK_SECRET_KEY' not in os.environ:
            os.environ['FLASK_SECRET_KEY'] = 'fallback-secret-key-change-in-production'
            print("  ⚙️  Set fallback FLASK_SECRET_KEY")
        
        if 'ENTERPRISE_NAME' not in os.environ:
            os.environ['ENTERPRISE_NAME'] = 'My Business'
            print("  ⚙️  Set ENTERPRISE_NAME to 'My Business'")

def get_environment_info():
    """
    Get information about the current environment for debugging.
    """
    info = {
        'frozen': getattr(sys, 'frozen', False),
        'executable': sys.executable,
        'working_directory': os.getcwd(),
        'python_path': sys.path[0] if sys.path else 'Unknown',
    }
    
    if getattr(sys, 'frozen', False):
        info['bundle_dir'] = getattr(sys, '_MEIPASS', 'Unknown')
        info['executable_dir'] = str(Path(sys.executable).parent)
    
    return info

def create_sample_env_file():
    """
    Create a sample .env file in the current directory if one doesn't exist.
    """
    env_file = Path('.env')
    
    if not env_file.exists():
        sample_content = """# Business Management Application Environment Variables

# Database Configuration
DB_TYPE=sqlite
DATABASE_URL=sqlite:///instance/instance_data.db

# Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here-change-in-production

# Business Information
ENTERPRISE_NAME=My Pharmacy
PHARMACY_ADDRESS=Global Business Solution Center
PHARMACY_CONTACT=+233547096268
PHARMACY_LOCATION=Your Town, Your Region

# SMS Configuration (Arkesel)
ARKESEL_API_KEY=your-arkesel-api-key
ARKESEL_SENDER_ID=uniquebence
ADMIN_PHONE_NUMBER=233547096268

# API Keys
REMOTE_ADMIN_API_KEY=your-remote-admin-api-key
FLASK_API_SECRET_KEY=your-flask-api-secret-key

# Admin Credentials
SUPER_ADMIN_USERNAME=superadmin
SUPER_ADMIN_PASSWORD=superpassword
APP_VIEWER_ADMIN_USERNAME=viewer
APP_VIEWER_ADMIN_PASSWORD=viewer123

# Online Sync Configuration
ONLINE_FLASK_APP_BASE_URL=https://www.globalbusinesstechnology.com
"""
        
        try:
            with open(env_file, 'w') as f:
                f.write(sample_content)
            print(f"✅ Created sample .env file: {env_file.absolute()}")
            print("📝 Please edit the .env file with your actual configuration values")
            return True
        except Exception as e:
            print(f"❌ Failed to create sample .env file: {e}")
            return False
    else:
        print(f"📄 .env file already exists: {env_file.absolute()}")
        return True

if __name__ == "__main__":
    # Test the environment loader
    print("Testing Environment Loader...")
    print("=" * 50)
    
    env_info = get_environment_info()
    print("Environment Information:")
    for key, value in env_info.items():
        print(f"  {key}: {value}")
    
    print("\nLoading environment variables...")
    success = load_environment_variables()
    
    if not success:
        print("\nCreating sample .env file...")
        create_sample_env_file()
    
    print("\nDone!")
