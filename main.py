# app.py - Enhanced Flask Application with PostgreSQL Database and Hardware Business Features

from flask import Flask, render_template, request, redirect, url_for, flash, session, Response,jsonify,abort
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
from flask_wtf.csrf import CSRFProtect # Add this line
import sys

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
def get_user_role():
    return session.get('role')

def get_business_id():
    return session.get('business_id')

def get_business_type():
    return session.get('business_type')

# Basic login_required (if Flask-Login is not explicitly used)
# def login_required(f):
#    from functools import wraps
#    @wraps(f)
#    def decorated_function(*args, **kwargs):
#        if 'username' not in session:
#            flash('Please log in to access this page.', 'warning')
#            return redirect(url_for('login'))
#        return f(*args, **kwargs)
#    return decorated_function

# --- Flask App and DB Initialization ---
app = Flask(__name__)
# Load environment variables
load_dotenv()

# Configuration for Flask and SQLAlchemy
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_super_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:////home/isaac/pharmapps/instance/instance_data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app) # Initialize CSRF protection

# --- Context Processors (for global variables in templates) ---
@app.context_processor
def inject_global_data():
    return {
        'get_user_role': get_user_role,
        'get_business_id': get_business_id,
        'get_business_type': get_business_type
    }

# --- Database Models ---
class Business(db.Model):
    __tablename__ = 'businesses'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), unique=True, nullable=False)
    address = db.Column(db.String(255))
    location = db.Column(db.String(100))
    contact = db.Column(db.String(50))
    email = db.Column(db.String(120), nullable=True) # Added email column
    type = db.Column(db.String(50), default='Pharmacy', nullable=False) # 'Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'
    is_active = db.Column(db.Boolean, default=True, nullable=False) # NEW: Field to track business activity status
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now) # NEW: Add this line
    # Relationships (rest of your relationships remain here)
    users = db.relationship('User', backref='business', lazy=True, cascade="all, delete-orphan")
    inventory_items = db.relationship('InventoryItem', backref='business', lazy=True, cascade="all, delete-orphan")
    sales_records = db.relationship('SalesRecord', backref='business', lazy=True, cascade="all, delete-orphan")
    companies = db.relationship('Company', backref='business', lazy=True, cascade="all, delete-orphan")
    future_orders = db.relationship('FutureOrder', backref='business', lazy=True, cascade="all, delete-orphan")
    hirable_items = db.relationship('HirableItem', backref='business', lazy=True, cascade="all, delete-orphan")
    rental_records = db.relationship('RentalRecord', backref='business', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Business {self.name} ({self.type})>'


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False) # Changed from 'password' to 'password_hash'
    role = db.Column(db.String(50), nullable=False)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False) # NEW LINE: Add this field
    __table_args__ = (db.UniqueConstraint('username', 'business_id', name='_username_business_uc'),)

    # Property to set password, automatically hashes it
    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    # Method to verify password
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'

class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    sale_price = db.Column(db.Float, nullable=False)
    current_stock = db.Column(db.Float, nullable=False)
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.now)
    batch_number = db.Column(db.String(100))
    number_of_tabs = db.Column(db.Integer, nullable=False, default=1) # Tabs for Pharmacy, pieces for Hardware
    unit_price_per_tab = db.Column(db.Float, nullable=False) # Unit price per tab/piece
    item_type = db.Column(db.String(50), default='Pharmacy') # 'Pharmacy', 'Provision Store', 'Hardware Material'
    expiry_date = db.Column(db.Date) # This is a db.Date, which should return datetime.date objects
    is_fixed_price = db.Column(db.Boolean, default=False)
    fixed_sale_price = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True, nullable=False) # New: For soft delete
    barcode = db.Column(db.String(50), unique=True, nullable=True)  # Add this line
    __table_args__ = (db.UniqueConstraint('product_name', 'business_id', name='_product_name_business_uc'),)
    markup_percentage_pharmacy = db.Column(db.Numeric(10, 2), default=0.00)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) # NEW
    def __repr__(self):
        return f'<InventoryItem {self.product_name} (Stock: {self.current_stock})>'


class SalesRecord(db.Model):
    __tablename__ = 'sales_records'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    transaction_date = db.Column(db.DateTime, default=datetime.now, nullable=False)
    customer_phone = db.Column(db.String(20), nullable=True)
    sales_person_name = db.Column(db.String(100), nullable=False)
    grand_total_amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=True)
    items_sold_json = db.Column(db.Text, nullable=False) # Stores JSON array of items, prices, quantities
    # Consider adding payment_status, e.g., 'paid', 'pending', 'partial'
    is_synced = db.Column(db.Boolean, default=False, nullable=False) # Track if synced to central server
    receipt_number = db.Column(db.String(50), unique=True, nullable=True) # Auto-generated unique receipt number
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False)

    def set_items_sold(self, items_list):
        self.items_sold_json = json.dumps(items_list)

    def get_items_sold(self):
        return json.loads(self.items_sold_json)

    def __repr__(self):
        return f'<SalesRecord {self.id} - Total: {self.grand_total_amount}>'

