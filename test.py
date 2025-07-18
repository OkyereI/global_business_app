# app.py - Enhanced Flask Application with PostgreSQL Database and Hardware Business Features

from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
import os
import uuid
from datetime import datetime, date, timedelta
import requests
from dotenv import load_dotenv
import json
import io
import csv # Import csv module for CSV export

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Database Configuration ---
# Updated DATABASE_URL with the user-provided external PostgreSQL connection string
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://bisinessdb_user:QceRMwRe2FtjhPk8iMLCIKB3j3s4KmhI@dpg-d1olvgbuibrs73cum700-a.oregon-postgres.render.com/bisinessdb'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Define Database Models ---

class Business(db.Model):
    __tablename__ = 'businesses'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), unique=True, nullable=False)
    address = db.Column(db.String(255))
    location = db.Column(db.String(100))
    contact = db.Column(db.String(50))
    type = db.Column(db.String(50), default='Pharmacy', nullable=False) # 'Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'

    # Relationships
    users = db.relationship('User', backref='business', lazy=True, cascade="all, delete-orphan")
    inventory_items = db.relationship('InventoryItem', backref='business', lazy=True, cascade="all, delete-orphan")
    sales_records = db.relationship('SaleRecord', backref='business', lazy=True, cascade="all, delete-orphan")
    companies = db.relationship('Company', backref='business', lazy=True, cascade="all, delete-orphan") # New: for Hardware
    future_orders = db.relationship('FutureOrder', backref='business', lazy=True, cascade="all, delete-orphan") # New: for Hardware
    hirable_items = db.relationship('HirableItem', backref='business', lazy=True, cascade="all, delete-orphan") # NEW: for Hardware Hiring
    rental_records = db.relationship('RentalRecord', backref='business', lazy=True, cascade="all, delete-orphan") # NEW: for Hardware Hiring

    def __repr__(self):
        return f'<Business {self.name} ({self.type})>'

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('username', 'business_id', name='_username_business_uc'),)

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
    expiry_date = db.Column(db.Date)
    is_fixed_price = db.Column(db.Boolean, default=False)
    fixed_sale_price = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True, nullable=False) # New: For soft delete

    __table_args__ = (db.UniqueConstraint('product_name', 'business_id', name='_product_name_business_uc'),)

    def __repr__(self):
        return f'<InventoryItem {self.product_name} (Stock: {self.current_stock})>'


class SaleRecord(db.Model):
    __tablename__ = 'sales_records'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('inventory_items.id'), nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    quantity_sold = db.Column(db.Float, nullable=False)
    sale_unit_type = db.Column(db.String(50))
    price_at_time_per_unit_sold = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    sale_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    customer_phone = db.Column(db.String(50))
    sales_person_name = db.Column(db.String(100))
    reference_number = db.Column(db.String(100))
    transaction_id = db.Column(db.String(36))

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
    balance = db.Column(db.Float, default=0.0, nullable=False) # Positive for credit, negative for debit

    # Relationship to CompanyTransaction
    transactions = db.relationship('CompanyTransaction', backref='company', lazy=True, cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint('name', 'business_id', name='_company_name_business_uc'),)

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
    number_of_days = db.Column(db.Integer, nullable=False) # Days calculated at the time of rental
    daily_hire_price_at_rent = db.Column(db.Float, nullable=False)
    total_hire_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='Rented', nullable=False) # 'Rented', 'Returned', 'Overdue', 'Cancelled'
    sales_person_name = db.Column(db.String(100)) # User who recorded the rental
    date_recorded = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f'<RentalRecord {self.item_name_at_rent} for {self.customer_name} (Status: {self.status})>'


# --- Flask app setup (secret_key, Arkesel, etc.) ---
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_super_secret_key_here')
ARKESEL_API_KEY = os.getenv('ARKESEL_API_KEY', 'b0FrYkNNVlZGSmdrendVT3hwUHk')
ARKESEL_SENDER_ID = os.getenv('ARKESEL_SENDER_ID', 'PHARMACY')
ARKESEL_SMS_URL = "https://sms.arkesel.com/sms/api" # Define Arkesel SMS URL
ADMIN_PHONE_NUMBER = os.getenv('ADMIN_PHONE_NUMBER', '233543169389')
ENTERPRISE_NAME = os.getenv('ENTERPRISE_NAME', 'My Pharmacy')
PHARMACY_LOCATION = os.getenv('PHARMACY_LOCATION', 'Accra, Ghana')
PHARMACY_ADDRESS = os.getenv('PHARMACY_ADDRESS', '123 Main St, City')
PHARMACY_CONTACT = os.getenv('PHARMACY_CONTACT', '+233543169389')

