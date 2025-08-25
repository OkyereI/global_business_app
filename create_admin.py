import os
import sys
from app import app, db, Business, User
import uuid
from werkzeug.security import generate_password_hash

# This script must be run with the correct database configured
# For local use, ensure DB_TYPE is set to 'sqlite' in your .env or environment

def create_default_admin():
    with app.app_context():
        try:
            # First, ensure all tables are created based on your models
            db.create_all()
            print("Database tables checked and created if they did not exist.")

            print("Checking for existing default business...")
            
            # Check if a default business already exists to prevent duplicates
            default_business = Business.query.filter_by(name='Default Admin Business').first()
            
            if not default_business:
                print("Creating default business...")
                default_business = Business(
                    id=str(uuid.uuid4()),
                    name='Default Admin Business',
                    type='Administration',
                    address='Global',
                    location='kenyasi',
                    contact='0547096268',
                    email='admin@global.com',
                    is_active=True
                )
                db.session.add(default_business)
                db.session.commit()
                print(f"Default business '{default_business.name}' created.")
            else:
                print(f"Default business '{default_business.name}' already exists. Using existing one.")
            
            # Ensure default_business is available for user creation, even if it existed before this run
            default_business = Business.query.filter_by(name='Default Admin Business').first()
            if not default_business:
                # This should ideally not happen if the above logic is correct, but as a safeguard
                print("Error: Default business not found after creation/check. Cannot create super admin.")
                return

            print("Checking for existing super admin user...")
            super_admin_username = 'admin' # Define username here
            existing_super_admin = User.query.filter_by(username=super_admin_username).first()

            if not existing_super_admin:
                print("Creating default super admin user...")
                super_admin_password = 'uniquebence' # Define password here
                hashed_password = generate_password_hash(super_admin_password, method='pbkdf2:sha256')
                
                new_user = User(
                    id=str(uuid.uuid4()),
                    username=super_admin_username,
                    password=hashed_password,
                    business_id=default_business.id,
                    role='super_admin',
                    is_active=True,
                )
                db.session.add(new_user)
                db.session.commit()
                print(f"Super admin user '{super_admin_username}' created successfully.")
                print(f"You can now log in with username: {super_admin_username} and password: {super_admin_password}")
            else:
                print(f"Super admin user '{super_admin_username}' already exists. Skipping creation.")
                print("If you need to reset the super admin password, you must do so manually or delete the user from the database.")
            
        except Exception as e:
            print(f"Error during initial super admin creation: {e}")
            db.session.rollback() # Rollback in case of error to prevent partial commits

if __name__ == '__main__':
    create_default_admin()