# --- New Models for Hardware Business ---

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    company_name = db.Column(db.String(255), nullable=False) # Renamed from 'name'
    contact_person = db.Column(db.String(100))
    phone_number = db.Column(db.String(20)) # Renamed from 'phone'
    email = db.Column(db.String(120)) # Changed length and nullable
    address = db.Column(db.String(200)) # Changed length
    balance = db.Column(db.Float, default=0.0, nullable=False) # Positive for credit, negative for debit (from your business's perspective)
    # Ensure 'last_updated' is defined here as it caused a migration issue before
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) # NEW
    is_active = db.Column(db.Boolean, default=True, nullable=False) # NEW

    # Relationship to CompanyTransaction
    transactions = db.relationship('CompanyTransaction', backref='company', lazy=True, cascade="all, delete-orphan")

    creditors_list = db.relationship(
                'Creditor',
                back_populates='company_creditor_rel', # This should match the backref name on Creditor
                lazy=True,
                cascade="all, delete-orphan"
            )
    debtors_list = db.relationship(
        'Debtor',
        back_populates='company_debtor_rel', # This should match the backref name on Debtor
        lazy=True,
        cascade="all, delete-orphan"
    )
    __table_args__ = (db.UniqueConstraint('company_name', 'business_id', name='_company_name_business_uc'),)

    @property
    def total_creditors_amount(self):
        
        # Sums the balance of all associated Creditor records
        return db.session.query(func.sum(Creditor.amount_owed)).filter( # Changed from balance to amount_owed
            Creditor.company_id == self.id, Creditor.business_id == self.business_id
        ).scalar() or 0.0

    @property
    def total_debtors_amount(self):
        # Sums the balance of all associated Debtor records
        return db.session.query(func.sum(Debtor.amount_due)).filter( # Changed from balance to amount_due
            Debtor.company_id == self.id, Debtor.business_id == self.business_id
        ).scalar() or 0.0

    def __repr__(self):
        return f'<Company {self.company_name} (Balance: {self.balance})>'

class CompanyTransaction(db.Model):
    __tablename__ = 'company_transactions'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), nullable=False)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False) # Redundant but useful for filtering
    transaction_type = db.Column(db.String(50), nullable=False) # Renamed from 'type'
    amount = db.Column(db.Float, nullable=False)
    transaction_date = db.Column(db.Date, nullable=False, default=date.today) # Renamed from 'date' and changed to Date type
    notes = db.Column(db.Text) # Renamed from 'description'
    recorded_by = db.Column(db.String(100)) # User who recorded the transaction
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) # NEW
    def __repr__(self):
        return f'<CompanyTransaction {self.transaction_type} {self.amount} for {self.company_id}>'

class FutureOrder(db.Model):
    __tablename__ = 'future_orders'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), nullable=True) # NEW: Link to Company
    order_details = db.Column(db.Text, nullable=False) # Stores JSON of ordered items
    order_date = db.Column(db.Date, nullable=False, default=date.today) # Renamed from 'date_ordered', changed to Date
    pickup_date = db.Column(db.Date, nullable=False) # Renamed from 'expected_collection_date'
    customer_name = db.Column(db.String(255), nullable=False)
    customer_phone = db.Column(db.String(20)) # Changed length
    notes = db.Column(db.Text) # NEW: Added for additional order notes
    status = db.Column(db.String(50), default='Pending', nullable=False) # 'Pending', 'Collected', 'Cancelled'
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) # NEW

    # Relationship to Company (if linked)
    company = db.relationship('Company', backref='future_orders_rel', lazy=True)

    def __repr__(self):
        return f'<FutureOrder {self.customer_name} (Status: {self.status})>'

# NEW: Hirable Item Model for Hardware
class HirableItem(db.Model):
    __tablename__ = 'hirable_items'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    item_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    rental_price_per_day = db.Column(db.Float, nullable=False) # Renamed from 'daily_hire_price'
    current_stock = db.Column(db.Integer, nullable=False, default=0) # Number of units available for hiring
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True, nullable=False) # For soft delete
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) # NEW
    __table_args__ = (db.UniqueConstraint('item_name', 'business_id', name='_hirable_item_name_business_uc'),)

    def __repr__(self):
        return f'<HirableItem {self.item_name} (Stock: {self.current_stock})>'

# NEW: Rental Record Model for Hardware
class RentalRecord(db.Model):
    __tablename__ = 'rental_records'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    hirable_item_id = db.Column(db.String(36), db.ForeignKey('hirable_items.id'), nullable=False)
    item_name_at_rent = db.Column(db.String(255), nullable=False) # Store name at time of rent for historical accuracy
    quantity = db.Column(db.Integer, nullable=False) # NEW: Added quantity
    rental_price_per_day_at_rent = db.Column(db.Float, nullable=False) # NEW: Added rental price at rent
    rent_date = db.Column(db.Date, nullable=False) # Renamed from 'start_date', changed to Date
    return_date = db.Column(db.Date) # Renamed from 'end_date', changed to Date, this is the EXPECTED return
    customer_name = db.Column(db.String(255), nullable=False)
    customer_phone = db.Column(db.String(20)) # Changed length
    total_rental_amount = db.Column(db.Float, nullable=False) # Renamed from 'total_hire_amount'
    notes = db.Column(db.Text) # NEW: Added notes
    status = db.Column(db.String(50), default='Rented', nullable=False) # 'Rented', 'Completed', 'Overdue', 'Cancelled'
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) # NEW
    date_recorded = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # Define relationship to HirableItem
    hirable_item = db.relationship('HirableItem', backref='rental_records_rel', lazy=True)

    def __repr__(self):
        return f'<RentalRecord {self.item_name_at_rent} for {self.customer_name} (Status: {self.status})>'