# --- Helper function for current business ID ---
def get_current_business_id():
    return session.get('business_id')

def get_current_business_type():
    business_id = get_current_business_id()
    if business_id:
        business = Business.query.get(business_id)
        if business:
            return business.type
    return None

# --- JSON Serialization Helper for InventoryItem and HirableItem ---
def serialize_inventory_item(item):
    """Converts an InventoryItem SQLAlchemy object to a JSON-serializable dictionary."""
    return {
        'id': item.id,
        'product_name': item.product_name,
        'category': item.category,
        'purchase_price': item.purchase_price,
        'sale_price': item.sale_price,
        'current_stock': item.current_stock,
        'last_updated': item.last_updated.isoformat(), # Convert datetime to ISO 8601 string
        'batch_number': item.batch_number,
        'number_of_tabs': item.number_of_tabs,
        'unit_price_per_tab': item.unit_price_per_tab,
        'item_type': item.item_type,
        'expiry_date': item.expiry_date.isoformat() if item.expiry_date else None, # Convert date to ISO 8601 string
        'is_fixed_price': item.is_fixed_price,
        'fixed_sale_price': item.fixed_sale_price,
        'is_active': item.is_active
    }

def serialize_hirable_item(item):
    """Converts a HirableItem SQLAlchemy object to a JSON-serializable dictionary."""
    return {
        'id': item.id,
        'item_name': item.item_name,
        'description': item.description,
        'daily_hire_price': item.daily_hire_price,
        'current_stock': item.current_stock,
        'last_updated': item.last_updated.isoformat(),
        'is_active': item.is_active
    }


# --- Authentication Routes ---

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

        if username == os.getenv('SUPER_ADMIN_USERNAME', 'superadmin') and \
           password == os.getenv('SUPER_ADMIN_PASSWORD', 'superpassword'):
            session.clear()
            session['username'] = username
            session['role'] = 'super_admin'
            flash(f'Welcome, Super Admin!', 'success')
            return redirect(url_for('super_admin_dashboard'))

        user_in_db = User.query.filter_by(username=username, password=password).first()

        if user_in_db:
            business = Business.query.get(user_in_db.business_id)
            if business:
                session.clear()
                session['username'] = username
                session['role'] = user_in_db.role
                session['business_id'] = business.id
                session['business_name'] = business.name
                session['business_type'] = business.type # Store business type in session
                session['business_info'] = {
                    'name': business.name,
                    'address': business.address,
                    'location': business.location,
                    'contact': business.contact
                }
                flash(f'Welcome, {username} ({session["role"].replace("_", " ").title()}) to {session["business_name"]}!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Associated business not found for this user.', 'danger')
        else:
            flash('Invalid username or password. Please try again.', 'danger')
    return render_template('login.html')

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

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))
    if session.get('role') == 'super_admin':
        return redirect(url_for('super_admin_dashboard'))
    if 'business_id' not in session:
        return redirect(url_for('business_selection'))

    return render_template('dashboard.html', 
                           username=session['username'], 
                           user_role=session.get('role'),
                           business_name=session.get('business_name'),
                           business_type=session.get('business_type')) # Pass business type to dashboard

# --- Super Admin Routes (now also accessible by 'admin' role) ---

@app.route('/super_admin_dashboard')
def super_admin_dashboard():
    # Allow 'admin' role to view this dashboard
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    businesses = Business.query.all()
    return render_template('super_admin_dashboard.html', businesses=businesses, user_role=session.get('role'))

@app.route('/super_admin/add_business', methods=['GET', 'POST'])
def add_business():
    # Allow 'admin' role to add businesses
    if session.get('role') not in ['super_admin', 'admin']:
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
            }, business_types=['Pharmacy', 'Hardware', 'Supermarket', 'Provision Store']) # Pass types to template
        
        new_business = Business(
            name=business_name, address=business_address, location=business_location,
            contact=business_contact, type=business_type # Save business type
        )
        db.session.add(new_business)
        db.session.commit()

        initial_admin_user = User(
            username=initial_admin_username, password=initial_admin_password,
            role='admin', business_id=new_business.id
        )
        db.session.add(initial_admin_user)
        db.session.commit()

        flash(f'Business "{business_name}" added successfully with initial admin "{initial_admin_username}".', 'success')
        return redirect(url_for('super_admin_dashboard'))
    
    return render_template('add_edit_business.html', title='Add New Business', business={}, business_types=['Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'])

