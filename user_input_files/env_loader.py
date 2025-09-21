"""
Environment variable loader for PyInstaller bundles
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
    
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        try:
            # Try to load from the bundle's temporary directory (_MEIPASS)
            bundle_dir = Path(sys._MEIPASS)
            env_file_bundle = bundle_dir / '.env'
            env_locations.append(str(env_file_bundle))
            
            if env_file_bundle.exists():
                load_dotenv(env_file_bundle)
                env_loaded = True
                logging.info(f"✅ Loaded .env from bundle: {env_file_bundle}")
            
            # Also try to load from the executable's directory
            executable_dir = Path(sys.executable).parent
            env_file_exe = executable_dir / '.env'
            env_locations.append(str(env_file_exe))
            
            if env_file_exe.exists():
                load_dotenv(env_file_exe)
                env_loaded = True
                logging.info(f"✅ Loaded .env from executable directory: {env_file_exe}")
                
        except Exception as e:
            logging.warning(f"Error loading .env from bundle locations: {e}")
    else:
        # Running in development mode
        current_dir = Path.cwd()
        env_file_dev = current_dir / '.env'
        env_locations.append(str(env_file_dev))
        
        if env_file_dev.exists():
            load_dotenv(env_file_dev)
            env_loaded = True
            logging.info(f"✅ Loaded .env from development directory: {env_file_dev}")
    
    # Log attempted locations for debugging
    logging.info(f"Environment file search locations: {env_locations}")
    
    if not env_loaded:
        logging.warning("⚠️  No .env file found in any expected location!")
        logging.warning("🔧 Using default/system environment variables only")
    
    # Verify critical environment variables
    verify_environment_variables()
    
    return env_loaded

def verify_environment_variables():
    """
    Verify that critical environment variables are loaded and log their status.
    """
    critical_vars = [
        'ONLINE_FLASK_APP_BASE_URL',
        'FLASK_SECRET_KEY',
        'REMOTE_ADMIN_API_KEY',
        'ENTERPRISE_NAME'
    ]
    
    logging.info("🔍 Environment Variables Status:")
    
    for var in critical_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values for logging
            if 'KEY' in var or 'SECRET' in var:
                masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '***'
                logging.info(f"  ✅ {var}: {masked_value}")
            elif 'URL' in var:
                logging.info(f"  ✅ {var}: {value}")
            else:
                logging.info(f"  ✅ {var}: {value}")
        else:
            logging.warning(f"  ❌ {var}: NOT SET")
    
    # Special check for the problematic URL
    online_url = os.getenv('ONLINE_FLASK_APP_BASE_URL')
    if online_url:
        if 'localhost' in online_url:
            logging.warning(f"⚠️  ONLINE_FLASK_APP_BASE_URL is set to localhost: {online_url}")
            logging.warning("   This might cause issues in production!")
        else:
            logging.info(f"✅ ONLINE_FLASK_APP_BASE_URL is properly configured: {online_url}")
    else:
        logging.error("❌ ONLINE_FLASK_APP_BASE_URL is not set - will default to localhost:5000!")

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

if __name__ == "__main__":
    # Test the environment loader
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("Testing Environment Loader...")
    print("=" * 50)
    
    env_info = get_environment_info()
    print("Environment Information:")
    for key, value in env_info.items():
        print(f"  {key}: {value}")
    
    print("\nLoading environment variables...")
    load_environment_variables()
    
    print("\nDone!")