class Creditor(db.Model):
    __tablename__ = 'creditors'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False) # Changed nullable to False, added foreign key
    company_name = db.Column(db.String(255), nullable=False) # NEW
    contact_person = db.Column(db.String(100)) # NEW
    phone_number = db.Column(db.String(20)) # NEW
    email = db.Column(db.String(120)) # NEW
    amount_owed = db.Column(db.Float, nullable=False) # Renamed from 'balance', nullable False
    date_incurred = db.Column(db.Date, nullable=False) # NEW
    due_date = db.Column(db.Date) # NEW
    status = db.Column(db.String(50), nullable=False, default='Pending') # NEW
    notes = db.Column(db.Text) # NEW
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) # NEW

    # Relationship to Company (optional, but good for direct access)
    company_creditor_rel = db.relationship(
                'Company',
                back_populates='creditors_list', # This matches the relationship name on Company
                lazy=True
            )

    def __repr__(self):
        return f"<Creditor {self.company_name} (Amount Owed: {self.amount_owed:.2f})>"

class Debtor(db.Model):
    __tablename__ = 'debtors'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False) # Changed nullable to False, added foreign key
    customer_name = db.Column(db.String(255), nullable=False) # NEW
    phone_number = db.Column(db.String(20)) # NEW
    email = db.Column(db.String(120)) # NEW
    amount_due = db.Column(db.Float, nullable=False) # Renamed from 'balance', nullable False
    date_incurred = db.Column(db.Date, nullable=False) # NEW
    due_date = db.Column(db.Date) # NEW
    status = db.Column(db.String(50), nullable=False, default='Pending') # NEW
    notes = db.Column(db.Text) # NEW
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) # NEW

    # Relationship to Company (optional, but good for direct access)
    company_debtor_rel = db.relationship(
        'Company',back_populates='debtors_list',lazy=True)

    def __repr__(self):
        return f"<Debtor {self.customer_name} (Amount Due: {self.amount_due:.2f})>"

# --- Utility Functions ---
def get_current_business_id():
    # Placeholder for getting the current business ID from session or context
    # In a real app, this would be more robust
    return session.get('business_id')

def get_current_business_type():
    # Placeholder for getting the current business type from session or context
    # In a real app, this would be more robust
    return session.get('business_type')


# --- Helper for API serialization (re-using for dashboard) ---
def serialize_inventory_item_api(item):
    """Serializes an InventoryItem object for API response, ensuring consistent types."""
    return {
        'id': str(item.id),
        'product_name': item.product_name,
        'category': item.category,
        'purchase_price': float(item.purchase_price),
        'sale_price': float(item.sale_price),
        'current_stock': float(item.current_stock),
        'last_updated': item.last_updated.isoformat() if item.last_updated else None,
        'batch_number': item.batch_number,
        'number_of_tabs': float(item.number_of_tabs), # Return as float for consistency
        'unit_price_per_tab': float(item.unit_price_per_tab), # Return as float for consistency
        'item_type': item.item_type,
        'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else None,
        'is_fixed_price': item.is_fixed_price,
        'fixed_sale_price': float(item.fixed_sale_price),
        'is_active': item.is_active,
        'barcode': item.barcode,
        'markup_percentage_pharmacy': float(item.markup_percentage_pharmacy),
        'synced_to_remote': item.synced_to_remote
    }