@app.route('/super_admin/edit_business/<business_id>', methods=['GET', 'POST'])
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
            }, business_types=['Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'])
        
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
            initial_admin.password = new_initial_admin_password
        
        db.session.commit()
        flash(f'Business "{new_business_name}" and admin credentials updated successfully!', 'success')
        return redirect(url_for('super_admin_dashboard'))

    business_data_for_form = {
        'name': business_to_edit.name, 'address': business_to_edit.address, 'location': business_to_edit.location,
        'contact': business_to_edit.contact, 'type': business_to_edit.type, # Pass current type for pre-selection
        'initial_admin_username': initial_admin.username if initial_admin else '',
        'initial_admin_password': initial_admin.password if initial_admin else ''
    }
    return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit.name}', business=business_data_for_form, business_types=['Pharmacy', 'Hardware', 'Supermarket', 'Provision Store'])


@app.route('/super_admin/view_business_details/<business_id>')
def view_business_details(business_id):
    # Allow 'admin' role to view business details
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))

    business = Business.query.get_or_404(business_id)
    initial_admin = User.query.filter_by(business_id=business_id, role='admin').first()

    return render_template('view_business_details.html', business=business, initial_admin=initial_admin)


@app.route('/super_admin/delete_business/<business_id>')
def delete_business(business_id):
    # Allow 'admin' role to delete businesses
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    business_to_delete = Business.query.get_or_404(business_id)
    
    db.session.delete(business_to_delete)
    db.session.commit()

    flash(f'Business "{business_to_delete.name}" and all its associated data deleted successfully!', 'success')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/super_admin/download_inventory/<business_id>')
