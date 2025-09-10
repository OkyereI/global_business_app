# register_superadmin.py
import os
from app import create_app
from models import Business, User # Import the User model
from extensions import db
from werkzeug.security import generate_password_hash # Import password hashing utility
from datetime import datetime, date, timedelta
# Create a Flask application instance.
# This is necessary to work with the database context.
app = create_app()

def register_superadmin_business():
    """
    Registers a super admin business in the database if it doesn't already exist.
    """
    superadmin_name = "Admin Business Global"
    superadmin_business_id = "super_admin_business_global"
    
    # Check if the super admin business with the correct ID already exists.
    existing_business = db.session.get(Business, superadmin_business_id)
    
    if existing_business:
        print(f"Business '{existing_business.name}' with ID '{existing_business.id}' already exists.")
        return existing_business.id
    
    # Create a new Business record for the super admin
    superadmin_business = Business(
        id=superadmin_business_id,
        name=superadmin_name,
        type="Administration Office",
        email="superadmin@pharmapp.com",
        is_active=True,
        remote_id=superadmin_business_id
    )
    
    try:
        db.session.add(superadmin_business)
        db.session.commit()
        print(f"'{superadmin_name}' business successfully registered.")
        return superadmin_business.id
    except Exception as e:
        db.session.rollback()
        print(f"An error occurred while registering the super admin business: {e}")
        return None

def register_superadmin_user(business_id):
    """
    Registers or updates the super admin user.
    """
    if not business_id:
        print("Superadmin business ID is missing. Cannot register user.")
        return

    superadmin_id = "super_admin"
    superadmin_password = "super_password" # A new, known default password

    # Check if the superadmin user already exists
    existing_user = db.session.get(User, superadmin_id)

    if existing_user:
        # User exists, so update their password
        existing_user.password = generate_password_hash(superadmin_password)
        db.session.commit()
        print(f"Superadmin user '{superadmin_id}' already exists. Password has been reset.")
    else:
        # User does not exist, create a new one
        new_superadmin = User(
            id=superadmin_id,
            username=superadmin_id,
            password=generate_password_hash(superadmin_password),
            role='super_admin',
            business_id=business_id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(new_superadmin)
        db.session.commit()
        print(f"Superadmin user '{superadmin_id}' successfully registered.")
    
    print(f"\nUse the following credentials to log in:")
    print(f"Username: {superadmin_id}")
    print(f"Password: {superadmin_password}")

if __name__ == '__main__':
    with app.app_context():
        # Make sure you have run 'flask db upgrade' first to create the tables.
        business_id = register_superadmin_business()
        if business_id:
            register_superadmin_user(business_id)
