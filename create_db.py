from app import create_app
from extensions import db # <<< MUST import db from extensions.py
from models import User, Business # <<< Correctly imports models

# Create the application instance by calling the create_app() function
app = create_app()

# Use the application context to perform database operations
with app.app_context():
    db.create_all()
    print("Database tables created successfully!")

    super_admin_user = User.query.filter_by(role='super_admin').first()
    if not super_admin_user:
        global_business = Business.query.filter_by(name='Global Business').first()
        if not global_business:
            global_business = Business(name='Global Business', type='Global', address='N/A', location='N/A')
            db.session.add(global_business)
            db.session.commit()

        new_admin = User(username='superadmin', role='super_admin', business_id=global_business.id)
        new_admin.password = 'superpassword'
        db.session.add(new_admin)
        db.session.commit()
        print("Default super admin user created with username 'superadmin' and password 'password'.")
        print("!! REMEMBER TO CHANGE THIS PASSWORD IMMEDIATELY !!")
    else:
        print("Super admin user already exists. Skipping creation.")