# --- Routes ---

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', title='Login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and user.verify_password(password):
            if not user.is_active:
                flash('Your account is currently inactive. Please contact your administrator.', 'danger')
                return redirect(url_for('login'))

            session['username'] = user.username
            session['role'] = user.role
            session['user_id'] = str(user.id) # Store user ID in session
            session['business_id'] = str(user.business_id) # Store business ID in session

            # Fetch and store business info in session for easy access
            business = Business.query.get(user.business_id)
            if business:
                if not getattr(business, 'is_active', True): # Use getattr for backward compatibility if column doesn't exist
                    flash('Your associated business account is inactive. Please contact support.', 'danger')
                    session.clear() # Clear session to prevent partial login
                    return redirect(url_for('login'))

                session['business_name'] = business.name
                session['business_type'] = business.type
                session['business_info'] = { # Store comprehensive business info
                    'id': str(business.id),
                    'name': business.name,
                    'address': business.address,
                    'location': business.location,
                    'contact': business.contact,
                    'email': business.email,
                    'type': business.type,
                    'is_active': business.is_active
                }

            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', title='Login')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        business_name = request.form.get('business_name').strip()
        business_type = request.form.get('business_type').strip()
        address = request.form.get('address').strip()
        location = request.form.get('location').strip()
        contact = request.form.get('contact').strip()
        email = request.form.get('email').strip() # Get email from form

        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        confirm_password = request.form.get('confirm_password').strip()

        if not all([business_name, business_type, username, password, confirm_password]):
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')

        # Check if business name already exists
        if Business.query.filter_by(name=business_name).first():
            flash('Business name already registered.', 'danger')
            return render_template('register.html')

        # Check if username already exists for any business (if not using business-specific unique constraint)
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return render_template('register.html')

        try:
            new_business = Business(
                name=business_name,
                type=business_type,
                address=address,
                location=location,
                contact=contact,
                email=email, # Assign email
                is_active=True # New businesses are active by default
            )
            db.session.add(new_business)
            db.session.flush() # Flush to get new_business.id for user

            new_user = User(
                username=username,
                password=password, # Password will be hashed by setter
                role='admin', # First user for a new business is admin
                business_id=new_business.id,
                is_active=True
            )
            db.session.add(new_user)
            db.session.commit()

            flash('Business and Admin User registered successfully!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
            app.logger.error(f"Error during registration: {e}")

    return render_template('register.html', current_year=datetime.now().year)

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    business_id = get_current_business_id()
    if not business_id:
        flash('No business selected. Please select a business or register one.', 'warning')
        return redirect(url_for('login'))

    current_business = Business.query.get(business_id)
    # Check if the current business is active
    if not current_business or not getattr(current_business, 'is_active', True):
        flash('Your business account is currently inactive. Please contact support.', 'danger')
        session.clear() # Clear session to force re-login/business selection
        return redirect(url_for('login'))

    business_type = get_current_business_type()

    # Common data for all business types
    # Ensure 'is_active' attribute exists before filtering
    total_products_query = InventoryItem.query.filter_by(business_id=business_id)
    if hasattr(InventoryItem, 'is_active'):
        total_products_query = total_products_query.filter_by(is_active=True)
    total_products = total_products_query.count()

    total_users_query = User.query.filter_by(business_id=business_id)
    if hasattr(User, 'is_active'):
        total_users_query = total_users_query.filter_by(is_active=True)
    total_users = total_users_query.count()

    # Sales data for all business types
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday()) # Monday
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)

    sales_today = db.session.query(func.sum(SalesRecord.grand_total_amount)).filter(
        SalesRecord.business_id == business_id,
        cast(SalesRecord.transaction_date, db.Date) == today
    ).scalar() or 0.0

    sales_this_week = db.session.query(func.sum(SalesRecord.grand_total_amount)).filter(
        SalesRecord.business_id == business_id,
        cast(SalesRecord.transaction_date, db.Date) >= start_of_week
    ).scalar() or 0.0

    sales_this_month = db.session.query(func.sum(SalesRecord.grand_total_amount)).filter(
        SalesRecord.business_id == business_id,
        cast(SalesRecord.transaction_date, db.Date) >= start_of_month
    ).scalar() or 0.0

    sales_this_year = db.session.query(func.sum(SalesRecord.grand_total_amount)).filter(
        SalesRecord.business_id == business_id,
        cast(SalesRecord.transaction_date, db.Date) >= start_of_year
    ).scalar() or 0.0
    
    # Low stock alerts
    low_stock_threshold = 10 # Example threshold
    low_stock_items_query = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        InventoryItem.current_stock <= low_stock_threshold
    )
    if hasattr(InventoryItem, 'is_active'):
        low_stock_items_query = low_stock_items_query.filter(InventoryItem.is_active == True)
    low_stock_items = low_stock_items_query.order_by(InventoryItem.current_stock).all()


    # Expiring items
    expiring_items = []
    if business_type in ['Pharmacy', 'Supermarket', 'Provision Store']:
        expiry_threshold_days = 30 # Items expiring within 30 days
        expiry_date_threshold = today + timedelta(days=expiry_threshold_days)
        expiring_items_query = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.expiry_date.isnot(None),
            InventoryItem.expiry_date <= expiry_date_threshold
        )
        if hasattr(InventoryItem, 'is_active'):
            expiring_items_query = expiring_items_query.filter(InventoryItem.is_active == True)
        expiring_items = expiring_items_query.order_by(InventoryItem.expiry_date).all()

    # Sales by Sales Person for Today
    sales_by_person_today = db.session.query(
        User.username,
        func.sum(SalesRecord.grand_total_amount)
    ).join(User, SalesRecord.sales_person_name == User.username).filter(
        SalesRecord.business_id == business_id,
        cast(SalesRecord.transaction_date, db.Date) == today
    ).group_by(User.username).all()

    # Business-specific dashboard data for Hardware
    business_dashboard_data = {}
    if business_type == 'Hardware':
        total_hirable_items_query = HirableItem.query.filter_by(business_id=business_id)
        if hasattr(HirableItem, 'is_active'):
            total_hirable_items_query = total_hirable_items_query.filter_by(is_active=True)
        total_hirable_items = total_hirable_items_query.count()

        rented_items = RentalRecord.query.filter_by(business_id=business_id, status='Rented').count()
        overdue_rentals = RentalRecord.query.filter(
            RentalRecord.business_id == business_id,
            RentalRecord.status == 'Rented',
            RentalRecord.return_date < today # Changed from end_date to return_date
        ).count()
        business_dashboard_data = {
            'total_hirable_items': total_hirable_items,
            'rented_items': rented_items,
            'overdue_rentals': overdue_rentals
        }
        # Also include for Hardware specific report section (Future Orders and Companies counts)
        total_companies = Company.query.filter_by(business_id=business_id).count()
        total_future_orders = FutureOrder.query.filter_by(business_id=business_id, status='Pending').count()
        business_dashboard_data['total_companies'] = total_companies
        business_dashboard_data['total_future_orders'] = total_future_orders


    return render_template('dashboard.html',
                           username=session.get('username'),
                           user_role=session.get('role'),
                           business_name=session.get('business_name'),
                           business_type=business_type,
                           total_products=total_products,
                           total_users=total_users,
                           sales_today=sales_today,
                           sales_this_week=sales_this_week,
                           sales_this_month=sales_this_month,
                           sales_this_year=sales_this_year,
                           low_stock_items=low_stock_items,
                           expiring_items=expiring_items,
                           sales_by_person_today=sales_by_person_today,
                           business_dashboard_data=business_dashboard_data,
                           current_year=datetime.now().year)

