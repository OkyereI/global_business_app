# app.py - Enhanced Flask Application with PostgreSQL Database and Hardware Business Features

from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import uuid
from datetime import datetime, date, timedelta
import requests
from dotenv import load_dotenv
import json
import io
import csv # Import csv module for CSV export
from flask_migrate import Migrate # Import Flask-Migrate
from werkzeug.security import generate_password_hash, check_password_hash # Import for password hashing
from sqlalchemy import func,cast # Import func for aggregate functions
from flask_wtf.csrf import CSRFProtect # NEW: Import CSRFProtect


# --- Flask-Login setup (if you are using it, otherwise remove these lines) ---
# For simplicity, I'll define a basic login_required if Flask-Login is not explicitly used.
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Database Configuration ---
# Updated DATABASE_URL with the user-provided external PostgreSQL connection string
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://bisinessdb_user:QceRMwRe2FtjhPk8iMLCIKB3j3s4KmhI@dpg-d1olvgbu2psc73e2g10g-a.oregon-postgres.render.com/bisinessdb'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_very_secret_key_that_should_be_in_env')

db = SQLAlchemy(app)
migrate = Migrate(app, db) # Initialize Flask-Migrate
csrf = CSRFProtect(app) # NEW: Initialize CSRFProtect

# --- Arkesel SMS API Configuration ---
ARKESEL_SMS_URL = "https://sms.arkesel.com/sms/api"
ARKESEL_API_KEY = os.getenv('ARKESEL_API_KEY')
ARKESEL_SENDER_ID = os.getenv('ARKESEL_SENDER_ID', 'BizApp') # Default sender ID

# --- Global Constants ---
ENTERPRISE_NAME = "Your Enterprise Name" # Default name if not set in business info

# --- Database Models ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='sales') # 'admin', 'sales', 'manager', 'viewer_admin'
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True) # For soft deletion/deactivation
    date_added = db.Column(db.DateTime, default=datetime.now)
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Business(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    contact = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    business_type = db.Column(db.String(50), nullable=False) # e.g., 'Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'
    date_created = db.Column(db.DateTime, default=datetime.now)
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = db.Column(db.Boolean, default=True) # NEW: Field to track business activity status

    users = db.relationship('User', backref='business', lazy=True)
    inventory_items = db.relationship('InventoryItem', backref='business', lazy=True)
    sales_records = db.relationship('SaleRecord', backref='business', lazy=True)
    rental_records = db.relationship('RentalRecord', backref='business', lazy=True)
    hirable_items = db.relationship('HirableItem', backref='business', lazy=True)

    def __repr__(self):
        return f'<Business {self.name}>'

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    product_name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    supplier = db.Column(db.String(100), nullable=True)
    current_stock = db.Column(db.Float, default=0.0) # Can be decimal for items like tablets
    unit_of_measure = db.Column(db.String(50), default='units') # e.g., 'tablets', 'bottles', 'pieces', 'kg'
    cost_price = db.Column(db.Float, nullable=False)
    sale_price = db.Column(db.Float, nullable=False)
    batch_number = db.Column(db.String(100), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.now)
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = db.Column(db.Boolean, default=True) # For soft deletion/deactivation
    barcode = db.Column(db.String(100), unique=True, nullable=True) # New field for barcode
    item_type = db.Column(db.String(50), nullable=False) # 'Pharmacy', 'Hardware Material', 'Provision Store'
    number_of_tabs = db.Column(db.Float, default=1.0) # For Pharmacy: tabs per pack/bottle
    unit_price_per_tab = db.Column(db.Float, default=0.0) # For Pharmacy: calculated price per tab
    is_fixed_price = db.Column(db.Boolean, default=False) # For Hardware: if price is fixed per item
    fixed_sale_price = db.Column(db.Float, default=0.0) # For Hardware: fixed sale price if is_fixed_price is True

    def __repr__(self):
        return f'<InventoryItem {self.product_name}>'

class SaleRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    product_name = db.Column(db.String(150), nullable=False) # Store name at time of sale
    quantity_sold = db.Column(db.Float, nullable=False)
    sale_unit_type = db.Column(db.String(50), nullable=False) # 'pack', 'piece', 'tab'
    price_at_time_per_unit_sold = db.Column(db.Float, nullable=False) # Price per pack/piece/tab
    total_amount = db.Column(db.Float, nullable=False)
    sale_date = db.Column(db.DateTime, default=datetime.now)
    customer_phone = db.Column(db.String(50), nullable=True)
    sales_person_name = db.Column(db.String(80), nullable=True) # Store sales person name at time of sale
    transaction_id = db.Column(db.String(100), nullable=False, index=True) # Group items in one transaction

    def __repr__(self):
        return f'<SaleRecord {self.product_name} - {self.quantity_sold}>'

class HirableItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    item_name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    total_stock = db.Column(db.Integer, default=0)
    current_stock = db.Column(db.Integer, default=0) # Available for hire
    hire_rate_per_day = db.Column(db.Float, nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.now)
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = db.Column(db.Boolean, default=True)

    rental_records = db.relationship('RentalRecord', backref='hirable_item', lazy=True)

    def __repr__(self):
        return f'<HirableItem {self.item_name}>'

class RentalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    hirable_item_id = db.Column(db.Integer, db.ForeignKey('hirable_item.id'), nullable=False)
    item_name_at_rent = db.Column(db.String(150), nullable=False) # Store name at time of rental
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(50), nullable=True)
    rental_date = db.Column(db.DateTime, default=datetime.now)
    return_date = db.Column(db.DateTime, nullable=True)
    expected_return_date = db.Column(db.DateTime, nullable=False)
    hire_rate_at_rent = db.Column(db.Float, nullable=False) # Rate per day at time of rental
    total_hire_amount = db.Column(db.Float, nullable=True) # Calculated upon return or for display
    status = db.Column(db.String(50), default='Rented') # 'Rented', 'Returned', 'Overdue', 'Cancelled'
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f'<RentalRecord {self.item_name_at_rent} to {self.customer_name}>'

# --- Helper Functions ---

# Function to get the current business ID from the session
def get_current_business_id():
    return session.get('business_id')

# Function to get the current business type from the session
def get_current_business_type():
    return session.get('business_type')

# Helper for robust serialization
def safe_convert(value, converter, default):
    """
    Safely converts a value using a specified converter.
    Returns default if value is None or conversion fails.
    """
    try:
        # Attempt conversion only if value is not None
        return converter(value) if value is not None else default
    except (TypeError, ValueError):
        # Catch specific conversion errors and return default
        return default

def serialize_inventory_item(item):
    """
    Serializes an InventoryItem object to a dictionary for JSON conversion.
    Uses getattr for robust attribute access and safe_convert for type handling.
    Includes comprehensive error logging for debugging.
    """
    try:
        # Use getattr() for robust attribute access.
        # If an attribute is missing on the 'item' object, getattr returns None.
        _id = getattr(item, 'id', None)
        _product_name = getattr(item, 'product_name', None)
        _category = getattr(item, 'category', None)
        _cost_price = getattr(item, 'cost_price', None) # Renamed from purchase_price to cost_price as per model
        _sale_price = getattr(item, 'sale_price', None)
        _current_stock = getattr(item, 'current_stock', None)
        _last_updated = getattr(item, 'last_updated', None)
        _batch_number = getattr(item, 'batch_number', None)
        _number_of_tabs = getattr(item, 'number_of_tabs', None)
        _unit_price_per_tab = getattr(item, 'unit_price_per_tab', None)
        _item_type = getattr(item, 'item_type', None)
        _expiry_date = getattr(item, 'expiry_date', None)
        _is_fixed_price = getattr(item, 'is_fixed_price', None)
        _fixed_sale_price = getattr(item, 'fixed_sale_price', None)
        _is_active = getattr(item, 'is_active', None)
        _barcode = getattr(item, 'barcode', None)
        _unit_of_measure = getattr(item, 'unit_of_measure', None)


        # Handle dates more defensively:
        # Check if it's actually a date/datetime object before calling isoformat().
        last_updated_iso = None
        if isinstance(_last_updated, (datetime, date)):
            last_updated_iso = _last_updated.isoformat()

        expiry_date_iso = None
        if isinstance(_expiry_date, (datetime, date)):
            expiry_date_iso = _expiry_date.isoformat()

        return {
            'id': safe_convert(_id, str, ''),
            'product_name': safe_convert(_product_name, str, 'N/A'),
            'category': safe_convert(_category, str, 'N/A'),
            'cost_price': safe_convert(_cost_price, float, 0.0), # Updated field name
            'sale_price': safe_convert(_sale_price, float, 0.0),
            'current_stock': safe_convert(_current_stock, float, 0.0),
            'last_updated': last_updated_iso, # Use processed ISO string or None
            'batch_number': safe_convert(_batch_number, str, 'N/A'),
            'number_of_tabs': safe_convert(_number_of_tabs, float, 1.0),
            'unit_price_per_tab': safe_convert(_unit_price_per_tab, float, 0.0),
            'item_type': safe_convert(_item_type, str, 'N/A'),
            'expiry_date': expiry_date_iso, # Use processed ISO string or None
            'is_fixed_price': safe_convert(_is_fixed_price, bool, False),
            'fixed_sale_price': safe_convert(_fixed_sale_price, float, 0.0),
            'is_active': safe_convert(_is_active, bool, False),
            'barcode': safe_convert(_barcode, str, ''),
            'unit_of_measure': safe_convert(_unit_of_measure, str, 'units') # Added unit_of_measure
        }
    except Exception as e:
        # This block catches any remaining unexpected errors during serialization.
        # It's crucial for logging and returning a safe fallback to the frontend.
        error_id = getattr(item, 'id', 'UNKNOWN_ID_ERROR')
        error_product_name = getattr(item, 'product_name', 'UNKNOWN_PRODUCT_NAME_ERROR')
        app.logger.error(f"CRITICAL: Serialization failed for item '{error_product_name}' (ID: {error_id}). "
                         f"Exception Type: {e.__class__.__name__}, Message: {str(e)}", exc_info=True)
        # Return a minimal, error-safe dictionary that won't crash the JavaScript.
        return {
            "id": "serialization_error_" + str(error_id)[:8], # Unique ID for error items
            "product_name": f"Serialization Error (ID: {str(error_id)[:8]})",
            "current_stock": 0.0,
            "sale_price": 0.0,
            "unit_price_per_tab": 0.0,
            "number_of_tabs": 1.0,
            "is_fixed_price": False,
            "fixed_sale_price": 0.0,
            "expiry_date": None,
            "barcode": "",
            "item_type": "N/A",
            "category": "N/A",
            "cost_price": 0.0, # Updated field name
            "last_updated": None,
            "batch_number": "N/A",
            "is_active": False,
            "unit_of_measure": "units" # Added unit_of_measure
        }


