import os
import sys
from sqlalchemy import create_engine, inspect, text
import logging
from pathlib import Path

def check_database_exists_and_has_tables(db_path, app, db):
    """
    More robust check for database existence and table presence.
    Returns True if database exists and has tables, False otherwise.
    """
    try:
        # Ensure the directory exists
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            print(f"📁 Creating database directory: {db_dir}")
            os.makedirs(db_dir, exist_ok=True)
        
        # First check if the database file exists
        if not os.path.exists(db_path):
            print(f"📄 Database file does not exist: {db_path}")
            return False
        
        # Check if file has reasonable size (not empty)
        file_size = os.path.getsize(db_path)
        if file_size < 1024:  # Less than 1KB suggests empty/new DB
            print(f"📄 Database file is too small: {file_size} bytes")
            return False
        
        # Use SQLAlchemy inspector to check for tables
        with app.app_context():
            try:
                engine = db.get_engine()
                inspector = inspect(engine)
                table_names = inspector.get_table_names()
                
                # Check for key tables that should exist
                required_tables = ['user', 'businesses', 'inventory_items', 'sales_records']
                existing_tables = [table for table in required_tables if table in table_names]
                
                if len(existing_tables) >= 3:  # At least 3 core tables should exist
                    print(f"✅ Database exists with {len(existing_tables)} core tables: {existing_tables}")
                    return True
                else:
                    print(f"⚠️  Database exists but missing core tables.")
                    print(f"   Found tables: {table_names}")
                    print(f"   Required tables: {required_tables}")
                    return False
            except Exception as engine_error:
                print(f"❌ Engine error while checking database: {engine_error}")
                return False
                
    except Exception as e:
        print(f"❌ Error checking database existence: {e}")
        logging.warning(f"Error checking database existence: {e}")
        return False

def safe_database_initialization(db_path, app, db):
    """
    Safely initialize database only if it doesn't exist or is incomplete.
    Enhanced for PyInstaller compatibility.
    """
    try:
        print(f"📋 Database initialization starting...")
        print(f"   Database path: {db_path}")
        print(f"   Database directory: {os.path.dirname(db_path)}")
        print(f"   App frozen: {getattr(sys, 'frozen', False)}")
        
        # Ensure database directory exists and is writable
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            print(f"📁 Creating database directory: {db_dir}")
            os.makedirs(db_dir, exist_ok=True)
        
        # Check if directory is writable
        if not os.access(db_dir, os.W_OK):
            raise PermissionError(f"Database directory is not writable: {db_dir}")
        
        if check_database_exists_and_has_tables(db_path, app, db):
            print("✅ Database exists with all required tables - skipping creation")
            return True
        else:
            print("🔧 Database missing or incomplete - creating tables...")
            
            with app.app_context():
                try:
                    # Create all tables
                    db.create_all()
                    print("✅ Database tables created successfully")
                    
                    # Verify tables were created
                    engine = db.get_engine()
                    inspector = inspect(engine)
                    table_names = inspector.get_table_names()
                    print(f"📄 Created tables: {table_names}")
                    
                    # Create default admin user if needed
                    create_default_users(db)
                    
                    return True
                    
                except Exception as create_error:
                    print(f"❌ Error creating database tables: {create_error}")
                    logging.error(f"Database table creation failed: {create_error}")
                    raise
                    
    except Exception as e:
        print(f"❌ Error during database initialization: {e}")
        logging.error(f"Database initialization failed: {e}")
        
        # In frozen apps, provide more helpful error information
        if getattr(sys, 'frozen', False):
            print("\n🔧 Troubleshooting tips for packaged app:")
            print("   1. Ensure the app has write permissions to its directory")
            print("   2. Try running as administrator if on Windows")
            print("   3. Check if antivirus is blocking file creation")
            print(f"   4. Database directory: {os.path.dirname(db_path)}")
            
        raise

def create_default_users(db):
    """
    Create default users and business if they don't exist.
    """
    try:
        from models import User, Business
        import uuid
        from werkzeug.security import generate_password_hash
        
        print("👥 Checking for default users...")
        
        # Check if any users exist
        existing_users = User.query.count()
        if existing_users > 0:
            print(f"✅ Found {existing_users} existing users - skipping default user creation")
            return
        
        print("👥 Creating default users and business...")
        
        # Create default business
        default_business = Business(
            id=str(uuid.uuid4()),
            name="Default Business",
            type="pharmacy",
            address="Default Address",
            location="Default Location",
            contact="+1234567890",
            is_active=True
        )
        db.session.add(default_business)
        db.session.flush()  # Get the ID
        
        # Create super admin user
        super_admin = User(
            id=str(uuid.uuid4()),
            username=os.getenv('SUPER_ADMIN_USERNAME', 'superadmin'),
            role='super_admin',
            business_id=default_business.id,
            is_active=True
        )
        super_admin.password = os.getenv('SUPER_ADMIN_PASSWORD', 'superpassword')
        db.session.add(super_admin)
        
        # Create viewer user
        viewer_user = User(
            id=str(uuid.uuid4()),
            username=os.getenv('APP_VIEWER_ADMIN_USERNAME', 'viewer'),
            role='viewer',
            business_id=default_business.id,
            is_active=True
        )
        viewer_user.password = os.getenv('APP_VIEWER_ADMIN_PASSWORD', 'viewer123')
        db.session.add(viewer_user)
        
        db.session.commit()
        print("✅ Default users and business created successfully")
        print(f"   Super Admin: {super_admin.username}")
        print(f"   Viewer: {viewer_user.username}")
        print(f"   Business: {default_business.name}")
        
    except Exception as e:
        print(f"❌ Error creating default users: {e}")
        db.session.rollback()
        logging.error(f"Default user creation failed: {e}")
        # Don't raise - this is not critical for app functionality

def verify_database_health(db_path, app, db):
    """
    Perform a comprehensive health check on the database.
    """
    try:
        print("🔍 Performing database health check...")
        
        if not os.path.exists(db_path):
            print("❌ Database file does not exist")
            return False
        
        with app.app_context():
            # Test basic connectivity
            try:
                result = db.session.execute(text("SELECT 1")).scalar()
                if result == 1:
                    print("✅ Database connectivity: OK")
                else:
                    print("❌ Database connectivity: FAILED")
                    return False
            except Exception as e:
                print(f"❌ Database connectivity test failed: {e}")
                return False
            
            # Check table structure
            try:
                engine = db.get_engine()
                inspector = inspect(engine)
                table_names = inspector.get_table_names()
                
                required_tables = ['user', 'businesses', 'inventory_items', 'sales_records']
                missing_tables = [table for table in required_tables if table not in table_names]
                
                if missing_tables:
                    print(f"❌ Missing tables: {missing_tables}")
                    return False
                else:
                    print(f"✅ All required tables present: {len(table_names)} total tables")
            except Exception as e:
                print(f"❌ Table structure check failed: {e}")
                return False
            
            # Test user table
            try:
                from models import User
                user_count = User.query.count()
                print(f"✅ User table accessible: {user_count} users")
            except Exception as e:
                print(f"❌ User table test failed: {e}")
                return False
        
        print("✅ Database health check passed")
        return True
        
    except Exception as e:
        print(f"❌ Database health check failed: {e}")
        return False

if __name__ == "__main__":
    print("Database Initializer Test")
    print("=" * 30)
    
    # This would typically be called from your main app
    test_db_path = "test_database.db"
    print(f"Test database path: {test_db_path}")