@app.route('/sales', methods=['GET'])
@login_required
def sales():
    business_id = get_current_business_id()
    if not business_id:
        flash('No business selected.', 'warning')
        return redirect(url_for('dashboard'))

    # Base query for sales records of the current business
    sales_records_query = SalesRecord.query.filter_by(business_id=business_id)

    # Filtering by date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            sales_records_query = sales_records_query.filter(SalesRecord.transaction_date >= start_date)
        except ValueError:
            flash('Invalid start date format.', 'danger')

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            sales_records_query = sales_records_query.filter(SalesRecord.transaction_date <= end_date)
        except ValueError:
            flash('Invalid end date format.', 'danger')

    # Filtering by sales person name
    sales_person_filter = request.args.get('sales_person')
    if sales_person_filter and sales_person_filter != 'All':
        sales_records_query = sales_records_query.filter_by(sales_person_name=sales_person_filter)

    # Get all distinct sales persons for the dropdown filter
    sales_persons = db.session.query(SalesRecord.sales_person_name).filter_by(
        business_id=business_id
    ).distinct().order_by(SalesRecord.sales_person_name).all()
    sales_persons = [p[0] for p in sales_persons if p[0]] # Extract names and filter out None/empty

    # Order the results
    sales_records = sales_records_query.order_by(SalesRecord.transaction_date.desc()).all()

    # Prepare sales data for display
    # This loop is where the 'transaction_id' and now 'product_id' errors were occurring.
    # We now properly parse 'items_sold_json' to get individual product details.
    processed_sales_records = []
    for sale in sales_records:
        items_sold_list = sale.get_items_sold() # This returns a list of dictionaries

        # We need to iterate over items_sold_list to get product details for each item
        detailed_items = []
        for item_data in items_sold_list:
            product_id_from_json = item_data.get('id') # Assuming 'id' is the product ID in the JSON
            product_name_from_json = item_data.get('product_name', 'Unknown Product')
            quantity_sold_from_json = item_data.get('quantity', 0)
            price_at_sale_from_json = item_data.get('sale_price', 0.0) # Assuming 'sale_price' is in the JSON

            # You might want to fetch more details from InventoryItem if needed,
            # but for display purposes, the data in items_sold_json should be sufficient.
            # Example: Fetching the current product name from InventoryItem (optional)
            # product_item = InventoryItem.query.filter_by(id=product_id_from_json, business_id=business_id).first()
            # current_product_name = product_item.product_name if product_item else product_name_from_json

            detailed_items.append({
                'product_name': product_name_from_json,
                'quantity_sold': quantity_sold_from_json,
                'price_at_sale': price_at_sale_from_json
            })
        
        # Use receipt_number, or fallback to id if receipt_number is None/empty
        display_id = sale.receipt_number if sale.receipt_number else str(sale.id)

        processed_sales_records.append({
            'id': str(sale.id),
            'receipt_number': display_id, # Use display_id here
            'transaction_date': sale.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
            'customer_phone': sale.customer_phone,
            'sales_person_name': sale.sales_person_name,
            'grand_total_amount': float(sale.grand_total_amount),
            'payment_method': sale.payment_method,
            'items_sold': detailed_items, # Pass the processed detailed items
            'is_synced': sale.is_synced,
            'synced_to_remote': sale.synced_to_remote
        })


    return render_template('sales.html',
                           sales_records=processed_sales_records, # Pass processed records
                           sales_persons=sales_persons,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           selected_sales_person=sales_person_filter,
                           user_role=session.get('role'),
                           current_year=datetime.now().year)

@app.route('/inventory', methods=['GET'])
@login_required
def inventory():
    business_id = get_current_business_id()
    if not business_id:
        flash('No business selected.', 'warning')
        return redirect(url_for('dashboard'))

    # Base query for inventory items of the current business
    inventory_items_query = InventoryItem.query.filter_by(business_id=business_id)

    # Filtering by item_type (e.g., Pharmacy, Hardware Material, Provision Store, Supermarket)
    item_type_filter = request.args.get('item_type')
    if item_type_filter and item_type_filter != 'All':
        inventory_items_query = inventory_items_query.filter_by(item_type=item_type_filter)

    # Filtering by search query (product_name or barcode)
    search_query = request.args.get('search_query', '').strip()
    if search_query:
        inventory_items_query = inventory_items_query.filter(
            (InventoryItem.product_name.ilike(f'%{search_query}%')) |
            (InventoryItem.barcode.ilike(f'%{search_query}%'))
        )

    # Filtering by stock status
    stock_status_filter = request.args.get('stock_status')
    if stock_status_filter:
        if stock_status_filter == 'low':
            low_stock_threshold = 10 # Define your low stock threshold
            inventory_items_query = inventory_items_query.filter(InventoryItem.current_stock <= low_stock_threshold)
        elif stock_status_filter == 'out_of_stock':
            inventory_items_query = inventory_items_query.filter(InventoryItem.current_stock == 0)

    # Filtering by expiry status
    expiry_status_filter = request.args.get('expiry_status')
    if expiry_status_filter:
        today = date.today()
        if expiry_status_filter == 'expiring_soon':
            expiry_threshold_days = 30
            expiry_date_threshold = today + timedelta(days=expiry_threshold_days)
            inventory_items_query = inventory_items_query.filter(
                InventoryItem.expiry_date.isnot(None),
                InventoryItem.expiry_date <= expiry_date_threshold,
                InventoryItem.expiry_date >= today
            )
        elif expiry_status_filter == 'expired':
            inventory_items_query = inventory_items_query.filter(
                InventoryItem.expiry_date.isnot(None),
                InventoryItem.expiry_date < today
            )

    # Order the results (default to product name, then last_updated)
    sort_by = request.args.get('sort_by', 'product_name')
    sort_order = request.args.get('sort_order', 'asc') # 'asc' or 'desc'

    if sort_by == 'product_name':
        if sort_order == 'desc':
            inventory_items_query = inventory_items_query.order_by(InventoryItem.product_name.desc())
        else:
            inventory_items_query = inventory_items_query.order_by(InventoryItem.product_name.asc())
    elif sort_by == 'current_stock':
        if sort_order == 'desc':
            inventory_items_query = inventory_items_query.order_by(InventoryItem.current_stock.desc())
        else:
            inventory_items_query = inventory_items_query.order_by(InventoryItem.current_stock.asc())
    elif sort_by == 'expiry_date':
        if sort_order == 'desc':
            inventory_items_query = inventory_items_query.order_by(InventoryItem.expiry_date.desc())
        else:
            inventory_items_query = inventory_items_query.order_by(InventoryItem.expiry_date.asc())
    elif sort_by == 'last_updated':
        if sort_order == 'desc':
            inventory_items_query = inventory_items_query.order_by(InventoryItem.last_updated.desc())
        else:
            inventory_items_query = inventory_items_query.order_by(InventoryItem.last_updated.asc())

    inventory_items = inventory_items_query.all()

    # Get all distinct item types for the dropdown filter
    all_item_types = db.session.query(InventoryItem.item_type).filter_by(
        business_id=business_id
    ).distinct().order_by(InventoryItem.item_type).all()
    all_item_types = [t[0] for t in all_item_types if t[0]] # Extract names and filter out None/empty

    return render_template('inventory.html',
                           inventory_items=inventory_items,
                           all_item_types=all_item_types,
                           item_type_filter=item_type_filter,
                           search_query=search_query,
                           stock_status_filter=stock_status_filter,
                           expiry_status_filter=expiry_status_filter,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           user_role=session.get('role'),
                           current_year=datetime.now().year)

