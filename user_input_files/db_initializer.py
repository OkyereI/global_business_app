import os
import sys
from sqlalchemy import create_engine, inspect, text
import logging

def check_database_exists_and_has_tables(db_path, app, db):
    """
    More robust check for database existence and table presence.
    Returns True if database exists and has tables, False otherwise.
    """
    try:
        # First check if the database file exists
        if not os.path.exists(db_path):
            logging.info(f"Database file does not exist: {db_path}")
            return False
        
        # Check if file has reasonable size (not empty)
        if os.path.getsize(db_path) < 1024:  # Less than 1KB suggests empty/new DB
            logging.info(f"Database file is too small: {os.path.getsize(db_path)} bytes")
            return False
        
        # Use SQLAlchemy inspector to check for tables
        with app.app_context():
            engine = db.get_engine()
            inspector = inspect(engine)
            table_names = inspector.get_table_names()
            
            # Check for key tables that should exist
            required_tables = ['users', 'businesses', 'inventory_items', 'sales_records']
            existing_tables = [table for table in required_tables if table in table_names]
            
            if len(existing_tables) >= 3:  # At least 3 core tables should exist
                logging.info(f"Database exists with {len(existing_tables)} core tables: {existing_tables}")
                return True
            else:
                logging.info(f"Database exists but missing core tables. Found: {table_names}")
                return False
                
    except Exception as e:
        logging.warning(f"Error checking database existence: {e}")
        return False

def safe_database_initialization(db_path, app, db):
    """
    Safely initialize database only if it doesn't exist or is incomplete.
    """
    try:
        if check_database_exists_and_has_tables(db_path, app, db):
            print("✅ Database exists with all required tables - skipping creation")
            return True
        else:
            print("🔧 Database missing or incomplete - creating tables...")
            with app.app_context():
                db.create_all()
                print("✅ Database tables created successfully")
                return True
    except Exception as e:
        print(f"❌ Error during database initialization: {e}")
        logging.error(f"Database initialization failed: {e}")
        raise
