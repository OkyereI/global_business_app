# desktop_launcher.py

import os
import sys
import subprocess
import time
import threading
import webbrowser
from datetime import datetime

# Set environment variables for the bundled app
os.environ['DB_TYPE'] = 'sqlite' # Tell app.py to use SQLite
os.environ['FLASK_ENV'] = 'production' # Don't run in debug mode for desktop
os.environ['FLASK_SECRET_KEY'] = 'your_desktop_app_secret_key' # Use a consistent key

# !!! IMPORTANT: Replace with the actual URL of your *online* Flask API
# This is the central server the desktop app will sync with.
os.environ['FLASK_API_URL'] = 'https://global-business-app.onrender.com' # <-- CHANGE THIS to your deployed API URL (e.g., 'https://your-pharmacy-app.com')

# Path for your app.py relative to this launcher script
# If desktop_launcher.py is in the same directory as app.py:
APP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.py')

FLASK_HOST = '127.0.0.1'
FLASK_PORT = 5000
LOCAL_URL = f"http://{FLASK_HOST}:{FLASK_PORT}"

# Import app for context (optional, but good for direct function calls)
try:
    from app import app, db, perform_sync, check_network_online # Import your app and sync function
except ImportError:
    print("Error: Could not import Flask app. Make sure app.py is accessible.")
    sys.exit(1)

# Function to start the Flask server
def run_flask_server():
    print(f"Starting Flask server at {LOCAL_URL}...")
    # Use Flask's CLI to run the app
    # We need to set FLASK_APP and cwd to the directory of app.py
    env = os.environ.copy()
    env['FLASK_APP'] = 'app.py' # Specify your Flask app file

    try:
        # Use subprocess.Popen to run Flask in a non-blocking way
        # stdout/stderr can be redirected to a log file if needed
        process = subprocess.Popen(
            [sys.executable, '-m', 'flask', 'run', '--host', FLASK_HOST, '--port', str(FLASK_PORT)],
            env=env,
            cwd=os.path.dirname(APP_PATH) # Set current working directory
        )
        print(f"Flask server process started with PID: {process.pid}")
        return process
    except Exception as e:
        print(f"Failed to start Flask server: {e}")
        return None

# Function to open the browser
def open_browser():
    print(f"Attempting to open browser to {LOCAL_URL}...")
    # Give the server a moment to start up
    time.sleep(3)
    webbrowser.open(LOCAL_URL)
    print("Browser opened.")

# Main desktop app logic
if __name__ == '__main__':
    # Initialize app context for db.create_all() etc. if needed on first run
    with app.app_context():
        # This part runs when the desktop app is launched
        print("Desktop launcher started.")
        # Ensure local SQLite DB is created (db.create_all() is conditional in app.py)
        db.create_all() 

        # Start Flask server in a separate thread/process
        flask_process = run_flask_server()

        if flask_process:
            # Open browser after a short delay
            threading.Thread(target=open_browser).start()

            # Basic sync loop (can be more sophisticated with threading/interval)
            business_id_for_sync = "445fd196-b59e-4582-97ac-31b7a3b7a057" # !!! IMPORTANT: This needs to be the ID of the specific business tied to this desktop app.
                                                             # In a real app, this would be set during initial setup/login.
                                                             # E.g., read from a local config file, or fetched via a one-time login API call.
                                                             # For now, it's a placeholder.

            if business_id_for_sync == "445fd196-b59e-4582-97ac-31b7a3b7a057":
                print("WARNING: '445fd196-b59e-4582-97ac-31b7a3b7a057' placeholder used for sync. Please update it.")


            # Keep the main thread alive to monitor Flask process, or implement a GUI
            try:
                while True:
                    # Periodically try to sync if online
                    if check_network_online():
                        sync_success, sync_message = perform_sync(business_id_for_sync)
                        print(f"Automated sync attempt: {sync_message}")
                    else:
                        print("Still offline. Sync will resume when online.")
                    time.sleep(300) # Sync every 5 minutes (300 seconds)

            except KeyboardInterrupt:
                print("Shutting down desktop app.")
            finally:
                if flask_process:
                    print("Terminating Flask server...")
                    flask_process.terminate()
                    flask_process.wait() # Wait for process to exit
                print("Desktop app terminated.")