@app.route('/inventory/add', methods=['GET', 'POST'])
def add_inventory_item():
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to add inventory items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    business_type = get_current_business_type()

    # Determine which item types are relevant for the current business type
   
    relevant_item_types = []
    if business_type == 'Pharmacy':
        relevant_item_types = ['Pharmacy']
    elif business_type == 'Hardware':
        relevant_item_types = ['Hardware Material']

    elif business_type in ['Supermarket', 'Provision Store']:
        relevant_item_types = ['Provision Store']
    # The following two elifs are redundant with the one above, but kept for direct mapping to original.
    elif business_type == 'Supermarket':
        relevant_item_types = ['Supermarket']
    elif business_type == 'Provision Store':
        relevant_item_types = ['Provision Store']
    else:
        # Fallback or general type if none matches. Consider if a business can have diverse types.
        relevant_item_types = ['Pharmacy', 'Hardware Material', 'Supermarket', 'Provision Store'] # Include all if flexible

    available_inventory_items = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        InventoryItem.is_active == True,
        InventoryItem.item_type.in_(relevant_item_types)
    ).all()
    # Assuming serialize_inventory_item_api exists for consistent serialization with API needs
    serialized_inventory_items = [serialize_inventory_item_api(item) for item in available_inventory_items]
    
    # Get pharmacy info for receipts (ensure it's clean for template rendering)
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
        # Fallback if session['business_info'] is not a dict
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
                'name': "Your Enterprise Name", 'address': "N/A", 'location': "N/A",
                'phone': "N/A", 'email': "N/A", 'contact': "N/A"
            }

    # Fetch other businesses for the import section
    other_businesses = []
    if session.get('role') == 'admin':
        # Filter businesses of the same type, excluding the current business
        other_businesses_query = Business.query.filter(
            Business.id != business_id,
            Business.type == business_type # Only show businesses of the same type for import
        )
        other_businesses = other_businesses_query.all()


    if request.method == 'POST':
        product_name = request.form.get('product_name', '').strip()
        category = request.form.get('category', '').strip()
        
        # Safely get numerical inputs, default to 0.0 or 1 if conversion fails or missing
        try:
            purchase_price = float(request.form.get('purchase_price', 0.0))
            current_stock = float(request.form.get('current_stock', 0.0))
            number_of_tabs = int(request.form.get('number_of_tabs', 1))
        except ValueError:
            flash('Invalid input for numerical fields (Price, Stock, Units per Pack). Please enter valid numbers.', 'danger')
            # Re-render with existing form data to preserve user input
            item_data_for_form_on_error = {
                'product_name': product_name, 'category': category,
                'purchase_price': request.form.get('purchase_price', '0.00'),
                'current_stock': request.form.get('current_stock', '0.00'),
                'batch_number': request.form.get('batch_number', '').strip(),
                'barcode': request.form.get('barcode', '').strip(),
                'number_of_tabs': request.form.get('number_of_tabs', '1'),
                'item_type': request.form.get('item_type', business_type),
                'expiry_date': request.form.get('expiry_date', ''),
                'is_fixed_price': 'is_fixed_price' in request.form,
                'fixed_sale_price': request.form.get('fixed_sale_price', '0.00')
            }
            return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                   item=item_data_for_form_on_error, user_role=session.get('role'),
                                   business_type=business_type, current_year=datetime.now().year,
                                   pharmacy_info=pharmacy_info, other_businesses=other_businesses)


        batch_number = request.form.get('batch_number', '').strip()
        raw_barcode = request.form.get('barcode', '').strip() # Get the barcode string
        
        # Set barcode to None if it's an empty string, otherwise keep the value
        barcode_to_save = raw_barcode if raw_barcode else None

        # Validate required string fields
        if not product_name or not category:
            flash('Product Name and Category are required fields.', 'danger')
            item_data_for_form_on_error = {
                'product_name': product_name, 'category': category,
                'purchase_price': purchase_price, 'current_stock': current_stock,
                'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                'number_of_tabs': number_of_tabs,
                'item_type': request.form.get('item_type', business_type),
                'expiry_date': request.form.get('expiry_date', ''),
                'is_fixed_price': 'is_fixed_price' in request.form,
                'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
            }
            return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                   item=item_data_for_form_on_error, user_role=session.get('role'),
                                   business_type=business_type, current_year=datetime.now().year,
                                   pharmacy_info=pharmacy_info, other_businesses=other_businesses)


        # Check if barcode is unique if provided and not None
        if barcode_to_save: # Only check uniqueness if barcode_to_save is not None/empty
            existing_barcode_item = InventoryItem.query.filter_by(
                business_id=business_id,
                barcode=barcode_to_save
            ).first()
            if existing_barcode_item:
                flash('Barcode already in use for another product.', 'danger')
                item_data_for_form_on_error = {
                    'product_name': product_name, 'category': category,
                    'purchase_price': purchase_price, 'current_stock': current_stock,
                    'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                    'number_of_tabs': number_of_tabs,
                    'item_type': request.form.get('item_type', business_type),
                    'expiry_date': request.form.get('expiry_date', ''),
                    'is_fixed_price': 'is_fixed_price' in request.form,
                    'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
                }
                return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                       item=item_data_for_form_on_error, user_role=session.get('role'),
                                       business_type=business_type, current_year=datetime.now().year,
                                       pharmacy_info=pharmacy_info, other_businesses=other_businesses)
        
        expiry_date_str = request.form.get('expiry_date', '').strip()
        
        expiry_date_obj = None 
        if expiry_date_str:
            try:
                expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid expiry date format. Please use YYYY-MM-DD.', 'danger')
                item_data_for_form_on_error = {
                    'product_name': product_name, 'category': category,
                    'purchase_price': purchase_price, 'current_stock': current_stock,
                    'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                    'number_of_tabs': number_of_tabs,
                    'item_type': request.form.get('item_type', business_type),
                    'expiry_date': '',
                    'is_fixed_price': 'is_fixed_price' in request.form,
                    'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
                }
                return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                       item=item_data_for_form_on_error, user_role=session.get('role'),
                                       business_type=business_type, current_year=datetime.now().year,
                                       pharmacy_info=pharmacy_info, other_businesses=other_businesses)

        if number_of_tabs <= 0:
            flash('Number of units/pieces per pack must be greater than zero.', 'danger')
            item_data_for_form_on_error = {
                'product_name': product_name, 'category': category,
                'purchase_price': purchase_price, 'current_stock': current_stock,
                'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                'number_of_tabs': number_of_tabs,
                'item_type': request.form.get('item_type', business_type),
                'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '',
                'is_fixed_price': 'is_fixed_price' in request.form,
                'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
            }
            return render_template('add_edit_inventory.html', title='Add Inventory Item', item=item_data_for_form_on_error, user_role=session.get('role'), business_type=business_type, current_year=datetime.now().year, pharmacy_info=pharmacy_info, other_businesses=other_businesses)


        if InventoryItem.query.filter_by(product_name=product_name, business_id=business_id).first():
            flash('Product with this name already exists for this business.', 'danger')
            item_data_for_form_on_error = {
                'product_name': product_name, 'category': category,
                'purchase_price': purchase_price, 'current_stock': current_stock,
                'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                'number_of_tabs': number_of_tabs,
                'item_type': request.form.get('item_type', business_type),
                'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '',
                'is_fixed_price': 'is_fixed_price' in request.form,
                'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0))
            }
            return render_template('add_edit_inventory.html', title='Add Inventory Item', item=item_data_for_form_on_error, user_role=session.get('role'), business_type=business_type, current_year=datetime.now().year, pharmacy_info=pharmacy_info, other_businesses=other_businesses)
        
        sale_price = 0.0
        unit_price_per_tab = 0.0
        
        is_fixed_price = 'is_fixed_price' in request.form
        fixed_sale_price = float(request.form.get('fixed_sale_price', 0.0)) # Ensure it's always a float

        if is_fixed_price:
            sale_price = fixed_sale_price
            if number_of_tabs > 0:
                unit_price_per_tab = fixed_sale_price / number_of_tabs
        else:
            # If not fixed price and not pharmacy, assume a sale_price input field is needed
            # Since the form doesn't have it, we must ensure it's provided or handled
            if business_type != 'Pharmacy':
                # This field is MISSING from your HTML template
                # You need to add an input for name="sale_price" if you want to use this logic
                input_sale_price = request.form.get('sale_price')
                if input_sale_price is None or input_sale_price.strip() == '':
                    flash('Sale Price is required for non-fixed price items in this business type.', 'danger')
                    item_data_for_form_on_error = {
                        'product_name': product_name, 'category': category,
                        'purchase_price': purchase_price, 'current_stock': current_stock,
                        'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                        'number_of_tabs': number_of_tabs,
                        'item_type': request.form.get('item_type', business_type),
                        'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '',
                        'is_fixed_price': is_fixed_price,
                        'fixed_sale_price': fixed_sale_price
                    }
                    return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                           item=item_data_for_form_on_error, user_role=session.get('role'),
                                           business_type=business_type, current_year=datetime.now().year,
                                           pharmacy_info=pharmacy_info, other_businesses=other_businesses)
                try:
                    sale_price = float(input_sale_price)
                except ValueError:
                    flash('Invalid input for Sale Price. Please enter a valid number.', 'danger')
                    item_data_for_form_on_error = {
                        'product_name': product_name, 'category': category,
                        'purchase_price': purchase_price, 'current_stock': current_stock,
                        'batch_number': batch_number, 'barcode': raw_barcode, # Use raw_barcode for rendering
                        'number_of_tabs': number_of_tabs,
                        'item_type': request.form.get('item_type', business_type),
                        'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '',
                        'is_fixed_price': is_fixed_price,
                        'fixed_sale_price': fixed_sale_price
                    }
                    return render_template('add_edit_inventory.html', title='Add Inventory Item',
                                           item=item_data_for_form_on_error, user_role=session.get('role'),
                                           business_type=business_type, current_year=datetime.now().year,
                                           pharmacy_info=pharmacy_info, other_businesses=other_businesses)
                
                if number_of_tabs > 0:
                    unit_price_per_tab = sale_price / number_of_tabs
            else: # Business type is Pharmacy, and not fixed price
                markup_percentage = float(request.form.get('markup_percentage_pharmacy', 0.0)) / 100
                sale_price = purchase_price + (purchase_price * markup_percentage)
                if number_of_tabs > 0:
                    unit_price_per_tab = sale_price / number_of_tabs


        new_item = InventoryItem(
            business_id=business_id,
            product_name=product_name,
            category=category,
            purchase_price=purchase_price,
            sale_price=sale_price,
            current_stock=current_stock,
            batch_number=batch_number,
            barcode=barcode_to_save, # Use the processed barcode_to_save here
            number_of_tabs=number_of_tabs,
            unit_price_per_tab=unit_price_per_tab,
            item_type=request.form.get('item_type', business_type), # Use the selected item_type from form
            expiry_date=expiry_date_obj,
            is_fixed_price=is_fixed_price,
            fixed_sale_price=fixed_sale_price,
            is_active=True
        )
        db.session.add(new_item)
        db.session.commit()
        flash(f'Inventory item "{product_name}" added successfully!', 'success')
        return redirect(url_for('inventory'))
    
    # GET request / Initial render
    # Ensure all context variables are passed on GET for initial form rendering
    return render_template('add_edit_inventory.html',
                           title='Add Inventory Item',
                           item={}, # Empty item for new form
                           user_role=session.get('role'),
                           business_type=business_type,
                           current_year=datetime.now().year,
                           pharmacy_info=pharmacy_info,
                           other_businesses=other_businesses)
