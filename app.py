from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort, Response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user, login_required, UserMixin
from functools import wraps
from datetime import datetime, date, timedelta
import os
import csv
import sys
import uuid
import pandas as pd
import requests
import json
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, create_engine, text, func, cast, or_
from dotenv import load_dotenv
from flask import current_app
from extensions import db, migrate
import io
import logging
from sync_api import sync_api
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import time
import threading
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from env_loader import load_environment_variables
from browser_launcher import open_browser
from db_initializer import safe_database_initialization

# Load environment variables using the custom loader
load_environment_variables()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Path Configuration for PyInstaller ---
def get_app_paths():
    """Get proper paths for templates, static files, and database based on execution context."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        base_dir = sys._MEIPASS
        template_dir = os.path.join(base_dir, 'templates')
        static_dir = os.path.join(base_dir, 'static')
        
        # For database, use a writable location outside the bundle
        executable_dir = os.path.dirname(sys.executable)
        instance_dir = os.path.join(executable_dir, 'instance')
        if not os.path.exists(instance_dir):
            os.makedirs(instance_dir)
        db_path = os.path.join(instance_dir, 'instance_data.db')
    else:
        # Running in development
        base_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(base_dir, 'templates')
        static_dir = os.path.join(base_dir, 'static')
        
        instance_dir = os.path.join(base_dir, 'instance')
        if not os.path.exists(instance_dir):
            os.makedirs(instance_dir)
        db_path = os.path.join(instance_dir, 'instance_data.db')
    
    return {
        'template_folder': template_dir,
        'static_folder': static_dir,
        'db_path': db_path,
        'instance_path': os.path.dirname(db_path)
    }

# --- Global Configuration ---
ARKESEL_API_KEY = os.getenv('ARKESEL_API_KEY')
ARKESEL_SENDER_ID = os.getenv('ARKESEL_SENDER_ID', 'YourSenderID')
ARKESEL_SMS_URL = "https://sms.arkesel.com/sms/api"
REMOTE_SERVER_URL = os.getenv('ONLINE_FLASK_APP_BASE_URL', 'http://localhost:5000')
ENTERPRISE_NAME = os.getenv('ENTERPRISE_NAME', 'Your Enterprise Name')
PHARMACY_LOCATION = os.getenv('PHARMACY_LOCATION', 'Your Town, Your Region')
PHARMACY_ADDRESS = os.getenv('PHARMACY_ADDRESS', '123 Business St')
PHARMACY_CONTACT = os.getenv('PHARMACY_CONTACT', '+1234567890')
ADMIN_PHONE_NUMBER = os.getenv('ADMIN_PHONE_NUMBER', '')

# --- Sync Status Variables ---
SYNC_STATUS = {
    "is_syncing": False,
    "last_sync_time": None,
    "last_sync_success": None,
    "last_sync_message": "Idle."
}

enhanced_sync_status = {
    'last_sync': None,
    'sync_conflicts': [],
    'sync_health': 'healthy',
    'sync_running': False
}

CONFLICT_TYPES = {
    'DATA_MISMATCH': 'Data mismatch between systems',
    'TIMESTAMP_CONFLICT': 'Timestamp synchronization conflict',
    'DUPLICATE_RECORD': 'Duplicate record detected',
    'VALIDATION_ERROR': 'Data validation error'
}

# --- Sync Helper Functions ---
def check_sync_conflicts():
    """Check for potential sync conflicts"""
    from datetime import datetime
    import random
    
    conflicts = []
    
    if random.random() > 0.7:
        conflicts.append({
            'id': f'conflict_{int(datetime.now().timestamp())}',
            'type': 'TIMESTAMP_CONFLICT', 
            'description': 'Data timestamp mismatch detected',
            'severity': 'medium',
            'created_at': datetime.now().isoformat(),
            'table_affected': 'sales'
        })
    
    enhanced_sync_status['sync_conflicts'] = conflicts
    return conflicts

def resolve_sync_conflict(conflict_id, resolution):
    """Resolve a sync conflict"""
    for i, conflict in enumerate(enhanced_sync_status['sync_conflicts']):
        if conflict['id'] == conflict_id:
            conflict['status'] = 'resolved'
            conflict['resolution'] = resolution
            conflict['resolved_at'] = datetime.now().isoformat()
            enhanced_sync_status['sync_conflicts'].pop(i)
            return {'success': True, 'message': 'Conflict resolved successfully'}
    
    return {'success': False, 'message': 'Conflict not found'}

def get_enhanced_sync_status():
    """Get current enhanced synchronization status"""
    from datetime import datetime
    
    check_sync_conflicts()
    
    return {
        'last_sync': enhanced_sync_status.get('last_sync') or datetime.now().isoformat(),
        'sync_health': enhanced_sync_status['sync_health'],
        'sync_running': enhanced_sync_status['sync_running'],
        'conflicts_count': len(enhanced_sync_status['sync_conflicts']),
        'conflicts': enhanced_sync_status['sync_conflicts'],
        'status_updated': datetime.now().isoformat()
    }

def create_app():
    """Application factory function with proper path handling"""
    
    # Get proper paths
    paths = get_app_paths()
    
    # Create Flask app with correct template and static folders
    app = Flask(__name__, 
                template_folder=paths['template_folder'],
                static_folder=paths['static_folder'],
                instance_path=paths['instance_path'])
    
    print(f"✅ App paths configured:")
    print(f"   Template folder: {paths['template_folder']}")
    print(f"   Static folder: {paths['static_folder']}")
    print(f"   Database path: {paths['db_path']}")
    print(f"   Instance path: {paths['instance_path']}")
    
    # --- Configuration ---
    DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
    if DB_TYPE == 'sqlite':
        # Use the properly configured database path
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{paths["db_path"]}'
        print(f"✅ Using SQLite database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    else:
        pg_url = os.getenv(
            'DATABASE_URL',
            'postgresql://bisinessdb_user:QceRMwRe2FtjhPk8iMLCIKB3j3s4KmhI@dpg-d1olvgbuibrs73cum700-a.oregon-postgres.render.com/bisinessdb'
        )
        app.config['SQLALCHEMY_DATABASE_URI'] = pg_url.replace("postgresql://", "postgresql+psycopg2://")
        print(f"✅ Using PostgreSQL database with psycopg2: {app.config['SQLALCHEMY_DATABASE_URI']}")

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your_super_secret_key_here')
    app.config['ENV'] = 'development'
    app.config['DEBUG'] = True

    # --- Initialize Flask Extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    csrf = CSRFProtect(app)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'
    
    # Import models after the extensions have been initialized
    from models import User, Business, SalesRecord, InventoryItem, HirableItem, RentalRecord, Creditor, Debtor, CompanyTransaction, FutureOrder, Company, Customer, ReturnRecord
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, user_id)

    # --- Initialize Database ---
    if DB_TYPE == 'sqlite':
        safe_database_initialization(paths['db_path'], app, db)
    else:
        with app.app_context():
            db.create_all()
    
    # Register the sync API blueprint
    app.register_blueprint(sync_api)
    
    # --- Route Definitions and Other App Logic ---
    # ... (Add your routes here - the rest of your app.py content)
    
    return app

def main():
    """Main entry point for the application"""
    try:
        print("🚀 Starting Business Management Application...")
        
        # Check if running as frozen executable
        if getattr(sys, 'frozen', False):
            print("📦 Running as packaged executable")
        else:
            print("🐍 Running in development mode")
        
        # Create the Flask application
        app = create_app()
        
        # Get port from environment or use default
        port = int(os.getenv('PORT', 5000))
        
        print(f"🌐 Application will run on port {port}")
        print(f"🔗 Access the application at: http://127.0.0.1:{port}")
        
        # Open browser automatically (only in non-frozen mode for development)
        if not getattr(sys, 'frozen', False):
            open_browser(port)
        
        # Run the Flask application
        app.run(
            host='127.0.0.1',
            port=port,
            debug=False,  # Set to False for production/frozen apps
            use_reloader=False  # Disable reloader for frozen apps
        )
        
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        logging.error(f"Application startup failed: {e}")
        if getattr(sys, 'frozen', False):
            input("Press Enter to exit...")  # Keep console open in frozen mode
        raise

if __name__ == '__main__':
    main()
