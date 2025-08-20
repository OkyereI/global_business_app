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
#     from functools import wraps
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if 'username' not in session:
#             flash('Please log in to access this page.', 'warning')
#             return redirect(url_for('login'))
#         return f(*args, **kwargs)
#     return decorated_function

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Access denied: Admins only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'super_admin':
            flash('Access denied: Super Admin only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Permissions based on roles (can be extended)
def permission_required(roles):
    from functools import wraps
    def wrapper(f): # 'f' is the function being decorated (e.g., dashboard, inventory)
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('role') not in roles:
                flash(f'Access denied. Required roles: {", ".join(roles)}.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper




# Load environment variables from .env file
load_dotenv()
# Create a variable to determine the correct path for templates
if getattr(sys, 'frozen', False):
    # Running as a PyInstaller-bundled executable
    base_dir = sys._MEIPASS
else:
    # Running in a normal Python environment
    base_dir = os.path.abspath(os.path.dirname(__file__))

# Construct the paths for templates and the database file
template_dir = os.path.join(base_dir, 'templates')

# The database file will be at the base directory after being bundled
# The path is adjusted to find the database file in its new location
db_path = os.path.join(base_dir, 'instance_data.db')


app = Flask(__name__)

# --- Database Configuration ---
# Updated DATABASE_URL with the user-provided external PostgreSQL connection string
DB_TYPE = os.getenv('DB_TYPE', 'postgresql') # Default to postgresql for server deployment

if DB_TYPE == 'sqlite':
    # Local SQLite database for desktop client
    # This path should be within a writable directory in the bundled app context
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'instance_data.db')
    print(f"Using SQLite database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    # Ensure instance path exists for SQLite
    if not os.path.exists(app.instance_path):
        os.makedirs(app.instance_path)
else:
    # Remote PostgreSQL database for server deployment
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL',
            'postgresql://bisinessdb_user:QceRMwRe2FtjhPk8iMLCIKB3j3s4KmhI@dpg-d1olvgbuibrs73cum700-a.oregon-postgres.render.com/bisinessdb'

    )
    print(f"Using PostgreSQL database: {app.config['SQLALCHEMY_DATABASE_URI']}")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your_super_secret_key_here')

# app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
#     'DATABASE_URL',
#     'postgresql://bisinessdb_user:QceRMwRe2FtjhPk8iMLCIKB3j3s4KmhI@dpg-d1olvgbuibrs73cum700-a.oregon-postgres.render.com/bisinessdb'
# )
csrf = CSRFProtect(app) # Add this line to initialize CSRFProtect
db = SQLAlchemy(app)
migrate = Migrate(app, db) # Initialize Flask-Migrate

# --- Define Database Models ---

class Business(db.Model):
    __tablename__ = 'businesses'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), unique=True, nullable=False)
    address = db.Column(db.String(255))
    location = db.Column(db.String(100))
    contact = db.Column(db.String(50))
    type = db.Column(db.String(50), default='Pharmacy', nullable=False) # 'Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'
    is_active = db.Column(db.Boolean, default=True, nullable=False) # NEW: Field to track business activity status
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now) # NEW: Add this line
    # Relationships (rest of your relationships remain here)
    users = db.relationship('User', backref='business', lazy=True, cascade="all, delete-orphan")
    inventory_items = db.relationship('InventoryItem', backref='business', lazy=True, cascade="all, delete-orphan")
    sales_records = db.relationship('SaleRecord', backref='business', lazy=True, cascade="all, delete-orphan")
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
<<<<<<< HEAD
=======

>>>>>>> 9823f2e49f8fad873f50c5a3321e708833d8c6cb
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
    def __repr__(self):
        return f'<InventoryItem {self.product_name} (Stock: {self.current_stock})>'


class SaleRecord(db.Model):
    __tablename__ = 'sales_records'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('inventory_items.id'), nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    quantity_sold = db.Column(db.Float, nullable=False)
    sale_unit_type = db.Column(db.String(50)) # e.g., 'pack', 'tab', 'unit'
    price_at_time_per_unit_sold = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    sale_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    customer_phone = db.Column(db.String(50))
    sales_person_name = db.Column(db.String(100))
    reference_number = db.Column(db.String(100)) # For external reference if needed
    transaction_id = db.Column(db.String(36), nullable=False, default=lambda: str(uuid.uuid4())) # To group items in one sale
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) # NEW: Flag for sync

    def __repr__(self):
        return f'<SaleRecord {self.product_name} - {self.quantity_sold}>'
    def __repr__(self):
        return f'<SaleRecord {self.product_name} (Qty: {self.quantity_sold})>'

# --- New Models for Hardware Business ---

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    address = db.Column(db.String(255))
    balance = db.Column(db.Float, default=0.0, nullable=False) # Positive for credit, negative for debit (from your business's perspective)
    # Ensure 'last_updated' is defined here as it caused a migration issue before
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


    # Relationship to CompanyTransaction
    transactions = db.relationship('CompanyTransaction', backref='company', lazy=True, cascade="all, delete-orphan")

    # Relationships to Creditor and Debtor models with overlaps to resolve warnings
    # These definitions should match what you have, ensuring 'Creditor' and 'Debtor'
    # models correctly define their 'company_id' foreign keys.

<<<<<<< HEAD
    # Primary relationships with descriptive backrefs
    # If the warnings specifically mentioned 'creditor_records' and 'debtor_records'
    # as the conflicting ones, and you don't have explicit definitions for them
    # in your Company model, then the 'overlaps' should go on the relationships
    # on the Creditor/Debtor side.
    # However, if 'creditor_records' and 'debtors_records' *do* exist, you need to
    # decide which ones are primary and apply overlaps accordingly.
    # For now, I'm assuming 'creditors_list' and 'debtors_list' are your main ones
    # from the Company side.

    # If your SQLAlchemy warnings refer to specific relationship names like
    # 'Company.creditor_records' and 'Company.debtors_records' (which are NOT in this snippet),
    # you MUST add the overlaps parameter to *those* specific relationships.
    # The snippet you sent does *not* contain the relationships that the warnings
    # directly called out as needing the overlaps parameter.

    # Re-adding `overlaps` to the `creditors_list` and `debtors_list` relationships
    # ONLY IF these are actually conflicting with *other* relationships defined
    # on the Company model (e.g., if you still have `creditor_records` defined elsewhere).
    # If 'creditors_list' is the ONLY relationship to Creditor from Company, it might not
    # need an 'overlaps' here. The warnings suggest *other* named relationships.

    # Based on the warnings you shared:
    # `Company.creditor_records` conflicts with `Company.creditors_list` AND `Creditor.company_creditor_rel`.
    # This implies that `creditor_records` is a relationship that needs the `overlaps` parameter
    # and should list `creditors_list` and `company_creditor_rel` within it.

    # If you only have `creditors_list` and `debtors_list` defined on Company:
=======
    # NEW: Relationships to Creditor and Debtor models
    # This assumes your Creditor and Debtor models have 'company_id' foreign keys
>>>>>>> 9823f2e49f8fad873f50c5a3321e708833d8c6cb
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
<<<<<<< HEAD

=======
>>>>>>> 9823f2e49f8fad873f50c5a3321e708833d8c6cb
    __table_args__ = (db.UniqueConstraint('name', 'business_id', name='_company_name_business_uc'),)

    @property
    def total_creditors_amount(self):
        
        # Sums the balance of all associated Creditor records
        return db.session.query(func.sum(Creditor.balance)).filter_by(
            company_id=self.id, business_id=self.business_id
        ).scalar() or 0.0

    @property
    def total_debtors_amount(self):
        # Sums the balance of all associated Debtor records
        return db.session.query(func.sum(Debtor.balance)).filter_by(
            company_id=self.id, business_id=self.business_id
        ).scalar() or 0.0

    def __repr__(self):
        return f'<Company {self.name} (Balance: {self.balance})>'

class CompanyTransaction(db.Model):
    __tablename__ = 'company_transactions'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), nullable=False)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False) # Redundant but useful for filtering
    type = db.Column(db.String(50), nullable=False) # 'Credit' or 'Debit'
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    description = db.Column(db.Text)
    recorded_by = db.Column(db.String(100)) # User who recorded the transaction

    def __repr__(self):
        return f'<CompanyTransaction {self.type} {self.amount} for {self.company_id}>'

class FutureOrder(db.Model):
    __tablename__ = 'future_orders'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    customer_name = db.Column(db.String(255), nullable=False)
    customer_phone = db.Column(db.String(50))
    items_json = db.Column(db.Text, nullable=False) # JSON string of [{'product_id', 'product_name', 'quantity', 'unit_price', 'unit_type'}]
    total_amount = db.Column(db.Float, nullable=False)
    date_ordered = db.Column(db.DateTime, nullable=False, default=datetime.now)
    expected_collection_date = db.Column(db.Date)
    actual_collection_date = db.Column(db.DateTime)
    status = db.Column(db.String(50), default='Pending', nullable=False) # 'Pending', 'Collected', 'Cancelled'
    remaining_balance = db.Column(db.Float, nullable=False, default=0.0) # Amount still owed by customer

    def get_items(self):
        return json.loads(self.items_json)

    def set_items(self, items_list):
        self.items_json = json.dumps(items_list)

    def __repr__(self):
        return f'<FutureOrder {self.customer_name} (Status: {self.status})>'

# NEW: Hirable Item Model for Hardware
class HirableItem(db.Model):
    __tablename__ = 'hirable_items'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    item_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    daily_hire_price = db.Column(db.Float, nullable=False)
    current_stock = db.Column(db.Integer, nullable=False, default=0) # Number of units available for hiring
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True, nullable=False) # For soft delete

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
    customer_name = db.Column(db.String(255), nullable=False)
    customer_phone = db.Column(db.String(50))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date) # Expected return date
    actual_return_date = db.Column(db.DateTime)
    # Removed 'quantity' column as it does not exist in the database and was always 1
    number_of_days = db.Column(db.Integer, nullable=False) # Days calculated at the time of rental
    daily_hire_price_at_rent = db.Column(db.Float, nullable=False)
    total_hire_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='Rented', nullable=False) # 'Rented', 'Completed', 'Overdue', 'Cancelled'
    sales_person_name = db.Column(db.String(100)) # User who recorded the rental
    date_recorded = db.Column(db.DateTime, nullable=False, default=datetime.now)

    # Define relationship to HirableItem
    hirable_item = db.relationship('HirableItem', backref='rental_records_rel', lazy=True)

    def __repr__(self):
        return f'<RentalRecord {self.item_name_at_rent} for {self.customer_name} (Status: {self.status})>'
class Creditor(db.Model):
    __tablename__ = 'creditors'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), nullable=False, index=True)
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), nullable=False, index=True) # CORRECTED: 'companies.id'
    balance = db.Column(db.Float, default=0.0, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationship to Company (optional, but good for direct access)
    company_creditor_rel = db.relationship(
                'Company',
                back_populates='creditors_list', # This matches the relationship name on Company
                lazy=True
            )

    def __repr__(self):
        return f"<Creditor {self.id} (Company: {self.company_id}) Balance: {self.balance:.2f}>"

class Debtor(db.Model):
    __tablename__ = 'debtors'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), nullable=False, index=True)
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), nullable=False, index=True) # CORRECTED: 'companies.id'
    balance = db.Column(db.Float, default=0.0, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationship to Company (optional, but good for direct access)
    company_debtor_rel = db.relationship(
<<<<<<< HEAD
                    'Company',
                    back_populates='debtors_list', # This matches the relationship name on Company
                    lazy=True
                )
=======
                'Company',
                back_populates='debtors_list', # This matches the relationship name on Company
                lazy=True
            )
>>>>>>> 9823f2e49f8fad873f50c5a3321e708833d8c6cb

    def __repr__(self):
        return f"<Debtor {self.id} (Company: {self.company_id}) Balance: {self.balance:.2f}>"

# --- Flask app setup (secret_key, Arkesel, etc.) ---
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_super_secret_key_here')
csrf = CSRFProtect(app) # Add this line to initialize CSRFProtect
ARKESEL_API_KEY = os.getenv('ARKESEL_API_KEY', 'b0FrYkNNVlZGSmdrendVT3hwUHk')
ARKESEL_SENDER_ID = os.getenv('ARKESEL_SENDER_ID', 'uniquebence')
ARKESEL_SMS_URL = "https://sms.arkesel.com/sms/api" # Define Arkesel SMS URL
ADMIN_PHONE_NUMBER = os.getenv('ADMIN_PHONE_NUMBER', '233543169389')
ENTERPRISE_NAME = os.getenv('ENTERPRISE_NAME','Global Business')
PHARMACY_LOCATION = os.getenv('PHARMACY_LOCATION', 'Accra, Ghana')
PHARMACY_ADDRESS = os.getenv('PHARMACY_ADDRESS', '123 Main St, City')
PHARMACY_CONTACT = os.getenv('PHARMACY_CONTACT', '+233543169389')


# --- Helper function for current business ID ---
def get_current_business_id():
    return session.get('business_id')

def get_current_business_type():
    business_id = session.get('business_id')
    if business_id:
        business = Business.query.get(business_id)
        if business:
            return business.type
    return None

# --- JSON Serialization Helper for InventoryItem and HirableItem ---
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
        _purchase_price = getattr(item, 'purchase_price', None)
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
            'purchase_price': safe_convert(_purchase_price, float, 0.0),
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
            'barcode': safe_convert(_barcode, str, '')
        }
    except Exception as e:
        # Log the specific exception type and message for powerful debugging
        error_id = getattr(item, 'id', 'UNKNOWN_ID_ERROR')
        error_product_name = getattr(item, 'product_name', 'UNKNOWN_PRODUCT_NAME_ERROR')
        print(f"CRITICAL: Serialization failed for item '{error_product_name}' (ID: {error_id}). "
              f"Exception Type: {e.__class__.__name__}, Message: {str(e)}")
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
            "purchase_price": 0.0,
            "last_updated": None,
            "batch_number": "N/A",
            "is_active": False
        }
def calculate_company_balance_details(company_id):
    """
    Calculates the balance, total debtors, and total creditors for a single company
    based on its transactions from the database.
    """
    # Fetch all transactions for the given company_id
    transactions = CompanyTransaction.query.filter_by(company_id=company_id).all()
    current_balance = 0.0

    for transaction in transactions:
        if transaction.type == 'Debit':
            current_balance += transaction.amount
        elif transaction.type == 'Credit':
            current_balance -= transaction.amount

    total_debtors = 0.0
    total_creditors = 0.0

    if current_balance > 0:
        total_debtors = current_balance
    elif current_balance < 0:
        total_creditors = abs(current_balance) # Use abs() for absolute value

    return {
        'balance': current_balance,
        'total_debtors': total_debtors,
        'total_creditors': total_creditors
    }
def serialize_sale_record(sale):
    """Converts a SaleRecord SQLAlchemy object to a JSON-serializable dictionary."""
    return {
        'id': sale.id,
        'product_id': sale.product_id,
        'product_name': sale.product_name,
        'quantity_sold': float(sale.quantity_sold),
        'sale_unit_type': sale.sale_unit_type,
        'price_at_time_per_unit_sold': float(sale.price_at_time_per_unit_sold),
        'total_amount': float(sale.total_amount),
        'sale_date': sale.sale_date.isoformat(),
        'customer_phone': sale.customer_phone,
        'sales_person_name': sale.sales_person_name,
        'transaction_id': sale.transaction_id
    }


# --- NEW: API Serialization Helpers ---
def serialize_business(business):
    """Converts a Business SQLAlchemy object to a JSON-serializable dictionary."""
    return {
        'id': str(business.id),
        'name': str(business.name),
        'address': str(business.address) if business.address else None,
        'location': str(business.location) if business.location else None,
        'contact': str(business.contact) if business.contact else None,
        'type': str(business.type),
        'is_active': bool(business.is_active),
        'last_updated': business.last_updated.isoformat() if business.last_updated else None
    }

def serialize_inventory_item_api(item):
    """Converts an InventoryItem SQLAlchemy object to a JSON-serializable dictionary for API."""
    return {
        'id': str(item.id),
        'business_id': str(item.business_id),
        'product_name': str(item.product_name),
        'category': str(item.category),
        'purchase_price': float(item.purchase_price),
        'sale_price': float(item.sale_price),
        'current_stock': float(item.current_stock),
        'last_updated': item.last_updated.isoformat() if item.last_updated else None,
        'batch_number': str(item.batch_number) if item.batch_number else None,
        'number_of_tabs': int(item.number_of_tabs),
        'unit_price_per_tab': float(item.unit_price_per_tab),
        'item_type': str(item.item_type),
        'expiry_date': item.expiry_date.isoformat() if item.expiry_date else None,
        'is_fixed_price': bool(item.is_fixed_price),
        'fixed_sale_price': float(item.fixed_sale_price),
        'is_active': bool(item.is_active)
    }

def serialize_sale_record_api(sale):
    """Converts a SaleRecord SQLAlchemy object to a JSON-serializable dictionary for API."""
    return {
        'id': str(sale.id),
        'business_id': str(sale.business_id),
        'product_id': str(sale.product_id),
        'product_name': str(sale.product_name),
        'quantity_sold': float(sale.quantity_sold),
        'sale_unit_type': str(sale.sale_unit_type) if sale.sale_unit_type else None,
        'price_at_time_per_unit_sold': float(sale.price_at_time_per_unit_sold),
        'total_amount': float(sale.total_amount),
        'sale_date': sale.sale_date.isoformat() if sale.sale_date else None,
        'customer_phone': str(sale.customer_phone) if sale.customer_phone else None,
        'sales_person_name': str(sale.sales_person_name) if sale.sales_person_name else None,
        'reference_number': str(sale.reference_number) if hasattr(sale, 'reference_number') and sale.reference_number else None,
        'transaction_id': str(sale.transaction_id) if sale.transaction_id else None
    }

def get_remote_flask_base_url():
    """
    Determines the base URL for the remote Flask API.
    This URL should NOT have a trailing slash.
    """
    remote_url = os.getenv('FLASK_API_URL', 'http://localhost:5000')
    # Ensure no trailing slash for consistent joining
    if remote_url.endswith('/'):
        remote_url = remote_url.rstrip('/')
    return remote_url

def get_last_synced_timestamp():
    """Retrieves the last successful sync timestamp from a configuration or file."""
    # In a desktop app, you'd save this to a local config file or SQLite table
    # For now, let's use a simple file in the instance path for demonstration
    sync_marker_path = os.path.join(app.instance_path, 'last_sync.txt')
    if os.path.exists(sync_marker_path):
        with open(sync_marker_path, 'r') as f:
            return f.read().strip()
    return '1970-01-01T00:00:00Z' # Epoch for initial sync

def set_last_synced_timestamp(timestamp):
    """Saves the last successful sync timestamp."""
    sync_marker_path = os.path.join(app.instance_path, 'last_sync.txt')
    with open(sync_marker_path, 'w') as f:
        f.write(timestamp)

# Helper function to check network connectivity
def check_network_online(timeout=5):
    """Checks if there's an active internet connection by trying to reach a reliable host."""
    try:
        requests.head("http://www.google.com", timeout=timeout)
        return True
    except requests.ConnectionError:
        return False
    except Exception as e:
        print(f"Network check error: {e}")
        return False

# Function to pull data from remote (PostgreSQL) to local (SQLite)
def pull_data_from_remote(remote_business_id, last_synced_at):
    remote_url = get_remote_flask_base_url()
    headers = {} # No special headers for now, relying on session for sync APIs in Flask

    # 1. Pull Inventory
    try:
        inventory_response = requests.get(
            f"{remote_url}/api/v1/inventory?business_id={remote_business_id}&last_synced_at={last_synced_at}",
            headers=headers
        )
        inventory_response.raise_for_status()
        new_inventory_items = inventory_response.json()
        
        with app.app_context(): # Ensure we are in app context for DB operations
            for item_data in new_inventory_items:
                # Upsert into local SQLite
                item = InventoryItem.query.filter_by(id=item_data['id'], business_id=remote_business_id).first()
                if item:
                    # Update existing local item
                    item.product_name = item_data['product_name']
                    item.category = item_data['category']
                    item.purchase_price = item_data['purchase_price']
                    item.sale_price = item_data['sale_price']
                    item.current_stock = item_data['current_stock']
                    item.last_updated = datetime.fromisoformat(item_data['last_updated'])
                    item.batch_number = item_data['batch_number']
                    item.number_of_tabs = item_data['number_of_tabs']
                    item.unit_price_per_tab = item_data['unit_price_per_tab']
                    item.item_type = item_data['item_type']
                    item.expiry_date = datetime.fromisoformat(item_data['expiry_date']).date() if item_data['expiry_date'] else None
                    item.is_fixed_price = item_data['is_fixed_price']
                    item.fixed_sale_price = item_data['fixed_sale_price']
                    item.is_active = item_data['is_active']
                else:
                    # Insert new local item
                    db.session.add(InventoryItem(
                        id=item_data['id'],
                        business_id=remote_business_id,
                        product_name=item_data['product_name'],
                        category=item_data['category'],
                        purchase_price=item_data['purchase_price'],
                        sale_price=item_data['sale_price'],
                        current_stock=item_data['current_stock'],
                        last_updated=datetime.fromisoformat(item_data['last_updated']),
                        batch_number=item_data['batch_number'],
                        number_of_tabs=item_data['number_of_tabs'],
                        unit_price_per_tab=item_data['unit_price_per_tab'],
                        item_type=item_data['item_type'],
                        expiry_date=datetime.fromisoformat(item_data['expiry_date']).date() if item_data['expiry_date'] else None,
                        is_fixed_price=item_data['is_fixed_price'],
                        fixed_sale_price=item_data['fixed_sale_price'],
                        is_active=item_data['is_active']
                    ))
            db.session.commit()
            print(f"Pulled {len(new_inventory_items)} inventory items from remote.")
            return True, f"Pulled {len(new_inventory_items)} inventory items."
    except requests.exceptions.RequestException as e:
        print(f"Error pulling inventory: {e}")
        return False, f"Error pulling inventory: {e}"
    except Exception as e:
        print(f"Unexpected error pulling inventory: {e}")
        return False, f"Unexpected error pulling inventory: {e}"

