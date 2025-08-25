# create_db.py - Script to initialize the database and create default users/data

import os
import sys
from datetime import datetime
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv
import uuid
import json

# Add project root to sys.path to allow imports from app and models
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()

# Set up Flask app context for DB operations
from flask import Flask
from extensions import db, migrate # Import db and migrate from extensions
from flask_wtf.csrf import CSRFProtect # Only needed if CSRFProtect requires app context at import

# Define the create_app function here or import if it's external
# For this script, a minimal app creation is usually sufficient
def create_minimal_app_for_db():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    DB_TYPE = os.getenv('DB_TYPE', 'postgresql') # Default to postgresql if not set
    if DB_TYPE == 'sqlite':
        db_path = os.path.join(app.instance_path, 'instance_data.db')
        if not os.path.exists(app.instance_path):
            os.makedirs(app.instance_path)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        print(f"Configuring for SQLite: {app.config['SQLALCHEMY_DATABASE_URI']}")
    else: # Default to PostgreSQL
        pg_url = os.getenv(
            'DATABASE_URL',
            'postgresql://user:pass@host:port/dbname' # Fallback for local testing if env var not set
        )
        app.config['SQLALCHEMY_DATABASE_URI'] = pg_url.replace("postgresql://", "postgresql+psycopg2://")
        print(f"Configuring for PostgreSQL: {app.config['SQLALCHEMY_DATABASE_URI']}")

    db.init_app(app)
    migrate.init_app(app, db) # Initialize migrate too, even if not running migrations here
    
    # Import models AFTER db.init_app
    with app.app_context(): # Ensure models are loaded within app context
        from models import User, Business, InventoryItem # Import necessary models

    return app

app = create_minimal_app_for_db()

with app.app_context():
    from models import User, Business, InventoryItem, HirableItem, SalesRecord, Company, Customer, Creditor, Debtor, FutureOrder, RentalRecord
    
    # --- Check if tables exist and perform migrations if necessary ---
    # This script is primarily for initial data, migrations should be run via 'flask db upgrade'
    # db.create_all() is typically not used with Flask-Migrate
    
    # Check if a super admin already exists to prevent duplicates
    existing_super_admin = User.query.filter_by(username=os.getenv('SUPER_ADMIN_USERNAME')).first()

    if not existing_super_admin:
        print("Creating default super admin user...")
        # Hash password from environment variable
        super_admin_password_hash = generate_password_hash(os.getenv('SUPER_ADMIN_PASSWORD', 'superpassword'), method='pbkdf2:sha256')
        
        # Create a default business for the super admin if none exists
        default_business = Business.query.filter_by(name='SuperAdmin Global Business').first()
        if not default_business:
            print("Creating default 'SuperAdmin Global Business'...")
            default_business = Business(
                id=str(uuid.uuid4()),
                name='SuperAdmin Global Business',
                type='Pharmacy', # Or a more generic "Global Management" type
                address='Global',
                location='Global HQ',
                contact=os.getenv('ADMIN_PHONE_NUMBER', 'N/A'),
                email='superadmin@global.com',
                is_active=True,
                date_added=datetime.utcnow(),
                last_updated=datetime.utcnow(),
                # Assuming remote_id will be populated during the first sync
                # last_synced_at will also be updated during sync
            )
            db.session.add(default_business)
            db.session.commit() # Commit business first to get its ID

        super_admin_user = User(
            id=str(uuid.uuid4()),
            username=os.getenv('SUPER_ADMIN_USERNAME', 'superadmin'),
            _password_hash=super_admin_password_hash, # Directly assign the hashed password
            role='super_admin',
            business_id=default_business.id, # Link super admin to the global business
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(super_admin_user)
        db.session.commit()
        print("Default super admin user created successfully.")
    else:
        print("Super admin user already exists.")

    # You might want to add other initial data here for development/testing
    # e.g., default categories, a few inventory items, etc.

    print("Database initialization/check complete.")

