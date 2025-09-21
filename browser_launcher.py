import webbrowser
from threading import Timer
import logging

def open_browser(port=5000):
    """
    Open the default web browser to the application URL after a short delay.
    
    Args:
        port (int): The port number where the Flask app is running (default: 5000)
    """
    url = f"http://127.0.0.1:{port}"
    
    def _open_browser():
        try:
            webbrowser.open(url)
            logging.info(f"Browser opened to: {url}")
        except Exception as e:
            logging.error(f"Failed to open browser: {e}")
    
    # Open the URL in a new thread after a 1-second delay
    # This ensures the Flask server has time to start up
    Timer(1, _open_browser).start()
    logging.info(f"Browser will open to {url} in 1 second...")