# Function to push data from local (SQLite) to remote (PostgreSQL)
def push_data_to_remote(remote_business_id):
    remote_url = get_remote_flask_base_url()
    headers = {'Content-Type': 'application/json'} # API expects JSON
    
    # 1. Push pending Sales Records (those not yet marked as synced in local DB)
    with app.app_context(): # Ensure we are in app context for DB operations
        pending_sales = SaleRecord.query.filter_by(business_id=remote_business_id, synced_to_remote=False).all()
        if pending_sales:
            sales_data = [serialize_sale_record_api(s) for s in pending_sales]
            try:
                sales_response = requests.post(f"{remote_url}/api/v1/sales", json=sales_data, headers=headers)
                sales_response.raise_for_status()
                response_json = sales_response.json()
                if response_json.get('message') == 'Sales records synchronized successfully.':
                    for sale in pending_sales:
                        sale.synced_to_remote = True # Mark as synced locally
                    db.session.commit()
                    print(f"Pushed {len(pending_sales)} sales to remote. Response: {response_json}")
                    return True, f"Pushed {len(pending_sales)} sales."
                else:
                    print(f"Error pushing sales (remote message): {response_json.get('message')}")
                    return False, f"Error pushing sales: {response_json.get('message')}"
            except requests.exceptions.RequestException as e:
                print(f"Error pushing sales: {e}")
                db.session.rollback() # Rollback if API call fails
                return False, f"Error pushing sales: {e}"
            except Exception as e:
                print(f"Unexpected error pushing sales: {e}")
                db.session.rollback()
                return False, f"Unexpected error pushing sales: {e}"
        else:
            print("No pending sales to push.")
            return True, "No pending sales to push."

    # NOTE: If you enable local inventory modifications, you'd need a similar
    # push logic for InventoryItem objects here, possibly using a `synced_to_remote` flag
    # on InventoryItem as well. For now, we assume inventory is primarily pulled.

# Main synchronization function
def perform_sync(business_id):
    if not check_network_online():
        print("Offline: Cannot perform synchronization.")
        return False, "Offline: Cannot perform synchronization."

    print("Online: Starting synchronization...")
    
    # In a desktop app, you'd ideally have a way to securely log in once
    # and maintain that session or token for API calls.
    # For this example, we're assuming the desktop app has some way to authenticate
    # or that the remote Flask app's APIs are accessible without full session login
    # if using API keys (which is the recommended production approach).
    # For now, we assume a session is somehow maintained or the remote API is open for sync.

    last_synced_at = get_last_synced_timestamp()
    print(f"Last synced at: {last_synced_at}")
    
    success_push, msg_push = push_data_to_remote(business_id)
    if not success_push:
        return False, f"Sync failed during push: {msg_push}"

    success_pull, msg_pull = pull_data_from_remote(business_id, last_synced_at)
    if not success_pull:
        return False, f"Sync failed during pull: {msg_pull}"

    current_timestamp = datetime.now().isoformat()
    set_last_synced_timestamp(current_timestamp)
    print(f"Synchronization successful at {current_timestamp}")
    return True, "Synchronization successful!"


# --- NEW: Desktop-Specific Routes for Sync Management ---
# These routes would be called from the local UI (renderer.js)
# to trigger sync actions via IPC.

# Before: @app.route('/sync_status', methods=['GET'])
# Before: @login_required
@app.route('/sync_status', methods=['GET'])
@permission_required(['admin']) # Change this line
def sync_status():
    """Returns the current sync status and last sync time."""
    current_status = "Online" if check_network_online() else "Offline"
    last_sync = get_last_synced_timestamp()
    return jsonify({
        'online': check_network_online(),
        'status': current_status,
        'last_sync': last_sync
    })

# ---

# Before: @app.route('/trigger_sync', methods=['POST'])
# Before: @login_required
@app.route('/trigger_sync', methods=['POST'])
@permission_required(['admin']) # Change this line
def trigger_sync():
    """Endpoint to manually trigger a sync from the desktop UI."""
    business_id = get_current_business_id()
    if not business_id:
        return jsonify({'success': False, 'message': 'Business ID not found in session for sync.'}), 400

    success, message = perform_sync(business_id)
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 500
# --- Database Initialization (IMPORTANT for SQLite) ---
# Ensure this block creates tables only if they don't exist for SQLite.
# For local desktop app, you would run this once to create the local SQLite DB.
with app.app_context():
    if DB_TYPE == 'sqlite' and not os.path.exists(os.path.join(app.instance_path, 'instance_data.db')):
        print("Creating SQLite database tables...")
        db.create_all() # Create tables for local SQLite DB
        # You might also want to do an initial pull here to populate the local DB
        # if the user is online for the very first run.
    # For PostgreSQL, you'd manage with Alembic, not db.create_all() here.

# --- NEW: API Endpoints for Data Synchronization ---

@app.route('/api/v1/businesses', methods=['GET'])
@login_required # Temporary: Should be API-specific auth in production
def api_get_businesses():
    """
    API endpoint to fetch a list of businesses.
    Can be filtered by last_updated timestamp for incremental sync.
    """
    if session.get('role') != 'super_admin':
        # For non-super admins, restrict to their own business if applicable
        business_id = get_current_business_id()
        if not business_id:
            return jsonify({'message': 'Access denied: Business ID not in session for this user.'}), 403
        businesses = Business.query.filter_by(id=business_id, is_active=True).all()
    else:
        # Super admin can see all active businesses
        businesses = Business.query.filter_by(is_active=True).all()
    
    # Filter by last_synced_at if provided in query parameters
    last_synced_at_str = request.args.get('last_synced_at')
    if last_synced_at_str:
        try:
            last_synced_at = datetime.fromisoformat(last_synced_at_str)
            businesses = [b for b in businesses if b.last_updated and b.last_updated > last_synced_at]
        except ValueError:
            return jsonify({'message': 'Invalid last_synced_at format. Use ISO 8601.'}), 400

    return jsonify([serialize_business(b) for b in businesses])


@app.route('/api/v1/inventory', methods=['GET'])
@login_required # Temporary: Should be API-specific auth in production
def api_get_inventory():
    """
    API endpoint to fetch inventory items for a business.
    Requires business_id in query params. Can be filtered by last_updated.
    """
    business_id = request.args.get('business_id', get_current_business_id())
    if not business_id:
        return jsonify({'message': 'Business ID is required.'}), 400

    if session.get('role') != 'super_admin' and business_id != get_current_business_id():
        return jsonify({'message': 'Access denied: You can only view inventory for your assigned business.'}), 403

    inventory_query = InventoryItem.query.filter_by(business_id=business_id, is_active=True)

    # Filter by last_synced_at for incremental sync
    last_synced_at_str = request.args.get('last_synced_at')
    if last_synced_at_str:
        try:
            last_synced_at = datetime.fromisoformat(last_synced_at_str)
            inventory_query = inventory_query.filter(InventoryItem.last_updated > last_synced_at)
        except ValueError:
            return jsonify({'message': 'Invalid last_synced_at format. Use ISO 8601.'}), 400
    
    inventory_items = inventory_query.all()
    return jsonify([serialize_inventory_item_api(item) for item in inventory_items])


@app.route('/api/v1/inventory', methods=['POST'])
@login_required # Temporary: Should be API-specific auth in production
def api_upsert_inventory():
    """
    API endpoint to create or update inventory items in batch.
    Expected data: JSON list of inventory item objects.
    """
    business_id = get_current_business_id()
    if not business_id:
        return jsonify({'message': 'Business ID is required to add/update inventory.'}), 400

    if session.get('role') not in ['admin', 'sales']: # Sales can also update stock if part of their workflow
        return jsonify({'message': 'Access denied: Insufficient role to add/update inventory.'}), 403

    items_data = request.get_json()
    if not isinstance(items_data, list):
        return jsonify({'message': 'Request body must be a JSON array of inventory items.'}), 400

    updated_count = 0
    added_count = 0
    errors = []

    for item_data in items_data:
        try:
            item_id = item_data.get('id')
            product_name = item_data.get('product_name')
            category = item_data.get('category')
            purchase_price = float(item_data.get('purchase_price'))
            sale_price = float(item_data.get('sale_price'))
            current_stock = float(item_data.get('current_stock'))
            batch_number = item_data.get('batch_number')
            number_of_tabs = int(item_data.get('number_of_tabs', 1))
            unit_price_per_tab = float(item_data.get('unit_price_per_tab', 0.0))
            item_type = item_data.get('item_type')
            expiry_date_str = item_data.get('expiry_date')
            is_fixed_price = bool(item_data.get('is_fixed_price', False))
            fixed_sale_price = float(item_data.get('fixed_sale_price', 0.0))
            is_active = bool(item_data.get('is_active', True))

            expiry_date_obj = datetime.fromisoformat(expiry_date_str).date() if expiry_date_str else None

            item = None
            if item_id:
                item = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first()
            
            # If item_id was not provided or not found, try by product_name for existing items within the business
            if not item:
                item = InventoryItem.query.filter_by(product_name=product_name, business_id=business_id).first()

            if item:
                # Update existing item
                item.product_name = product_name
                item.category = category
                item.purchase_price = purchase_price
                item.sale_price = sale_price
                item.current_stock = current_stock
                item.batch_number = batch_number
                item.number_of_tabs = number_of_tabs
                item.unit_price_per_tab = unit_price_per_tab
                item.item_type = item_type
                item.expiry_date = expiry_date_obj
                item.is_fixed_price = is_fixed_price
                item.fixed_sale_price = fixed_sale_price
                item.is_active = is_active
                item.last_updated = datetime.now() # Update timestamp
                db.session.add(item)
                updated_count += 1
            else:
                # Create new item
                new_item = InventoryItem(
                    business_id=business_id,
                    product_name=product_name,
                    category=category,
                    purchase_price=purchase_price,
                    sale_price=sale_price,
                    current_stock=current_stock,
                    batch_number=batch_number,
                    number_of_tabs=number_of_tabs,
                    unit_price_per_tab=unit_price_per_tab,
                    item_type=item_type,
                    expiry_date=expiry_date_obj,
                    is_fixed_price=is_fixed_price,
                    fixed_sale_price=fixed_sale_price,
                    is_active=is_active,
                    last_updated=datetime.now() # Set timestamp for new item
                )
                db.session.add(new_item)
                added_count += 1
        except Exception as e:
            errors.append(f"Error processing item '{item_data.get('product_name', 'N/A')}': {str(e)}")
            db.session.rollback() # Rollback current transaction on error
            return jsonify({'message': 'Error processing some items.', 'errors': errors}), 400

    db.session.commit()
    return jsonify({
        'message': 'Inventory synchronization successful.',
        'added_count': added_count,
        'updated_count': updated_count,
        'errors': errors
    })


@app.route('/api/v1/sales', methods=['POST'])
@login_required # Temporary: Should be API-specific auth in production
def api_record_sales():
    """
    API endpoint to record new sales in batch.
    Expected data: JSON list of sales record objects.
    """
    business_id = get_current_business_id()
    if not business_id:
        return jsonify({'message': 'Business ID is required to record sales.'}), 400

    if session.get('role') not in ['admin', 'sales']:
        return jsonify({'message': 'Access denied: Insufficient role to record sales.'}), 403

    sales_data = request.get_json()
    if not isinstance(sales_data, list):
        return jsonify({'message': 'Request body must be a JSON array of sales records.'}), 400

    recorded_count = 0
    errors = []

    for sale_data in sales_data:
        try:
            # Assuming a new sale record is always created, no 'upsert' for sales for now.
            # If the client provides an 'id', we use it, otherwise generate a new one.
            sale_id = sale_data.get('id', str(uuid.uuid4()))
            product_id = sale_data.get('product_id')
            product_name = sale_data.get('product_name')
            quantity_sold = float(sale_data.get('quantity_sold'))
            sale_unit_type = sale_data.get('sale_unit_type')
            price_at_time_per_unit_sold = float(sale_data.get('price_at_time_per_unit_sold'))
            total_amount = float(sale_data.get('total_amount'))
            sale_date_str = sale_data.get('sale_date')
            customer_phone = sale_data.get('customer_phone')
            sales_person_name = sale_data.get('sales_person_name')
            reference_number = sale_data.get('reference_number')
            transaction_id = sale_data.get('transaction_id')

            sale_date_obj = datetime.fromisoformat(sale_date_str) if sale_date_str else datetime.now()

            # Optional: Deduct stock if sales are pushed from offline app (already deducted locally)
            # This logic depends on whether offline app fully handles stock or just records sales.
            # For robustness, we might re-verify/deduct here or log discrepancies.
            # For now, we assume stock was handled locally and just record the sale.
            
            # Check if this exact sale record (by ID and transaction_id) already exists to prevent duplicates on sync
            existing_sale = SaleRecord.query.filter_by(id=sale_id, business_id=business_id, transaction_id=transaction_id).first()
            if existing_sale:
                errors.append(f"Sale record with ID '{sale_id}' and transaction ID '{transaction_id}' already exists. Skipping.")
                continue # Skip adding duplicate

            new_sale = SaleRecord(
                id=sale_id, # Use provided ID for idempotency
                business_id=business_id,
                product_id=product_id,
                product_name=product_name,
                quantity_sold=quantity_sold,
                sale_unit_type=sale_unit_type,
                price_at_time_per_unit_sold=price_at_time_per_unit_sold,
                total_amount=total_amount,
                sale_date=sale_date_obj,
                customer_phone=customer_phone,
                sales_person_name=sales_person_name,
                reference_number=reference_number,
                transaction_id=transaction_id
            )
            db.session.add(new_sale)
            recorded_count += 1
        except Exception as e:
            errors.append(f"Error processing sale for product '{sale_data.get('product_name', 'N/A')}': {str(e)}")
            db.session.rollback() # Rollback current transaction on error
            return jsonify({'message': 'Error processing some sales records.', 'errors': errors}), 400

    db.session.commit()
    return jsonify({
        'message': 'Sales records synchronized successfully.',
        'recorded_count': recorded_count,
        'errors': errors
    })
# ... (existing imports and other code) ...

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

    # 1. Try searching by exact barcode first (case-insensitive and trimmed)
    product = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        func.lower(func.trim(InventoryItem.barcode)) == func.lower(query_string), # Trim and lower both sides
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

@app.route('/')
def index():
    if 'username' in session:
        if session.get('role') == 'super_admin':
            return redirect(url_for('super_admin_dashboard'))
        elif 'business_id' in session:
            return redirect(url_for('dashboard'))
        else:
            return redirect(url_for('business_selection'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Note: The 'is_active=True' check here is for the USER, not the business.
        # We need to check the business's active status separately.
        user = User.query.filter_by(username=username).first() # User.is_active is handled by login_required generally.

        if user and user.verify_password(password): # Using verify_password as per your model
            business = Business.query.get(user.business_id)
            # NEW: Check if the associated business is active
            if not business or not business.is_active:
                flash('Your business account is currently inactive. Please contact support.', 'danger')
                return render_template('login.html', current_year=datetime.now().year)

            session['username'] = user.username
            session['role'] = user.role
            session['business_id'] = user.business_id
            
            # Fetch business info and store in session
            session['business_type'] = business.type # Changed from business.business_type to business.type
            session['business_info'] = {
                'name': business.name,
                'address': business.address,
                'location': business.location,
                'contact': business.contact,
                # 'email' field seems to be missing in your Business model. If you add it, uncomment below:
                # 'email': business.email
                'business_type': business.type # Ensure consistency with type
            }
            
            flash('Login successful!', 'success')
            if session.get('role') == 'super_admin':
                return redirect(url_for('super_admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', current_year=datetime.now().year)
@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    session.pop('business_id', None)
    session.pop('business_name', None)
    session.pop('business_type', None) # Clear business type from session
    session.pop('business_info', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/business_selection', methods=['GET', 'POST'])
def business_selection():
    if 'username' not in session or session.get('role') == 'super_admin':
        flash('Please log in or you are a Super Admin.', 'warning')
        return redirect(url_for('login'))

    current_username = session['username']
    user_businesses_ids = [u.business_id for u in User.query.filter_by(username=current_username).all()]
    user_businesses = Business.query.filter(Business.id.in_(user_businesses_ids)).all()

    if request.method == 'POST':
        selected_business_id = request.form['business_id']
        selected_business = Business.query.get(selected_business_id)

        if selected_business:
            user_data = User.query.filter_by(username=session['username'], business_id=selected_business_id).first()
            
            if user_data:
                session['business_id'] = selected_business_id
                session['business_name'] = selected_business.name
                session['business_type'] = selected_business.type # Update business type in session
                session['role'] = user_data.role
                session['business_info'] = {
                    'name': selected_business.name,
                    'address': selected_business.address,
                    'location': selected_business.location,
                    'contact': selected_business.contact
                }
                flash(f'Switched to business: {session["business_name"]}', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('You do not have access to the selected business.', 'danger')
        else:
            flash('Invalid business selection.', 'danger')
    
    if not user_businesses:
        flash('No businesses found for your account. Please contact an administrator.', 'danger')

    return render_template('business_selection.html', businesses=user_businesses)


# --- Dashboard Route ---

# --- Placeholder routes for demonstration ---
# In a real application, these would be fully implemented.
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

    sales_today = db.session.query(func.sum(SaleRecord.total_amount)).filter(
        SaleRecord.business_id == business_id,
        cast(SaleRecord.sale_date, db.Date) == today
    ).scalar() or 0.0

    sales_this_week = db.session.query(func.sum(SaleRecord.total_amount)).filter(
        SaleRecord.business_id == business_id,
        cast(SaleRecord.sale_date, db.Date) >= start_of_week
    ).scalar() or 0.0

    sales_this_month = db.session.query(func.sum(SaleRecord.total_amount)).filter(
        SaleRecord.business_id == business_id,
        cast(SaleRecord.sale_date, db.Date) >= start_of_month
    ).scalar() or 0.0

    sales_this_year = db.session.query(func.sum(SaleRecord.total_amount)).filter(
        SaleRecord.business_id == business_id,
        cast(SaleRecord.sale_date, db.Date) >= start_of_year
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
        func.sum(SaleRecord.total_amount)
    ).join(User, SaleRecord.sales_person_name == User.username).filter(
        SaleRecord.business_id == business_id,
        cast(SaleRecord.sale_date, db.Date) == today
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
            RentalRecord.end_date < today
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
@app.route('/super_admin_dashboard')
def super_admin_dashboard():
    # Allow 'admin' role to view this dashboard
    if session.get('role') not in ['super_admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    businesses = Business.query.all()
    return render_template('super_admin_dashboard.html', businesses=businesses, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/super_admin/add_business', methods=['GET', 'POST'])
def add_business():
    # Allow 'admin' role to add businesses
    if session.get('role') not in ['super_admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        business_name = request.form['business_name'].strip()
        business_address = request.form['business_address'].strip()
        business_location = request.form['business_location'].strip()
        business_contact = request.form['business_contact'].strip()
        business_type = request.form['business_type'].strip() # New: Get business type
        initial_admin_username = request.form['initial_admin_username'].strip()
        initial_admin_password = request.form['initial_admin_password'].strip()

        if Business.query.filter_by(name=business_name).first():
            flash('Business with this name already exists.', 'danger')
            return render_template('add_edit_business.html', title='Add New Business', business={
                'name': business_name, 'address': business_address, 'location': business_location,
                'contact': business_contact, 'type': business_type, # Pass type back to form
                'initial_admin_username': initial_admin_username, 'initial_admin_password': initial_admin_password
            }, business_types=['Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'], current_year=datetime.now().year) # Pass types to template
        
        new_business = Business(
            name=business_name, address=business_address, location=business_location,
            contact=business_contact, type=business_type, # Save business type
            is_active=True
        )
        db.session.add(new_business)
        db.session.commit()

        initial_admin_user = User(
            username=initial_admin_username, password=initial_admin_password, # Use .password setter which hashes
            role='admin', business_id=new_business.id
        )
        db.session.add(initial_admin_user)
        db.session.commit()

        flash(f'Business "{business_name}" added successfully with initial admin "{initial_admin_username}".', 'success')
        return redirect(url_for('super_admin_dashboard'))
    
    return render_template('add_edit_business.html', title='Add New Business', business={}, business_types=['Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'], current_year=datetime.now().year)

@app.route('/super_admin/edit_business/<string:business_id>', methods=['GET', 'POST'])
def edit_business(business_id):
    # Allow 'admin' role to edit businesses
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))

    business_to_edit = Business.query.get_or_404(business_id)
    initial_admin = User.query.filter_by(business_id=business_id, role='admin').first()

    if request.method == 'POST':
        new_business_name = request.form['business_name'].strip()
        new_business_address = request.form['business_address'].strip()
        new_business_location = request.form['business_location'].strip()
        new_business_contact = request.form['business_contact'].strip()
        new_business_type = request.form['business_type'].strip() # New: Get business type
        new_initial_admin_username = request.form['initial_admin_username'].strip()
        new_initial_admin_password = request.form['initial_admin_password'].strip()

        if Business.query.filter(Business.name == new_business_name, Business.id != business_id).first():
            flash('Business with this name already exists.', 'danger')
            return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit.name}', business={
                'name': new_business_name, 'address': new_business_address, 'location': new_business_location,
                'contact': new_business_contact, 'type': new_business_type, # Pass type back to form
                'initial_admin_username': new_initial_admin_username, 'initial_admin_password': new_initial_admin_password
            }, business_types=['Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'], current_year=datetime.now().year)
        
        business_to_edit.name = new_business_name
        business_to_edit.address = new_business_address
        business_to_edit.location = new_business_location
        business_to_edit.contact = new_business_contact
        business_to_edit.type = new_business_type # Update business type
        
        if initial_admin:
            if new_initial_admin_username != initial_admin.username and \
               User.query.filter_by(username=new_initial_admin_username, business_id=business_id).first():
                flash('New admin username already exists for this business. Business details updated, but admin username not changed.', 'warning')
            else:
                initial_admin.username = new_initial_admin_username
            initial_admin.password = new_initial_admin_password # Use .password setter which hashes
        
        db.session.commit()
        flash(f'Business "{new_business_name}" and admin credentials updated successfully!', 'success')
        return redirect(url_for('super_admin_dashboard'))

    business_data_for_form = {
        'name': business_to_edit.name, 'address': business_to_edit.address, 'location': business_to_edit.location,
        'contact': business_to_edit.contact, 'type': business_to_edit.type, # Pass current type for pre-selection
        # For security, never send password hashes back to the form.
        # The form should only accept new passwords.
        'initial_admin_username': initial_admin.username if initial_admin else '',
        'initial_admin_password': '' # Always leave password field empty for security
    }
    return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit.name}', business=business_data_for_form, business_types=['Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'], current_year=datetime.now().year)


@app.route('/super_admin/view_business_details/<string:business_id>')
def view_business_details(business_id):
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))

    business = Business.query.get_or_404(business_id)
    initial_admin = User.query.filter_by(business_id=business_id, role='admin').first()

    return render_template('view_business_details.html', business=business, initial_admin=initial_admin, current_year=datetime.now().year)


@app.route('/super_admin/delete_business/<string:business_id>')
def delete_business(business_id):
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    business_to_delete = Business.query.get_or_404(business_id)
    
    db.session.delete(business_to_delete)
    db.session.commit()

    flash(f'Business "{business_to_delete.name}" and all its associated data deleted successfully!', 'success')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/super_admin/download_inventory/<string:business_id>')
def download_inventory_csv(business_id):
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))

    business = Business.query.get_or_404(business_id)
    inventory_items = InventoryItem.query.filter_by(business_id=business.id).all()

    si = io.StringIO()
    headers = [
        'id', 'product_name', 'category', 'purchase_price', 'sale_price', 'current_stock', 
        'last_updated', 'batch_number', 'number_of_tabs', 'unit_price_per_tab', 'item_type', 
        'expiry_date', 'is_fixed_price', 'fixed_sale_price', 'business_id', 'is_active'
    ]
    
    writer = csv.DictWriter(si, fieldnames=headers)
    writer.writeheader()
    
    for item in inventory_items:
        row_to_write = {
            'id': item.id,
            'product_name': item.product_name,
            'category': item.category,
            'purchase_price': f"{item.purchase_price:.2f}",
            'sale_price': f"{item.sale_price:.2f}",
            'current_stock': f"{item.current_stock:.2f}",
            'last_updated': item.last_updated.strftime('%Y-%m-%d %H:%M:%S'),
            'batch_number': item.batch_number,
            'number_of_tabs': item.number_of_tabs,
            'unit_price_per_tab': f"{item.unit_price_per_tab:.2f}",
            'item_type': item.item_type,
            'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else '',
            'is_fixed_price': str(item.is_fixed_price),
            'fixed_sale_price': f"{item.fixed_sale_price:.2f}",
            'business_id': item.business_id,
            'is_active': str(item.is_active)
        }
        writer.writerow(row_to_write)

    output = si.getvalue()
    si.close()

    response = Response(output, mimetype='text/csv')
    response.headers["Content-Disposition"] = f"attachment; filename={business.name.replace(' ', '_')}_inventory_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return response

