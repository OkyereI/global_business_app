import os
from datetime import datetime
from app import create_app, db
from models import User, Business
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError

# Initialize the Flask app and database
app = create_app()

with app.app_context():
    print("Creating database tables...")
    db.create_all()
    print("Database tables created successfully.")

    # Check for and create the superadmin user and business
    super_admin_business_id = 'super_admin_business'
    super_admin_username = os.getenv('SUPER_ADMIN_USERNAME') or 'superadmin'
    super_admin_password = os.getenv('SUPER_ADMIN_PASSWORD') or 'superpassword'

    existing_business = Business.query.filter_by(id=super_admin_business_id).first()
    existing_super_admin = User.query.filter_by(username=super_admin_username).first()

    if not existing_super_admin:
        print("Superadmin user not found. Creating new superadmin...")
        
        # If business does not exist, create it
        if not existing_business:
            print("Superadmin business not found. Creating new business...")
            super_admin_business = Business(
                id=super_admin_business_id,
                name='Admin Business',
                type='headquarters',
                is_active=True
            )
            db.session.add(super_admin_business)
        
        # Create the user, leveraging the password setter in the model
        super_admin = User(
            id='superadmin',
            username=super_admin_username,
            role='super_admin',
            business_id=super_admin_business_id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        # Manually set the password to trigger the hashing property
        super_admin.password = super_admin_password
        
        db.session.add(super_admin)
        
        try:
            db.session.commit()
            print(f"Superadmin user '{super_admin_username}' created successfully.")
        except IntegrityError as e:
            db.session.rollback()
            print(f"Failed to create superadmin due to an integrity error: {e}")
        except Exception as e:
            db.session.rollback()
            print(f"An unexpected error occurred: {e}")
    else:
        print(f"Superadmin user '{super_admin_username}' already exists. No new user created.")