# --- Routes ---

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, is_active=True).first()

        if user and user.check_password(password):
            business = Business.query.get(user.business_id)
            if not business or not business.is_active: # Check if business is active
                flash('Your business account is inactive. Please contact support.', 'danger')
                return render_template('login.html', current_year=datetime.now().year)

            session['username'] = user.username
            session['role'] = user.role
            session['business_id'] = user.business_id
            
            # Fetch business info and store in session
            session['business_type'] = business.business_type
            session['business_info'] = {
                'name': business.name,
                'address': business.address,
                'location': business.location,
                'contact': business.contact,
                'email': business.email,
                'business_type': business.business_type
            }
            
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', current_year=datetime.now().year)

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/register_business', methods=['GET', 'POST'])
def register_business():
    if request.method == 'POST':
        business_name = request.form['business_name']
        business_address = request.form['business_address']
        business_location = request.form['business_location']
        business_contact = request.form['business_contact']
        business_email = request.form['business_email']
        business_type = request.form['business_type']
        admin_username = request.form['admin_username']
        admin_password = request.form['admin_password']

        # Check if business name already exists
        existing_business = Business.query.filter_by(name=business_name).first()
        if existing_business:
            flash('Business name already registered. Please choose a different name.', 'danger')
            return render_template('register_business.html', current_year=datetime.now().year)

        # Check if admin username already exists
        existing_user = User.query.filter_by(username=admin_username).first()
        if existing_user:
            flash('Admin username already exists. Please choose a different username.', 'danger')
            return render_template('register_business.html', current_year=datetime.now().year)

        try:
            new_business = Business(
                name=business_name,
                address=business_address,
                location=business_location,
                contact=business_contact,
                email=business_email,
                business_type=business_type,
                is_active=True # New businesses are active by default
            )
            db.session.add(new_business)
            db.session.flush() # Flush to get new_business.id

            new_admin_user = User(
                username=admin_username,
                role='admin',
                business_id=new_business.id
            )
            new_admin_user.set_password(admin_password)
            db.session.add(new_admin_user)
            db.session.commit()

            flash('Business registered and admin user created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            app.logger.error(f"Error during business registration: {e}", exc_info=True)

    return render_template('register_business.html', current_year=datetime.now().year)

@app.route('/switch_business', methods=['GET', 'POST'])
@login_required
def switch_business():
    current_user_id = session.get('user_id') # Assuming user_id is stored in session
    if not current_user_id:
        flash('User not identified. Please log in again.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(current_user_id)
    if not user or user.role != 'admin':
        flash('Only administrators can switch businesses.', 'danger')
        return redirect(url_for('dashboard'))

    # For simplicity, let's assume an admin can see all businesses
    # In a real app, you might restrict this to businesses the admin is associated with
    available_businesses = Business.query.all()

    if request.method == 'POST':
        new_business_id = request.form.get('new_business_id')
        if new_business_id:
            new_business = Business.query.get(new_business_id)
            if new_business:
                # Update session with new business context
                session['business_id'] = new_business.id
                session['business_type'] = new_business.business_type
                session['business_info'] = {
                    'name': new_business.name,
                    'address': new_business.address,
                    'location': new_business.location,
                    'contact': new_business.contact,
                    'email': new_business.email,
                    'business_type': new_business.business_type
                }
                flash(f'Switched to business: {new_business.name}', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Selected business not found.', 'danger')
        else:
            flash('No business selected.', 'warning')

    return render_template('switch_business.html', businesses=available_businesses, current_year=datetime.now().year)

@app.route('/dashboard')
@login_required
def dashboard():
    business_id = get_current_business_id()
    if not business_id:
        flash('No business selected. Please select a business or register one.', 'warning')
        return redirect(url_for('login')) # Or a dedicated business selection page

    current_business = Business.query.get(business_id)
    if not current_business or not current_business.is_active:
        flash('Your business account is currently inactive. Please contact support.', 'danger')
        # Redirect to login or a page explaining the inactive status
        session.clear() # Clear session to force re-login/business selection
        return redirect(url_for('login'))


    business_type = get_current_business_type()

    # Common data for all business types
    total_products = InventoryItem.query.filter_by(business_id=business_id, is_active=True).count()
    total_users = User.query.filter_by(business_id=business_id, is_active=True).count()

    # Sales data for all business types
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday()) # Monday
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)

    sales_today = db.session.query(func.sum(SaleRecord.total_amount)).filter(
        SaleRecord.business_id == business_id,
        func.cast(SaleRecord.sale_date, db.Date) == today
    ).scalar() or 0.0

    sales_this_week = db.session.query(func.sum(SaleRecord.total_amount)).filter(
        SaleRecord.business_id == business_id,
        func.cast(SaleRecord.sale_date, db.Date) >= start_of_week
    ).scalar() or 0.0

    sales_this_month = db.session.query(func.sum(SaleRecord.total_amount)).filter(
        SaleRecord.business_id == business_id,
        func.cast(SaleRecord.sale_date, db.Date) >= start_of_month
    ).scalar() or 0.0

    sales_this_year = db.session.query(func.sum(SaleRecord.total_amount)).filter(
        SaleRecord.business_id == business_id,
        func.cast(SaleRecord.sale_date, db.Date) >= start_of_year
    ).scalar() or 0.0
    
    # Low stock alerts (common for all inventory-based businesses)
    low_stock_threshold = 10 # Example threshold
    low_stock_items = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        InventoryItem.current_stock <= low_stock_threshold,
        InventoryItem.is_active == True
    ).order_by(InventoryItem.current_stock).all()

    # Expiring items (relevant for Pharmacy/Supermarket/Provision Store)
    expiring_items = []
    if business_type in ['Pharmacy', 'Supermarket', 'Provision Store']:
        expiry_threshold_days = 30 # Items expiring within 30 days
        expiry_date_threshold = today + timedelta(days=expiry_threshold_days)
        expiring_items = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.expiry_date.isnot(None),
            InventoryItem.expiry_date <= expiry_date_threshold,
            InventoryItem.is_active == True
        ).order_by(InventoryItem.expiry_date).all()

    # Business-specific dashboard data
    business_dashboard_data = {}
    if business_type == 'Hardware':
        total_hirable_items = HirableItem.query.filter_by(business_id=business_id, is_active=True).count()
        rented_items = RentalRecord.query.filter_by(business_id=business_id, status='Rented').count()
        overdue_rentals = RentalRecord.query.filter(
            RentalRecord.business_id == business_id,
            RentalRecord.status == 'Rented',
            RentalRecord.expected_return_date < today
        ).count()
        business_dashboard_data = {
            'total_hirable_items': total_hirable_items,
            'rented_items': rented_items,
            'overdue_rentals': overdue_rentals
        }

    return render_template('dashboard.html',
                           total_products=total_products,
                           total_users=total_users,
                           sales_today=sales_today,
                           sales_this_week=sales_this_week,
                           sales_this_month=sales_this_month,
                           sales_this_year=sales_this_year,
                           low_stock_items=low_stock_items,
                           expiring_items=expiring_items,
                           business_type=business_type,
                           business_dashboard_data=business_dashboard_data,
                           user_role=session.get('role'),
                           current_year=datetime.now().year)