@app.route('/super_admin/upload_inventory/<business_id>', methods=['GET', 'POST'])
def upload_inventory_csv_super_admin(business_id):
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))

    business = Business.query.get_or_404(business_id)

    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        file = request.files['csv_file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        if file and file.filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"))
            csv_reader = csv.DictReader(stream)
            
            updated_count = 0
            added_count = 0
            errors = []

            for row in csv_reader:
                try:
                    product_name = row['product_name'].strip()
                    category = row['category'].strip()
                    purchase_price = float(row['purchase_price'])
                    current_stock = float(row['current_stock'])
                    batch_number = row.get('batch_number', '').strip()
                    number_of_tabs = int(row.get('number_of_tabs', 1))
                    item_type = row.get('item_type', 'Pharmacy').strip()
                    expiry_date_str = row.get('expiry_date', '').strip()
                    expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None
                    is_fixed_price = row.get('is_fixed_price', 'False').lower() == 'true'
                    fixed_sale_price = float(row.get('fixed_sale_price', 0.0))
                    is_active = row.get('is_active', 'True').lower() == 'true' # Read is_active from CSV

                    if number_of_tabs <= 0:
                        errors.append(f"Skipping '{product_name}': 'Number of units/pieces per pack' must be greater than zero.")
                        continue

                    sale_price = 0.0
                    unit_price_per_tab_with_markup = 0.0
                    if item_type == 'Pharmacy':
                        # For Pharmacy, assuming sale_price and unit_price_per_tab are derived from purchase_price + markup
                        # This needs to be consistent with how new pharmacy items are added via UI
                        # For now, let's just directly use sale_price and unit_price_per_tab if provided in CSV
                        sale_price = float(row.get('sale_price', 0.0))
                        unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', 0.0))
                        if sale_price == 0.0 and unit_price_per_tab_with_markup > 0:
                            sale_price = unit_price_per_tab_with_markup * number_of_tabs
                        elif unit_price_per_tab_with_markup == 0.0 and sale_price > 0 and number_of_tabs > 0:
                             unit_price_per_tab_with_markup = sale_price / number_of_tabs

                    elif item_type in ['Hardware Material', 'Provision Store']:
                        sale_price = float(row.get('sale_price', 0.0))
                        # For hardware/provision, unit_price_per_tab might represent price per piece/item
                        unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', sale_price))
                        if number_of_tabs > 0 and sale_price == 0.0:
                             sale_price = unit_price_per_tab_with_markup * number_of_tabs
                        elif number_of_tabs > 0 and unit_price_per_tab_with_markup == 0.0:
                             unit_price_per_tab_with_markup = sale_price / number_of_tabs


                    existing_item = InventoryItem.query.filter_by(
                        product_name=product_name, business_id=business_id
                    ).first()

                    if existing_item:
                        # Update existing item
                        existing_item.category = category
                        existing_item.purchase_price = purchase_price
                        existing_item.sale_price = sale_price
                        existing_item.current_stock = current_stock
                        existing_item.last_updated = datetime.now()
                        existing_item.batch_number = batch_number
                        existing_item.number_of_tabs = number_of_tabs
                        existing_item.unit_price_per_tab = unit_price_per_tab_with_markup
                        existing_item.item_type = item_type
                        existing_item.expiry_date = expiry_date_obj
                        existing_item.is_fixed_price = is_fixed_price
                        existing_item.fixed_sale_price = fixed_sale_price
                        existing_item.is_active = is_active # Update is_active
                        updated_count += 1
                    else:
                        # Add new item
                        new_item = InventoryItem(
                            business_id=business_id,
                            product_name=product_name,
                            category=category,
                            purchase_price=purchase_price,
                            sale_price=sale_price,
                            current_stock=current_stock,
                            batch_number=batch_number,
                            number_of_tabs=number_of_tabs,
                            unit_price_per_tab=unit_price_per_tab_with_markup,
                            item_type=item_type,
                            expiry_date=expiry_date_obj,
                            is_fixed_price=is_fixed_price,
                            fixed_sale_price=fixed_sale_price,
                            is_active=is_active # Set is_active for new item
                        )
                        db.session.add(new_item)
                        added_count += 1
                except Exception as e:
                    errors.append(f"Error processing row for product '{row.get('product_name', 'N/A')}': {e}")
            
            db.session.commit()
            
            if errors:
                flash(f'CSV upload completed with {updated_count} updated, {added_count} added, and {len(errors)} errors. Check console for details.', 'warning')
                for error in errors:
                    print(f"CSV Upload Error: {error}")
            else:
                flash(f'CSV inventory uploaded successfully! {updated_count} items updated, {added_count} items added.', 'success')
            
            return redirect(url_for('super_admin_dashboard'))
        else:
            flash('Invalid file type. Please upload a CSV file.', 'danger')
            return redirect(request.url)
    
    return render_template('upload_inventory.html', business=business, user_role=session.get('role'), current_year=datetime.now().year)

# NEW ROUTE: Export all registered businesses to CSV
@app.route('/super_admin/download_businesses_csv')
@login_required
def download_businesses_csv():
    # ACCESS CONTROL: Only super_admin or admin can export business data
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))

    businesses = Business.query.all()

    si = io.StringIO()
    headers = ['id', 'name', 'address', 'location', 'contact', 'type']
    writer = csv.DictWriter(si, fieldnames=headers)
    writer.writeheader()

    for business in businesses:
        writer.writerow({
            'id': business.id,
            'name': business.name,
            'address': business.address,
            'location': business.location,
            'contact': business.contact,
            'type': business.type
        })

    output = si.getvalue()
    si.close()

    response = Response(output, mimetype='text/csv')
    response.headers["Content-Disposition"] = f"attachment; filename=registered_businesses_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return response

# NEW ROUTE: Transfer Inventory Between Businesses
@app.route('/admin/transfer_inventory', methods=['GET', 'POST'])
@login_required
def transfer_inventory():
    # ACCESS CONTROL: Only super_admin or admin can transfer inventory
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))

    all_businesses = Business.query.all()
    
    # Get all unique categories across all businesses for the dropdown
    all_categories = db.session.query(InventoryItem.category).distinct().all()
    all_categories = sorted([c[0] for c in all_categories if c[0]]) # Extract string and sort

    # Get all unique item types for filtering
    all_item_types = db.session.query(InventoryItem.item_type).distinct().all()
    all_item_types = sorted([t[0] for t in all_item_types if t[0]])

    if request.method == 'POST':
        source_business_id = request.form.get('source_business_id')
        target_business_id = request.form.get('target_business_id')
        category_to_transfer = request.form.get('category_to_transfer').strip()
        item_type_filter = request.form.get('item_type_filter', '').strip() # Get the selected item type filter

        if not source_business_id or not target_business_id or not category_to_transfer:
            flash('Please select both source and target businesses and a category.', 'danger')
            return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)

        if source_business_id == target_business_id:
            flash('Source and target businesses cannot be the same.', 'danger')
            return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)

        source_business = Business.query.get(source_business_id)
        target_business = Business.query.get(target_business_id)

        if not source_business or not target_business:
            flash('Invalid source or target business selected.', 'danger')
            return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)

        # Fetch items from source business for the specified category and optional item_type
        items_to_transfer_query = InventoryItem.query.filter_by(
            business_id=source_business_id,
            category=category_to_transfer,
            is_active=True
        )
        if item_type_filter:
            items_to_transfer_query = items_to_transfer_query.filter_by(item_type=item_type_filter)

        items_to_transfer = items_to_transfer_query.all()

        if not items_to_transfer:
            flash(f'No active inventory items found in "{source_business.name}" for category "{category_to_transfer}" and type "{item_type_filter if item_type_filter else "any"}".', 'warning')
            return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)

        transferred_count = 0
        updated_count = 0
        
        for item in items_to_transfer:
            # Check if an item with the same product_name already exists in the target business
            existing_target_item = InventoryItem.query.filter_by(
                product_name=item.product_name,
                business_id=target_business_id
            ).first()

            if existing_target_item:
                # Update existing item's stock and other relevant fields
                existing_target_item.current_stock += item.current_stock # Add stock
                existing_target_item.purchase_price = item.purchase_price # Overwrite purchase price
                existing_target_item.sale_price = item.sale_price # Overwrite sale price
                existing_target_item.number_of_tabs = item.number_of_tabs # Overwrite units/pack
                existing_target_item.unit_price_per_tab = item.unit_price_per_tab # Overwrite unit price
                existing_target_item.last_updated = datetime.now()
                existing_target_item.batch_number = item.batch_number # Overwrite batch number
                existing_target_item.is_fixed_price = item.is_fixed_price
                existing_target_item.fixed_sale_price = item.fixed_sale_price
                existing_target_item.is_active = item.is_active # Maintain active status

                # For expiry date, update only if the source item has a valid, newer expiry date
                if item.expiry_date and (not existing_target_item.expiry_date or item.expiry_date > existing_target_item.expiry_date):
                    existing_target_item.expiry_date = item.expiry_date

                db.session.add(existing_target_item)
                updated_count += 1
            else:
                # Add new item
                new_item = InventoryItem(
                    business_id=target_business_id,
                    product_name=item.product_name,
                    category=item.category,
                    purchase_price=item.purchase_price,
                    sale_price=item.sale_price,
                    current_stock=item.current_stock,
                    last_updated=datetime.now(), # Set current time for new record
                    batch_number=item.batch_number,
                    number_of_tabs=item.number_of_tabs,
                    unit_price_per_tab=item.unit_price_per_tab,
                    item_type=item.item_type,
                    expiry_date=item.expiry_date,
                    is_fixed_price=item.is_fixed_price,
                    fixed_sale_price=item.fixed_sale_price,
                    is_active=True # New items are active
                )
                db.session.add(new_item)
                transferred_count += 1
        
        db.session.commit()
        flash(f'Inventory transfer completed: {transferred_count} new items added, {updated_count} existing items updated (stock added and details overwritten) from "{source_business.name}" to "{target_business.name}" for category "{category_to_transfer}".', 'success')

        return redirect(url_for('transfer_inventory'))

    return render_template('transfer_inventory.html', businesses=all_businesses, categories=all_categories, user_role=session.get('role'), business_types=all_item_types, current_year=datetime.now().year)


# --- Business User Management ---