@app.route('/api/get_product_by_barcode', methods=['POST'])
@login_required
def get_product_by_barcode():
    """
    API endpoint to fetch product details by barcode or product name.
    Ensures robust search (case-insensitive, trimmed) and
    correct, consistent data formatting for frontend consumption.
    """
    business_id = get_current_business_id()
    print(f"DEBUG: get_product_by_barcode - business_id: {business_id}")
    if not business_id:
        return jsonify({'success': False, 'message': 'Business context not found.'}), 400

    data = request.get_json()
    query_string = data.get('barcode', '').strip() # Strip whitespace from input
    print(f"DEBUG: get_product_by_barcode - Received query_string: '{query_string}'")

    if not query_string:
        return jsonify({'success': False, 'message': 'Barcode or product name not provided.'}), 400

    # 1. Try searching by exact barcode first.
    # We explicitly handle cases where the barcode might be empty or None in the database.
    product = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        (InventoryItem.barcode == query_string) | (InventoryItem.barcode == None) | (InventoryItem.barcode == ''),
        InventoryItem.is_active == True
    ).first()
    print(f"DEBUG: get_product_by_barcode - Product found by exact barcode: {product.product_name if product else 'None'}")

    if not product:
        # 2. If not found by exact barcode, try searching by product name
        # (case-insensitive, partial match on product_name)
        product = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.is_active == True,
            func.lower(InventoryItem.product_name).ilike(f'%{query_string.lower()}%') # Case-insensitive partial match
        ).first()
        print(f"DEBUG: get_product_by_barcode - Product found by product name: {product.product_name if product else 'None'}")

    if product:
        # Check stock before returning
        if product.current_stock <= 0:
            print(f"DEBUG: Product '{product.product_name}' is out of stock.")
            return jsonify({
                'success': False,
                'message': f"Product '{product.product_name}' is out of stock."
            }), 400

        # Prepare product data for JSON response, ensuring correct types and defaults
        # This structure ensures all expected keys are always present for the frontend
        product_data = {
            'id': str(product.id), # Ensure ID is string for consistency with UUIDs
            'product_name': product.product_name,
            'current_stock': float(product.current_stock or 0.0), # Ensure float, default 0.0
            'is_fixed_price': product.is_fixed_price,
            'barcode': product.barcode,
            'number_of_tabs': float(product.number_of_tabs or 1.0), # Ensure float, default 1.0
            'unit_price_per_tab': float(product.unit_price_per_tab or 0.0), # Ensure float, default 0.0
            'item_type': product.item_type,
            'expiry_date': product.expiry_date.strftime('%Y-%m-%d') if product.expiry_date else None,
            'batch_number': product.batch_number,
            'purchase_price': float(product.purchase_price or 0.0),
            'sale_price': float(product.sale_price or 0.0), # Always include regular sale price
            'fixed_sale_price': float(product.fixed_sale_price or 0.0), # Always include fixed sale price
            'markup_percentage_pharmacy': float(product.markup_percentage_pharmacy or 0.0) # Always include markup
        }

        print(f"DEBUG: Product found and returning: {product_data}")
        return jsonify({'success': True, 'product': product_data})
    else:
        # If no product found by barcode or name, suggest similar products if any exist
        similar_products = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.is_active == True,
            func.lower(InventoryItem.product_name).ilike(f'%{query_string.lower()}%')
        ).limit(5).all()

        if similar_products:
            suggestions = [p.product_name for p in similar_products]
            message = f'Product not found. Did you mean: {", ".join(suggestions)}?'
            print(f"DEBUG: Product not found, suggesting: {message}")
            return jsonify({
                'success': False,
                'message': message
            }), 404
        
        message = 'Product not found for this barcode or name.'
        print(f"DEBUG: Product not found: {message}")
        return jsonify({
            'success': False,
            'message': message
        }), 404

# --- Database Initialization (This part should generally be managed by Alembic) ---
# Keep this pass statement or remove it if db.create_all() is truly not needed.
with app.app_context():
    # db.create_all() # Ensure this line is commented out if Alembic handles schema
    pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=os.getenv('PORT', 5000))