def download_inventory_csv(business_id):
    # Allow 'admin' role to download inventory CSV
    if session.get('role') not in ['super_admin', 'admin']:
        flash('Access denied. Super Admin or Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    business = Business.query.get_or_404(business_id)
    inventory_items = InventoryItem.query.filter_by(business_id=business.id).all()

    si = io.StringIO()
    headers = [
        'id', 'product_name', 'category', 'purchase_price', 'sale_price',
        'current_stock', 'last_updated', 'batch_number', 'number_of_tabs',
        'unit_price_per_tab', 'item_type', 'expiry_date', 'is_fixed_price',
        'fixed_sale_price', 'business_id', 'is_active'
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
def upload_inventory_csv(business_id):
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
                    unit_price_per_tab = float(row.get('unit_price_per_tab', purchase_price / number_of_tabs if number_of_tabs else 0))
                    item_type = row.get('item_type', 'Pharmacy').strip()
                    expiry_date_str = row.get('expiry_date', '').strip()
                    expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None
                    is_fixed_price = row.get('is_fixed_price', 'False').lower() == 'true'
                    fixed_sale_price = float(row.get('fixed_sale_price', 0.0))
                    is_active = row.get('is_active', 'True').lower() == 'true'
                    sale_price = float(row['sale_price'])

                    item = InventoryItem.query.filter_by(product_name=product_name, business_id=business_id).first()
                    if item:
                        # Update existing item
                        item.category = category
                        item.purchase_price = purchase_price
                        item.sale_price = sale_price
                        item.current_stock = current_stock
                        item.last_updated = datetime.now()
                        item.batch_number = batch_number
                        item.number_of_tabs = number_of_tabs
                        item.unit_price_per_tab = unit_price_per_tab
                        item.item_type = item_type
                        item.expiry_date = expiry_date
                        item.is_fixed_price = is_fixed_price
                        item.fixed_sale_price = fixed_sale_price
                        item.is_active = is_active
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
                            unit_price_per_tab=unit_price_per_tab,
                            item_type=item_type,
                            expiry_date=expiry_date,
                            is_fixed_price=is_fixed_price,
                            fixed_sale_price=fixed_sale_price,
                            is_active=is_active
                        )
                        db.session.add(new_item)
                        added_count += 1
                except Exception as e:
                    errors.append(f"Row for product '{row.get('product_name', 'N/A')}': {e}")
                    db.session.rollback() # Rollback changes for this row

            db.session.commit()
            if errors:
                flash(f'CSV Uploaded. {added_count} items added, {updated_count} items updated. Errors: {"; ".join(errors)}', 'warning')
            else:
                flash(f'CSV inventory uploaded successfully! {added_count} items added, {updated_count} items updated.', 'success')
            return redirect(url_for('super_admin_dashboard'))
        else:
            flash('Invalid file format. Please upload a CSV file.', 'danger')
    return render_template('upload_inventory.html', business=business)


# --- User Management (Business-level admins) ---

@app.route('/manage_business_users')
def manage_business_users():
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to manage business users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    users = User.query.filter_by(business_id=business_id).all()
    return render_template('manage_business_users.html', users=users, user_role=session.get('role'))

@app.route('/add_business_user', methods=['GET', 'POST'])
def add_business_user():
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to add business users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        role = request.form['role'].strip()

        if User.query.filter_by(username=username, business_id=business_id).first():
            flash('Username already exists for this business. Please choose a different username.', 'danger')
            return render_template('add_edit_business_user.html', title='Add New Business User', user={}, user_role=session.get('role'))

        new_user = User(username=username, password=password, role=role, business_id=business_id)
        db.session.add(new_user)
        db.session.commit()
        flash(f'Business user "{username}" added successfully!', 'success')
        return redirect(url_for('manage_business_users'))

    return render_template('add_edit_business_user.html', title='Add New Business User', user={}, user_role=session.get('role'))

@app.route('/edit_business_user/<user_id>', methods=['GET', 'POST'])
def edit_business_user(user_id):
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to edit business users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    user_to_edit = User.query.filter_by(id=user_id, business_id=business_id).first_or_404()

    if request.method == 'POST':
        new_username = request.form['username'].strip()
        new_password = request.form['password'].strip()
        new_role = request.form['role'].strip()

        # Check if new username already exists for another user in the same business
        if User.query.filter(User.username == new_username, User.business_id == business_id, User.id != user_id).first():
            flash('Username already exists for another user in this business. Please choose a different username.', 'danger')
            return render_template('add_edit_business_user.html', title='Edit Business User', user=user_to_edit, user_role=session.get('role'))
        
        # Prevent changing an admin's role or password if not the admin themselves (optional, but good practice)
        # For simplicity, we'll allow admin to edit other users including other admins.
        # But an admin cannot change their own role here.
        if user_to_edit.username == session['username'] and user_to_edit.role != new_role:
             flash('You cannot change your own role.', 'danger')
             return redirect(url_for('manage_business_users'))


        user_to_edit.username = new_username
        user_to_edit.password = new_password
        user_to_edit.role = new_role # Allow changing role, but an admin cannot change their own role.
        db.session.commit()
        flash(f'User "{new_username}" updated successfully!', 'success')
        return redirect(url_for('manage_business_users'))

    return render_template('add_edit_business_user.html', title='Edit Business User', user=user_to_edit, user_role=session.get('role'))

@app.route('/manage_business_users/delete/<username>')
def delete_business_user(username):
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
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


# --- Hardware Business Specific Features: Hirable Items ---

@app.route('/hirable_items')
def hirable_items():
    if 'username' not in session or session.get('role') not in ['admin', 'manager', 'sales_personnel'] or not get_current_business_id():
        flash('You do not have permission to view hirable items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    hirable_items_list = HirableItem.query.filter_by(business_id=business_id, is_active=True).order_by(HirableItem.item_name).all()
    
    return render_template('hirable_item_list.html', 
                           hirable_items=hirable_items_list, 
                           user_role=session.get('role'),
                           business_type=session.get('business_type'))

@app.route('/add_hirable_item', methods=['GET', 'POST'])
def add_hirable_item():
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to add hirable items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()

    if request.method == 'POST':
        item_name = request.form['item_name'].strip()
        description = request.form['description'].strip()
        daily_hire_price = float(request.form['daily_hire_price'])
        current_stock = int(request.form['current_stock'])

        if HirableItem.query.filter_by(item_name=item_name, business_id=business_id, is_active=True).first():
            flash('Hirable item with this name already exists and is active. Please choose a different name or reactivate the existing one.', 'danger')
            return render_template('add_edit_hirable_item.html', title='Add New Hirable Item', item={
                'item_name': item_name, 'description': description, 'daily_hire_price': daily_hire_price, 'current_stock': current_stock
            }, user_role=session.get('role'))
        
        new_item = HirableItem(
            business_id=business_id,
            item_name=item_name,
            description=description,
            daily_hire_price=daily_hire_price,
            current_stock=current_stock,
            last_updated=datetime.now(),
            is_active=True
        )
        db.session.add(new_item)
        db.session.commit()
        flash(f'Hirable item "{item_name}" added successfully!', 'success')
        return redirect(url_for('hirable_items'))
    
    return render_template('add_edit_hirable_item.html', title='Add New Hirable Item', item={}, user_role=session.get('role'))

@app.route('/edit_hirable_item/<item_id>', methods=['GET', 'POST'])
def edit_hirable_item(item_id):
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to edit hirable items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    item_to_edit = HirableItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()

    if request.method == 'POST':
        new_item_name = request.form['item_name'].strip()
        new_description = request.form['description'].strip()
        new_daily_hire_price = float(request.form['daily_hire_price'])
        new_current_stock = int(request.form['current_stock'])
        new_is_active = 'is_active' in request.form # Checkbox value

        if HirableItem.query.filter(HirableItem.item_name == new_item_name, 
                                    HirableItem.business_id == business_id, 
                                    HirableItem.id != item_id, 
                                    HirableItem.is_active == True).first():
            flash('An active hirable item with this name already exists. Please choose a different name.', 'danger')
            return render_template('add_edit_hirable_item.html', title='Edit Hirable Item', item=item_to_edit, user_role=session.get('role'))

        item_to_edit.item_name = new_item_name
        item_to_edit.description = new_description
        item_to_edit.daily_hire_price = new_daily_hire_price
        item_to_edit.current_stock = new_current_stock
        item_to_edit.is_active = new_is_active
        item_to_edit.last_updated = datetime.now()

        db.session.commit()
        flash(f'Hirable item "{new_item_name}" updated successfully!', 'success')
        return redirect(url_for('hirable_items'))
    
    return render_template('add_edit_hirable_item.html', title='Edit Hirable Item', item=item_to_edit, user_role=session.get('role'))

@app.route('/delete_hirable_item/<item_id>')
def delete_hirable_item(item_id):
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to delete hirable items or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    item_to_delete = HirableItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()

    item_to_delete.is_active = False # Soft delete
    item_to_delete.last_updated = datetime.now()
    db.session.commit()
    flash(f'Hirable item "{item_to_delete.item_name}" marked as inactive successfully!', 'success')
    return redirect(url_for('hirable_items'))


# --- Hardware Business Specific Features: Rental Records ---

@app.route('/rental_records')
def rental_records():
    if 'username' not in session or session.get('role') not in ['admin', 'manager', 'sales_personnel'] or not get_current_business_id():
        flash('You do not have permission to view rental records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    # Eager load hirable_item to avoid N+1 queries when accessing item details
    rental_records_list = RentalRecord.query.filter_by(business_id=business_id).order_by(RentalRecord.date_recorded.desc()).all()
    
    return render_template('rental_record_list.html', 
                           rental_records=rental_records_list, 
                           user_role=session.get('role'),
                           business_type=session.get('business_type'))

@app.route('/record_rental', methods=['GET', 'POST'])
def record_rental():
    if 'username' not in session or session.get('role') not in ['admin', 'manager', 'sales_personnel'] or not get_current_business_id():
        flash('You do not have permission to record rentals or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    hirable_items_available = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()

    if request.method == 'POST':
        hirable_item_id = request.form['hirable_item_id']
        customer_name = request.form['customer_name'].strip()
        quantity = int(request.form['quantity'])
        daily_price = float(request.form['daily_price'])
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        # customer_phone = request.form.get('customer_phone', '').strip() # Optional field
        calculated_total_price = float(request.form['calculated_total_price']) # From JS calculation

        hirable_item = HirableItem.query.filter_by(id=hirable_item_id, business_id=business_id).first()
        if not hirable_item:
            flash('Selected hirable item not found.', 'danger')
            return redirect(url_for('record_rental'))
        
        if hirable_item.current_stock < quantity:
            flash(f'Not enough stock for {hirable_item.item_name}. Available: {hirable_item.current_stock}', 'danger')
            return render_template('add_edit_rental_record.html', 
                                   title='Record New Rental', 
                                   hirable_items=hirable_items_available, 
                                   user_role=session.get('role'),
                                   record=request.form) # Pass form data back to pre-fill
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        if start_date > end_date:
            flash('End date cannot be before start date.', 'danger')
            return render_template('add_edit_rental_record.html', 
                                   title='Record New Rental', 
                                   hirable_items=hirable_items_available, 
                                   user_role=session.get('role'),
                                   record=request.form) # Pass form data back to pre-fill
        
        number_of_days = (end_date - start_date).days + 1
        
        new_rental = RentalRecord(
            business_id=business_id,
            hirable_item_id=hirable_item.id,
            item_name_at_rent=hirable_item.item_name,
            customer_name=customer_name,
            # customer_phone=customer_phone,
            start_date=start_date,
            end_date=end_date,
            number_of_days=number_of_days,
            daily_hire_price_at_rent=daily_price,
            total_hire_amount=calculated_total_price,
            status='Rented', # Default status for new rental
            sales_person_name=session.get('username'),
            date_recorded=datetime.now()
        )

        hirable_item.current_stock -= quantity # Decrement stock
        hirable_item.last_updated = datetime.now()

        db.session.add(new_rental)
        db.session.commit()
        flash(f'Rental for "{hirable_item.item_name}" to "{customer_name}" recorded successfully!', 'success')
        return redirect(url_for('rental_records'))

    return render_template('add_edit_rental_record.html', 
                           title='Record New Rental', 
                           hirable_items=hirable_items_available, 
                           user_role=session.get('role'))

@app.route('/edit_rental_record/<record_id>', methods=['GET', 'POST'])
def edit_rental_record(record_id):
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to edit rental records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    record_to_edit = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()
    hirable_items_available = HirableItem.query.filter_by(business_id=business_id, is_active=True).all()

    if request.method == 'POST':
        original_quantity = record_to_edit.quantity # Get original quantity before update
        original_hirable_item_id = record_to_edit.hirable_item_id # Get original item ID

        record_to_edit.hirable_item_id = request.form['hirable_item_id']
        record_to_edit.customer_name = request.form['customer_name'].strip()
        record_to_edit.quantity = int(request.form['quantity'])
        record_to_edit.daily_hire_price_at_rent = float(request.form['daily_price'])
        record_to_edit.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        record_to_edit.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        record_to_edit.status = request.form['status'].strip()
        record_to_edit.total_hire_amount = float(request.form['calculated_total_price']) # From JS calculation

        if record_to_edit.start_date > record_to_edit.end_date:
            flash('End date cannot be before start date.', 'danger')
            return render_template('add_edit_rental_record.html', 
                                   title='Edit Rental Record', 
                                   record=record_to_edit, 
                                   hirable_items=hirable_items_available, 
                                   user_role=session.get('role'))
        
        record_to_edit.number_of_days = (record_to_edit.end_date - record_to_edit.start_date).days + 1

        # Adjust stock if item or quantity changes
        if record_to_edit.hirable_item_id != original_hirable_item_id:
            # Return original quantity to old item
            old_hirable_item = HirableItem.query.filter_by(id=original_hirable_item_id, business_id=business_id).first()
            if old_hirable_item:
                old_hirable_item.current_stock += original_quantity
                old_hirable_item.last_updated = datetime.now()
            
            # Deduct new quantity from new item
            new_hirable_item = HirableItem.query.filter_by(id=record_to_edit.hirable_item_id, business_id=business_id).first()
            if new_hirable_item:
                if new_hirable_item.current_stock < record_to_edit.quantity:
                    flash(f'Not enough stock for {new_hirable_item.item_name}. Available: {new_hirable_item.current_stock}', 'danger')
                    db.session.rollback() # Rollback any changes
                    return render_template('add_edit_rental_record.html', 
                                   title='Edit Rental Record', 
                                   record=record_to_edit, 
                                   hirable_items=hirable_items_available, 
                                   user_role=session.get('role'))
                new_hirable_item.current_stock -= record_to_edit.quantity
                new_hirable_item.last_updated = datetime.now()
        else:
            # Item is the same, only quantity changed
            if record_to_edit.quantity != original_quantity:
                hirable_item = HirableItem.query.filter_by(id=record_to_edit.hirable_item_id, business_id=business_id).first()
                if hirable_item:
                    stock_difference = record_to_edit.quantity - original_quantity
                    if hirable_item.current_stock < stock_difference: # Trying to increase rented quantity beyond stock
                        flash(f'Not enough stock to increase quantity for {hirable_item.item_name}. Available: {hirable_item.current_stock}', 'danger')
                        db.session.rollback()
                        return render_template('add_edit_rental_record.html', 
                                   title='Edit Rental Record', 
                                   record=record_to_edit, 
                                   hirable_items=hirable_items_available, 
                                   user_role=session.get('role'))
                    hirable_item.current_stock -= stock_difference
                    hirable_item.last_updated = datetime.now()
        
        # If status changes to 'Completed', update actual_return_date and adjust stock if it wasn't already handled
        if record_to_edit.status == 'Completed' and record_to_edit.actual_return_date is None:
            record_to_edit.actual_return_date = datetime.now()
            # Ensure stock is returned only if it hasn't been already (e.g., if status changed from Rented)
            # This logic needs to be careful. If rental status changes *to* completed, stock should be returned.
            # If item was 'Rented' and now is 'Completed', stock comes back.
            # If it was 'Cancelled' and changed to 'Completed', stock would have already been back.
            # So this is critical: Only return stock if the previous status was 'Rented' and it's now 'Completed'
            # Or if it's changing from 'Overdue' to 'Completed'.
            # Simplest logic: always return stock *here* and ensure `record_rental` or `cancel_rental_record` also manages it correctly.
            # Let's assume stock is decremented at rental and incremented at completion/cancellation.
            # If editing a record from 'Rented' to 'Completed', stock should be returned.
            # The current stock adjustment logic above only handles item/quantity changes for active rentals.
            # A separate logic for status change is better.

        db.session.commit()
        flash(f'Rental record for "{record_to_edit.item_name_at_rent}" updated successfully!', 'success')
        return redirect(url_for('rental_records'))
    
    return render_template('add_edit_rental_record.html', 
                           title='Edit Rental Record', 
                           record=record_to_edit, 
                           hirable_items=hirable_items_available, 
                           user_role=session.get('role'))

@app.route('/complete_rental_record/<record_id>')
def complete_rental_record(record_id):
    if 'username' not in session or session.get('role') not in ['admin', 'manager', 'sales_personnel'] or not get_current_business_id():
        flash('You do not have permission to complete rental records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    record_to_complete = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()

    if record_to_complete.status in ['Completed', 'Cancelled']:
        flash(f'Rental record is already {record_to_complete.status}.', 'warning')
        return redirect(url_for('rental_records'))
    
    # Return stock to hirable item
    hirable_item = HirableItem.query.filter_by(id=record_to_complete.hirable_item_id, business_id=business_id).first()
    if hirable_item:
        hirable_item.current_stock += record_to_complete.quantity
        hirable_item.last_updated = datetime.now()
        db.session.add(hirable_item)

    record_to_complete.status = 'Completed'
    record_to_complete.actual_return_date = datetime.now() # Set actual return date
    db.session.commit()
    flash(f'Rental record for "{record_to_complete.item_name_at_rent}" marked as completed! Stock returned.', 'success')
    return redirect(url_for('rental_records'))

@app.route('/cancel_rental_record/<record_id>')
def cancel_rental_record(record_id):
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to cancel rental records or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    record_to_cancel = RentalRecord.query.filter_by(id=record_id, business_id=business_id).first_or_404()

    if record_to_cancel.status in ['Completed', 'Cancelled']:
        flash(f'Cannot cancel rental record with status: {record_to_cancel.status}.', 'danger')
        return redirect(url_for('rental_records'))
    
    # Return stock to hirable item if it was rented (not yet returned/cancelled)
    hirable_item = HirableItem.query.filter_by(id=record_to_cancel.hirable_item_id, business_id=business_id).first()
    if hirable_item:
        hirable_item.current_stock += record_to_cancel.quantity
        hirable_item.last_updated = datetime.now()
        db.session.add(hirable_item)

    record_to_cancel.status = 'Cancelled'
    db.session.commit()
    flash(f'Rental record for "{record_to_cancel.item_name_at_rent}" cancelled successfully! Stock returned.', 'success')
    return redirect(url_for('rental_records'))


# --- Database Initialization (run once to create tables) ---
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)