@app.route('/manage_business_users')
def manage_business_users():
    # ACCESS CONTROL: Allows 'admin' and 'viewer' roles to view this page
    if 'username' not in session or session.get('role') not in ['admin', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to manage business users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    users = User.query.filter_by(business_id=business_id).all()
    return render_template('manage_business_users.html', users=users, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/manage_business_users/add', methods=['GET', 'POST'])
def add_business_user():
    # ACCESS CONTROL: Allows 'admin' and 'viewer' roles to add business users
    if 'username' not in session or session.get('role') not in ['admin', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to add business users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    current_user_role = session.get('role')
    
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip() # Plain text password from form
        role = request.form['role'].strip()

        # ACCESS CONTROL: Viewer role specific restriction: can only add 'sales' or 'viewer' users
        if current_user_role == 'viewer' and role == 'admin':
            flash('As a Viewer, you can only add Sales or Viewer users, not Admin users.', 'danger')
            return render_template('add_edit_business_user.html', title='Add New Business User', user={
                'username': username, 'role': role
            }, user_role=current_user_role, current_year=datetime.now().year)

        if User.query.filter_by(username=username, business_id=business_id).first():
            flash('Username already exists for this business.', 'danger')
            return render_template('add_edit_business_user.html', title='Add New Business User', user={
                'username': username, 'role': role
            }, user_role=current_user_role, current_year=datetime.now().year)
        
        new_user = User(username=username, password=password, role=role, business_id=business_id) # The .password setter will hash it
        db.session.add(new_user)
        db.session.commit()
        flash(f'User "{username}" added successfully!', 'success')
        return redirect(url_for('manage_business_users'))
    
    return render_template('add_edit_business_user.html', title='Add New Business User', user={}, user_role=current_user_role, current_year=datetime.now().year)


@app.route('/manage_business_users/edit/<username>', methods=['GET', 'POST'])
def edit_business_user(username):
    # ACCESS CONTROL: Allows 'admin' role to edit business users
    # Viewers cannot edit existing users, only add new ones (sales/viewer)
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to edit business users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    user_to_edit = User.query.filter_by(username=username, business_id=business_id).first_or_404()

    if request.method == 'POST':
        new_username = request.form['username'].strip()
        new_password = request.form['password'].strip() # Plain text password from form
        new_role = request.form['role'].strip()

        if User.query.filter(User.username == new_username, User.business_id == business_id, User.id != user_to_edit.id).first():
            flash('Username already exists for this business.', 'danger')
            return render_template('add_edit_business_user.html', title=f'Edit User: {user_to_edit.username}', user={
                'username': new_username, 'role': new_role
            }, user_role=session.get('role'), current_year=datetime.now().year)

        # Prevent admin from changing their own role to non-admin or deleting themselves
        if user_to_edit.username == session['username'] and new_role != 'admin':
            flash('You cannot change your own role from admin.', 'danger')
            return render_template('add_edit_business_user.html', title=f'Edit User: {user_to_edit.username}', user=user_to_edit, user_role=session.get('role'), current_year=datetime.now().year)

        user_to_edit.username = new_username
        if new_password: # Only update password if a new one is provided
            user_to_edit.password = new_password # The .password setter will hash it
        user_to_edit.role = new_role
        
        flash(f'User "{username}" updated successfully!', 'success')
        
        db.session.commit()
        return redirect(url_for('manage_business_users'))

    # For GET request, do not send password hash to form
    user_data_for_form = {
        'id': user_to_edit.id,
        'username': user_to_edit.username,
        'role': user_to_edit.role,
        'password': '' # Never pre-fill password fields
    }
    return render_template('add_edit_business_user.html', title=f'Edit User: {user_to_edit.username}', user=user_data_for_form, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/manage_business_users/delete/<username>')
def delete_business_user(username):
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to delete business users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    user_to_delete = User.query.filter_by(username=username, business_id=business_id).first_or_404()

    # Prevent admin from deleting other admins or themselves
    if user_to_delete.role == 'admin':
        flash('Cannot delete an admin user.', 'danger')
        return redirect(url_for('manage_business_users'))
    if user_to_delete.username == session['username']:
        flash('You cannot delete your own user account.', 'danger')
        return redirect(url_for('manage_business_users'))

    db.session.delete(user_to_delete)
    db.session.commit()
    flash(f'User "{username}" deleted successfully!', 'success')
    return redirect(url_for('manage_business_users'))


# --- Inventory Management Routes ---

@app.route('/inventory')
def inventory():
    # ACCESS CONTROL: Allows admin, sales, and viewer roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to view inventory or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    search_query = request.args.get('search', '').strip() # Get search query from URL parameters

    inventory_items_query = InventoryItem.query.filter_by(business_id=business_id, is_active=True)

    # Apply search filter if query exists
    if search_query:
        inventory_items_query = inventory_items_query.filter(
            InventoryItem.product_name.ilike(f'%{search_query}%') |
            InventoryItem.category.ilike(f'%{search_query}%') |
            InventoryItem.batch_number.ilike(f'%{search_query}%')
        )
    
    inventory_items = inventory_items_query.all()
    
    today = date.today()
    three_months_from_now = today + timedelta(days=90) # Define threshold for "expiring soon"

    # Calculate profit margin and expiry flags for each item
    for item in inventory_items:
        item.profit_margin = 0.0
        if item.sale_price > 0:
            item.profit_margin = ((item.sale_price - item.purchase_price) / item.sale_price) * 100

        item.is_expiring_soon = False
        item.is_expired = False
        if item.expiry_date:
            if item.expiry_date < today:
                item.is_expired = True
            elif item.expiry_date >= today and item.expiry_date <= three_months_from_now:
                item.is_expiring_soon = True

    business_type = get_current_business_type()
    if business_type == 'Pharmacy':
        return render_template('pharmacy_inventory.html', inventory_items=inventory_items, user_role=session.get('role'), search_query=search_query, current_year=datetime.now().year)
    elif business_type in ['Hardware', 'Supermarket', 'Provision Store']:
        return render_template('hardware_inventory.html', inventory_items=inventory_items, user_role=session.get('role'), business_type=business_type, search_query=search_query, current_year=datetime.now().year) # Pass business_type
    return render_template('inventory.html', inventory_items=inventory_items, user_role=session.get('role'), search_query=search_query, current_year=datetime.now().year)

# NEW ROUTE: Download CSV for current business's inventory
@app.route('/inventory/download_current_csv')
@login_required
def download_current_inventory_csv():
    # ACCESS CONTROL: Allows admin, sales, and viewer roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to download inventory or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    business_name = session.get('business_name', 'current_business')
    inventory_items = InventoryItem.query.filter_by(business_id=business_id, is_active=True).all()

    si = io.StringIO()
    headers = [
        'id', 'product_name', 'category', 'purchase_price', 'sale_price', 'current_stock', 
        'last_updated', 'batch_number', 'number_of_tabs', 'unit_price_per_tab', 'item_type', 
        'expiry_date', 'is_fixed_price', 'fixed_sale_price', 'business_id', 'is_active'
    ]
    
    writer = csv.DictWriter(si, fieldnames=headers)
    writer.writeheader()
    
    for item in inventory_items:
        row_to_write = {
            'id': item.id,
            'product_name': item.product_name,
            'category': item.category,
            'purchase_price': f"{item.purchase_price:.2f}",
            'sale_price': f"{item.sale_price:.2f}",
            'current_stock': f"{item.current_stock:.2f}",
            'last_updated': item.last_updated.strftime('%Y-%m-%d %H:%M:%S'),
            'batch_number': item.batch_number,
            'number_of_tabs': item.number_of_tabs,
            'unit_price_per_tab': f"{item.unit_price_per_tab:.2f}",
            'item_type': item.item_type,
            'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else '',
            'is_fixed_price': str(item.is_fixed_price),
            'fixed_sale_price': f"{item.fixed_sale_price:.2f}",
            'business_id': item.business_id,
            'is_active': str(item.is_active)
        }
        writer.writerow(row_to_write)

    output = si.getvalue()
    si.close()

    response = Response(output, mimetype='text/csv')
    response.headers["Content-Disposition"] = f"attachment; filename={business_name.replace(' ', '_')}_inventory_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return response

# NEW ROUTE: Admin can upload inventory to their current business
@app.route('/inventory/upload_csv', methods=['GET', 'POST'])
@login_required
def upload_current_inventory_csv():
    # ACCESS CONTROL: Only admin can upload inventory to their current business
    if session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to upload inventory or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    business_name = session.get('business_name', 'Your Business')

    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        file = request.files['csv_file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        if file and file.filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"))
            csv_reader = csv.DictReader(stream)
            
            updated_count = 0
            added_count = 0
            errors = []

            for row in csv_reader:
                try:
                    product_name = row['product_name'].strip()
                    category = row['category'].strip()
                    purchase_price = float(row['purchase_price'])
                    current_stock = float(row['current_stock'])
                    batch_number = row.get('batch_number', '').strip()
                    number_of_tabs = int(row.get('number_of_tabs', 1))
                    item_type = row.get('item_type', session.get('business_type', 'Pharmacy')).strip() # Default to business type
                    expiry_date_str = row.get('expiry_date', '').strip()
                    expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None
                    is_fixed_price = row.get('is_fixed_price', 'False').lower() == 'true'
                    fixed_sale_price = float(row.get('fixed_sale_price', 0.0))
                    is_active = row.get('is_active', 'True').lower() == 'true' # Read is_active from CSV

                    if number_of_tabs <= 0:
                        errors.append(f"Skipping '{product_name}': 'Number of units/pieces per pack' must be greater than zero.")
                        continue

                    sale_price = 0.0
                    unit_price_per_tab_with_markup = 0.0
                    
                    # Determine sale_price and unit_price_per_tab based on item_type and fixed_price status
                    if is_fixed_price:
                        sale_price = fixed_sale_price
                        if number_of_tabs > 0:
                            unit_price_per_tab = fixed_sale_price / number_of_tabs
                    else:
                        if item_type == 'Pharmacy':
                            # For Pharmacy, assuming sale_price and unit_price_per_tab are derived from purchase_price + markup
                            # If CSV provides them, use them directly. Otherwise, apply a default markup (e.g., 20%)
                            sale_price = float(row.get('sale_price', purchase_price * 1.2)) # Default 20% markup
                            unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', sale_price / number_of_tabs if number_of_tabs > 0 else sale_price))
                        elif item_type in ['Hardware Material', 'Provision Store', 'Supermarket']:
                            sale_price = float(row.get('sale_price', purchase_price * 1.2)) # Default 20% markup
                            unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', sale_price / number_of_tabs if number_of_tabs > 0 else sale_price))
                        else: # Fallback for unknown types, or if item_type is not explicitly provided in CSV
                            sale_price = float(row.get('sale_price', purchase_price * 1.2))
                            unit_price_per_tab_with_markup = float(row.get('unit_price_per_tab', sale_price / number_of_tabs if number_of_tabs > 0 else sale_price))

                    existing_item = InventoryItem.query.filter_by(
                        product_name=product_name, business_id=business_id
                    ).first()

                    if existing_item:
                        # Update existing item
                        existing_item.category = category
                        existing_item.purchase_price = purchase_price
                        existing_item.sale_price = sale_price
                        existing_item.current_stock = current_stock
                        existing_item.last_updated = datetime.now()
                        existing_item.batch_number = batch_number
                        existing_item.number_of_tabs = number_of_tabs
                        existing_item.unit_price_per_tab = unit_price_per_tab_with_markup
                        existing_item.item_type = item_type
                        existing_item.expiry_date = expiry_date_obj
                        existing_item.is_fixed_price = is_fixed_price
                        existing_item.fixed_sale_price = fixed_sale_price
                        existing_item.is_active = is_active # Update is_active
                        updated_count += 1
                    else:
                        # Add new item
                        new_item = InventoryItem(
                            business_id=business_id,
                            product_name=product_name,
                            category=category,
                            purchase_price=purchase_price,
                            sale_price=sale_price,
                            current_stock=current_stock,
                            batch_number=batch_number,
                            number_of_tabs=number_of_tabs,
                            unit_price_per_tab=unit_price_per_tab_with_markup,
                            item_type=item_type,
                            expiry_date=expiry_date_obj,
                            is_fixed_price=is_fixed_price,
                            fixed_sale_price=fixed_sale_price,
                            is_active=is_active # Set is_active for new item
                        )
                        db.session.add(new_item)
                        added_count += 1
                except Exception as e:
                    errors.append(f"Error processing row for product '{row.get('product_name', 'N/A')}': {e}. Row data: {row}")
            
            db.session.commit()
            
            if errors:
                flash(f'CSV upload completed with {updated_count} updated, {added_count} added, and {len(errors)} errors. Check server console for details.', 'warning')
                for error in errors:
                    print(f"CSV Upload Error: {error}")
            else:
                flash(f'CSV inventory uploaded successfully! {updated_count} items updated, {added_count} items added.', 'success')
            
            return redirect(url_for('inventory')) # Redirect to the inventory list
        else:
            flash('Invalid file type. Please upload a CSV file.', 'danger')
            return redirect(request.url)
    
    return render_template('upload_current_inventory.html', business_name=business_name, user_role=session.get('role'), current_year=datetime.now().year)


# app.py (your add_inventory_item route)

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
<<<<<<< HEAD
    elif business_type in ['Supermarket', 'Provision Store']:
        relevant_item_types = ['Provision Store']
=======
    elif business_type == 'Supermarket': # Changed from 'in' to handle 'Supermarket' type specifically
        relevant_item_types = ['Supermarket'] # Add 'Supermarket' as relevant item type
    elif business_type == 'Provision Store': # Handle Provision Store separately if its items are distinct
        relevant_item_types = ['Provision Store']
    else:
        # Fallback or general type if none matches. Consider if a business can have diverse types.
        relevant_item_types = ['Pharmacy', 'Hardware Material', 'Supermarket', 'Provision Store'] # Include all if flexible
>>>>>>> 9823f2e49f8fad873f50c5a3321e708833d8c6cb

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
        barcode = request.form.get('barcode', '').strip()
        
        # Validate required string fields
        if not product_name or not category:
            flash('Product Name and Category are required fields.', 'danger')
            item_data_for_form_on_error = {
                'product_name': product_name, 'category': category,
                'purchase_price': purchase_price, 'current_stock': current_stock,
                'batch_number': batch_number, 'barcode': barcode,
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


        # Check if barcode is unique if provided
        if barcode:
            existing_barcode_item = InventoryItem.query.filter_by(
                business_id=business_id,
                barcode=barcode
            ).first()
            if existing_barcode_item:
                flash('Barcode already in use for another product.', 'danger')
                item_data_for_form_on_error = {
                    'product_name': product_name, 'category': category,
                    'purchase_price': purchase_price, 'current_stock': current_stock,
                    'batch_number': batch_number, 'barcode': barcode,
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
                    'batch_number': batch_number, 'barcode': barcode,
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
                'batch_number': batch_number, 'barcode': barcode,
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
                'batch_number': batch_number, 'barcode': barcode,
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
                        'batch_number': batch_number, 'barcode': barcode,
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
                        'batch_number': batch_number, 'barcode': barcode,
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
            barcode=barcode,
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
@app.route('/inventory/edit/<item_id>', methods=['GET', 'POST'])
def edit_inventory_item(item_id):
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to edit inventory items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    item_to_edit = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()
    business_type = get_current_business_type()

    # Determine which item types are relevant for the current business type
    relevant_item_types = []
    if business_type == 'Pharmacy':
        relevant_item_types = ['Pharmacy']
    elif business_type == 'Hardware':
        relevant_item_types = ['Hardware Material']
    elif business_type == 'Supermarket' or business_type == 'Provision Store':
        relevant_item_types = ['Provision Store'] # Assuming 'Provision Store' covers general goods for these

    available_inventory_items = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        InventoryItem.is_active == True,
        InventoryItem.item_type.in_(relevant_item_types)).all()
    serialized_available_inventory_items = [serialize_inventory_item(item) for item in available_inventory_items]


    if request.method == 'POST':
        product_name = request.form['product_name'].strip()
        category = request.form['category'].strip()
        purchase_price = float(request.form['purchase_price'])
        current_stock = float(request.form['current_stock'])
        batch_number = request.form.get('batch_number', '').strip()
        new_barcode = request.form.get('barcode', '').strip()  # NEW: Get barcode
        
        # NEW: Check if barcode is unique
        if new_barcode and new_barcode != item_to_edit.barcode:
            existing_barcode = InventoryItem.query.filter_by(
                business_id=business_id,
                barcode=new_barcode
            ).first()
            if existing_barcode:
                flash('Barcode already in use for another product', 'danger')
                item_data_for_form_on_error = {
                    'id': item_to_edit.id,
                    'product_name': product_name, 'category': category,
                    'purchase_price': purchase_price, 'current_stock': current_stock,
                    'batch_number': batch_number, 'barcode': new_barcode,
                    'number_of_tabs': int(request.form.get('number_of_tabs', 1)),
                    'item_type': business_type,
                    'expiry_date': request.form.get('expiry_date', ''),
                    'is_fixed_price': 'is_fixed_price' in request.form,
                    'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0)),
                    'is_active': 'is_active' in request.form
                }
                if business_type == 'Pharmacy':
                    item_data_for_form_on_error['markup_percentage_pharmacy'] = request.form.get('markup_percentage_pharmacy', '')
                return render_template('add_edit_inventory.html', title=f'Edit Inventory Item: {item_to_edit.product_name}',
                                       item=item_data_for_form_on_error, user_role=session.get('role'),
                                       business_type=business_type, current_year=datetime.now().year)
        
        number_of_tabs = int(request.form.get('number_of_tabs', 1))
        expiry_date_str = request.form.get('expiry_date', '').strip()
        
        # Initialize expiry_date_obj to None
        expiry_date_obj = None 
        if expiry_date_str:
            try:
                expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid expiry date format. Please use YYYY-MM-DD.', 'danger')
                # Prepare item_data_for_form_on_error for re-rendering with error, ensuring expiry_date is handled
                item_data_for_form_on_error = {
                    'id': item_to_edit.id, # Keep ID for context
                    'product_name': product_name, 'category': category,
                    'purchase_price': purchase_price, 'current_stock': current_stock,
                    'batch_number': batch_number, 'barcode': new_barcode,  # NEW: Include barcode
                    'number_of_tabs': number_of_tabs,
                    'item_type': business_type,
                    'expiry_date': '', # Pass empty string to template for invalid date
                    'is_fixed_price': 'is_fixed_price' in request.form,
                    'fixed_sale_price': float(request.form.get('fixed_sale_price', 0.0)),
                    'is_active': 'is_active' in request.form
                }
                if business_type == 'Pharmacy':
                    item_data_for_form_on_error['markup_percentage_pharmacy'] = request.form.get('markup_percentage_pharmacy', '')

                return render_template('add_edit_inventory.html', title=f'Edit Inventory Item: {item_to_edit.product_name}',
                                       item=item_data_for_form_on_error, user_role=session.get('role'),
                                       business_type=business_type, current_year=datetime.now().year)

        is_fixed_price = 'is_fixed_price' in request.form
        fixed_sale_price = float(request.form.get('fixed_sale_price', 0.0))

        if number_of_tabs <= 0:
            flash('Number of units/pieces per pack must be greater than zero.', 'danger')
            # Prepare item_data_for_form_on_error for re-rendering with error, ensuring expiry_date is handled
            item_data_for_form_on_error = {
                'id': item_to_edit.id,
                'product_name': product_name, 'category': category,
                'purchase_price': purchase_price, 'current_stock': current_stock,
                'batch_number': batch_number, 'barcode': new_barcode,  # NEW: Include barcode
                'number_of_tabs': number_of_tabs,
                'item_type': business_type,
                'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '', # Format parsed date or empty
                'is_fixed_price': is_fixed_price, 'fixed_sale_price': fixed_sale_price,
                'is_active': 'is_active' in request.form
            }
            if business_type == 'Pharmacy':
                item_data_for_form_on_error['markup_percentage_pharmacy'] = request.form.get('markup_percentage_pharmacy', '')
            return render_template('add_edit_inventory.html', title='Edit Inventory Item', item=item_data_for_form_on_error, user_role=session.get('role'), business_type=business_type, current_year=datetime.now().year)


        if InventoryItem.query.filter(InventoryItem.product_name == product_name, InventoryItem.business_id == business_id, InventoryItem.id != item_id).first():
            flash('Product with this name already exists for this business.', 'danger')
            # Prepare item_data_for_form_on_error for re-rendering with error, ensuring expiry_date is handled
            item_data_for_form_on_error = {
                'id': item_to_edit.id,
                'product_name': product_name, 'category': category,
                'purchase_price': purchase_price, 'current_stock': current_stock,
                'batch_number': batch_number, 'barcode': new_barcode,  # NEW: Include barcode
                'number_of_tabs': number_of_tabs,
                'item_type': business_type,
                'expiry_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else '', # Format parsed date or empty
                'is_fixed_price': is_fixed_price, 'fixed_sale_price': fixed_sale_price,
                'is_active': 'is_active' in request.form
            }
            if business_type == 'Pharmacy':
                item_data_for_form_on_error['markup_percentage_pharmacy'] = request.form.get('markup_percentage_pharmacy', '')
            return render_template('add_edit_inventory.html', title='Edit Inventory Item', item=item_data_for_form_on_error, user_role=session.get('role'), business_type=business_type, current_year=datetime.now().year)
        
        item_to_edit.product_name = product_name
        item_to_edit.category = category
        item_to_edit.purchase_price = purchase_price
        item_to_edit.current_stock = current_stock
        item_to_edit.last_updated = datetime.now()
        item_to_edit.batch_number = batch_number
        item_to_edit.barcode = new_barcode  # NEW: Set barcode
        item_to_edit.number_of_tabs = number_of_tabs
        item_to_edit.expiry_date = expiry_date_obj # This is now a datetime.date object or None
        item_to_edit.is_fixed_price = is_fixed_price
        item_to_edit.fixed_sale_price = fixed_sale_price
        item_to_edit.is_active = 'is_active' in request.form # Update is_active based on checkbox

        sale_price = 0.0
        unit_price_per_tab = 0.0

        if is_fixed_price:
            sale_price = fixed_sale_price
            if number_of_tabs > 0:
                unit_price_per_tab = fixed_sale_price / number_of_tabs
        else:
            if business_type == 'Pharmacy':
                markup_percentage = float(request.form.get('markup_percentage_pharmacy', 0.0)) / 100
                sale_price = purchase_price + (purchase_price * markup_percentage)
                if number_of_tabs > 0:
                    unit_price_per_tab = sale_price / number_of_tabs
            else: # Hardware, Supermarket, Provision Store
                sale_price = float(request.form['sale_price']) # Assuming a sale_price field for non-pharmacy
                if number_of_tabs > 0:
                    unit_price_per_tab = sale_price / number_of_tabs
        
        item_to_edit.sale_price = sale_price
        item_to_edit.unit_price_per_tab = unit_price_per_tab

        db.session.commit()
        flash(f'Inventory item "{product_name}" updated successfully!', 'success')
        return redirect(url_for('inventory'))

    # --- GET Request / Initial Render ---
    # Prepare item data for the form, ensuring expiry date is a string for the HTML input
    item_data_for_form = {
        'id': item_to_edit.id,
        'product_name': item_to_edit.product_name,
        'category': item_to_edit.category,
        'purchase_price': item_to_edit.purchase_price,
        'sale_price': item_to_edit.sale_price,
        'current_stock': item_to_edit.current_stock,
        'last_updated': item_to_edit.last_updated.isoformat(),
        'batch_number': item_to_edit.batch_number,
        'barcode': item_to_edit.barcode,  # NEW: Include barcode
        'number_of_tabs': item_to_edit.number_of_tabs,
        'unit_price_per_tab': item_to_edit.unit_price_per_tab,
        'item_type': item_to_edit.item_type,
        'is_fixed_price': item_to_edit.is_fixed_price,
        'fixed_sale_price': item_to_edit.fixed_sale_price,
        'is_active': item_to_edit.is_active
    }

    # Format expiry_date for the HTML input
    item_data_for_form['expiry_date'] = item_to_edit.expiry_date.strftime('%Y-%m-%d') if item_to_edit.expiry_date else ''
    
    # Calculate initial markup percentage for display if not fixed price
    if business_type == 'Pharmacy' and not item_to_edit.is_fixed_price and item_to_edit.purchase_price > 0:
        markup_percentage = ((item_to_edit.sale_price - item_to_edit.purchase_price) / item_to_edit.purchase_price) * 100
        item_data_for_form['markup_percentage_pharmacy'] = f"{markup_percentage:.2f}"
    else:
        item_data_for_form['markup_percentage_pharmacy'] = ""


    return render_template('add_edit_inventory.html', title=f'Edit Inventory Item: {item_to_edit.product_name}', item=item_data_for_form, user_role=session.get('role'), business_type=business_type, current_year=datetime.now().year)
@app.route('/inventory/delete/<item_id>')
def delete_inventory_item(item_id):
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to delete inventory items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    item_to_delete = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()
    
    item_to_delete.is_active = False # Soft delete
    db.session.commit()

    flash(f'Inventory item "{item_to_delete.product_name}" marked as inactive successfully!', 'success')
    return redirect(url_for('inventory'))

# --- Sales Records Management ---

@app.route('/sales')
@login_required # Ensure this decorator is present for access control
def sales():
    # ACCESS CONTROL: Allows admin, sales, and viewer roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to view sales records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    search_query = request.args.get('search', '').strip()

    sales_records_query = SaleRecord.query.filter_by(business_id=business_id)

    if search_query:
        # Search by product name, customer phone, sales person name, or transaction ID
        sales_records_query = sales_records_query.filter(
            SaleRecord.product_name.ilike(f'%{search_query}%') |
            SaleRecord.customer_phone.ilike(f'%{search_query}%') |
            SaleRecord.sales_person_name.ilike(f'%{search_query}%') |
            SaleRecord.transaction_id.ilike(f'%{search_query}%')
        )

    sales_records = sales_records_query.order_by(SaleRecord.sale_date.desc()).all()
    
    transactions = {}
    today = date.today() # Get today's date for expiry checks

    for sale in sales_records:
        transaction_id = sale.transaction_id if sale.transaction_id else 'N/A'
        
        # Fetch the associated InventoryItem to get expiry date
        product_item = InventoryItem.query.filter_by(id=sale.product_id, business_id=business_id).first()
        
        # Determine expiry status for the sale item
        sale_item_expires_soon = False
        sale_item_expiry_date = None
        if product_item and product_item.expiry_date:
            sale_item_expiry_date = product_item.expiry_date
            time_to_expiry = product_item.expiry_date - today
            if time_to_expiry.days <= 180 and time_to_expiry.days >= 0:
                sale_item_expires_soon = True
            elif time_to_expiry.days < 0:
                sale_item_expires_soon = 'Expired'

        # Augment the sale record with expiry info and ensure all fields are JSON-serializable
        sale_data = {
            'id': str(sale.id),
            'product_id': str(sale.product_id),
            'product_name': str(sale.product_name),
            'quantity_sold': float(sale.quantity_sold), # Convert Numeric to float
            'sale_unit_type': str(sale.sale_unit_type),
            'price_at_time_per_unit_sold': float(sale.price_at_time_per_unit_sold), # Convert Numeric to float
            'total_amount': float(sale.total_amount), # Convert Numeric to float
            'sale_date': sale.sale_date.isoformat(), # Convert datetime to ISO 8601 string
            'customer_phone': str(sale.customer_phone) if sale.customer_phone else None,
            'sales_person_name': str(sale.sales_person_name) if sale.sales_person_name else None,
            'reference_number': str(sale.reference_number) if hasattr(sale, 'reference_number') and sale.reference_number else None, # Ensure reference_number exists and is string
            'transaction_id': str(sale.transaction_id) if sale.transaction_id else 'N/A',
            'expiry_date': sale_item_expiry_date.isoformat() if sale_item_expiry_date else None, # Convert date to ISO 8601 string
            'expires_soon': sale_item_expires_soon # This is already boolean or string 'Expired'
        }

        if transaction_id not in transactions:
            transactions[transaction_id] = {
                'id': str(transaction_id),
                'sale_date': sale.sale_date.isoformat(), # Convert datetime to ISO 8601 string
                'customer_phone': str(sale.customer_phone) if sale.customer_phone else None,
                'sales_person_name': str(sale.sales_person_name) if sale.sales_person_name else None,
                'total_amount': 0.0,
                'items': [],
                'reference_number': str(sale.reference_number) if hasattr(sale, 'reference_number') and sale.reference_number else None
            }
        transactions[transaction_id]['items'].append(sale_data)
        transactions[transaction_id]['total_amount'] += float(sale.total_amount) # Ensure addition is with float

    sorted_transactions = sorted(list(transactions.values()), 
                                 key=lambda x: datetime.fromisoformat(x['sale_date']), # Use fromisoformat for sorting
                                 reverse=True)
    
    # Calculate total for currently displayed sales
    total_displayed_sales = sum(t['total_amount'] for t in sorted_transactions)
    for transaction in transactions:
        if 'items' in transaction:
            for item in transaction['items']:
                # Convert string dates to datetime objects
                if 'expiry_date' in item:
                    if isinstance(item['expiry_date'], str):
                        try:
                            # Convert string to datetime object
                            item['expiry_date'] = datetime.strptime(
                                item['expiry_date'], 
                                '%Y-%m-%d'  # Match your date format
                            )
                        except (ValueError, TypeError):
                            # Handle invalid/empty dates
                            item['expiry_date'] = None
                    # Ensure existing datetimes are timezone-naive
                    elif isinstance(item['expiry_date'], datetime):
                        # Remove timezone info if present
                        if item['expiry_date'].tzinfo is not None:
                            item['expiry_date'] = item['expiry_date'].replace(tzinfo=None)
    
    return render_template('sales_list.html', 
                           transactions=sorted_transactions, 
                           user_role=session.get('role'), 
                           business_type=session.get('business_type'), 
                           search_query=search_query, 
                           total_displayed_sales=total_displayed_sales, 
                           current_year=datetime.now().year) # Pass current_year


# app.py

# ... (Existing imports, Flask app setup, DB_TYPE configuration, models, etc.) ...

# app.py

@app.route('/sales/add', methods=['GET', 'POST'])
@login_required
def add_sale():
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to add sales records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    business_type = get_current_business_type()

<<<<<<< HEAD
=======
    print(f"DEBUG: Current business_id: {business_id}")
    print(f"DEBUG: Current business_type: {business_type}")

    
>>>>>>> 9823f2e49f8fad873f50c5a3321e708833d8c6cb
    relevant_item_types = []
    
    # Check the business type from the session to filter relevant items
    if business_type == 'Pharmacy':
        relevant_item_types = ['Pharmacy']
    elif business_type == 'Hardware':
        # The item_type for hardware is 'Hardware Material'
        relevant_item_types = ['Hardware Material']
<<<<<<< HEAD
    elif business_type == 'Supermarket':
        relevant_item_types = ['Supermarket', 'Provision Store']
    else:
        # Default to Pharmacy if business_type is not recognized or not yet set
        relevant_item_types = ['Pharmacy']

=======
    elif business_type == 'Supermarket': # Changed from 'in' to handle 'Supermarket' type specifically
        relevant_item_types = ['Supermarket'] # Add 'Supermarket' as relevant item type
    elif business_type == 'Provision Store': # Handle Provision Store separately if its items are distinct
        relevant_item_types = ['Provision Store']
    else:
        # Fallback or general type if none matches. Consider if a business can have diverse types.
        relevant_item_types = ['Pharmacy', 'Hardware Material', 'Supermarket', 'Provision Store'] # Include all if flexible
>>>>>>> 9823f2e49f8fad873f50c5a3321e708833d8c6cb

    search_query = request.args.get('search', '').strip()

    available_inventory_items_query = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        InventoryItem.is_active == True,
        InventoryItem.item_type.in_(relevant_item_types)
    )

    if search_query:
        available_inventory_items_query = available_inventory_items_query.filter(
            InventoryItem.product_name.ilike(f'%{search_query}%') |
            InventoryItem.category.ilike(f'%{search_query}%') |
            InventoryItem.batch_number.ilike(f'%{search_query}%')
        )
    
    available_inventory_items = available_inventory_items_query.all()
    
    serialized_inventory_items = []
    try:
        serialized_inventory_items = [serialize_inventory_item_api(item) for item in available_inventory_items]
    except Exception as e:
        print(f"ERROR: Exception during serialization of available_inventory_items: {e}")
        serialized_inventory_items = []

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
                'name': "Your Enterprise Name",
                'address': "Your Pharmacy Address",
                'location': "Your Pharmacy Location",
                'phone': "Your Pharmacy Contact",
                'email': 'info@example.com',
                'contact': "Your Pharmacy Contact"
            }

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

    sale_for_template_items = [] 
    customer_phone_for_template = ''
    sales_person_name_for_template = session.get('username', 'N/A') 
    print_ready = request.args.get('print_ready', 'false').lower() == 'true'
    last_transaction_details = session.pop('last_transaction_details', [])
    last_transaction_grand_total = session.pop('last_transaction_grand_total', 0.0)
    last_transaction_id = session.pop('last_transaction_id', '')
    last_transaction_customer_phone = session.pop('last_transaction_customer_phone', '')
    last_transaction_sales_person = session.pop('last_transaction_sales_person', '')
    last_transaction_date = session.pop('last_transaction_date', '')
    
    # Use session.get to prevent the value from being removed.
    auto_print = session.get('auto_print', False)
    if DB_TYPE == 'sqlite':
        auto_print = True

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
        
        sale_for_template_items = cart_items

        if not cart_items:
            flash('No items in the cart to record a sale.', 'danger')
            return render_template('add_edit_sale.html',
                                title='Add Sale Record',
                                inventory_items=serialized_inventory_items,
                                sale={'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items},
                                user_role=session.get('role'),
                                pharmacy_info=pharmacy_info,
                                print_ready=False,
                                current_year=datetime.now().year,
                                search_query=search_query,
                                business_type=business_type,
                                auto_print=auto_print)

        total_grand_amount = 0.0
        recorded_sale_details = []

        for item_data in cart_items:
            product_id = item_data['product_id']
            quantity_sold = item_data['quantity_sold']
            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
            if not product:
                flash(f'Product with ID {product_id} not found.', 'danger')
                return render_template('add_edit_sale.html',
                                        title='Add Sale Record',
                                        inventory_items=serialized_inventory_items,
                                        sale={'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items},
                                        user_role=session.get('role'),
                                        pharmacy_info=pharmacy_info,
                                        print_ready=False,
                                        current_year=datetime.now().year,
                                        search_query=search_query,
                                        business_type=business_type,
                                        auto_print=auto_print)

            quantity_for_stock_check = quantity_sold
            if item_data['sale_unit_type'] == 'pack':
                quantity_for_stock_check = quantity_sold * product.number_of_tabs

            if product.current_stock < quantity_for_stock_check:
                flash(f'Insufficient stock for {product.product_name}. Available: {product.current_stock:.2f} units. Tried to sell: {quantity_for_stock_check:.2f} units.', 'danger')
                return render_template('add_edit_sale.html',
                                        title='Add Sale Record',
                                        inventory_items=serialized_inventory_items,
                                        sale={'customer_phone': customer_phone_for_template, 'sales_person_name': sales_person_name_for_template, 'items': sale_for_template_items},
                                        user_role=session.get('role'),
                                        pharmacy_info=pharmacy_info,
                                        print_ready=False,
                                        current_year=datetime.now().year,
                                        search_query=search_query,
                                        business_type=business_type,
                                        auto_print=auto_print)

        transaction_id = str(uuid.uuid4())
        sale_date = datetime.now()
        for item_data in cart_items:
            product_id = item_data['product_id']
            quantity_sold = item_data['quantity_sold']
            sale_unit_type = item_data['sale_unit_type']
            price_at_time_per_unit_sold = item_data['price_at_time_per_unit_sold']
            item_total_amount = item_data['item_total_amount']

            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
            
            quantity_to_deduct = quantity_sold
            if sale_unit_type == 'pack':
                quantity_to_deduct = quantity_sold * product.number_of_tabs

            product.current_stock -= quantity_to_deduct
            product.last_updated = datetime.now()

            new_sale = SaleRecord(
                id=str(uuid.uuid4()),
                business_id=business_id,
                product_id=product.id,
                product_name=product.product_name,
                quantity_sold=quantity_sold,
                sale_unit_type=sale_unit_type,
                price_at_time_per_unit_sold=price_at_time_per_unit_sold,
                total_amount=item_total_amount,
                sale_date=sale_date,
                customer_phone=customer_phone_for_template,
                sales_person_name=sales_person_name_for_template,
                transaction_id=transaction_id,
                synced_to_remote=False
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
        session['auto_print'] = auto_print

        send_sms = 'send_sms_receipt' in request.form
        if send_sms and customer_phone_for_template:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            
            sms_message = (
                f"{business_name_for_sms} Sales Receipt:\n"
                f"Transaction ID: {transaction_id[:8].upper()}\n"
                f"Date: {sale_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Total Amount: GH₵{total_grand_amount:.2f}\n"
                f"Items: " + ", ".join([f"{item['product_name']} ({item['quantity_sold']} {item['sale_unit_type']})" for item in recorded_sale_details]) + "\n"
                f"Sales Person: {sales_person_name_for_template}\n\n"
                f"Thank you for your purchase!\n"
                f"From: {business_name_for_sms}"
            )
            
            if check_network_online():
                try:
                    sms_payload = {
                        'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': customer_phone_for_template,
                        'from': ARKESEL_SENDER_ID, 'sms': sms_message
                    }
                    sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
                    sms_response.raise_for_status()
                    sms_result = sms_response.json()

                    if sms_result.get('status') == 'success':
                        flash(f'SMS receipt sent to customer {customer_phone_for_template} successfully!', 'success')
                    else:
                        error_message = sms_result.get('message', 'Unknown error from SMS provider.')
                        flash(f'Failed to send SMS receipt to customer. Error: {error_message}', 'danger')
                except requests.exceptions.HTTPError as http_err:
                    flash(f'HTTP error sending SMS receipt: {http_err}. Please check API key or sender ID.', 'danger')
                except requests.exceptions.ConnectionError as conn_err:
                    flash(f'Network connection error sending SMS receipt: {conn_err}. Please check your internet connection.', 'danger')
                except requests.exceptions.Timeout as timeout_err:
                    flash(f'SMS request timed out: {timeout_err}. Please try again later.', 'danger')
                except requests.exceptions.RequestException as req_err:
                    flash(f'An unexpected error occurred while sending SMS receipt: {req_err}', 'danger')
                except json.JSONDecodeError:
                    flash('Failed to parse SMS provider response. The response might not be in JSON format.', 'danger')
            else:
                flash("SMS receipt not sent: You are offline.", 'warning')

        elif send_sms and not customer_phone_for_template:
            flash(f'SMS receipt not sent: No customer phone number provided.', 'warning')

        return redirect(url_for('add_sale', print_ready='true'))
    
    if print_ready:
        sale_for_template_items = []
    else:
        sale_for_template_items = [] 

    sale_final_context = {
        'sales_person_name': sales_person_name_for_template,
        'customer_phone': customer_phone_for_template,
        'items': sale_for_template_items
    }

    try:
        return render_template('add_edit_sale.html', 
                               title='Add Sale Record', 
                               inventory_items=serialized_inventory_items,
                               sale=sale_final_context,
                               user_role=session.get('role'),
                               pharmacy_info=pharmacy_info,
                               print_ready=print_ready,
                               auto_print=auto_print,
                               last_transaction_details=last_transaction_details,
                               last_transaction_grand_total=last_transaction_grand_total,
                               last_transaction_id=last_transaction_id,
                               last_transaction_customer_phone=last_transaction_customer_phone,
                               last_transaction_sales_person=last_transaction_sales_person,
                               last_transaction_date=last_transaction_date,
                               current_year=datetime.now().year,
                               search_query=search_query,
                               business_type=business_type)
    except Exception as e:
        print(f"ERROR: Exception caught during final render_template (GET): {e}")
        raise
@app.route('/sales/edit_transaction/<transaction_id>', methods=['GET', 'POST'])
def edit_sale_transaction(transaction_id): # Note the parameter name change
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to edit sales records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    # Fetch all sale records for this transaction ID
    sales_in_transaction_to_edit = SaleRecord.query.filter_by(
        transaction_id=transaction_id, # Use transaction_id here
        business_id=business_id
    ).all()

    if not sales_in_transaction_to_edit:
        flash('Sale transaction not found.', 'danger')
        return redirect(url_for('sales'))

    # Use the first sale record to get common transaction details like original date
    first_sale_record = sales_in_transaction_to_edit[0]
    
    business_type = get_current_business_type()
    # Determine which item types are relevant for the current business type
    relevant_item_types = []
    if business_type == 'Pharmacy':
        relevant_item_types = ['Pharmacy']
    elif business_type == 'Hardware':
        relevant_item_types = ['Hardware Material']
    elif business_type in ['Supermarket', 'Provision Store']:
        relevant_item_types = ['Provision Store']
    
    available_inventory_items = InventoryItem.query.filter(
        InventoryItem.business_id == business_id,
        InventoryItem.is_active == True,
        InventoryItem.item_type.in_(relevant_item_types)
    ).all()
    serialized_available_inventory_items = [serialize_inventory_item(item) for item in available_inventory_items]
    
    pharmacy_info = session.get('business_info', {})

    if request.method == 'POST':
        customer_phone = request.form.get('customer_phone', '').strip()
        sales_person_name = request.form.get('sales_person_name', '').strip()
        
        cart_items_json = request.form.get('cart_items_json')
        if not cart_items_json:
            flash('No items in the cart to update the sale.', 'danger')
            return redirect(url_for('edit_sale_transaction', transaction_id=transaction_id)) # Use new route name

        new_cart_items = json.loads(cart_items_json)

        # --- Revert old stock and prepare for new stock deduction ---
        for old_sale_record in sales_in_transaction_to_edit: # Iterate through the fetched records
            product = InventoryItem.query.filter_by(id=old_sale_record.product_id, business_id=business_id).first()
            if product:
                quantity_to_return = old_sale_record.quantity_sold
                if old_sale_record.sale_unit_type == 'pack':
                    # Need to fetch the product again to get number_of_tabs if not already available
                    original_product_for_tabs = InventoryItem.query.filter_by(id=old_sale_record.product_id, business_id=business_id).first()
                    if original_product_for_tabs:
                        quantity_to_return = old_sale_record.quantity_sold * original_product_for_tabs.number_of_tabs
                
                product.current_stock += quantity_to_return
                product.last_updated = datetime.now()
                db.session.add(product)
            db.session.delete(old_sale_record) # Mark old records for deletion

        # --- Validate and record new items ---
        total_grand_amount = 0.0
        recorded_sale_details = []

        # First pass: Validate stock for new cart items
        for item_data in new_cart_items:
            product_id = item_data['product_id']
            quantity_sold = float(item_data['quantity_sold'])
            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
            if not product:
                flash(f'Product with ID {product_id} not found for new cart items.', 'danger')
                db.session.rollback()
                return render_template('add_edit_sale.html',
                                       title='Edit Sale Record',
                                       inventory_items=serialized_available_inventory_items,
                                       sale={'customer_phone': customer_phone, 'sales_person_name': sales_person_name, 'items': new_cart_items},
                                       user_role=session.get('role'),
                                       pharmacy_info=pharmacy_info,
                                       print_ready=False,
                                       current_year=datetime.now().year)

            quantity_for_stock_check = quantity_sold
            if item_data['sale_unit_type'] == 'pack':
                quantity_for_stock_check = quantity_sold * product.number_of_tabs

            if product.current_stock < quantity_for_stock_check:
                flash(f'Insufficient stock for {product.product_name}. Available: {product.current_stock:.2f} units. Tried to sell: {quantity_for_stock_check:.2f} units.', 'danger')
                db.session.rollback()
                return render_template('add_edit_sale.html',
                                       title='Edit Sale Record',
                                       inventory_items=serialized_available_inventory_items,
                                       sale={'customer_phone': customer_phone, 'sales_person_name': sales_person_name, 'items': new_cart_items},
                                       user_role=session.get('role'),
                                       pharmacy_info=pharmacy_info,
                                       print_ready=False,
                                       current_year=datetime.now().year)

        # Second pass: Record new sales and deduct stock
        for item_data in new_cart_items:
            product_id = item_data['product_id']
            quantity_sold = float(item_data['quantity_sold'])
            sale_unit_type = item_data['sale_unit_type']
            price_at_time_per_unit_sold = float(item_data['price_at_time_per_unit_sold'])
            item_total_amount = float(item_data['item_total_amount'])

            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
            
            quantity_to_deduct = quantity_sold
            if sale_unit_type == 'pack':
                quantity_to_deduct = quantity_sold * product.number_of_tabs

            product.current_stock -= quantity_to_deduct
            product.last_updated = datetime.now()

            new_sale_record = SaleRecord( # Renamed variable to avoid conflict
                business_id=business_id,
                product_id=product.id,
                product_name=product.product_name,
                quantity_sold=quantity_sold,
                sale_unit_type=sale_unit_type,
                price_at_time_per_unit_sold=price_at_time_per_unit_sold,
                total_amount=item_total_amount,
                sale_date=first_sale_record.sale_date, # Keep original sale date for the transaction
                customer_phone=customer_phone,
                sales_person_name=sales_person_name,
                transaction_id=transaction_id # Use the original transaction ID
            )
            db.session.add(new_sale_record) # Use new variable
            total_grand_amount += item_total_amount
            recorded_sale_details.append({
                'product_name': product.product_name,
                'quantity_sold': quantity_sold,
                'sale_unit_type': sale_unit_type,
                'price_at_time_per_unit_sold': price_at_time_per_unit_sold,
                'total_amount': item_total_amount
            })

        db.session.commit()
        flash(f'Sale transaction {transaction_id[:8].upper()} updated successfully!', 'success')
        return redirect(url_for('sales'))

    # --- GET Request / Initial Render ---
    items_for_cart = []
    for sale_record in sales_in_transaction_to_edit:
        items_for_cart.append({
            'product_id': sale_record.product_id,
            'product_name': sale_record.product_name,
            'quantity_sold': sale_record.quantity_sold,
            'sale_unit_type': sale_record.sale_unit_type,
            'price_at_time_per_unit_sold': sale_record.price_at_time_per_unit_sold,
            'total_amount': sale_record.total_amount
        })

    sale_data_for_form = {
        'customer_phone': first_sale_record.customer_phone,
        'sales_person_name': first_sale_record.sales_person_name,
        'items': items_for_cart
    }

    return render_template('add_edit_sale.html', 
                           title=f'Edit Sale Transaction: {transaction_id[:8].upper()}', 
                           sale=sale_data_for_form, 
                           inventory_items=serialized_available_inventory_items,
                           user_role=session.get('role'),
                           pharmacy_info=pharmacy_info,
                           print_ready=False,
                           last_transaction_details=[],
                           last_transaction_grand_total=0.0,
                           last_transaction_id='',
                           last_transaction_customer_phone='',
                           last_transaction_sales_person='',
                           last_transaction_date='',
                           current_year=datetime.now().year)


@app.route('/sales/delete_transaction/<transaction_id>')
def delete_sale_transaction(transaction_id): # Note the parameter name change
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to delete sales records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    business_id = get_current_business_id()
    # Fetch all sale records for this transaction ID
    sales_to_delete = SaleRecord.query.filter_by(
        transaction_id=transaction_id, # Use transaction_id here
        business_id=business_id
    ).all()

    if not sales_to_delete:
        flash('Sale transaction not found.', 'danger')
        return redirect(url_for('sales'))
    
    transaction_id_for_flash = sales_to_delete[0].transaction_id # Get ID for flash message

    # Return stock to inventory for all items in the transaction
    for sale_record in sales_to_delete:
        product = InventoryItem.query.filter_by(id=sale_record.product_id, business_id=business_id).first()
        if product:
            quantity_to_return = sale_record.quantity_sold
            if sale_record.sale_unit_type == 'pack':
                # Need to fetch the product again to get number_of_tabs if not already available
                original_product_for_tabs = InventoryItem.query.filter_by(id=sale_record.product_id, business_id=business_id).first()
                if original_product_for_tabs:
                    quantity_to_return = sale_record.quantity_sold * original_product_for_tabs.number_of_tabs
            
            product.current_stock += quantity_to_return
            product.last_updated = datetime.now()
            db.session.add(product)
        db.session.delete(sale_record) # Delete the individual sale record

    db.session.commit()
    flash(f'Sale transaction {transaction_id_for_flash[:8].upper()} and all its items deleted successfully! Stock returned to inventory.', 'success')
    return redirect(url_for('sales'))

@app.route('/sales/print_receipt/<transaction_id>')
@login_required
def print_sale_receipt(transaction_id):
    # ACCESS CONTROL: Allows admin, sales, and viewer roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to view sales receipts or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    # Fetch all sale records for this specific transaction ID
    sales_in_transaction = SaleRecord.query.filter_by(
        transaction_id=transaction_id,
        business_id=business_id
    ).order_by(SaleRecord.sale_date.asc()).all()

    if not sales_in_transaction:
        flash('Sale transaction not found.', 'danger')
        return redirect(url_for('sales'))

    # Reconstruct the transaction details for the receipt
    first_sale = sales_in_transaction[0] # Use first item for common transaction details
    
    # Prepare items for the receipt
    receipt_items = []
    total_grand_amount = 0.0
    today = date.today()

    for sale_record in sales_in_transaction:
        product_item = InventoryItem.query.filter_by(id=sale_record.product_id, business_id=business_id).first()
        
        sale_item_expires_soon = False
        sale_item_expiry_date = None
        if product_item and product_item.expiry_date:
            sale_item_expiry_date = product_item.expiry_date
            time_to_expiry = product_item.expiry_date - today
            if time_to_expiry.days <= 180 and time_to_expiry.days >= 0:
                sale_item_expires_soon = True
            elif time_to_expiry.days < 0:
                sale_item_expires_soon = 'Expired'

        receipt_items.append({
            'product_name': sale_record.product_name,
            'quantity_sold': sale_record.quantity_sold,
            'sale_unit_type': sale_record.sale_unit_type,
            'price_at_time_per_unit_sold': sale_record.price_at_time_per_unit_sold,
            'total_amount': sale_record.total_amount,
            'expiry_date': sale_item_expiry_date,
            'expires_soon': sale_item_expires_soon
        })
        total_grand_amount += sale_record.total_amount

    last_transaction_details = receipt_items
    last_transaction_grand_total = total_grand_amount
    last_transaction_id = transaction_id
    last_transaction_customer_phone = first_sale.customer_phone
    last_transaction_sales_person = first_sale.sales_person_name
    last_transaction_date = first_sale.sale_date.strftime('%Y-%m-%d %H:%M:%S')

    # Get business info for receipts (reusing from session)
    pharmacy_info = session.get('business_info', {
        "name": ENTERPRISE_NAME,
        "location": PHARMACY_LOCATION,
        "address": PHARMACY_ADDRESS,
        "contact": PHARMACY_CONTACT
    })

    return render_template('add_edit_sale.html',
                           title='Sale Receipt',
                           inventory_items=[], # Not needed for receipt view
                           sale={}, # Not needed for receipt view
                           user_role=session.get('role'),
                           pharmacy_info=pharmacy_info,
                           print_ready=True, # This flag will trigger receipt display
                           last_transaction_details=last_transaction_details,
                           last_transaction_grand_total=last_transaction_grand_total,
                           last_transaction_id=last_transaction_id,
                           last_transaction_customer_phone=last_transaction_customer_phone,
                           last_transaction_sales_person=last_transaction_sales_person,
                           last_transaction_date=last_transaction_date,
                           current_year=datetime.now().year)

# NEW: Add a route for returns. For now, it just redirects to sales list.
@app.route('/sales/add_return', methods=['GET', 'POST'])
@login_required
@permission_required(['admin', 'sales']) # Adjust permissions as needed
def add_return():
    flash('This is the Add Return page. Functionality to be implemented.', 'info')
    # You would typically render a new template here for return forms:
    # return render_template('add_edit_return.html', title='Add Return')
    # For now, redirect to sales list.
    return redirect(url_for('sales'))
# --- Reports Route ---

@app.route('/reports')
def reports():
    # ACCESS CONTROL: Allows admin, sales, and viewer roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to view reports or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    business_type = get_current_business_type()

    # Overall Business Metrics
    total_purchase_value = db.session.query(db.func.sum(InventoryItem.purchase_price * InventoryItem.current_stock)).filter(
        InventoryItem.business_id == business_id, InventoryItem.is_active == True
    ).scalar() or 0.0

    total_potential_sale_value = db.session.query(db.func.sum(InventoryItem.sale_price * InventoryItem.current_stock)).filter(
        InventoryItem.business_id == business_id, InventoryItem.is_active == True
    ).scalar() or 0.0
    
    total_potential_gross_profit = total_potential_sale_value - total_purchase_value
    overall_stock_profit_margin = (total_potential_gross_profit / total_potential_sale_value) * 100 if total_potential_sale_value > 0 else 0.0

    total_actual_sales_revenue = db.session.query(db.func.sum(SaleRecord.total_amount)).filter(
        SaleRecord.business_id == business_id
    ).scalar() or 0.0

    # Sales by Sales Person (Last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    sales_by_person = db.session.query(
        SaleRecord.sales_person_name,
        db.func.sum(SaleRecord.total_amount)
    ).filter(
        SaleRecord.business_id == business_id,
        SaleRecord.sale_date >= thirty_days_ago
    ).group_by(SaleRecord.sales_person_name).order_by(db.func.sum(SaleRecord.total_amount).desc()).all()

    # Inventory Stock Summary (all active items)
    inventory_summary = InventoryItem.query.filter_by(business_id=business_id, is_active=True).order_by(InventoryItem.product_name).all()

    # Pharmacy specific reports
    expired_items = []
    expiring_soon_items = []
    if business_type == 'Pharmacy':
        today = date.today()
        three_months_from_now = today + timedelta(days=90)
        
        expired_items = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.is_active == True,
            InventoryItem.expiry_date != None,
            InventoryItem.expiry_date < today
        ).order_by(InventoryItem.expiry_date).all()

        expiring_soon_items = InventoryItem.query.filter(
            InventoryItem.business_id == business_id,
            InventoryItem.is_active == True,
            InventoryItem.expiry_date != None,
            InventoryItem.expiry_date >= today,
            InventoryItem.expiry_date <= three_months_from_now
        ).order_by(InventoryItem.expiry_date).all()

    # Hardware specific reports
    company_balances = []
    rental_records = [] # Initialize for all business types
    if business_type == 'Hardware':
        company_balances = Company.query.filter_by(business_id=business_id).all()
        # Also include Rental Records for hardware reports
        rental_records = RentalRecord.query.filter_by(business_id=business_id).order_by(RentalRecord.date_recorded.desc()).all()


    return render_template('reports.html',
                           user_role=session.get('role'),
                           total_purchase_value=total_purchase_value,
                           total_potential_sale_value=total_potential_sale_value,
                           total_potential_gross_profit=total_potential_gross_profit,
                           overall_stock_profit_margin=overall_stock_profit_margin,
                           total_actual_sales_revenue=total_actual_sales_revenue,
                           sales_by_person=sales_by_person,
                           inventory_summary=inventory_summary,
                           business_type=business_type,
                           expired_items=expired_items,
                           expiring_soon_items=expiring_soon_items,
                           company_balances=company_balances,
                           rental_records=rental_records,
                           total_cost_of_stock=total_purchase_value, # Passed as total_cost_of_stock
                           total_sale_value_of_stock=total_potential_sale_value, # Passed as total_sale_value_of_stock
                           total_sales_amount=total_actual_sales_revenue,
                           current_year=datetime.now().year)

@app.route('/send_daily_sales_sms_report')
def send_daily_sales_sms_report():
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to send daily sales reports or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    today = date.today()
    
    today_sales = SaleRecord.query.filter_by(business_id=business_id).filter(
        db.func.date(SaleRecord.sale_date) == today
    ).all()

    total_sales_amount = sum(s.total_amount for s in today_sales)
    total_items_sold = sum(s.quantity_sold for s in today_sales) # This is approximate as it sums different units

    product_sales_summary = {}
    for sale in today_sales:
        product_name = sale.product_name
        quantity = sale.quantity_sold
        unit_type = sale.sale_unit_type
        key = f"{product_name} ({unit_type})"
        product_sales_summary[key] = product_sales_summary.get(key, 0.0) + quantity

    business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
    message = f"Daily Sales Report ({today.strftime('%Y-%m-%d')}):\n"
    message += f"Total Revenue: GH₵{total_sales_amount:.2f}\n"
    message += f"Total Items Sold (approx): {total_items_sold:.2f}\n"
    
    if product_sales_summary:
        message += "Product Breakdown:\n"
        for product_key, qty in product_sales_summary.items():
            message += f"- {product_key}: {qty:.2f} units\n"
    else:
        message += "No sales recorded today."
    
    message += f"\nThank you for trading with us\n"
    message += f"From: {business_name_for_sms}"

    if not ADMIN_PHONE_NUMBER:
        flash('Admin phone number is not configured for SMS reports.', 'danger')
        return redirect(url_for('reports'))

    sms_payload = {
        'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': ADMIN_PHONE_NUMBER,
        'from': ARKESEL_SENDER_ID, 'sms': message
    }
    
    try:
        sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
        sms_result = sms_response.json()
        if sms_result.get('status') == 'success':
            flash('Daily sales report SMS sent to admin successfully!', 'success')
        else:
            print(f"Arkesel SMS Error: {sms_result.get('message', 'Unknown error')}")
            flash(f'Failed to send daily sales report SMS. Error: {sms_result.get("message", "Unknown error")}', 'danger')
    except requests.exceptions.RequestException as e:
        print(f'Network error sending SMS: {e}')
        flash(f'Network error when trying to send daily sales report SMS: {e}', 'danger')
    
    return redirect(url_for('reports'))

# --- New Hardware Business Routes ---

@app.route('/companies')
# @login_required # Uncomment this if you have a login_required decorator
def companies():
    # ACCESS CONTROL: Allows admin, sales, and viewer roles
    if 'username' not in session or session.get('role') not in ['admin', 'viewer', 'sales'] or not get_current_business_id():
        flash('You do not have permission to manage companies or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    search_query = request.args.get('search', '').strip()

    companies_query = Company.query.filter_by(business_id=business_id)

    if search_query:
        companies_query = companies_query.filter(
            Company.name.ilike(f'%{search_query}%') |
            Company.contact_person.ilike(f'%{search_query}%') |
            Company.phone.ilike(f'%{search_query}%') |
            Company.email.ilike(f'%{search_query}%') |
            Company.address.ilike(f'%{search_query}%')
        )

    companies = companies_query.all()

    processed_companies = []
    total_creditors_sum = 0.0 # Initialize sum for creditors
    total_debtors_sum = 0.0   # Initialize sum for debtors

    for company in companies:
        # Ensure company.balance is a float, defaulting to 0.0 if None
        company_balance = float(company.balance) if company.balance is not None else 0.0
        
        # Calculate total_creditors and total_debtors for each company based on balance
        # A company is a creditor if its balance is negative (we owe them)
        # A company is a debtor if its balance is positive (they owe us)
        if company_balance < 0:
            company.display_creditors = abs(company_balance) # Store as positive for display
            company.display_debtors = 0.0
            total_creditors_sum += abs(company_balance)
        elif company_balance > 0:
            company.display_creditors = 0.0
            company.display_debtors = company_balance
            total_debtors_sum += company_balance
        else:
            company.display_creditors = 0.0
            company.display_debtors = 0.0

        processed_companies.append(company)

    return render_template('company_list.html', 
                           companies=processed_companies, 
                           user_role=session.get('role'), 
                           search_query=search_query, 
                           current_year=datetime.now().year,
                           total_creditors_sum=total_creditors_sum, # Pass the sum of creditors
                           total_debtors_sum=total_debtors_sum)     # Pass the sum of debtors



@app.route('/companies/add', methods=['GET', 'POST'])
def add_company():
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to add companies or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    if request.method == 'POST':
        name = request.form['name'].strip()
        contact_person = request.form['contact_person'].strip()
        phone = request.form['phone'].strip()
        email = request.form['email'].strip()
        address = request.form['address'].strip()
        
        # Check if company with this name already exists for this business
        if Company.query.filter_by(name=name, business_id=business_id).first():
            flash('Company with this name already exists for this business.', 'danger')
            # Pass the form data back to pre-fill the form fields on error
            form_data = request.form.to_dict()
            # For display purposes on error, you can still pass these as 0.0
            # They are NOT being passed to the Company constructor here.
            form_data['total_creditors_amount'] = 0.0 # Use the property name for consistency
            form_data['total_debtors_amount'] = 0.0   # Use the property name for consistency
            return render_template('add_edit_company.html', title='Add New Company', company=form_data, current_year=datetime.now().year)

        new_company = Company(
            business_id=business_id,
            name=name,
            contact_person=contact_person,
            phone=phone,
            email=email,
            address=address,
            balance=0.0            # New company starts with 0 balance
            # IMPORTANT: REMOVE total_creditors and total_debtors here.
            # They are calculated properties, not direct columns.
            # total_creditors=0.0,
            # total_debtors=0.0
        )
        db.session.add(new_company)
        db.session.commit()

        # After the company is created, you might want to initialize Creditor/Debtor records
        # for it with a 0 balance, though they will be created on first transaction anyway.
        # This is optional, as the current transaction logic handles creation if not exists.
        # new_creditor_record = Creditor(business_id=business_id, company_id=new_company.id, balance=0.0)
        # new_debtor_record = Debtor(business_id=business_id, company_id=new_company.id, balance=0.0)
        # db.session.add(new_creditor_record)
        # db.session.add(new_debtor_record)
        # db.session.commit() # Commit again if you add these here

        flash(f'Company "{name}" added successfully!', 'success')
        return redirect(url_for('companies'))

    # For GET request, display an empty form for adding
    # Initialize company dictionary with default values for a new company
    empty_company = {
        'name': '', 'contact_person': '', 'phone': '', 'email': '', 'address': '',
        'balance': 0.0, # This is the actual column
        'total_creditors_amount': 0.0, # For display in template, matching property name
        'total_debtors_amount': 0.0    # For display in template, matching property name
    }
    return render_template('add_edit_company.html', title='Add New Company', company=empty_company, current_year=datetime.now().year)

# The filter_company_transactions function is fine as is, no changes needed for this error.
def filter_company_transactions(company_id, search_query, start_date_str, end_date_str):
    transactions_query = CompanyTransaction.query.filter_by(company_id=company_id)

    if search_query:
        transactions_query = transactions_query.filter(
            CompanyTransaction.description.ilike(f'%{search_query}%') |
            CompanyTransaction.type.ilike(f'%{search_query}%') |
            CompanyTransaction.recorded_by.ilike(f'%{search_query}%')
        )

    if start_date_str:
        try:
            start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            transactions_query = transactions_query.filter(cast(CompanyTransaction.date, db.Date) >= start_date_obj)
        except ValueError:
            flash('Invalid start date format. Please use YYYY-MM-DD.', 'danger')
    
    if end_date_str:
        try:
            end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            transactions_query = transactions_query.filter(cast(CompanyTransaction.date, db.Date) <= end_date_obj)
        except ValueError:
            flash('Invalid end date format. Please use YYYY-MM-DD.', 'danger')

    return transactions_query.order_by(CompanyTransaction.date.desc()).all()


@app.route('/companies/edit/<company_id>', methods=['GET', 'POST'])
def edit_company(company_id):
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to edit companies or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    company_to_edit = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

    # --- THIS IS THE CRITICAL CORRECTION: CALCULATE BALANCES BEFORE RENDERING ---
    # This ensures that total_creditors and total_debtors are always up-to-date
    # based on transactions, not user input.
    balance_details = calculate_company_balance_details(company_id)
    company_to_edit.balance = balance_details['balance']
    company_to_edit.total_creditors = balance_details['total_creditors']
    company_to_edit.total_debtors = balance_details['total_debtors']
    # Note: These calculated values are updated on the Python object for display,
    # but are NOT committed to the database here. They should only be updated
    # in the database when transactions are added, edited, or deleted.

    if request.method == 'POST':
        name = request.form['name'].strip()
        contact_person = request.form['contact_person'].strip()
        phone = request.form['phone'].strip()
        email = request.form['email'].strip()
        address = request.form['address'].strip()
        
        # IMPORTANT: Do NOT retrieve total_creditors and total_debtors from request.form here.
        # They are calculated fields and should not be modified by this form submission.

        # Check for duplicate name (excluding the current company being edited)
        if Company.query.filter(Company.name == name, Company.business_id == business_id, Company.id != company_id).first():
            flash('Company with this name already exists for this business.', 'danger')
            # Pass the form data back, ensuring the calculated balance details are preserved
            form_data = request.form.to_dict()
            form_data['total_creditors'] = company_to_edit.total_creditors # Use the already calculated values
            form_data['total_debtors'] = company_to_edit.total_debtors   # Use the already calculated values
            return render_template('add_edit_company.html', title='Edit Company', company=form_data, current_year=datetime.now().year)

        company_to_edit.name = name
        company_to_edit.contact_person = contact_person
        company_to_edit.phone = phone
        company_to_edit.email = email
        company_to_edit.address = address

        db.session.commit() # Commit changes to the company's static details
        flash(f'Company "{name}" updated successfully!', 'success')
        return redirect(url_for('companies'))

    return render_template('add_edit_company.html', title='Edit Company', company=company_to_edit, current_year=datetime.now().year)
@app.route('/companies/delete/<company_id>')
def delete_company(company_id):
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to delete companies or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    company_to_delete = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

    if company_to_delete.balance != 0:
        flash('Cannot delete company with outstanding balance. Please settle balance first.', 'danger')
        return redirect(url_for('companies'))

    db.session.delete(company_to_delete)
    db.session.commit()
    flash(f'Company "{company_to_delete.name}" deleted successfully!', 'success')
    return redirect(url_for('companies'))

@app.route('/company/<string:company_id>/transactions', methods=['GET', 'POST'])
@login_required
def company_transaction(company_id):
    """
    Handles company transactions, including recording new transactions,
    updating company balance, sending SMS receipts, and displaying
    a list of transactions with filtering capabilities.
    """
    business_id = get_current_business_id()
    company = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

    business_info = session.get('business_info', {})
    if not business_info or not business_info.get('name'):
        business_details = Business.query.filter_by(id=business_id).first()
        if business_details:
            business_info = {
                'name': business_details.name,
                'address': business_details.address,
                'location': business_details.location,
                'phone': business_details.contact,
                'email': business_details.email if hasattr(business_details, 'email') else 'N/A'
            }
        else:
            business_info = {
                'name': "Your Enterprise Name", # Replace with actual constant
                'address': "Your Pharmacy Address", # Replace with actual constant
                'location': "Your Pharmacy Location", # Replace with actual constant
                'phone': "Your Pharmacy Contact", # Replace with actual constant
                'email': 'info@example.com' # Default email
            }

    last_company_transaction_id = None
    last_company_transaction_details = None
    # print_ready is no longer passed to this template, it's for the dedicated print route

    transactions = [] # Initialize here to ensure it's always defined

    if request.method == 'POST':
        transaction_type = request.form['type']
        amount = float(request.form['amount'])
        description = request.form.get('description')
        send_sms_receipt = 'send_sms_receipt' in request.form
        recorded_by = session['username']

        new_transaction = CompanyTransaction(
            business_id=business_id,
            company_id=company.id,
            type=transaction_type,
            amount=amount,
            description=description,
            recorded_by=recorded_by
        )
        db.session.add(new_transaction)

        if transaction_type == 'Debit':
            company.balance += amount
            debtor_record = Debtor.query.filter_by(company_id=company.id, business_id=business_id).first()
            if not debtor_record:
                debtor_record = Debtor(company_id=company.id, business_id=business_id, balance=0.0)
                db.session.add(debtor_record)
            debtor_record.balance += amount
        elif transaction_type == 'Credit':
            company.balance -= amount
            creditor_record = Creditor.query.filter_by(company_id=company.id, business_id=business_id).first()
            if not creditor_record:
                creditor_record = Creditor(company_id=company.id, business_id=business_id, balance=0.0)
                db.session.add(creditor_record)
            creditor_record.balance += amount
            
        db.session.add(company)
        db.session.commit()

        flash(f'Transaction recorded successfully! Company balance updated to GH₵{company.balance:.2f}', 'success')

        last_company_transaction_details = {
            'id': new_transaction.id,
            'transaction_type': new_transaction.type,
            'amount': new_transaction.amount,
            'description': new_transaction.description,
            'date': new_transaction.date.strftime('%Y-%m-%d %H:%M:%S'),
            'recorded_by': new_transaction.recorded_by,
            'company_name': company.name,
            'company_id': company.id,
            'new_balance': company.balance
        }
        session['last_company_transaction_id'] = new_transaction.id
        session['last_company_transaction_details'] = last_company_transaction_details

        if send_sms_receipt and company.phone:
            message = (f"Dear {company.name}, a {new_transaction.type} transaction of GH₵{new_transaction.amount:.2f} "
                       f"was recorded by {business_info.get('name', 'Your Business')}. Your new balance is GH₵{company.balance:.2f}. "
                       f"Description: {new_transaction.description or 'N/A'}")
            # Assuming send_sms function exists
            # sms_success, sms_msg = send_sms(company.phone, message)
            # if sms_success:
            #     flash(f'SMS receipt sent to {company.phone}.', 'info')
            # else:
            #     flash(f'Failed to send SMS receipt: {sms_msg}', 'warning')
        elif send_sms_receipt and not company.phone:
            flash('Cannot send SMS receipt: Company contact number not available.', 'warning')

        # Redirect to the main page, not the print page directly after POST
        # The print_last_company_transaction_receipt route is for printing after redirect
        return redirect(url_for('company_transaction', company_id=company.id))


    # --- Logic for GET request and initial page load ---
    # Base query for transactions
    transactions_query = CompanyTransaction.query.filter_by(
        company_id=company.id,
        business_id=business_id
    )

    search_query = request.args.get('search', '').strip()
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if search_query:
        transactions_query = transactions_query.filter(
            (CompanyTransaction.description.ilike(f'%{search_query}%')) |
            (CompanyTransaction.type.ilike(f'%{search_query}%')) |
            (CompanyTransaction.recorded_by.ilike(f'%{search_query}%'))
        )

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            transactions_query = transactions_query.filter(CompanyTransaction.date >= start_date)
        except ValueError:
            flash('Invalid start date format.', 'danger')
            pass

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            transactions_query = transactions_query.filter(CompanyTransaction.date < (end_date + timedelta(days=1)))
        except ValueError:
            flash('Invalid end date format.', 'danger')
            pass

    transactions = transactions_query.order_by(CompanyTransaction.date.desc()).all()

    # --- NEW: Calculate total transactions amount for display on the main page ---
    total_transactions_sum = sum(t.amount for t in transactions)
    # --- END NEW ---

    return render_template('company_transaction.html',
                           company=company,
                           transactions=transactions,
                           search_query=search_query,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           business_info=business_info,
                           # last_company_transaction_id and last_company_transaction_details
                           # are only for the dedicated print route now.
                           # print_ready is also no longer passed to this template.
                           total_transactions_sum=total_transactions_sum, # NEW: Pass the calculated sum
                           current_year=datetime.now().year
                           )

@app.route('/company/print_last_receipt')
@login_required
def print_last_company_transaction_receipt():
    """
    Renders a dedicated, minimal page for printing the last recorded company transaction receipt.
    This page is designed to be immediately printed.
    """
    business_id = get_current_business_id()

    # Retrieve last transaction details from session
    last_company_transaction_details = session.pop('last_company_transaction_details', None)
    last_company_transaction_id = session.pop('last_company_transaction_id', None)

    if not last_company_transaction_details:
        flash('No recent transaction details found for printing.', 'warning')
        return redirect(url_for('companies')) # Redirect to companies list or dashboard

    # Fetch the company and business info needed for the receipt
    company = Company.query.filter_by(id=last_company_transaction_details['company_id'], business_id=business_id).first()
    if not company: # Fallback if company not found (shouldn't happen if transaction exists)
        flash('Company not found for the last transaction.', 'danger')
        return redirect(url_for('companies'))

    business_info = session.get('business_info', {})
    if not business_info or not business_info.get('name'):
        business_details = Business.query.filter_by(id=business_id).first()
        if business_details:
            business_info = {
                'name': business_details.name,
                'address': business_details.address,
                'location': business_details.location,
                'phone': business_details.contact,
                'email': business_details.email if hasattr(business_details, 'email') else 'N/A'
            }
        else:
            business_info = {
                'name': "Your Enterprise Name", # Replace with actual constant
                'address': "Your Pharmacy Address", # Replace with actual constant
                'location': "Your Pharmacy Location", # Replace with actual constant
                'phone': "Your Pharmacy Contact", # Replace with actual constant
                'email': 'info@example.com' # Default email
            }

    current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return render_template('company_last_receipt_print.html',
                           transaction_details=last_company_transaction_details,
                           company=company,
                           business_info=business_info,
                           current_date=current_date)

# NEW ROUTE: Send SMS for a specific Company Transaction
@app.route('/companies/transaction/send_sms/<string:transaction_id>')
@login_required
def send_company_transaction_sms(transaction_id):
    # ACCESS CONTROL: Allows admin, sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to send SMS receipts or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    transaction = CompanyTransaction.query.filter_by(id=transaction_id, business_id=business_id).first_or_404()
    company = Company.query.filter_by(id=transaction.company_id, business_id=business_id).first_or_404()

    if not company.phone:
        flash(f'SMS receipt not sent: No phone number configured for company {company.name}.', 'warning')
        return redirect(url_for('company_transaction', company_id=company.id))

    business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
    current_balance_str = f"GH₵{company.balance:.2f}" if company.balance >= 0 else f"-GH₵{abs(company.balance):.2f}"
    
    sms_message = (
        f"{business_name_for_sms} Transaction Alert for {company.name}:\n"
        f"Type: {transaction.type}\n"
        f"Amount: GH₵{transaction.amount:.2f}\n"
        f"New Balance: {current_balance_str}\n"
        f"Date: {transaction.date.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Description: {transaction.description if transaction.description else 'N/A'}\n"
        f"Recorded By: {transaction.recorded_by}\n\n"
        f"Thank you for your business!\n"
        f"From: {business_name_for_sms}"
    )
    
    sms_payload = {
        'action': 'send-sms',
        'api_key': ARKESEL_API_KEY,
        'to': company.phone,
        'from': ARKESEL_SENDER_ID,
        'sms': sms_message
    }
    
    try:
        sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
        sms_response.raise_for_status()
        sms_result = sms_response.json()

        if sms_result.get('status') == 'success':
            flash(f'SMS receipt sent to {company.name} successfully!', 'success')
        else:
            error_message = sms_result.get('message', 'Unknown error from SMS provider.')
            flash(f'Failed to send SMS receipt to {company.name}. Error: {error_message}', 'danger')
    except requests.exceptions.RequestException as e:
        flash(f'Network error sending SMS receipt: {e}', 'danger')
    except json.JSONDecodeError:
        flash('Failed to parse SMS provider response. The response might not be in JSON format.', 'danger')
        
    return redirect(url_for('company_transaction', company_id=company.id))
@app.route('/print_company_receipt/<string:transaction_id>')
@login_required
def print_company_receipt(transaction_id):
    """
    Renders a printable receipt for a specific company transaction.
    """
    business_id = get_current_business_id()

    transaction = CompanyTransaction.query.filter_by(id=transaction_id, business_id=business_id).first_or_404()
    company = Company.query.filter_by(id=transaction.company_id, business_id=business_id).first_or_404()

    # Fetch business info for the receipt header/footer
    business_info = session.get('business_info', {})
    
    if not business_info or not business_info.get('name'):
        business_details = Business.query.filter_by(id=business_id).first()
        if business_details:
            business_info = {
                'name': business_details.name,
                'address': business_details.address,
                'location': business_details.location,
                'phone': business_details.contact,
                'email': business_details.email if hasattr(business_details, 'email') else 'N/A'
            }
        else:
            business_info = {
                'name': "Your Enterprise Name", # Replace with actual constant
                'address': "Your Pharmacy Address", # Replace with actual constant
                'location': "Your Pharmacy Location", # Replace with actual constant
                'phone': "Your Pharmacy Contact", # Replace with actual constant
                'email': 'info@example.com' # Default email
            }

    current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Now access the properties directly from the company object
    # No need for separate db.session.query for total_creditor_amount/total_debtor_amount here
    # as they are calculated via @property on the Company model.

    return render_template('company_receipt_template.html',
                           transaction=transaction,
                           company=company,
                           business_info=business_info,
                           current_date=current_date,
                           total_creditor_amount=company.total_creditors_amount, # Use the property
                           total_debtor_amount=company.total_debtors_amount # Use the property
                           )

@app.route('/print_all_company_transactions/<string:company_id>')
@login_required
def print_all_company_transactions(company_id):
    """
    Renders a printable list of all transactions for a specific company,
    with optional filtering by search query, start date, and end date.
    """
    business_id = get_current_business_id()

    # Fetch the company details
    company = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

    # Get filter parameters from the request query string
    search_query = request.args.get('search', '').strip()
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Build the base query for company transactions
    transactions_query = CompanyTransaction.query.filter_by(
        company_id=company.id,
        business_id=business_id
    )

    # Apply search filter if provided
    if search_query:
        transactions_query = transactions_query.filter(
            (CompanyTransaction.description.ilike(f'%{search_query}%')) |
            (CompanyTransaction.type.ilike(f'%{search_query}%'))
        )

    # Apply date filters if provided
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            transactions_query = transactions_query.filter(CompanyTransaction.date >= start_date)
        except ValueError:
            flash('Invalid start date format. Please use YYYY-MM-DD.', 'danger')
            pass

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            transactions_query = transactions_query.filter(CompanyTransaction.date < (end_date + timedelta(days=1)))
        except ValueError:
            flash('Invalid end date format. Please use YYYY-MM-DD.', 'danger')
            pass

    # Order transactions by date, newest first
    transactions = transactions_query.order_by(CompanyTransaction.date.desc()).all()

    # --- FIX START: Calculate total transactions amount here ---
    total_transactions_sum = sum(t.amount for t in transactions)
    # --- FIX END ---

    # Fetch business info for the receipt header/footer
    business_info = session.get('business_info', {})
    if not business_info or not business_info.get('name'):
        business_details = Business.query.filter_by(id=business_id).first()
        if business_details:
            business_info = {
                'name': business_details.name,
                'address': business_details.address,
                'location': business_details.location,
                'phone': business_details.contact,
                'email': business_details.email if hasattr(business_details, 'email') else 'N/A'
            }
        else:
            business_info = {
                'name': "Your Enterprise Name", # Replace with actual constant
                'address': "Your Pharmacy Address", # Replace with actual constant
                'location': "Your Pharmacy Location", # Replace with actual constant
                'phone': "Your Pharmacy Contact", # Replace with actual constant
                'email': 'info@example.com' # Default email
            }

    current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return render_template('company_transaction.html',
                           company=company,
                           transactions=transactions,
                           business_info=business_info,
                           current_date=current_date,
                           search_query=search_query,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           total_transactions_sum=total_transactions_sum # NEW: Pass the calculated sum
                           )


@app.route('/future_orders')
def future_orders():
    # ACCESS CONTROL: Allows admin, sales, and viewer roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to view future orders or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    orders = FutureOrder.query.filter_by(business_id=business_id).order_by(FutureOrder.date_ordered.desc()).all()
    return render_template('future_order_list.html', orders=orders, user_role=session.get('role'), current_year=datetime.now().year)


@app.route('/future_orders/add', methods=['GET', 'POST'])
def add_future_order():
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to add future orders or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    # Only show hardware items for future orders
    available_inventory_items = InventoryItem.query.filter_by(business_id=business_id, is_active=True, item_type='Hardware Material').all()
    serialized_inventory_items = [serialize_inventory_item(item) for item in available_inventory_items]


    if request.method == 'POST':
        customer_name = request.form['customer_name'].strip()
        customer_phone = request.form.get('customer_phone', '').strip()
        expected_collection_date_str = request.form['expected_collection_date'].strip()
        
        expected_collection_date_obj = None # Initialize to None
        if expected_collection_date_str:
            try:
                expected_collection_date_obj = datetime.strptime(expected_collection_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid expected collection date format. Please use YYYY-MM-DD.', 'danger')
                # Re-render the form with current data, ensuring expiry_date is handled
                order_data_for_form_on_error = {
                    'customer_name': customer_name,
                    'customer_phone': customer_phone,
                    'expected_collection_date': '', # Pass empty string for invalid date
                    'items': json.loads(request.form.get('cart_items_json', '[]')), # Re-populate cart
                    'total_amount': 0.0 # Ensure total_amount is passed on error re-render
                }
                return render_template('add_edit_future_order.html', title='Add Future Order', order=order_data_for_form_on_error, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)


        cart_items_json = request.form.get('cart_items_json')
        if not cart_items_json:
            flash('No items in the order to record.', 'danger')
            return redirect(url_for('add_future_order'))

        cart_items = json.loads(cart_items_json)
        
        total_amount = 0.0
        order_items_list = []

        for item_data in cart_items:
            product_id = item_data['product_id']
            quantity = float(item_data['quantity_sold']) # Renamed to quantity for clarity in future orders
            unit_price = float(item_data['price_at_time_per_unit_sold'])
            item_total_amount = float(item_data['item_total_amount'])

            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
            if not product:
                flash(f'Product with ID {product_id} not found.', 'danger')
                continue

            if product.current_stock < quantity:
                flash(f'Insufficient stock for {product.product_name}. Currently {product.current_stock}. Tried to order: {quantity}. Please reduce quantity or fulfill later.', 'danger')
                continue
            
            # Deduct stock immediately when order is placed
            product.current_stock -= quantity
            product.last_updated = datetime.now()
            db.session.add(product) # Add product to session for update

            order_items_list.append({
                'product_id': product_id,
                'product_name': product.product_name,
                'quantity': quantity,
                'unit_price': unit_price,
                'unit_type': item_data['sale_unit_type'] # Store unit type
            })
            total_amount += item_total_amount
        
        # Ensure total_amount is calculated correctly from the sum of item_total_amount
        # If the form already sends a total_grand_amount for future orders, use that, else sum it up
        # For simplicity, let's assume total_amount is calculated server-side from cart_items
        
        new_order = FutureOrder(
            business_id=business_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            items_json=json.dumps(order_items_list),
            total_amount=total_amount,
            date_ordered=datetime.now(),
            expected_collection_date=expected_collection_date_obj, # This is now a datetime.date object or None
            status='Pending',
            remaining_balance=total_amount # Initially, the full amount is outstanding
        )
        db.session.add(new_order)
        db.session.commit()
        flash(f'Future order for {customer_name} recorded successfully! Order ID: {str(new_order.id)[:8].upper()}', 'success')
        
        # Send SMS confirmation to customer
        if customer_phone:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Order Confirmation:\\n"
                f"Order ID: {str(new_order.id)[:8].upper()}\\n"
                f"Customer: {customer_name}\\n"
                f"Total Amount: GH₵{total_amount:.2f}\\n"
                f"Expected Collection: {expected_collection_date_obj.strftime('%Y-%m-%d') if expected_collection_date_obj else 'N/A'}\\n\\n"
                f"Thank you for your order!\\n"
                f"From: {business_name_for_sms}"
            )
            sms_payload = {
                'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': customer_phone,
                'from': ARKESEL_SENDER_ID, 'sms': message
            }
            try:
                requests.get(ARKESEL_SMS_URL, params=sms_payload)
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS for future order: {e}')
                flash(f'Network error when trying to send SMS order confirmation.', 'warning')

        return redirect(url_for('future_orders'))

    # For GET request or re-render on error, ensure 'order' always has 'items' as an empty list
    # and total_amount initialized to 0.0
    return render_template('add_edit_future_order.html', title='Add Future Order', order={'items': [], 'total_amount': 0.0}, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)

@app.route('/future_orders/edit/<order_id>', methods=['GET', 'POST'])
def edit_future_order(order_id):
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to edit future orders or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    order_to_edit = FutureOrder.query.filter_by(id=order_id, business_id=business_id).first_or_404()
    
    available_inventory_items = InventoryItem.query.filter_by(business_id=business_id, is_active=True, item_type='Hardware Material').all()
    serialized_inventory_items = [serialize_inventory_item(item) for item in available_inventory_items]


    if request.method == 'POST':
        customer_name = request.form['customer_name'].strip()
        customer_phone = request.form.get('customer_phone', '').strip()
        expected_collection_date_str = request.form['expected_collection_date'].strip()
        status = request.form['status'].strip()

        expected_collection_date_obj = None # Initialize to None
        if expected_collection_date_str:
            try:
                expected_collection_date_obj = datetime.strptime(expected_collection_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid expected collection date format. Please use YYYY-MM-DD.', 'danger')
                # Re-render the form with current data, ensuring expiry_date is handled
                order_data_for_form_on_error = {
                    'id': order_to_edit.id, # Keep ID for context
                    'customer_name': customer_name,
                    'customer_phone': customer_phone,
                    'expected_collection_date': expected_collection_date_str, # Pass original string back
                    'status': status,
                    'items': json.loads(request.form.get('cart_items_json', '[]')), # Re-populate cart
                    'total_amount': order_to_edit.total_amount # Ensure total_amount is passed on error re-render
                }
                return render_template('add_edit_future_order.html', title=f'Edit Future Order: {order_to_edit.customer_name}', order=order_data_for_form_on_error, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)


        cart_items_json = request.form.get('cart_items_json')
        if not cart_items_json:
            flash('No items in the order to record.', 'danger')
            return redirect(url_for('edit_future_order', order_id=order_id))

        new_cart_items = json.loads(cart_items_json)

        # Revert old stock before processing new items
        old_items = order_to_edit.get_items()
        for old_item_data in old_items:
            product = InventoryItem.query.filter_by(id=old_item_data['product_id'], business_id=business_id).first()
            if product:
                product.current_stock += old_item_data['quantity']
                db.session.add(product)

        total_amount = 0.0
        updated_order_items_list = []

        for item_data in new_cart_items:
            product_id = item_data['product_id']
            quantity = float(item_data['quantity_sold'])
            unit_price = float(item_data['price_at_time_per_unit_sold'])
            item_total_amount = float(item_data['item_total_amount'])

            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
            if not product:
                flash(f'Product with ID {product_id} not found.', 'danger')
                # Rollback changes and redirect
                db.session.rollback()
                order_data_for_form_on_error = {
                    'id': order_to_edit.id,
                    'customer_name': customer_name,
                    'customer_phone': customer_phone,
                    'expected_collection_date': expected_collection_date_str, # Pass original string back
                    'status': status,
                    'items': new_cart_items, # Pass the new cart items as they were
                    'total_amount': order_to_edit.total_amount # Ensure total_amount is passed on error re-render
                }
                return render_template('add_edit_future_order.html', title=f'Edit Future Order: {order_to_edit.customer_name}', order=order_data_for_form_on_error, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)

            if product.current_stock < quantity:
                flash(f'Insufficient stock for {product.product_name}. Available: {product.current_stock}. Tried to order: {quantity}.', 'danger')
                # Rollback changes and redirect
                db.session.rollback()
                order_data_for_form_on_error = {
                    'id': order_to_edit.id,
                    'customer_name': customer_name,
                    'customer_phone': customer_phone,
                    'expected_collection_date': expected_collection_date_str, # Pass original string back
                    'status': status,
                    'items': new_cart_items, # Pass the new cart items as they were
                    'total_amount': order_to_edit.total_amount # Ensure total_amount is passed on error re-render
                }
                return render_template('add_edit_future_order.html', title=f'Edit Future Order: {order_to_edit.customer_name}', order=order_data_for_form_on_error, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)

            product.current_stock -= quantity
            product.last_updated = datetime.now()
            db.session.add(product)

            updated_order_items_list.append({
                'product_id': product_id,
                'product_name': product.product_name,
                'quantity': quantity,
                'unit_price': unit_price,
                'unit_type': item_data['sale_unit_type']
            })
            total_amount += item_total_amount

        # Update the order details
        order_to_edit.customer_name = customer_name
        order_to_edit.customer_phone = customer_phone
        order_to_edit.items_json = json.dumps(updated_order_items_list)
        order_to_edit.total_amount = total_amount
        order_to_edit.expected_collection_date = expected_collection_date_obj # This is now a datetime.date object or None
        order_to_edit.status = status
        # Re-calculate remaining_balance if total_amount changed
        order_to_edit.remaining_balance = total_amount - (order_to_edit.total_amount - order_to_edit.remaining_balance)

        db.session.commit()
        flash(f'Future order for {customer_name} updated successfully!', 'success')
        return redirect(url_for('future_orders'))

    # --- GET Request / Initial Render ---
    order_data_for_form = {
        'id': order_to_edit.id,
        'customer_name': order_to_edit.customer_name,
        'customer_phone': order_to_edit.customer_phone,
        'status': order_to_edit.status,
        'total_amount': order_to_edit.total_amount,
        'remaining_balance': order_to_edit.remaining_balance,
        'date_ordered': order_to_edit.date_ordered.strftime('%Y-%m-%d %H:%M:%S'),
        'actual_collection_date': order_to_edit.actual_collection_date.strftime('%Y-%m-%d %H:%M:%S') if order_to_edit.actual_collection_date else '',
        'items': order_to_edit.get_items() # <--- IMPORTANT: Call get_items() here
    }
    # Format expected_collection_date for HTML input
    order_data_for_form['expected_collection_date'] = order_to_edit.expected_collection_date.strftime('%Y-%m-%d') if order_to_edit.expected_collection_date else ''


    return render_template('add_edit_future_order.html', title=f'Edit Future Order: {order_to_edit.customer_name}', order=order_data_for_form, user_role=session.get('role'), inventory_items=serialized_inventory_items, current_year=datetime.now().year)

@app.route('/future_orders/delete/<order_id>')
def delete_future_order(order_id):
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to delete future orders or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    order_to_delete = FutureOrder.query.filter_by(id=order_id, business_id=business_id).first_or_404()

    # Return stock to inventory if order was pending
    if order_to_delete.status == 'Pending':
        for item_data in order_to_delete.get_items():
            product = InventoryItem.query.filter_by(id=item_data['product_id'], business_id=business_id).first()
            if product:
                product.current_stock += item_data['quantity']
                product.last_updated = datetime.now()
                db.session.add(product)
    
    db.session.delete(order_to_delete)
    db.session.commit()
    flash(f'Future order for {order_to_delete.customer_name} deleted successfully!', 'success')
    return redirect(url_for('future_orders'))

@app.route('/future_orders/collect/<order_id>', methods=['GET', 'POST'])
def collect_future_order(order_id):
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to mark orders as collected or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    order_to_collect = FutureOrder.query.filter_by(id=order_id, business_id=business_id).first_or_404()

    if order_to_collect.status == 'Collected':
        flash('This order has already been collected.', 'warning')
        return redirect(url_for('future_orders'))
    
    if order_to_collect.remaining_balance > 0:
        flash(f'Outstanding balance of GH₵{order_to_collect.remaining_balance:.2f} remaining. Please settle payment before marking as collected.', 'danger')
        return redirect(url_for('future_order_payment', order_id=order_id))

    if request.method == 'POST':
        order_to_collect.actual_collection_date = datetime.now()
        order_to_collect.status = 'Collected'
        db.session.commit()
        flash(f'Order {str(order_to_collect.id)[:8].upper()} collected successfully!', 'success')
        
        # Send SMS confirmation to customer
        if order_to_collect.customer_phone:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Order Collection Confirmation:\\n"
                f"Order ID: {str(order_to_collect.id)[:8].upper()}\\n"
                f"Customer: {order_to_collect.customer_name}\\n"
                f"Total Amount: GH₵{order_to_collect.total_amount:.2f}\\n"
                f"Collected On: {order_to_collect.actual_collection_date.strftime('%Y-%m-%d %H:%M:%S')}\\n\\n"
                f"Thank you for your business!\\n"
                f"From: {business_name_for_sms}"
            )
            sms_payload = {
                'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': order_to_collect.customer_phone,
                'from': ARKESEL_SENDER_ID, 'sms': message
            }
            try:
                requests.get(ARKESEL_SMS_URL, params=sms_payload)
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS for collection: {e}')
                flash(f'Network error when trying to send SMS collection confirmation.', 'warning')
    else:
        flash('Failed to mark order as collected.', 'danger')

    return redirect(url_for('future_orders'))

@app.route('/future_orders/payment/<order_id>', methods=['GET', 'POST'])
def future_order_payment(order_id):
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to record payments or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    order = FutureOrder.query.filter_by(id=order_id, business_id=business_id).first_or_404()

    if order.status == 'Collected':
        flash('This order has already been collected and paid for.', 'warning')
        return redirect(url_for('future_orders'))
    
    if order.remaining_balance <= 0: # Check if balance is already zero or less
        flash('This order has no outstanding balance.', 'warning')
        return redirect(url_for('future_orders'))

    if request.method == 'POST':
        amount_paid = float(request.form['amount_paid'])
        if amount_paid <= 0:
            flash('Amount paid must be positive.', 'danger')
            return render_template('future_order_payment.html', order=order, user_role=session.get('role'), current_year=datetime.now().year)
        
        if amount_paid > order.remaining_balance:
            flash(f'Amount paid (GH₵{amount_paid:.2f}) exceeds remaining balance (GH₵{order.remaining_balance:.2f}).', 'danger')
            return render_template('future_order_payment.html', order=order, user_role=session.get('role'), current_year=datetime.now().year)
        
        order.remaining_balance -= amount_paid
        db.session.commit()
        flash(f'Payment of GH₵{amount_paid:.2f} recorded for order {order.customer_name}. Remaining balance: GH₵{order.remaining_balance:.2f}', 'success')
        return redirect(url_for('future_orders'))
    
    return render_template('future_order_payment.html', order=order, user_role=session.get('role'), current_year=datetime.now().year)

# NEW: Routes for Hirable Items
@app.route('/hirable_items')
def hirable_items():
    # ACCESS CONTROL: Allows admin, sales, and viewer roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to view hirable items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    items = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()
    return render_template('hirable_item_list.html', hirable_items=items, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/hirable_items/add', methods=['GET', 'POST'])
def add_hirable_item():
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to add hirable items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    if request.method == 'POST':
        item_name = request.form['item_name'].strip()
        description = request.form.get('description', '').strip()
        daily_hire_price = float(request.form['daily_hire_price'])
        current_stock = int(request.form['current_stock'])

        if HirableItem.query.filter_by(item_name=item_name, business_id=business_id).first():
            flash('Hirable item with this name already exists for this business.', 'danger')
            return render_template('add_edit_hirable_item.html', title='Add Hirable Item', item=request.form, user_role=session.get('role'), current_year=datetime.now().year)
        
        new_item = HirableItem(
            business_id=business_id,
            item_name=item_name,
            description=description,
            daily_hire_price=daily_hire_price,
            current_stock=current_stock
        )
        db.session.add(new_item)
        db.session.commit()
        flash(f'Hirable item "{item_name}" added successfully!', 'success')
        return redirect(url_for('hirable_items'))
    
    return render_template('add_edit_hirable_item.html', title='Add Hirable Item', item={}, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/hirable_items/edit/<item_id>', methods=['GET', 'POST'])
def edit_hirable_item(item_id):
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to edit hirable items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    item_to_edit = HirableItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()

    if request.method == 'POST':
        item_name = request.form['item_name'].strip()
        description = request.form.get('description', '').strip()
        daily_hire_price = float(request.form['daily_hire_price'])
        current_stock = int(request.form['current_stock'])

        # Check for duplicate name, excluding the current item being edited
        if HirableItem.query.filter(HirableItem.item_name == item_name,
                                    HirableItem.business_id == business_id,
                                    HirableItem.id != item_id).first():
            flash('Hirable item with this name already exists for this business.', 'danger')
            # --- IMPORTANT FIX HERE: Pass the original item_to_edit object back ---
            # This ensures item.id is available for url_for in the form action
            return render_template('add_edit_hirable_item.html',
                                   title=f'Edit Hirable Item: {item_to_edit.item_name}', # Keep original title
                                   item=item_to_edit, # Pass the SQLAlchemy object
                                   user_role=session.get('role'),
                                   current_year=datetime.now().year)
        
        item_to_edit.item_name = item_name
        item_to_edit.description = description
        item_to_edit.daily_hire_price = daily_hire_price
        item_to_edit.current_stock = current_stock
        item_to_edit.last_updated = datetime.now()
        
        # Handle is_active checkbox
        item_to_edit.is_active = 'is_active' in request.form # Checkbox is present if checked

        db.session.commit()
        flash(f'Hirable item "{item_name}" updated successfully!', 'success')
        return redirect(url_for('hirable_items'))
    
    # GET request or initial render
    return render_template('add_edit_hirable_item.html',
                           title=f'Edit Hirable Item: {item_to_edit.item_name}',
                           item=item_to_edit, # This is already correct for GET
                           user_role=session.get('role'),
                           current_year=datetime.now().year)


@app.route('/hirable_items/delete/<item_id>')
def delete_hirable_item(item_id):
    # ACCESS CONTROL: Allows admin role
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to delete hirable items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    item_to_delete = HirableItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()
    
    item_to_delete.is_active = False # Soft delete
    db.session.commit()
    flash(f'Hirable item "{item_to_delete.item_name}" marked as inactive successfully!', 'success')
    return redirect(url_for('hirable_items'))

# NEW: Routes for Rental Records
@app.route('/rental_records')
def rental_records():
    # ACCESS CONTROL: Allows admin, sales, and viewer roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales', 'viewer'] or not get_current_business_id():
        flash('You do not have permission to view rental records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    records = RentalRecord.query.filter_by(business_id=business_id).order_by(RentalRecord.date_recorded.desc()).all()
    return render_template('rental_record_list.html', rental_records=records, user_role=session.get('role'), current_year=datetime.now().year)

@app.route('/rental_records/add', methods=['GET', 'POST'])
def add_rental_record():
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to add rental records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    available_hirable_items = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()
    serialized_hirable_items = [serialize_hirable_item(item) for item in available_hirable_items]

    # Get business info for receipts
    business_info = session.get('business_info', {
        'name': ENTERPRISE_NAME,
        'location': PHARMACY_LOCATION, # Reusing for consistency, rename if needed
        'address': PHARMACY_ADDRESS,
        'contact': PHARMACY_CONTACT
    })

    if request.method == 'POST':
        hirable_item_id = request.form['hirable_item_id']
        customer_name = request.form['customer_name'].strip()
        customer_phone = request.form.get('customer_phone', '').strip()
        start_date_str = request.form['start_date'].strip()
        end_date_str = request.form.get('end_date', '').strip()
        send_sms = 'send_sms_receipt' in request.form # Check if the checkbox was checked

        start_date_obj = None # Initialize to None
        if start_date_str:
            try:
                start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid start date format. Please use YYYY-MM-DD.', 'danger')
                record_data_for_form_on_error = { # Use a dedicated error dict
                    'hirable_item_id': hirable_item_id, 'customer_name': customer_name,
                    'customer_phone': customer_phone, 'start_date': start_date_str, # Pass original string back
                    'end_date': end_date_str # Pass original string back
                }
                return render_template('add_edit_rental_record.html', title='Add Rental Record', record=record_data_for_form_on_error, user_role=session.get('role'), hirable_items=serialized_hirable_items, business_info=business_info, current_year=datetime.now().year)

        end_date_obj = None # Initialize to None
        if end_date_str:
            try:
                end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid end date format. Please use YYYY-MM-DD.', 'danger')
                record_data_for_form_on_error = { # Use a dedicated error dict
                    'hirable_item_id': hirable_item_id, 'customer_name': customer_name,
                    'customer_phone': customer_phone, 'start_date': start_date_str, # Pass original string back
                    'end_date': end_date_str # Pass original string back
                }
                return render_template('add_edit_rental_record.html', title='Add Rental Record', record=record_data_for_form_on_error, user_role=session.get('role'), hirable_items=serialized_hirable_items, business_info=business_info, current_year=datetime.now().year)


        if end_date_obj and start_date_obj and end_date_obj < start_date_obj:
            flash('End date cannot be before start date.', 'danger')
            record_data_for_form_on_error = { # Use a dedicated error dict
                'hirable_item_id': hirable_item_id, 'customer_name': customer_name,
                'customer_phone': customer_phone, 'start_date': start_date_str, # Pass original string back
                'end_date': end_date_str # Pass original string back
            }
            return render_template('add_edit_rental_record.html', title='Add Rental Record', record=record_data_for_form_on_error, user_role=session.get('role'), hirable_items=serialized_hirable_items, business_info=business_info, current_year=datetime.now().year)
        
        hirable_item = HirableItem.query.filter_by(id=hirable_item_id, business_id=business_id).first_or_404()

        if hirable_item.current_stock < 1:
            flash(f'Insufficient stock for {hirable_item.item_name}. Currently 0 available for hiring.', 'danger')
            record_data_for_form_on_error = { # Use a dedicated error dict
                'hirable_item_id': hirable_item_id, 'customer_name': customer_name,
                'customer_phone': customer_phone, 'start_date': start_date_str, # Pass original string back
                'end_date': end_date_str # Pass original string back
            }
            return render_template('add_edit_rental_record.html', title='Add Rental Record', record=record_data_for_form_on_error, user_role=session.get('role'), hirable_items=serialized_hirable_items, business_info=business_info, current_year=datetime.now().year)

        number_of_days = (end_date_obj - start_date_obj).days + 1 if end_date_obj and start_date_obj else 1
        total_hire_amount = number_of_days * hirable_item.daily_hire_price

        # Deduct stock
        hirable_item.current_stock -= 1
        hirable_item.last_updated = datetime.now()
        db.session.add(hirable_item)

        new_record = RentalRecord(
            business_id=business_id,
            hirable_item_id=hirable_item.id,
            item_name_at_rent=hirable_item.item_name,
            customer_name=customer_name,
            customer_phone=customer_phone,
            start_date=start_date_obj,
            end_date=end_date_obj,
            # quantity=1, # Removed as per database schema
            number_of_days=number_of_days,
            daily_hire_price_at_rent=hirable_item.daily_hire_price,
            total_hire_amount=total_hire_amount,
            status='Rented',
            sales_person_name=session.get('username', 'N/A')
        )
        db.session.add(new_record)
        db.session.commit()
        
        # Store details in session for printing receipt
        session['last_rental_details'] = {
            'id': new_record.id,
            'item_name': new_record.item_name_at_rent,
            'customer_name': new_record.customer_name,
            'customer_phone': new_record.customer_phone,
            'start_date': new_record.start_date.strftime('%Y-%m-%d'),
            'end_date': new_record.end_date.strftime('%Y-%m-%d') if new_record.end_date else 'N/A',
            'number_of_days': new_record.number_of_days,
            'daily_hire_price': new_record.daily_hire_price_at_rent,
            'total_hire_amount': new_record.total_hire_amount,
            'sales_person': new_record.sales_person_name,
            'date_recorded': new_record.date_recorded.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # SMS Sending Logic
        if send_sms and new_record.customer_phone:
            business_name_for_sms = business_info.get('name', ENTERPRISE_NAME)
            sms_message = (
                f"{business_name_for_sms} Rental Confirmation:\n"
                f"Item: {new_record.item_name_at_rent}\n"
                f"Customer: {new_record.customer_name}\n"
                f"Period: {new_record.start_date.strftime('%Y-%m-%d')} to {new_record.end_date.strftime('%Y-%m-%d') if new_record.end_date else 'N/A'}\n"
                f"Total: GH₵{new_record.total_hire_amount:.2f}\n\n"
                f"Thank you for your business!\n"
                f"From: {business_name_for_sms}"
            )
            sms_payload = {
                'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': new_record.customer_phone,
                'from': ARKESEL_SENDER_ID, 'sms': sms_message
            }
            try:
                requests.get(ARKESEL_SMS_URL, params=sms_payload)
                flash(f'SMS receipt sent to {new_record.customer_name} successfully!', 'success')
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS for rental: {e}')
                flash(f'Network error when trying to send SMS rental confirmation.', 'warning')
        elif send_sms and not new_record.customer_phone:
            flash(f'SMS receipt not sent: No phone number configured for the customer.', 'warning')

        flash(f'Rental record for "{hirable_item.item_name}" added successfully!', 'success')
        return redirect(url_for('add_rental_record', print_ready='true'))
    
    # GET request / Initial render
    print_ready = request.args.get('print_ready', 'false').lower() == 'true'
    last_rental_details = session.pop('last_rental_details', None)

    return render_template('add_edit_rental_record.html', 
                           title='Add Rental Record', 
                           record={}, 
                           user_role=session.get('role'), 
                           hirable_items=serialized_hirable_items,
                           business_info=business_info,
                           print_ready=print_ready,
                           last_rental_details=last_rental_details,
                           current_year=datetime.now().year)

@app.route('/rental_records/print/<record_id>')
@login_required
def print_rental_receipt(record_id):
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    record_to_print = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()

    business_info = session.get('business_info', {
        "name": ENTERPRISE_NAME,
        "location": PHARMACY_LOCATION,
        "address": PHARMACY_ADDRESS,
        "contact": PHARMACY_CONTACT
    })

    rental_details_for_receipt = {
        'id': record_to_print.id,
        'item_name': record_to_print.item_name_at_rent,
        'customer_name': record_to_print.customer_name,
        'customer_phone': record_to_print.customer_phone,
        'start_date': record_to_print.start_date.strftime('%Y-%m-%d'),
        'end_date': record_to_print.end_date.strftime('%Y-%m-%d') if record_to_print.end_date else 'N/A',
        'number_of_days': record_to_print.number_of_days,
        'daily_hire_price': record_to_print.daily_hire_price_at_rent,
        'total_hire_amount': record_to_print.total_hire_amount,
        'sales_person': record_to_print.sales_person_name,
        'date_recorded': record_to_print.date_recorded.strftime('%Y-%m-%d %H:%M:%S')
    }

    # Fetch available hirable items for the sidebar/form if needed, though not strictly for receipt
    available_hirable_items = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()
    serialized_hirable_items = [serialize_hirable_item(item) for item in available_hirable_items]


    return render_template('add_edit_rental_record.html',
                           title='Rental Receipt',
                           record=rental_details_for_receipt, # Pass the specific record for the receipt
                           user_role=session.get('role'),
                           hirable_items=serialized_hirable_items, # Pass for sidebar/form
                           business_info=business_info,
                           print_ready=True,
                           last_rental_details=rental_details_for_receipt, # Use this for the receipt block
                           current_year=datetime.now().year
                           )


@app.route('/rental_records/mark_returned/<record_id>', methods=['GET', 'POST'])
def mark_rental_returned(record_id):
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to mark rental records as returned or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    record = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()

    if record.status == 'Returned':
        flash('This item has already been marked as returned.', 'warning')
        return redirect(url_for('rental_records'))
    
    if request.method == 'POST':
        record.actual_return_date = datetime.now()
        record.status = 'Returned'

        # Return stock to hirable item (implicitly assumes quantity of 1)
        hirable_item = HirableItem.query.filter_by(id=record.hirable_item_id, business_id=business_id).first()
        if hirable_item:
            hirable_item.current_stock += 1
            hirable_item.last_updated = datetime.now()
            db.session.add(hirable_item)

        db.session.commit()
        flash(f'Rental record for "{record.item_name_at_rent}" marked as returned successfully!', 'success')
        return redirect(url_for('rental_records'))
    
    return render_template('mark_rental_returned.html', record=record, user_role=session.get('role'), current_year=datetime.now().year)
# app.py - New route for importing inventory from another business

@app.route('/inventory/import_from_business', methods=['GET', 'POST'])
@login_required
def import_inventory_from_business():
    # ACCESS CONTROL: Only admin can import inventory from another business
    if session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to import inventory or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    current_business_id = get_current_business_id()
    current_business_type = get_current_business_type()

    # Fetch all other businesses of the same type, excluding the current business
    other_businesses_same_type = Business.query.filter(
        Business.id != current_business_id,
        Business.type == current_business_type
    ).all()

    if request.method == 'POST':
        source_business_id = request.form.get('source_business_id')

        if not source_business_id:
            flash('Please select a source business.', 'danger')
            return render_template('import_inventory_from_business.html',
                                   other_businesses=other_businesses_same_type,
                                   user_role=session.get('role'),
                                   current_year=datetime.now().year)

        source_business = Business.query.get(source_business_id)
        if not source_business or source_business.type != current_business_type:
            flash('Invalid source business selected or business type mismatch.', 'danger')
            return render_template('import_inventory_from_business.html',
                                   other_businesses=other_businesses_same_type,
                                   user_role=session.get('role'),
                                   current_year=datetime.now().year)

        # Fetch inventory items from the source business
        source_inventory_items = InventoryItem.query.filter_by(
            business_id=source_business_id,
            is_active=True # Only import active items
        ).all()

        if not source_inventory_items:
            flash(f'No active inventory items found in "{source_business.name}" to import.', 'warning')
            return render_template('import_inventory_from_business.html',
                                   other_businesses=other_businesses_same_type,
                                   user_role=session.get('role'),
                                   current_year=datetime.now().year)

        updated_count = 0
        added_count = 0
        errors = []

        for item in source_inventory_items:
            try:
                # Check if an item with the same product_name already exists in the current business
                existing_target_item = InventoryItem.query.filter_by(
                    product_name=item.product_name,
                    business_id=current_business_id
                ).first()

                if existing_target_item:
                    # Update existing item's stock and other relevant fields
                    # You might want to define a more sophisticated merge logic here
                    # For simplicity, we'll update key fields and add stock.
                    existing_target_item.current_stock += item.current_stock # Add stock
                    existing_target_item.purchase_price = item.purchase_price # Overwrite purchase price
                    existing_target_item.sale_price = item.sale_price # Overwrite sale price
                    existing_target_item.number_of_tabs = item.number_of_tabs # Overwrite units/pack
                    existing_target_item.unit_price_per_tab = item.unit_price_per_tab # Overwrite unit price
                    existing_target_item.last_updated = datetime.now()
                    existing_target_item.batch_number = item.batch_number # Overwrite batch number
                    existing_target_item.is_fixed_price = item.is_fixed_price
                    existing_target_item.fixed_sale_price = item.fixed_sale_price
                    existing_target_item.is_active = item.is_active # Maintain active status

                    # For expiry date, update only if the source item has a valid, newer expiry date
                    if item.expiry_date and (not existing_target_item.expiry_date or item.expiry_date > existing_target_item.expiry_date):
                        existing_target_item.expiry_date = item.expiry_date

                    db.session.add(existing_target_item)
                    updated_count += 1
                else:
                    # Add new item to the current business's inventory
                    new_item = InventoryItem(
                        business_id=current_business_id,
                        product_name=item.product_name,
                        category=item.category,
                        purchase_price=item.purchase_price,
                        sale_price=item.sale_price,
                        current_stock=item.current_stock,
                        last_updated=datetime.now(),
                        batch_number=item.batch_number,
                        number_of_tabs=item.number_of_tabs,
                        unit_price_per_tab=item.unit_price_per_tab,
                        item_type=item.item_type,
                        expiry_date=item.expiry_date,
                        is_fixed_price=item.is_fixed_price,
                        fixed_sale_price=item.fixed_sale_price,
                        is_active=True # New items are active by default
                    )
                    db.session.add(new_item)
                    added_count += 1
            except Exception as e:
                errors.append(f"Error processing item '{item.product_name}': {e}")
        
        db.session.commit()
        
        if errors:
            flash(f'Inventory import completed with {updated_count} updated, {added_count} added, and {len(errors)} errors. Check console for details.', 'warning')
            for error in errors:
                print(f"Inventory Import Error: {error}")
        else:
            flash(f'Inventory imported successfully! {updated_count} items updated, {added_count} items added from "{source_business.name}".', 'success')
        
        return redirect(url_for('inventory')) # Redirect to current business's inventory

    return render_template('import_inventory_from_business.html',
                           other_businesses=other_businesses_same_type,
                           user_role=session.get('role'),
                           current_year=datetime.now().year)
@app.route('/rental_records/cancel/<record_id>')
def cancel_rental_record(record_id):
    # ACCESS CONTROL: Allows admin and sales roles
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to cancel rental records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
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

@app.route('/manage_businesses')
@login_required
def manage_businesses():
    # Access control: Only 'super_admin' or 'admin' role can view this page
    if session.get('role') not in ['super_admin', 'admin']:
        flash('You do not have permission to manage businesses.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Retrieve all businesses from the database
    businesses = Business.query.all()
    
    # This line is critical – ensure it renders 'super_admin_dashboard.html'
    return render_template('super_admin_dashboard.html', # <--- THIS MUST BE 'super_admin_dashboard.html'
                           businesses=businesses,
                           user_role=session.get('role'),
                           current_year=datetime.now().year)

@app.route('/manage_businesses/toggle_active/<string:business_id>', methods=['POST'])
@login_required
def toggle_business_active(business_id):
    # Access control: Only 'admin' role can toggle business status
    if session.get('role') not in ['super_admin', 'admin']:
        flash('You do not have permission to manage businesses.', 'danger')
        return redirect(url_for('dashboard'))

    # Fetch the business by its ID or return 404 if not found
    business = Business.query.get_or_404(business_id)
    
    # Toggle the is_active status
    business.is_active = not business.is_active
    db.session.commit() # Commit the change to the database
    
    # Prepare a user-friendly message based on the new status
    status_message = "activated" if business.is_active else "deactivated"
    flash(f'Business "{business.name}" has been {status_message} successfully!', 'success')
    
    # Redirect back to the business management page
    return redirect(url_for('manage_businesses'))

@app.route('/manage_businesses/send_sms_warning/<string:business_id>', methods=['POST'])
@login_required
def send_payment_due_sms(business_id):
    """
    Sends an SMS warning message (e.g., payment due) to the contact number of a specific business.
    Accessible by 'super_admin' and 'admin' roles.
    """
    if session.get('role') not in ['super_admin', 'admin']:
        flash('You do not have permission to send SMS warnings.', 'danger')
        return redirect(url_for('dashboard'))

    business = Business.query.get_or_404(business_id)
    
    # Check if a contact number is available for the business
    if not business.contact:
        flash(f'Business "{business.name}" has no contact number registered for SMS.', 'danger')
        return redirect(url_for('super_admin_dashboard'))

    # Compose the SMS message
    enterprise_name = os.getenv('ENTERPRISE_NAME', 'Global Business Technology') # Fallback if not set
    sms_message = (
        f"Dear {business.name},\n"
        f"This is a friendly reminder that your subscription payment is due. "
        f"Please make your payment to continue using our services. "
        f"Contact us at {business.contact} for assistance.\n"
        f"Thank you, {enterprise_name}."
    )
    
    print(f"Attempting to send payment due SMS to {business.contact} for business {business.name}.")
    print(f"SMS Message: {sms_message}")
    
    # Prepare SMS payload for Arkesel API
    sms_payload = {
        'action': 'send-sms',
        'api_key': os.getenv('ARKESEL_API_KEY'), # Still get API key from env (secure practice)
        'to': business.contact,
        'from': os.getenv('ARKESEL_SENDER_ID', 'uniquebence'), # Still get Sender ID from env
        'sms': sms_message
    }
    
    try:
        # CORRECTED LINE: Use the global ARKESEL_SMS_URL variable directly
        sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
        sms_response.raise_for_status()
        sms_result = sms_response.json()
        print(f"Arkesel SMS API Response: {sms_result}")

        if sms_result.get('status') == 'success':
            flash(f'Payment due SMS sent to {business.name} ({business.contact}) successfully!', 'success')
        else:
            error_message = sms_result.get('message', 'Unknown error from SMS provider.')
            flash(f'Failed to send SMS to {business.name}. Error: {error_message}', 'danger')
    except requests.exceptions.HTTPError as http_err:
        flash(f'HTTP error sending SMS: {http_err}. Please check API key or sender ID.', 'danger')
        print(f"HTTP Error: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        flash(f'Network error sending SMS: {conn_err}. Please check your internet connection.', 'danger')
        print(f"Connection Error: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        flash(f'SMS request timed out: {timeout_err}. Please try again later.', 'danger')
        print(f"Timeout Error: {timeout_err}")
    except json.JSONDecodeError:
        flash('Failed to parse SMS provider response. The response might not be in JSON format.', 'danger')
        print("JSON Decode Error: Response was not valid JSON.")
    except Exception as e:
        flash(f'An unexpected error occurred while sending SMS: {e}', 'danger')
        print(f"Unexpected Error: {e}")

    return redirect(url_for('super_admin_dashboard'))


# ... (existing imports, app initialization, and other routes) ...

# ... (existing imports, app initialization, and other routes) ...

@app.route('/get_all_active_products', methods=['GET'])
@login_required
def get_all_active_products():
    """
    Returns a list of all active inventory items for the current business.
    This route is called by the frontend (add_edit_sale.html) via AJAX
    to populate the product dropdowns.
    """
    business_id = get_current_business_id()
    if not business_id:
        return jsonify({'success': False, 'message': 'Business context not found.'}), 400

    products = InventoryItem.query.filter_by(business_id=business_id, is_active=True).all()
    
    products_data = []
    for product in products:
        # Prepare product data, ensuring numerical values are floats and dates are formatted
        # Ensure all fields expected by the frontend JavaScript are included and consistently named.
        products_data.append({
            'id': str(product.id), # Convert UUID to string
            'product_name': product.product_name,
            'current_stock': float(product.current_stock or 0.0),
            'is_fixed_price': product.is_fixed_price,
            'barcode': product.barcode,
            'number_of_tabs': float(product.number_of_tabs or 1.0), # Default to 1.0 if None
            'unit_price_per_tab': float(product.unit_price_per_tab or 0.0),
            'item_type': product.item_type,
            'expiry_date': product.expiry_date.strftime('%Y-%m-%d') if product.expiry_date else None,
            'batch_number': product.batch_number,
            'purchase_price': float(product.purchase_price or 0.0),
            'sale_price': float(product.sale_price or 0.0), # Regular sale price
            'fixed_sale_price': float(product.fixed_sale_price or 0.0), # Fixed sale price
            'markup_percentage_pharmacy': float(product.markup_percentage_pharmacy or 0.0), # Markup percentage
        })
    
    return jsonify({'success': True, 'products': products_data})

# ... (rest of your app.py code) ...

# NEW: Jinja2 filter to safely format a date or datetime object
@app.template_filter('format_date')
def format_date(value, format='%Y-%m-%d'):
    if isinstance(value, (datetime, date)):
        return value.strftime(format)
    return "" # Return an empty string if the value is not a date object
# --- Database Initialization (run once to create tables) ---
# IMPORTANT: Once Alembic is set up and working, you should remove or comment out
# db.create_all() from here, as Alembic will manage your schema migrations.
with app.app_context():
    try:
        # Check if any user exists at all
        if User.query.first() is None:
            print("No users found in the database. Attempting to create initial super admin...")
            
            super_admin_username = os.getenv('SUPER_ADMIN_USERNAME', 'superadmin')
            super_admin_password = os.getenv('SUPER_ADMIN_PASSWORD', 'superpassword') 

            # Create a dummy business for the super admin if none exists
            super_admin_business = Business.query.filter_by(name="SuperAdmin Global Business").first()
            if not super_admin_business:
                super_admin_business = Business(
                    name="SuperAdmin Global Business",
                    address="Global Admin HQ",
                    location="Global",
                    contact="N/A",
                    type="Administration",
                    is_active=True,
                    last_updated=datetime.utcnow()
                )
                db.session.add(super_admin_business)
                db.session.commit()
                print("Created 'SuperAdmin Global Business' for initial super admin.")
            else:
                print("'SuperAdmin Global Business' already exists.")

            # Now create the super admin user
            existing_super_admin = User.query.filter_by(username=super_admin_username).first()
            if not existing_super_admin:
                new_super_admin = User(
                    username=super_admin_username,
                    password=super_admin_password, # The setter will hash it
                    role='super_admin',
                    business_id=super_admin_business.id,
                    is_active=True
                    # REMOVED: last_password_update=datetime.utcnow()
                    # SQLAlchemy's default will handle this if defined in the model
                )
                db.session.add(new_super_admin)
                db.session.commit()
                print(f"Initial super admin '{super_admin_username}' created successfully!")
            else:
                print(f"Super admin '{super_admin_username}' already exists. Skipping creation.")
        else:
            print("Users already exist in the database. Skipping initial super admin creation.")
    except Exception as e:
        print(f"Error during initial super admin creation: {e}")
        db.session.rollback()

# --- Database Initialization (This part should generally be managed by Alembic) ---
# Keep this pass statement or remove it if db.create_all() is truly not needed.
with app.app_context():
    # db.create_all() # Ensure this line is commented out if Alembic handles schema
    pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=os.getenv('PORT', 5000))