@app.route('/users')
@login_required
def users():
    if session.get('role') != 'admin':
        flash('You do not have permission to view users.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    users = User.query.filter_by(business_id=business_id).all()
    return render_template('users.html', users=users, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if session.get('role') != 'admin':
        flash('You do not have permission to add users.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        existing_user = User.query.filter_by(username=username, business_id=business_id).first()
        if existing_user:
            flash('Username already exists for this business. Please choose a different username.', 'danger')
            return render_template('add_edit_user.html', title='Add User', user={}, user_role=session.get('role'), current_year=datetime.now().year)

        new_user = User(username=username, role=role, business_id=business_id)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('User added successfully!', 'success')
        return redirect(url_for('users'))
    return render_template('add_edit_user.html', title='Add User', user={}, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if session.get('role') != 'admin':
        flash('You do not have permission to edit users.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    user = User.query.filter_by(id=user_id, business_id=business_id).first_or_404()

    if request.method == 'POST':
        user.username = request.form['username']
        user.role = request.form['role']
        new_password = request.form['password']
        if new_password:
            user.set_password(new_password)
        user.is_active = 'is_active' in request.form # Handle checkbox
        db.session.commit()
        flash('User updated successfully!', 'success')
        return redirect(url_for('users'))
    return render_template('add_edit_user.html', title='Edit User', user=user, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if session.get('role') != 'admin':
        flash('You do not have permission to delete users.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    user = User.query.filter_by(id=user_id, business_id=business_id).first_or_404()
    
    # Important: Prevent an admin from deactivating their own account if they are the last admin
    # Or, prevent deactivating if it's the only active user for a business
    # For now, a simpler check:
    if user.id == session.get('user_id'): # Prevent user from deactivating themselves
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('users'))

    # Soft delete
    user.is_active = False
    db.session.commit()
    flash('User deactivated successfully!', 'success')
    return redirect(url_for('users'))

@app.route('/inventory')
@login_required
def inventory():
    business_id = get_current_business_id()
    business_type = get_current_business_type()

    relevant_item_types = []
    if business_type == 'Pharmacy':
        relevant_item_types = ['Pharmacy']
    elif business_type == 'Hardware':
        relevant_item_types = ['Hardware Material']
    elif business_type in ['Supermarket', 'Provision Store']:
        relevant_item_types = ['Provision Store'] # Supermarket and Provision Store use this type

    search_query = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'product_name')
    sort_order = request.args.get('sort_order', 'asc')

    inventory_query = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        InventoryItem.is_active == True,
        InventoryItem.item_type.in_(relevant_item_types)
    )

    if search_query:
        inventory_query = inventory_query.filter(
            InventoryItem.product_name.ilike(f'%{search_query}%') |
            InventoryItem.category.ilike(f'%{search_query}%') |
            InventoryItem.batch_number.ilike(f'%{search_query}%') |
            InventoryItem.barcode.ilike(f'%{search_query}%') # Search by barcode
        )
    
    if sort_by == 'product_name':
        if sort_order == 'asc':
            inventory_query = inventory_query.order_by(InventoryItem.product_name.asc())
        else:
            inventory_query = inventory_query.order_by(InventoryItem.product_name.desc())
    elif sort_by == 'current_stock':
        if sort_order == 'asc':
            inventory_query = inventory_query.order_by(InventoryItem.current_stock.asc())
        else:
            inventory_query = inventory_query.order_by(InventoryItem.current_stock.desc())
    elif sort_by == 'expiry_date':
        if sort_order == 'asc':
            inventory_query = inventory_query.order_by(InventoryItem.expiry_date.asc().nulls_last())
        else:
            inventory_query = inventory_query.order_by(InventoryItem.expiry_date.desc().nulls_first())
    
    inventory_items = inventory_query.all()

    return render_template('inventory.html', 
                           inventory_items=inventory_items, 
                           business_type=business_type,
                           user_role=session.get('role'),
                           search_query=search_query,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           current_year=datetime.now().year)

@app.route('/inventory/add', methods=['GET', 'POST'])
@login_required
def add_inventory_item():
    business_id = get_current_business_id()
    business_type = get_current_business_type()

    if request.method == 'POST':
        product_name = request.form['product_name']
        category = request.form['category']
        supplier = request.form.get('supplier') # Made optional in form
        current_stock = float(request.form['current_stock'])
        unit_of_measure = request.form['unit_of_measure']
        cost_price = float(request.form['cost_price'])
        sale_price = float(request.form['sale_price'])
        batch_number = request.form.get('batch_number')
        expiry_date_str = request.form.get('expiry_date')
        barcode = request.form.get('barcode')
        
        # Pharmacy specific fields
        number_of_tabs = float(request.form.get('number_of_tabs', 1.0))
        unit_price_per_tab = float(request.form.get('unit_price_per_tab', 0.0))

        # Hardware specific fields
        is_fixed_price = 'is_fixed_price' in request.form
        fixed_sale_price = float(request.form.get('fixed_sale_price', 0.0))

        expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None

        # Determine item_type based on business_type
        item_type = ''
        if business_type == 'Pharmacy':
            item_type = 'Pharmacy'
        elif business_type == 'Hardware':
            item_type = 'Hardware Material'
        elif business_type in ['Supermarket', 'Provision Store']:
            item_type = 'Provision Store'

        # Validate barcode uniqueness if provided
        if barcode:
            existing_item_with_barcode = InventoryItem.query.filter_by(barcode=barcode, business_id=business_id).first()
            if existing_item_with_barcode:
                flash(f'Barcode "{barcode}" already exists for another product.', 'danger')
                # Prepare item_data for re-rendering the form with previous inputs
                item_data = {
                    'product_name': product_name, 'category': category, 'supplier': supplier,
                    'current_stock': current_stock, 'unit_of_measure': unit_of_measure,
                    'cost_price': cost_price, 'sale_price': sale_price,
                    'batch_number': batch_number, 'expiry_date': expiry_date_str,
                    'barcode': barcode, 'item_type': item_type,
                    'number_of_tabs': number_of_tabs, 'unit_price_per_tab': unit_price_per_tab,
                    'is_fixed_price': is_fixed_price, 'fixed_sale_price': fixed_sale_price
                }
                return render_template('add_edit_inventory_item.html', title='Add Inventory Item', item=item_data, business_type=business_type, user_role=session.get('role'), current_year=datetime.now().year)


        new_item = InventoryItem(
            business_id=business_id,
            product_name=product_name,
            category=category,
            supplier=supplier,
            current_stock=current_stock,
            unit_of_measure=unit_of_measure,
            cost_price=cost_price,
            sale_price=sale_price,
            batch_number=batch_number,
            expiry_date=expiry_date,
            barcode=barcode,
            item_type=item_type,
            number_of_tabs=number_of_tabs,
            unit_price_per_tab=unit_price_per_tab,
            is_fixed_price=is_fixed_price,
            fixed_sale_price=fixed_sale_price
        )
        db.session.add(new_item)
        db.session.commit()
        flash('Inventory item added successfully!', 'success')
        return redirect(url_for('inventory'))
    
    # Default values for GET request
    default_item = {
        'product_name': '', 'category': '', 'supplier': '', 'current_stock': 0.0,
        'unit_of_measure': 'units', 'cost_price': 0.0, 'sale_price': 0.0,
        'batch_number': '', 'expiry_date': '', 'barcode': '',
        'number_of_tabs': 1.0, 'unit_price_per_tab': 0.0,
        'is_fixed_price': False, 'fixed_sale_price': 0.0
    }
    return render_template('add_edit_inventory_item.html', title='Add Inventory Item', item=default_item, business_type=business_type, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/inventory/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit_inventory_item(item_id):
    business_id = get_current_business_id()
    business_type = get_current_business_type()
    item = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()

    if request.method == 'POST':
        item.product_name = request.form['product_name']
        item.category = request.form['category']
        item.supplier = request.form.get('supplier') # Made optional in form
        item.current_stock = float(request.form['current_stock'])
        item.unit_of_measure = request.form['unit_of_measure']
        item.cost_price = float(request.form['cost_price'])
        item.sale_price = float(request.form['sale_price'])
        item.batch_number = request.form.get('batch_number')
        expiry_date_str = request.form.get('expiry_date')
        item.barcode = request.form.get('barcode') # Update barcode

        # Pharmacy specific fields
        item.number_of_tabs = float(request.form.get('number_of_tabs', 1.0))
        item.unit_price_per_tab = float(request.form.get('unit_price_per_tab', 0.0))

        # Hardware specific fields
        item.is_fixed_price = 'is_fixed_price' in request.form
        item.fixed_sale_price = float(request.form.get('fixed_sale_price', 0.0))

        item.expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None
        item.is_active = 'is_active' in request.form # Handle checkbox
        item.last_updated = datetime.now()

        # Validate barcode uniqueness if provided and changed
        if item.barcode:
            existing_item_with_barcode = InventoryItem.query.filter(
                InventoryItem.barcode == item.barcode,
                InventoryItem.business_id == business_id,
                InventoryItem.id != item.id # Exclude current item
            ).first()
            if existing_item_with_barcode:
                flash(f'Barcode "{item.barcode}" already exists for another product.', 'danger')
                return render_template('add_edit_inventory_item.html', title='Edit Inventory Item', item=item, business_type=business_type, user_role=session.get('role'), current_year=datetime.now().year)

        db.session.commit()
        flash('Inventory item updated successfully!', 'success')
        return redirect(url_for('inventory'))
    
    return render_template('add_edit_inventory_item.html', title='Edit Inventory Item', item=item, business_type=business_type, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/inventory/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_inventory_item(item_id):
    business_id = get_current_business_id()
    item = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()
    
    # Soft delete
    item.is_active = False
    item.last_updated = datetime.now()
    db.session.commit()
    flash('Inventory item deactivated successfully!', 'success')
    return redirect(url_for('inventory'))

@app.route('/sales')
@login_required
def sales():
    business_id = get_current_business_id()
    
    search_query = request.args.get('search', '').strip()
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    sort_by = request.args.get('sort_by', 'sale_date')
    sort_order = request.args.get('sort_order', 'desc')

    sales_query = SaleRecord.query.filter_by(business_id=business_id)

    if search_query:
        # Search across product name, customer phone, sales person, transaction ID
        sales_query = sales_query.filter(
            (SaleRecord.product_name.ilike(f'%{search_query}%')) |
            (SaleRecord.customer_phone.ilike(f'%{search_query}%')) |
            (SaleRecord.sales_person_name.ilike(f'%{search_query}%')) |
            (SaleRecord.transaction_id.ilike(f'%{search_query}%'))
        )
    
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        sales_query = sales_query.filter(func.cast(SaleRecord.sale_date, db.Date) >= start_date)
    
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        sales_query = sales_query.filter(func.cast(SaleRecord.sale_date, db.Date) <= end_date)

    if sort_by == 'sale_date':
        if sort_order == 'asc':
            sales_query = sales_query.order_by(SaleRecord.sale_date.asc())
        else:
            sales_query = sales_query.order_by(SaleRecord.sale_date.desc())
    elif sort_by == 'total_amount':
        if sort_order == 'asc':
            sales_query = sales_query.order_by(SaleRecord.total_amount.asc())
        else:
            sales_query = sales_query.order_by(SaleRecord.total_amount.desc())
    elif sort_by == 'product_name':
        if sort_order == 'asc':
            sales_query = sales_query.order_by(SaleRecord.product_name.asc())
        else:
            sales_query = sales_query.order_by(SaleRecord.product_name.desc())
    
    sales_records = sales_query.all()

    # Group sales by transaction_id for display
    transactions = {}
    for record in sales_records:
        if record.transaction_id not in transactions:
            transactions[record.transaction_id] = {
                'id': record.transaction_id,
                'sale_date': record.sale_date,
                'customer_phone': record.customer_phone,
                'sales_person_name': record.sales_person_name,
                'total_amount': 0.0,
                'items': []
            }
        transactions[record.transaction_id]['total_amount'] += record.total_amount
        transactions[record.transaction_id]['items'].append(record)
    
    # Convert dict to list for easier sorting in template if needed, or just pass dict values
    sorted_transactions = sorted(transactions.values(), key=lambda x: x['sale_date'], reverse=(sort_order == 'desc'))

    return render_template('sales.html', 
                           transactions=sorted_transactions, 
                           user_role=session.get('role'),
                           search_query=search_query,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           current_year=datetime.now().year)

@app.route('/sales/add', methods=['GET', 'POST'])
@login_required
def add_sale():
    # DEBUG: Print at the very beginning of the route
    app.logger.debug(f"\n--- DEBUG: Entering add_sale route ---")
    app.logger.debug(f"DEBUG: Session username: {session.get('username')}")
    app.logger.debug(f"DEBUG: Session role: {session.get('role')}")
    app.logger.debug(f"DEBUG: Session business_id: {session.get('business_id')}")

    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to add sales records or no business selected.', 'danger')
        app.logger.debug(f"DEBUG: Access denied for user {session.get('username')}, role {session.get('role')}, business_id {session.get('business_id')}")
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    business_type = get_current_business_type()

    app.logger.debug(f"DEBUG: Current business_id: {business_id}")
    app.logger.debug(f"DEBUG: Current business_type: {business_type}")

    relevant_item_types = []
    if business_type == 'Pharmacy':
        relevant_item_types = ['Pharmacy']
    elif business_type == 'Hardware':
        relevant_item_types = ['Hardware Material']
    elif business_type in ['Supermarket', 'Provision Store']:
        relevant_item_types = ['Provision Store']

    search_query = request.args.get('search', '').strip()
    app.logger.debug(f"DEBUG: Search Query received: '{search_query}'")

    available_inventory_items_query = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        InventoryItem.is_active == True,
        InventoryItem.item_type.in_(relevant_item_types)
    )

    if search_query:
        available_inventory_items_query = available_inventory_items_query.filter(
            InventoryItem.product_name.ilike(f'%{search_query}%') |
            InventoryItem.category.ilike(f'%{search_query}%') |
            InventoryItem.batch_number.ilike(f'%{search_query}%') |
            InventoryItem.barcode.ilike(f'%{search_query}%') # Include barcode in search
        )
    
    available_inventory_items = available_inventory_items_query.all()
    app.logger.debug(f"DEBUG: Number of inventory items found for search '{search_query}': {len(available_inventory_items)}")

    # Ensure serialized_inventory_items is clean
    serialized_inventory_items = []
    for item in available_inventory_items:
        serialized_inventory_items.append(serialize_inventory_item(item))

    app.logger.debug(f"DEBUG: Successfully serialized inventory items. Count: {len(serialized_inventory_items)}")
    # NEW DEBUG: Log the actual serialized data (first 5 items for brevity)
    # app.logger.debug(f"DEBUG: Serialized Inventory Items Data (first 5): {json.dumps(serialized_inventory_items[:5], indent=2)}") # Uncomment for detailed debug

    # --- Defensive cleaning of pharmacy_info ---
    raw_pharmacy_info = session.get('business_info', {})
    if isinstance(raw_pharmacy_info, dict):
        pharmacy_info = {
            'name': str(raw_pharmacy_info.get('name', 'N/A')),
            'address': str(raw_pharmacy_info.get('address', 'N/A')),
            'location': str(raw_pharmacy_info.get('location', 'N/A')),
            'phone': str(raw_pharmacy_info.get('phone', 'N/A')),
            'email': str(raw_pharmacy_info.get('email', 'N/A')),
            'contact': str(raw_pharmacy_info.get('contact', 'N/A'))
        }
    else:
        business_details = Business.query.filter_by(id=business_id).first()
        if business_details:
            pharmacy_info = {
                'name': str(business_details.name),
                'address': str(business_details.address),
                'location': str(business_details.location),
                'phone': str(business_details.contact),
                'email': str(business_details.email) if hasattr(business_details, 'email') and business_details.email is not None else 'N/A',
                'contact': str(business_details.contact)
            }
        else:
            pharmacy_info = {
                'name': ENTERPRISE_NAME,
                'address': "Your Pharmacy Address",
                'location': "Your Pharmacy Location",
                'phone': "Your Pharmacy Contact",
                'email': 'info@example.com',
                'contact': "Your Pharmacy Contact"
            }
    app.logger.debug(f"DEBUG: Pharmacy info prepared. Type: {type(pharmacy_info)}")


    # --- Helper function to ensure cart items are JSON serializable ---
    def clean_cart_items_for_template(raw_cart_items):
        cleaned_items = []
        if isinstance(raw_cart_items, list):
            for item_data in raw_cart_items:
                if isinstance(item_data, dict):
                    cleaned_item = {
                        'product_id': str(item_data.get('product_id', '')),
                        'product_name': str(item_data.get('product_name', '')),
                        'quantity_sold': float(item_data.get('quantity_sold', 0.0)),
                        'sale_unit_type': str(item_data.get('sale_unit_type', '')),
                        'price_at_time_per_unit_sold': float(item_data.get('price_at_time_per_unit_sold', 0.0)),
                        'item_total_amount': float(item_data.get('item_total_amount', 0.0))
                    }
                    cleaned_items.append(cleaned_item)
        return cleaned_items
    # --- End Helper Function ---

    # Initialize variables for the template context
    sale_for_template_items = [] # Ensure this is explicitly an empty list
    customer_phone_for_template = ''
    sales_person_name_for_template = session.get('username', 'N/A') # Use this consistently
    print_ready = request.args.get('print_ready', 'false').lower() == 'true'
    last_transaction_details = session.pop('last_transaction_details', [])
    last_transaction_grand_total = session.pop('last_transaction_grand_total', 0.0)
    last_transaction_id = session.pop('last_transaction_id', '')
    last_transaction_customer_phone = session.pop('last_transaction_customer_phone', '')
    last_transaction_sales_person = session.pop('last_transaction_sales_person', '')
    last_transaction_date = session.pop('last_transaction_date', '')
    
    # NEW: Get auto_print flag from session and ensure it's a boolean
    auto_print = bool(session.pop('auto_print', False))


    if request.method == 'POST':
        customer_phone_for_template = request.form.get('customer_phone', '').strip()
        
        cart_items_json = request.form.get('cart_items_json')
        
        cart_items = []
        if cart_items_json:
            try:
                loaded_cart_items = json.loads(cart_items_json)
                cart_items = clean_cart_items_for_template(loaded_cart_items)
            except json.JSONDecodeError:
                flash('Error processing cart data. Please try again.', 'danger')
        
        # Always set sale_for_template_items based on the processed cart_items for POST errors
        sale_for_template_items = cart_items

        if not cart_items:
            flash('No items in the cart to record a sale.', 'danger')
            # DEBUG: Log types before rendering on error (re-enabled for specific error path)
            app.logger.debug(f"\n--- DEBUG (POST Error, No Items) ---")
            app.logger.debug(f"Type of sale_for_template_items: {type(sale_for_template_items)}")
            app.logger.debug(f"Type of serialized_inventory_items: {type(serialized_inventory_items)}")
            app.logger.debug(f"Type of pharmacy_info: {type(pharmacy_info)}")
            app.logger.debug(f"Type of user_role: {type(session.get('role'))}")
            app.logger.debug(f"Type of business_type: {type(business_type)}")
            app.logger.debug(f"Type of search_query: {type(search_query)}")
            app.logger.debug(f"Type of current_year: {type(datetime.now().year)}")
            app.logger.debug(f"--- END DEBUG ---")

            try:
                return render_template('add_edit_sale.html',
                                    title='Add Sale Record',
                                    # Pass pre-serialized JSON strings
                                    inventory_items_json=json.dumps(serialized_inventory_items),
                                    sale_json=json.dumps({'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items}),
                                    user_role=session.get('role'),
                                    pharmacy_info=pharmacy_info,
                                    print_ready=False,
                                    auto_print=auto_print, # Pass auto_print here
                                    current_year=datetime.now().year,
                                    search_query=search_query,
                                    business_type_json=json.dumps(business_type)) # Pass business_type as JSON
            except Exception as e:
                app.logger.error(f"ERROR: Exception caught during render_template (POST, No Items): {e}", exc_info=True)
                raise # Re-raise to see full traceback


        total_grand_amount = 0.0
        recorded_sale_details = []

        # Validate stock before processing any sales
        for item_data in cart_items:
            product_id = item_data['product_id']
            quantity_sold = float(item_data['quantity_sold']) # Ensure float
            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
            if not product:
                flash(f'Product with ID {product_id} not found.', 'danger')
                # DEBUG: Log types before rendering on error (re-enabled for specific error path)
                app.logger.debug(f"\n--- DEBUG (POST Error, Product Not Found) ---")
                app.logger.debug(f"Type of sale_for_template_items: {type(sale_for_template_items)}")
                app.logger.debug(f"Type of serialized_inventory_items: {type(serialized_inventory_items)}")
                app.logger.debug(f"Type of pharmacy_info: {type(pharmacy_info)}")
                app.logger.debug(f"Type of user_role: {type(session.get('role'))}")
                app.logger.debug(f"Type of business_type: {type(business_type)}")
                app.logger.debug(f"Type of search_query: {type(search_query)}")
                app.logger.debug(f"Type of current_year: {type(datetime.now().year)}")
                app.logger.debug(f"--- END DEBUG ---")
                try:
                    return render_template('add_edit_sale.html',
                                        title='Add Sale Record',
                                        inventory_items_json=json.dumps(serialized_inventory_items),
                                        sale_json=json.dumps({'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items}),
                                        user_role=session.get('role'),
                                        pharmacy_info=pharmacy_info,
                                        print_ready=False,
                                        auto_print=auto_print, # Pass auto_print here
                                        current_year=datetime.now().year,
                                        search_query=search_query,
                                        business_type_json=json.dumps(business_type)) # Pass business_type as JSON
                except Exception as e:
                    app.logger.error(f"ERROR: Exception caught during render_template (POST, Product Not Found): {e}", exc_info=True)
                    raise # Re-raise to see full traceback


            quantity_for_stock_check = quantity_sold
            if item_data['sale_unit_type'] == 'pack':
                quantity_for_stock_check = quantity_sold * product.number_of_tabs

            if product.current_stock < quantity_for_stock_check:
                flash(f'Insufficient stock for {product.product_name}. Available: {product.current_stock:.2f} units. Tried to sell: {quantity_for_stock_check:.2f} units.', 'danger')
                # DEBUG: Log types before rendering on error (re-enabled for specific error path)
                app.logger.debug(f"\n--- DEBUG (POST Error, Insufficient Stock) ---")
                app.logger.debug(f"Type of sale_for_template_items: {type(sale_for_template_items)}")
                app.logger.debug(f"Type of serialized_inventory_items: {type(serialized_inventory_items)}")
                app.logger.debug(f"Type of pharmacy_info: {type(pharmacy_info)}")
                app.logger.debug(f"Type of user_role: {type(session.get('role'))}")
                app.logger.debug(f"Type of business_type: {type(business_type)}")
                app.logger.debug(f"Type of search_query: {type(search_query)}")
                app.logger.debug(f"Type of current_year: {type(datetime.now().year)}")
                app.logger.debug(f"--- END DEBUG ---")
                try:
                    return render_template('add_edit_sale.html',
                                        title='Add Sale Record',
                                        inventory_items_json=json.dumps(serialized_inventory_items),
                                        sale_json=json.dumps({'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items}),
                                        user_role=session.get('role'),
                                        pharmacy_info=pharmacy_info,
                                        print_ready=False,
                                        auto_print=auto_print, # Pass auto_print here
                                        current_year=datetime.now().year,
                                        search_query=search_query,
                                        business_type_json=json.dumps(business_type)) # Pass business_type as JSON
                except Exception as e:
                    app.logger.error(f"ERROR: Exception caught during render_template (POST, Insufficient Stock): {e}", exc_info=True)
                    raise # Re-raise to see full traceback


        # If all stock checks pass, proceed with recording sales and deducting stock
        transaction_id = str(uuid.uuid4()) # Generate transaction ID here, after all checks
        sale_date = datetime.now() # Get sale date here
        for item_data in cart_items:
            product_id = item_data['product_id']
            quantity_sold = float(item_data['quantity_sold']) # Ensure float
            sale_unit_type = item_data['sale_unit_type']
            price_at_time_per_unit_sold = float(item_data['price_at_time_per_unit_sold'])
            item_total_amount = float(item_data['item_total_amount'])

            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
            
            quantity_to_deduct = quantity_sold
            if sale_unit_type == 'pack':
                quantity_to_deduct = quantity_sold * product.number_of_tabs

            product.current_stock -= quantity_to_deduct
            product.last_updated = datetime.now()

            new_sale = SaleRecord(
                business_id=business_id,
                product_id=product.id,
                product_name=product.product_name,
                quantity_sold=quantity_sold,
                sale_unit_type=sale_unit_type,
                price_at_time_per_unit_sold=price_at_time_per_unit_sold,
                total_amount=item_total_amount,
                sale_date=sale_date,
                customer_phone=customer_phone_for_template,
                sales_person_name=sales_person_name_for_template, # Use the consistently defined variable
                transaction_id=transaction_id
            )
            db.session.add(new_sale)
            total_grand_amount += item_total_amount
            recorded_sale_details.append({
                'product_name': product.product_name,
                'quantity_sold': quantity_sold,
                'sale_unit_type': sale_unit_type,
                'price_at_time_per_unit_sold': price_at_time_per_unit_sold,
                'total_amount': item_total_amount
            })

        db.session.commit()
        flash('Sale recorded successfully!', 'success')

        session['last_transaction_details'] = recorded_sale_details
        session['last_transaction_grand_total'] = total_grand_amount
        session['last_transaction_id'] = transaction_id
        session['last_transaction_customer_phone'] = customer_phone_for_template
        session['last_transaction_sales_person'] = sales_person_name_for_template
        session['last_transaction_date'] = sale_date.strftime('%Y-%m-%d %H:%M:%S')
        session['auto_print'] = True  # NEW: Set auto print flag

        send_sms = 'send_sms_receipt' in request.form
        if send_sms and customer_phone_for_template:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            
            sms_message = (
                f"{business_name_for_sms} Sales Receipt:\n"
                f"Transaction ID: {transaction_id[:8].upper()}\n"
                f"Date: {sale_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Total Amount: GH₵{total_grand_amount:.2f}\n"
                f"Items: " + ", ".join([f"{item['product_name']} ({item['quantity_sold']} {item['sale_unit_type']})" for item in recorded_sale_details]) + "\n"
                f"Sales Person: {sales_person_name_for_template}\n\n" # Use sales_person_name_for_sms
                f"Thank you for your purchase!\n"
                f"From: {business_name_for_sms}"
            )
            
            app.logger.info(f"Attempting to send SMS to {customer_phone_for_template} for sale transaction.")
            app.logger.info(f"SMS Payload: {sms_message}")

            sms_payload = {
                'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': customer_phone_for_template,
                'from': ARKESEL_SENDER_ID, 'sms': sms_message
            }
            
            try:
                sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
                sms_response.raise_for_status()
                sms_result = sms_response.json()
                app.logger.info(f"Arkesel SMS API Response: {sms_result}")

                if sms_result.get('status') == 'success':
                    flash(f'SMS receipt sent to customer {customer_phone_for_template} successfully!', 'success')
                else:
                    error_message = sms_result.get('message', 'Unknown error from SMS provider.')
                    flash(f'Failed to send SMS receipt to customer. Error: {error_message}', 'danger')
            except requests.exceptions.HTTPError as http_err:
                flash(f'HTTP error sending SMS receipt: {http_err}. Please check API key or sender ID.', 'danger')
                app.logger.error(f'HTTP error sending SMS receipt: {http_err}', exc_info=True)
            except requests.exceptions.ConnectionError as conn_err:
                flash(f'Network connection error sending SMS receipt: {conn_err}. Please check your internet connection.', 'danger')
                app.logger.error(f'Network connection error sending SMS receipt: {conn_err}', exc_info=True)
            except requests.exceptions.Timeout as timeout_err:
                flash(f'SMS request timed out: {timeout_err}. Please try again later.', 'danger')
                app.logger.error(f'SMS request timed out: {timeout_err}', exc_info=True)
            except json.JSONDecodeError:
                flash('Failed to parse SMS provider response. The response might not be in JSON format.', 'danger')
                app.logger.error('Failed to parse SMS provider response. The response might not be in JSON format.', exc_info=True)
        elif send_sms and not customer_phone_for_template:
            flash(f'SMS receipt not sent: No customer phone number provided.', 'warning')

        return redirect(url_for('add_sale', print_ready='true'))
    
    # GET request / Initial render
    # If print_ready is true, we are showing a receipt, the form items should be empty.
    if print_ready:
        sale_for_template_items = []
    # If not print_ready, it's either an initial GET or a GET after a non-print redirect.
    # In these cases, 'items' should be an empty list for a fresh form.
    else:
        # Explicitly ensure this is a fresh, empty list on GET
        sale_for_template_items = [] 

    # Construct the final 'sale' dictionary for the template
    sale_final_context = {
        'sales_person_name': sales_person_name_for_template,
        'customer_phone': customer_phone_for_template,
        'items': sale_for_template_items # This should now consistently be an empty list
    }

    # DEBUG: Log types before rendering on GET/Initial load (re-enabled for specific error path)
    app.logger.debug(f"\n--- DEBUG (GET/Initial Load) - Before Render ---")
    app.logger.debug(f"Type of sale_final_context['items']: {type(sale_final_context['items'])}, Value: {repr(sale_final_context['items'])}")
    app.logger.debug(f"Type of serialized_inventory_items: {type(serialized_inventory_items)}")
    app.logger.debug(f"Type of pharmacy_info: {type(pharmacy_info)}")
    app.logger.debug(f"Type of user_role: {type(session.get('role'))}")
    app.logger.debug(f"Type of business_type: {type(business_type)}")
    app.logger.debug(f"Type of search_query: {type(search_query)}")
    app.logger.debug(f"Type of current_year: {type(datetime.now().year)}")
    app.logger.debug(f"--- END DEBUG ---")

    try:
        return render_template('add_edit_sale.html', 
                               title='Add Sale Record', 
                               # Pass pre-serialized JSON strings
                               inventory_items_json=json.dumps(serialized_inventory_items),
                               sale_json=json.dumps(sale_final_context), # Use the explicitly constructed sale_final_context
                               user_role=session.get('role'),
                               pharmacy_info=pharmacy_info,
                               print_ready=print_ready,
                               auto_print=auto_print,  # NEW: Pass auto_print flag to template
                               last_transaction_details=last_transaction_details,
                               last_transaction_grand_total=last_transaction_grand_total,
                               last_transaction_id=last_transaction_id,
                               last_transaction_customer_phone=last_transaction_customer_phone,
                               last_transaction_sales_person=last_transaction_sales_person,
                               last_transaction_date=last_transaction_date,
                               current_year=datetime.now().year,
                               search_query=search_query,
                               business_type_json=json.dumps(business_type)) # Pass business_type as JSON
    except Exception as e:
        app.logger.error(f"ERROR: Exception caught during final render_template (GET): {e}", exc_info=True)
        raise # Re-raise to see full traceback

@app.route('/reports')
@login_required
def reports():
    business_id = get_current_business_id()
    business_type = get_current_business_type()
    user_role = session.get('role')

    if user_role not in ['admin', 'manager']:
        flash('You do not have permission to view reports.', 'danger')
        return redirect(url_for('dashboard'))

    today = date.today()
    start_of_month = today.replace(day=1)
    end_of_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    # Default date range for sales report
    sales_start_date_str = request.args.get('sales_start_date', start_of_month.strftime('%Y-%m-%d'))
    sales_end_date_str = request.args.get('sales_end_date', today.strftime('%Y-%m-%d'))

    # Default date range for inventory report (all time)
    inventory_start_date_str = request.args.get('inventory_start_date', '')
    inventory_end_date_str = request.args.get('inventory_end_date', '')

    # Default date range for rentals report (all time)
    rentals_start_date_str = request.args.get('rentals_start_date', '')
    rentals_end_date_str = request.args.get('rentals_end_date', '')

    # --- Sales Report Data ---
    sales_query = SaleRecord.query.filter_by(business_id=business_id)
    if sales_start_date_str:
        sales_start_date = datetime.strptime(sales_start_date_str, '%Y-%m-%d').date()
        sales_query = sales_query.filter(func.cast(SaleRecord.sale_date, db.Date) >= sales_start_date)
    if sales_end_date_str:
        sales_end_date = datetime.strptime(sales_end_date_str, '%Y-%m-%d').date()
        sales_query = sales_query.filter(func.cast(SaleRecord.sale_date, db.Date) <= sales_end_date)
    
    sales_data = sales_query.order_by(SaleRecord.sale_date.desc()).all()

    # Aggregate sales data by product for charting/summary
    sales_by_product = db.session.query(
        SaleRecord.product_name,
        func.sum(SaleRecord.quantity_sold).label('total_quantity_sold'),
        func.sum(SaleRecord.total_amount).label('total_revenue')
    ).filter(
        SaleRecord.business_id == business_id,
        func.cast(SaleRecord.sale_date, db.Date) >= (sales_start_date if sales_start_date_str else date.min),
        func.cast(SaleRecord.sale_date, db.Date) <= (sales_end_date if sales_end_date_str else date.max)
    ).group_by(SaleRecord.product_name).order_by(func.sum(SaleRecord.total_amount).desc()).all()

    # Aggregate sales data by date for charting
    sales_by_date = db.session.query(
        func.cast(SaleRecord.sale_date, db.Date).label('sale_day'),
        func.sum(SaleRecord.total_amount).label('daily_revenue')
    ).filter(
        SaleRecord.business_id == business_id,
        func.cast(SaleRecord.sale_date, db.Date) >= (sales_start_date if sales_start_date_str else date.min),
        func.cast(SaleRecord.sale_date, db.Date) <= (sales_end_date if sales_end_date_str else date.max)
    ).group_by(func.cast(SaleRecord.sale_date, db.Date)).order_by('sale_day').all()

    # Convert to format suitable for Chart.js
    sales_dates = [row.sale_day.strftime('%Y-%m-%d') for row in sales_by_date]
    sales_revenues = [float(row.daily_revenue) for row in sales_by_date] # Ensure float

    # --- Inventory Report Data ---
    relevant_item_types = []
    if business_type == 'Pharmacy':
        relevant_item_types = ['Pharmacy']
    elif business_type == 'Hardware':
        relevant_item_types = ['Hardware Material']
    elif business_type in ['Supermarket', 'Provision Store']:
        relevant_item_types = ['Provision Store']

    inventory_query = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        InventoryItem.is_active == True,
        InventoryItem.item_type.in_(relevant_item_types)
    )
    if inventory_start_date_str:
        inv_start_date = datetime.strptime(inventory_start_date_str, '%Y-%m-%d').date()
        inventory_query = inventory_query.filter(func.cast(InventoryItem.date_added, db.Date) >= inv_start_date)
    if inventory_end_date_str:
        inv_end_date = datetime.strptime(inventory_end_date_str, '%Y-%m-%d').date()
        inventory_query = inventory_query.filter(func.cast(InventoryItem.date_added, db.Date) <= inv_end_date)
    
    inventory_data = inventory_query.order_by(InventoryItem.product_name).all()

    # --- Rental Report Data (Hardware Business Only) ---
    rental_data = []
    if business_type == 'Hardware':
        rentals_query = RentalRecord.query.filter_by(business_id=business_id)
        if rentals_start_date_str:
            rent_start_date = datetime.strptime(rentals_start_date_str, '%Y-%m-%d').date()
            rentals_query = rentals_query.filter(func.cast(RentalRecord.rental_date, db.Date) >= rent_start_date)
        if rentals_end_date_str:
            rent_end_date = datetime.strptime(rentals_end_date_str, '%Y-%m-%d').date()
            rentals_query = rentals_query.filter(func.cast(RentalRecord.rental_date, db.Date) <= rent_end_date)
        rental_data = rentals_query.order_by(RentalRecord.rental_date.desc()).all()

    return render_template('reports.html',
                           sales_data=sales_data,
                           sales_by_product=sales_by_product,
                           sales_dates=json.dumps(sales_dates), # For Chart.js
                           sales_revenues=json.dumps(sales_revenues), # For Chart.js
                           sales_start_date=sales_start_date_str,
                           sales_end_date=sales_end_date_str,
                           inventory_data=inventory_data,
                           inventory_start_date=inventory_start_date_str,
                           inventory_end_date=inventory_end_date_str,
                           rental_data=rental_data, # Will be empty if not Hardware
                           rentals_start_date=rentals_start_date_str,
                           rentals_end_date=rentals_end_date_str,
                           business_type=business_type,
                           user_role=user_role,
                           current_year=datetime.now().year)

@app.route('/reports/export/<report_type>')
@login_required
def export_report(report_type):
    business_id = get_current_business_id()
    user_role = session.get('role')

    if user_role not in ['admin', 'manager']:
        flash('You do not have permission to export reports.', 'danger')
        return redirect(url_for('dashboard'))

    output = io.StringIO()
    writer = csv.writer(output)
    filename = f"{report_type}_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"

    if report_type == 'sales':
        sales_start_date_str = request.args.get('sales_start_date', '')
        sales_end_date_str = request.args.get('sales_end_date', '')

        sales_query = SaleRecord.query.filter_by(business_id=business_id)
        if sales_start_date_str:
            sales_start_date = datetime.strptime(sales_start_date_str, '%Y-%m-%d').date()
            sales_query = sales_query.filter(func.cast(SaleRecord.sale_date, db.Date) >= sales_start_date)
        if sales_end_date_str:
            sales_end_date = datetime.strptime(sales_end_date_str, '%Y-%m-%d').date()
            sales_query = sales_query.filter(func.cast(SaleRecord.sale_date, db.Date) <= sales_end_date)
        
        sales_data = sales_query.order_by(SaleRecord.sale_date.desc()).all()

        writer.writerow(['Transaction ID', 'Sale Date', 'Product Name', 'Quantity Sold', 'Unit Type', 'Price Per Unit', 'Total Amount', 'Customer Phone', 'Sales Person'])
        for record in sales_data:
            writer.writerow([
                record.transaction_id,
                record.sale_date.strftime('%Y-%m-%d %H:%M:%S'),
                record.product_name,
                f"{record.quantity_sold:.2f}",
                record.sale_unit_type,
                f"{record.price_at_time_per_unit_sold:.2f}",
                f"{record.total_amount:.2f}",
                record.customer_phone,
                record.sales_person_name
            ])
    elif report_type == 'inventory':
        inventory_start_date_str = request.args.get('inventory_start_date', '')
        inventory_end_date_str = request.args.get('inventory_end_date', '')

        relevant_item_types = []
        business_type = get_current_business_type()
        if business_type == 'Pharmacy':
            relevant_item_types = ['Pharmacy']
        elif business_type == 'Hardware':
            relevant_item_types = ['Hardware Material']
        elif business_type in ['Supermarket', 'Provision Store']:
            relevant_item_types = ['Provision Store']

        inventory_query = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.is_active == True,
            InventoryItem.item_type.in_(relevant_item_types)
        )
        if inventory_start_date_str:
            inv_start_date = datetime.strptime(inventory_start_date_str, '%Y-%m-%d').date()
            inventory_query = inventory_query.filter(func.cast(InventoryItem.date_added, db.Date) >= inv_start_date)
        if inventory_end_date_str:
            inv_end_date = datetime.strptime(inventory_end_date_str, '%Y-%m-%d').date()
            inventory_query = inventory_query.filter(func.cast(InventoryItem.date_added, db.Date) <= inv_end_date)
        
        inventory_data = inventory_query.order_by(InventoryItem.product_name).all()

        writer.writerow(['Product Name', 'Category', 'Supplier', 'Current Stock', 'Unit of Measure', 'Cost Price', 'Sale Price', 'Batch Number', 'Expiry Date', 'Barcode', 'Item Type', 'Number of Tabs', 'Unit Price Per Tab', 'Fixed Price', 'Fixed Sale Price'])
        for item in inventory_data:
            writer.writerow([
                item.product_name, item.category, item.supplier, f"{item.current_stock:.2f}",
                item.unit_of_measure, f"{item.cost_price:.2f}", f"{item.sale_price:.2f}",
                item.batch_number, item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else '',
                item.barcode, item.item_type, f"{item.number_of_tabs:.2f}", f"{item.unit_price_per_tab:.2f}",
                'Yes' if item.is_fixed_price else 'No', f"{item.fixed_sale_price:.2f}"
            ])
    elif report_type == 'rentals':
        if get_current_business_type() != 'Hardware':
            flash('Rental reports are only available for Hardware businesses.', 'warning')
            return redirect(url_for('reports'))

        rentals_start_date_str = request.args.get('rentals_start_date', '')
        rentals_end_date_str = request.args.get('rentals_end_date', '')

        rentals_query = RentalRecord.query.filter_by(business_id=business_id)
        if rentals_start_date_str:
            rent_start_date = datetime.strptime(rentals_start_date_str, '%Y-%m-%d').date()
            rentals_query = rentals_query.filter(func.cast(RentalRecord.rental_date, db.Date) >= rent_start_date)
        if rentals_end_date_str:
            rent_end_date = datetime.strptime(rentals_end_date_str, '%Y-%m-%d').date()
            rentals_query = rentals_query.filter(func.cast(RentalRecord.rental_date, db.Date) <= rent_end_date)
        rental_data = rentals_query.order_by(RentalRecord.rental_date.desc()).all()

        writer.writerow(['Item Name', 'Customer Name', 'Customer Phone', 'Rental Date', 'Expected Return Date', 'Actual Return Date', 'Hire Rate Per Day', 'Total Hire Amount', 'Status'])
        for record in rental_data:
            writer.writerow([
                record.item_name_at_rent, record.customer_name, record.customer_phone,
                record.rental_date.strftime('%Y-%m-%d %H:%M:%S'),
                record.expected_return_date.strftime('%Y-%m-%d %H:%M:%S'),
                record.return_date.strftime('%Y-%m-%d %H:%M:%S') if record.return_date else '',
                f"{record.hire_rate_at_rent:.2f}",
                f"{record.total_hire_amount:.2f}" if record.total_hire_amount is not None else '',
                record.status
            ])
    else:
        flash('Invalid report type.', 'danger')
        return redirect(url_for('reports'))

    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

@app.route('/hirable_items')
@login_required
def hirable_items():
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    search_query = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'item_name')
    sort_order = request.args.get('sort_order', 'asc')

    hirable_query = HirableItem.query.filter_by(business_id=business_id, is_active=True)

    if search_query:
        hirable_query = hirable_query.filter(
            HirableItem.item_name.ilike(f'%{search_query}%') |
            HirableItem.description.ilike(f'%{search_query}%')
        )
    
    if sort_by == 'item_name':
        if sort_order == 'asc':
            hirable_query = hirable_query.order_by(HirableItem.item_name.asc())
        else:
            hirable_query = hirable_query.order_by(HirableItem.item_name.desc())
    elif sort_by == 'current_stock':
        if sort_order == 'asc':
            hirable_query = hirable_query.order_by(HirableItem.current_stock.asc())
        else:
            hirable_query = hirable_query.order_by(HirableItem.current_stock.desc())
    elif sort_by == 'hire_rate_per_day':
        if sort_order == 'asc':
            hirable_query = hirable_query.order_by(HirableItem.hire_rate_per_day.asc())
        else:
            hirable_query = hirable_query.order_by(HirableItem.hire_rate_per_day.desc())
    
    hirable_items = hirable_query.all()
    return render_template('hirable_items.html', 
                           hirable_items=hirable_items, 
                           user_role=session.get('role'),
                           search_query=search_query,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           current_year=datetime.now().year)

@app.route('/hirable_items/add', methods=['GET', 'POST'])
@login_required
def add_hirable_item():
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    available_hirable_items = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()

    if request.method == 'POST':
        item_name = request.form['item_name']
        description = request.form.get('description')
        total_stock = int(request.form['total_stock'])
        hire_rate_per_day = float(request.form['hire_rate_per_day'])

        new_item = HirableItem(
            business_id=business_id,
            item_name=item_name,
            description=description,
            total_stock=total_stock,
            current_stock=total_stock, # Initially, all stock is available
            hire_rate_per_day=hire_rate_per_day
        )
        db.session.add(new_item)
        db.session.commit()
        flash('Hirable item added successfully!', 'success')
        return redirect(url_for('hirable_items'))
    
    default_item = {
        'item_name': '', 'description': '', 'total_stock': 0, 'hire_rate_per_day': 0.0
    }
    return render_template('add_edit_hirable_item.html', title='Add Hirable Item', item=default_item, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/hirable_items/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit_hirable_item(item_id):
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    item = HirableItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()

    if request.method == 'POST':
        item.item_name = request.form['item_name']
        item.description = request.form.get('description')
        
        new_total_stock = int(request.form['total_stock'])
        # Adjust current_stock based on change in total_stock
        stock_difference = new_total_stock - item.total_stock
        item.current_stock += stock_difference
        item.total_stock = new_total_stock

        item.hire_rate_per_day = float(request.form['hire_rate_per_day'])
        item.is_active = 'is_active' in request.form
        item.last_updated = datetime.now()
        db.session.commit()
        flash('Hirable item updated successfully!', 'success')
        return redirect(url_for('hirable_items'))
    
    return render_template('add_edit_hirable_item.html', title='Edit Hirable Item', item=item, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/hirable_items/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_hirable_item(item_id):
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    item = HirableItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()
    
    item.is_active = False # Soft delete
    item.last_updated = datetime.now()
    db.session.commit()
    flash('Hirable item deactivated successfully!', 'success')
    return redirect(url_for('hirable_items'))

@app.route('/rental_records')
@login_required
def rental_records():
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    search_query = request.args.get('search', '').strip()
    status_filter = request.args.get('status', 'All')
    sort_by = request.args.get('sort_by', 'rental_date')
    sort_order = request.args.get('sort_order', 'desc')

    rentals_query = RentalRecord.query.filter_by(business_id=business_id)

    if search_query:
        rentals_query = rentals_query.filter(
            RentalRecord.item_name_at_rent.ilike(f'%{search_query}%') |
            RentalRecord.customer_name.ilike(f'%{search_query}%') |
            RentalRecord.customer_phone.ilike(f'%{search_query}%')
        )
    
    if status_filter != 'All':
        rentals_query = rentals_query.filter_by(status=status_filter)
    
    if sort_by == 'rental_date':
        if sort_order == 'asc':
            rentals_query = rentals_query.order_by(RentalRecord.rental_date.asc())
        else:
            rentals_query = rentals_query.order_by(RentalRecord.rental_date.desc())
    elif sort_by == 'customer_name':
        if sort_order == 'asc':
            rentals_query = rentals_query.order_by(RentalRecord.customer_name.asc())
        else:
            rentals_query = rentals_query.order_by(RentalRecord.customer_name.desc())
    elif sort_by == 'status':
        if sort_order == 'asc':
            rentals_query = rentals_query.order_by(RentalRecord.status.asc())
        else:
            rentals_query = rentals_query.order_by(RentalRecord.status.desc())
    
    rental_records = rentals_query.all()
    return render_template('rental_records.html', 
                           rental_records=rental_records, 
                           user_role=session.get('role'),
                           search_query=search_query,
                           status_filter=status_filter,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           current_year=datetime.now().year)

@app.route('/rental_records/add', methods=['GET', 'POST'])
@login_required
def add_rental_record():
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    available_hirable_items = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()

    if request.method == 'POST':
        hirable_item_id = request.form['hirable_item_id']
        customer_name = request.form['customer_name']
        customer_phone = request.form.get('customer_phone')
        rental_date_str = request.form['rental_date']
        expected_return_date_str = request.form['expected_return_date']

        hirable_item = HirableItem.query.filter_by(id=hirable_item_id, business_id=business_id).first_or_404()

        if hirable_item.current_stock < 1:
            flash(f'No stock available for {hirable_item.item_name}.', 'danger')
            return render_template('add_edit_rental_record.html', 
                                   title='Add Rental Record', 
                                   record={}, 
                                   hirable_items=available_hirable_items, 
                                   user_role=session.get('role'),
                                   current_year=datetime.now().year)

        rental_date = datetime.strptime(rental_date_str, '%Y-%m-%d')
        expected_return_date = datetime.strptime(expected_return_date_str, '%Y-%m-%d')

        new_record = RentalRecord(
            business_id=business_id,
            hirable_item_id=hirable_item.id,
            item_name_at_rent=hirable_item.item_name,
            customer_name=customer_name,
            customer_phone=customer_phone,
            rental_date=rental_date,
            expected_return_date=expected_return_date,
            hire_rate_at_rent=hirable_item.hire_rate_per_day,
            status='Rented'
        )
        db.session.add(new_record)

        # Deduct from current stock
        hirable_item.current_stock -= 1
        hirable_item.last_updated = datetime.now()
        db.session.add(hirable_item)

        db.session.commit()
        flash('Rental record added successfully!', 'success')
        return redirect(url_for('rental_records'))
    
    default_record = {
        'hirable_item_id': '', 'customer_name': '', 'customer_phone': '',
        'rental_date': date.today().strftime('%Y-%m-%d'),
        'expected_return_date': (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    }
    return render_template('add_edit_rental_record.html', 
                           title='Add Rental Record', 
                           record=default_record, 
                           hirable_items=available_hirable_items, 
                           user_role=session.get('role'),
                           current_year=datetime.now().year)

@app.route('/rental_records/return/<int:record_id>', methods=['POST'])
@login_required
def return_rental_record(record_id):
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    record_to_return = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()

    if record_to_return.status != 'Rented' and record_to_return.status != 'Overdue':
        flash(f'Cannot return rental record with status: {record_to_return.status}. Only "Rented" or "Overdue" records can be returned.', 'danger')
        return redirect(url_for('rental_records'))
    
    return_date = datetime.now()
    record_to_return.return_date = return_date

    # Calculate total hire amount
    rental_duration = (record_to_return.return_date - record_to_return.rental_date).days
    if rental_duration < 1: # Minimum 1 day rental
        rental_duration = 1
    
    record_to_return.total_hire_amount = rental_duration * record_to_return.hire_rate_at_rent
    record_to_return.status = 'Returned'
    record_to_return.last_updated = datetime.now()

    # Return stock to hirable item
    hirable_item = HirableItem.query.filter_by(id=record_to_return.hirable_item_id, business_id=business_id).first()
    if hirable_item:
        hirable_item.current_stock += 1
        hirable_item.last_updated = datetime.now()
        db.session.add(hirable_item)

    db.session.commit()
    flash(f'Rental record for "{record_to_return.item_name_at_rent}" returned successfully! Total amount: GH₵{record_to_return.total_hire_amount:.2f}', 'success')
    return redirect(url_for('rental_records'))

@app.route('/rental_records/cancel/<int:record_id>', methods=['POST'])
@login_required
def cancel_rental_record(record_id):
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    record_to_cancel = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()

    if record_to_cancel.status != 'Rented':
        flash(f'Cannot cancel rental record with status: {record_to_cancel.status}. Only "Rented" records can be cancelled.', 'danger')
        return redirect(url_for('rental_records'))
    
    # Return stock to hirable item if it was rented (implicitly assumes quantity of 1)
    hirable_item = HirableItem.query.filter_by(id=record_to_cancel.hirable_item_id, business_id=business_id).first()
    if hirable_item:
        hirable_item.current_stock += 1
        hirable_item.last_updated = datetime.now()
        db.session.add(hirable_item)

    record_to_cancel.status = 'Cancelled'
    db.session.commit()
    flash(f'Rental record for "{record_to_cancel.item_name_at_rent}" cancelled successfully! Stock returned.', 'success')
    return redirect(url_for('rental_records'))


# --- NEW: Business Management Routes (Admin Only) ---

@app.route('/manage_businesses')
@login_required
def manage_businesses():
    if session.get('role') != 'admin':
        flash('You do not have permission to manage businesses.', 'danger')
        return redirect(url_for('dashboard'))
    
    businesses = Business.query.all()
    return render_template('manage_businesses.html', 
                           businesses=businesses, 
                           user_role=session.get('role'),
                           current_year=datetime.now().year)

@app.route('/manage_businesses/toggle_active/<int:business_id>', methods=['POST'])
@login_required
def toggle_business_active(business_id):
    if session.get('role') != 'admin':
        flash('You do not have permission to manage businesses.', 'danger')
        return redirect(url_for('dashboard'))

    business = Business.query.get_or_404(business_id)
    
    business.is_active = not business.is_active
    db.session.commit()
    
    status_message = "activated" if business.is_active else "deactivated"
    flash(f'Business "{business.name}" has been {status_message} successfully!', 'success')
    return redirect(url_for('manage_businesses'))

@app.route('/manage_businesses/send_sms_warning/<int:business_id>', methods=['POST'])
@login_required
def send_payment_due_sms(business_id):
    if session.get('role') != 'admin':
        flash('You do not have permission to send SMS warnings.', 'danger')
        return redirect(url_for('dashboard'))

    business = Business.query.get_or_404(business_id)
    
    if not business.contact:
        flash(f'Business "{business.name}" has no contact number registered for SMS.', 'danger')
        return redirect(url_for('manage_businesses'))

    # Compose the SMS message
    sms_message = (
        f"Dear {business.name},\n"
        f"This is a friendly reminder that your subscription payment is due. "
        f"Please make your payment to continue using our services. "
        f"Contact us at {business.contact} for assistance.\n"
        f"Thank you, {ENTERPRISE_NAME}."
    )
    
    app.logger.info(f"Attempting to send payment due SMS to {business.contact} for business {business.name}.")
    
    sms_payload = {
        'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': business.contact,
        'from': ARKESEL_SENDER_ID, 'sms': sms_message
    }
    
    try:
        sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
        sms_response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        sms_result = sms_response.json()
        app.logger.info(f"Arkesel SMS API Response: {sms_result}")

        if sms_result.get('status') == 'success':
            flash(f'Payment due SMS sent to {business.name} ({business.contact}) successfully!', 'success')
        else:
            error_message = sms_result.get('message', 'Unknown error from SMS provider.')
            flash(f'Failed to send SMS to {business.name}. Error: {error_message}', 'danger')
    except requests.exceptions.HTTPError as http_err:
        flash(f'HTTP error sending SMS: {http_err}. Check API key or sender ID.', 'danger')
        app.logger.error(f'HTTP error sending SMS: {http_err}', exc_info=True)
    except requests.exceptions.ConnectionError as conn_err:
        flash(f'Network error sending SMS: {conn_err}. Check internet connection.', 'danger')
        app.logger.error(f'Network error sending SMS: {conn_err}', exc_info=True)
    except requests.exceptions.Timeout as timeout_err:
        flash(f'SMS request timed out: {timeout_err}. Try again later.', 'danger')
        app.logger.error(f'SMS request timed out: {timeout_err}', exc_info=True)
    except json.JSONDecodeError:
        flash('Failed to parse SMS provider response. Response not in JSON format.', 'danger')
        app.logger.error('Failed to parse SMS provider response. Response not in JSON format.', exc_info=True)
    except Exception as e:
        flash(f'An unexpected error occurred while sending SMS: {e}', 'danger')
        app.logger.error(f'Unexpected error sending SMS: {e}', exc_info=True)

    return redirect(url_for('manage_businesses'))


# --- API Endpoints ---
@app.route('/api/get_product_by_barcode', methods=['POST'])
@login_required
def get_product_by_barcode():
    business_id = get_current_business_id()
    if not business_id:
        return jsonify({'error': 'No business selected.'}), 400

    data = request.get_json()
    barcode = data.get('barcode')

    if not barcode:
        return jsonify({'error': 'Barcode not provided.'}), 400

    # Search for product by barcode
    product = InventoryItem.query.filter_by(
        business_id=business_id, 
        barcode=barcode,
        is_active=True # Ensure only active products are returned
    ).first()

    if product:
        # Check stock before returning
        if product.current_stock <= 0:
            return jsonify({
                'success': False,
                'message': f"Product '{product.product_name}' is out of stock."
            }), 400 # Use 400 for a business logic error (out of stock)

        return jsonify({
            'success': True,
            'product': {
                'id': product.id,
                'product_name': product.product_name,
                'current_stock': float(product.current_stock),
                'sale_price': float(product.sale_price),
                'number_of_tabs': float(product.number_of_tabs) if product.number_of_tabs else 1.0,
                'unit_price_per_tab': float(product.unit_price_per_tab) if product.unit_price_per_tab else 0.0,
                'is_fixed_price': product.is_fixed_price,
                'fixed_sale_price': float(product.fixed_sale_price) if product.fixed_sale_price else 0.0,
                'barcode': product.barcode, # Ensure barcode is included here too
                'unit_of_measure': product.unit_of_measure
            }
        })
    else:
        # Try searching by product name if barcode not found
        similar_products = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.is_active == True, # Only suggest active products
            InventoryItem.product_name.ilike(f'%{barcode}%')
        ).limit(5).all()
        
        if similar_products:
            suggestions = [p.product_name for p in similar_products]
            return jsonify({
                'success': False,
                'message': f'Barcode not found. Did you mean: {", ".join(suggestions)}?'
            }), 404
        
        return jsonify({
            'success': False,
            'message': 'Product not found for this barcode.'
        }), 404


# NEW: Jinja2 filter to safely format a date or datetime object (if not already present)
@app.template_filter('format_date')
def format_date(value, format='%Y-%m-%d'):
    if isinstance(value, (datetime, date)):
        return value.strftime(format)
    return "" # Return an empty string if the value is not a date object

# --- Database Initialization (run once to create tables) ---
# IMPORTANT: Once Alembic is set up and working, you should remove or comment out
# db.create_all() from here, as Alembic will manage your schema migrations.
with app.app_context():
    # db.create_all() # Comment out or remove after initial setup with Flask-Migrate
    pass # Keep pass if db.create_all() is commented out

if __name__ == '__main__':
    app.run(debug=True)
