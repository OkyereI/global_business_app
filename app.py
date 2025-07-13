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

                    if is_fixed_price:
                        sale_price = fixed_sale_price
                        unit_price_per_tab_with_markup = fixed_sale_price / number_of_tabs
                    else:
                        cost_per_tab = purchase_price / number_of_tabs
                        if item_type == 'Provision Store':
                            unit_price_per_tab_with_markup = cost_per_tab * (1.10 if purchase_price >= 1000 else 1.08)
                        elif item_type == 'Hardware Material':
                            unit_price_per_tab_with_markup = cost_per_tab * 1.15
                        elif item_type == 'Supermarket': # New markup for Supermarket
                            unit_price_per_tab_with_markup = cost_per_tab * 1.20 # Example: 20% markup
                        else: # Default to Pharmacy
                            unit_price_per_tab_with_markup = cost_per_tab * 1.30
                        sale_price = unit_price_per_tab_with_markup * number_of_tabs 

                    existing_item = InventoryItem.query.filter_by(product_name=product_name, business_id=business.id).first()

                    if existing_item:
                        # Update existing item
                        existing_item.category = category
                        existing_item.purchase_price = purchase_price
                        existing_item.sale_price = sale_price
                        existing_item.current_stock = current_stock # Overwrite stock with CSV value
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
                            business_id=business.id,
                            product_name=product_name,
                            category=category,
                            purchase_price=purchase_price,
                            sale_price=sale_price,
                            current_stock=current_stock,
                            last_updated=datetime.now(),
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
            
            if errors:
                db.session.rollback()
                flash(f'CSV upload completed with {added_count} items added, {updated_count} items updated, and {len(errors)} errors. Please check the errors below.', 'warning')
                for error in errors:
                    flash(f'Error: {error}', 'danger')
            else:
                db.session.commit()
                flash(f'CSV inventory uploaded successfully! {added_count} items added, {updated_count} items updated.', 'success')
            
            return redirect(url_for('super_admin_dashboard'))
        else:
            flash('Invalid file type. Please upload a CSV file.', 'danger')

    return render_template('upload_inventory_csv.html', business=business)


# --- Business User Management (Admin & Viewer Admin) ---

@app.route('/manage_business_users')
def manage_business_users():
    if 'username' not in session or session.get('role') not in ['admin', 'viewer_admin'] or not get_current_business_id():
        flash('You do not have permission to manage users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    users = User.query.filter_by(business_id=business_id).all()
    return render_template('manage_business_users.html', users=users, user_role=session.get('role'))

@app.route('/add_edit_business_user', methods=['GET', 'POST'])
@app.route('/add_edit_business_user/<username>', methods=['GET', 'POST'])
def add_edit_business_user(username=None):
    if 'username' not in session or session.get('role') not in ['admin', 'viewer_admin'] or not get_current_business_id():
        flash('You do not have permission to manage users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    user_to_edit = None
    if username:
        user_to_edit = User.query.filter_by(username=username, business_id=business_id).first_or_404()
        if session.get('role') == 'viewer_admin' and user_to_edit.role == 'admin':
            flash('Viewer admins cannot edit admin users.', 'danger')
            return redirect(url_for('manage_business_users'))

    title = 'Add New User' if not username else f'Edit User: {username}'

    if request.method == 'POST':
        new_username = request.form['username'].strip()
        new_password = request.form['password'].strip()
        new_role = request.form['role'].strip()

        if session.get('role') == 'viewer_admin' and new_role != 'sales':
            flash('Viewer admins can only add/edit sales users.', 'danger')
            return render_template('add_edit_business_user.html', title=title, user=request.form, user_role=session.get('role'))

        if user_to_edit:
            if new_username != username and \
               User.query.filter_by(username=new_username, business_id=business_id).first():
                flash('Username already exists for this business.', 'danger')
                return render_template('add_edit_business_user.html', title=title, user=request.form, user_role=session.get('role'))
            
            user_to_edit.username = new_username
            user_to_edit.password = new_password
            user_to_edit.role = new_role
            flash(f'User "{new_username}" updated successfully!', 'success')
        else:
            if User.query.filter_by(username=new_username, business_id=business_id).first():
                flash('Username already exists for this business.', 'danger')
                return render_template('add_edit_business_user.html', title=title, user=request.form, user_role=session.get('role'))
            
            new_user = User(username=new_username, password=new_password, role=new_role, business_id=business_id)
            db.session.add(new_user)
            flash(f'User "{new_username}" added successfully!', 'success')
        
        db.session.commit()
        return redirect(url_for('manage_business_users'))

    return render_template('add_edit_business_user.html', title=title, user=user_to_edit, user_role=session.get('role'))

@app.route('/delete_business_user/<username>')
def delete_business_user(username):
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to delete users or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    user_to_delete = User.query.filter_by(username=username, business_id=business_id).first_or_404()
    
    if user_to_delete.role == 'admin':
        flash('Cannot delete another admin user or yourself.', 'danger')
        return redirect(url_for('manage_business_users'))

    db.session.delete(user_to_delete)
    db.session.commit()
    flash(f'User "{username}" deleted successfully!', 'success')
    return redirect(url_for('manage_business_users'))


# --- Inventory Management Routes ---

@app.route('/inventory')
def inventory():
    if 'username' not in session or not get_current_business_id():
        flash('Please log in and select a business to access this page.', 'warning')
        return redirect(url_for('login'))
    
    business_id = get_current_business_id()
    search_query = request.args.get('search', '').strip()

    # Only retrieve active inventory items by default
    items_query = InventoryItem.query.filter_by(business_id=business_id, is_active=True)

    if search_query:
        items_query = items_query.filter(
            InventoryItem.product_name.ilike(f'%{search_query}%') |
            InventoryItem.category.ilike(f'%{search_query}%') |
            InventoryItem.batch_number.ilike(f'%{search_query}%')
        )

    items = items_query.all()

    # Add expiry date logic to each item
    today = date.today()
    for item in items:
        item.expires_soon = False # Default
        if item.expiry_date:
            time_to_expiry = item.expiry_date - today
            if time_to_expiry.days <= 180 and time_to_expiry.days >= 0: # Within 6 months and not expired
                item.expires_soon = True
            elif time_to_expiry.days < 0: # Already expired
                item.expires_soon = 'Expired'
    
    return render_template('inventory_list.html', items=items, user_role=session.get('role'), business_type=session.get('business_type'), search_query=search_query)

@app.route('/inventory/add', methods=['GET', 'POST'])
def add_inventory():
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to add inventory items or no business selected.', 'danger')
        return redirect(url_for('inventory'))
        
    business_id = get_current_business_id()
    business_type = session.get('business_type')

    # Item types will depend on business type
    if business_type == 'Hardware':
        item_types_options = ['Hardware Material']
    elif business_type == 'Supermarket' or business_type == 'Provision Store':
        item_types_options = ['Provision Store'] # Supermarket and Provision Store will primarily sell 'Provision Store' items
    else: # Pharmacy or others
        item_types_options = ['Pharmacy', 'Provision Store']

    # Get other businesses of the same type for import functionality
    other_businesses = []
    if session.get('role') == 'admin':
        current_business = Business.query.get(business_id)
        if current_business:
            other_businesses = Business.query.filter(
                Business.type == current_business.type,
                Business.id != current_business.id
            ).all()

    if request.method == 'POST':
        product_name = request.form['product_name'].strip()
        category = request.form['category'].strip()
        purchase_price = float(request.form['purchase_price'])
        added_stock = float(request.form['current_stock'])
        batch_number = request.form['batch_number'].strip()
        number_of_tabs = int(request.form['number_of_tabs']) # Renamed to 'units' or 'pieces' for hardware
        item_type = request.form['item_type']
        expiry_date_str = request.form['expiry_date'].strip()
        
        # Convert expiry_date_str to date object for validation and re-rendering
        expiry_date_obj = None
        if expiry_date_str:
            try:
                expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid expiry date format. Please use YYYY-MM-DD.', 'danger')
                # Prepare item_data_for_form with original string for re-rendering
                item_data_for_form = {k: v for k, v in request.form.items()}
                item_data_for_form['expiry_date'] = expiry_date_str # Keep original string for display
                return render_template('add_edit_inventory.html', title='Add Inventory Item', item=item_data_for_form, user_role=session.get('role'), item_types=item_types_options, business_type=business_type, other_businesses=other_businesses)


        is_fixed_price = 'is_fixed_price' in request.form
        fixed_sale_price = float(request.form['fixed_sale_price']) if is_fixed_price else 0.0

        if number_of_tabs <= 0:
            flash('Number of units/pieces per pack must be greater than zero.', 'danger')
            # Prepare item_data_for_form with original string for re-rendering
            item_data_for_form = {k: v for k, v in request.form.items()}
            item_data_for_form['expiry_date'] = expiry_date_obj # Pass the date object
            return render_template('add_edit_inventory.html', title='Add Inventory Item', item=item_data_for_form, user_role=session.get('role'), item_types=item_types_options, business_type=business_type, other_businesses=other_businesses)

        sale_price = 0.0
        unit_price_per_tab_with_markup = 0.0

        if is_fixed_price:
            sale_price = fixed_sale_price
            unit_price_per_tab_with_markup = fixed_sale_price / number_of_tabs
        else:
            cost_per_tab = purchase_price / number_of_tabs
            if item_type == 'Provision Store':
                unit_price_per_tab_with_markup = cost_per_tab * (1.10 if purchase_price >= 1000 else 1.08)
            elif item_type == 'Hardware Material': # New markup logic for Hardware
                unit_price_per_tab_with_markup = cost_per_tab * 1.15 # Example: 15% markup for hardware
            elif item_type == 'Supermarket': # New markup for Supermarket
                unit_price_per_tab_with_markup = cost_per_tab * 1.20 # Example: 20% markup
            else: # Default to Pharmacy
                unit_price_per_tab_with_markup = cost_per_tab * 1.30
            sale_price = unit_price_per_tab_with_markup * number_of_tabs 

        existing_item = InventoryItem.query.filter_by(product_name=product_name, business_id=business_id).first()

        if existing_item:
            existing_item.current_stock += added_stock
            existing_item.category = category
            existing_item.purchase_price = purchase_price
            existing_item.sale_price = sale_price
            existing_item.last_updated = datetime.now()
            existing_item.batch_number = batch_number
            existing_item.number_of_tabs = number_of_tabs
            existing_item.unit_price_per_tab = unit_price_per_tab_with_markup
            existing_item.item_type = item_type
            existing_item.expiry_date = expiry_date_obj
            existing_item.is_fixed_price = is_fixed_price
            existing_item.fixed_sale_price = fixed_sale_price
            existing_item.is_active = True # Ensure item is active if stock is added
            db.session.commit()
            flash(f'Stock for {product_name} updated successfully! New stock: {existing_item.current_stock:.2f}', 'success')
        else:
            new_item = InventoryItem(
                business_id=business_id,
                product_name=product_name,
                category=category,
                purchase_price=purchase_price,
                sale_price=sale_price,
                current_stock=added_stock,
                last_updated=datetime.now(),
                batch_number=batch_number,
                number_of_tabs=number_of_tabs,
                unit_price_per_tab=unit_price_per_tab_with_markup,
                item_type=item_type,
                expiry_date=expiry_date_obj,
                is_fixed_price=is_fixed_price,
                fixed_sale_price=fixed_sale_price,
                is_active=True # New items are active
            )
            db.session.add(new_item)
            db.session.commit()
            flash('Inventory item added successfully!', 'success')
        
        return redirect(url_for('inventory'))
    
    default_item = {
        'product_name': '', 'category': '', 'purchase_price': 0.0, 'current_stock': 0.0,
        'batch_number': '', 'number_of_tabs': 1, 'item_type': item_types_options[0], 'expiry_date': '',
        'is_fixed_price': False, 'fixed_sale_price': 0.0, 'sale_price': 0.0, 'unit_price_per_tab': 0.0
    }
    return render_template('add_edit_inventory.html', title='Add Inventory Item', item=default_item, user_role=session.get('role'), item_types=item_types_options, business_type=business_type, other_businesses=other_businesses)

@app.route('/inventory/edit/<item_id>', methods=['GET', 'POST'])
def edit_inventory(item_id):
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to edit inventory items or no business selected.', 'danger')
        return redirect(url_for('inventory'))

    business_id = get_current_business_id()
    business_type = session.get('business_type')
    item_to_edit = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()

    if business_type == 'Hardware':
        item_types_options = ['Hardware Material']
    elif business_type == 'Supermarket' or business_type == 'Provision Store':
        item_types_options = ['Provision Store']
    else:
        item_types_options = ['Pharmacy', 'Provision Store']

    # Get other businesses of the same type for import functionality (even on edit page, for consistency)
    other_businesses = []
    if session.get('role') == 'admin':
        current_business = Business.query.get(business_id)
        if current_business:
            other_businesses = Business.query.filter(
                Business.type == current_business.type,
                Business.id != current_business.id
            ).all()

    if request.method == 'POST':
        item_to_edit.product_name = request.form['product_name'].strip()
        item_to_edit.category = request.form['category'].strip()
        purchase_price = float(request.form['purchase_price'])
        number_of_tabs = int(request.form['number_of_tabs'])
        item_type = request.form['item_type']
        expiry_date_str = request.form['expiry_date'].strip()
        
        # Convert expiry_date_str to date object for validation and re-rendering
        expiry_date_obj = None
        if expiry_date_str:
            try:
                expiry_date_obj = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid expiry date format. Please use YYYY-MM-DD.', 'danger')
                # Prepare item_data_for_form with original string for re-rendering
                item_data_for_form = {k: v for k, v in request.form.items()}
                item_data_for_form['expiry_date'] = expiry_date_str # Keep original string for display
                return render_template('add_edit_inventory.html', title='Edit Inventory Item', item=item_data_for_form, user_role=session.get('role'), item_types=item_types_options, business_type=business_type, other_businesses=other_businesses)


        is_fixed_price = 'is_fixed_price' in request.form
        fixed_sale_price = float(request.form['fixed_sale_price']) if is_fixed_price else 0.0

        if number_of_tabs <= 0:
            flash('Number of units/pieces per pack must be greater than zero.', 'danger')
            # Prepare item_data_for_form with original string for re-rendering
            item_data_for_form = {k: v for k, v in request.form.items()}
            item_data_for_form['expiry_date'] = expiry_date_obj # Pass the date object
            return render_template('add_edit_inventory.html', title='Edit Inventory Item', item=item_data_for_form, user_role=session.get('role'), item_types=item_types_options, business_type=business_type, other_businesses=other_businesses)

        sale_price = 0.0
        unit_price_per_tab_with_markup = 0.0

        if is_fixed_price:
            sale_price = fixed_sale_price
            unit_price_per_tab_with_markup = fixed_sale_price / number_of_tabs
        else:
            cost_per_tab = purchase_price / number_of_tabs
            if item_type == 'Provision Store':
                unit_price_per_tab_with_markup = cost_per_tab * (1.10 if purchase_price >= 1000 else 1.08)
            elif item_type == 'Hardware Material': # New markup logic for Hardware
                unit_price_per_tab_with_markup = cost_per_tab * 1.15
            elif item_type == 'Supermarket': # New markup for Supermarket
                unit_price_per_tab_with_markup = cost_per_tab * 1.20
            else:
                unit_price_per_tab_with_markup = cost_per_tab * 1.30
            sale_price = unit_price_per_tab_with_markup * number_of_tabs 
        
        item_to_edit.purchase_price = purchase_price
        item_to_edit.sale_price = sale_price
        item_to_edit.current_stock = float(request.form['current_stock'])
        item_to_edit.last_updated = datetime.now()
        item_to_edit.batch_number = request.form['batch_number'].strip()
        item_to_edit.number_of_tabs = number_of_tabs
        item_to_edit.unit_price_per_tab = unit_price_per_tab_with_markup
        item_to_edit.item_type = item_type
        item_to_edit.expiry_date = expiry_date_obj
        item_to_edit.is_fixed_price = is_fixed_price
        item_to_edit.fixed_sale_price = fixed_sale_price
        db.session.commit()
        flash('Inventory item updated successfully!', 'success')
        return redirect(url_for('inventory'))

    item_data_for_form = {
        'id': item_to_edit.id, 'product_name': item_to_edit.product_name, 'category': item_to_edit.category,
        'purchase_price': item_to_edit.purchase_price, 'current_stock': item_to_edit.current_stock,
        'batch_number': item_to_edit.batch_number, 'number_of_tabs': item_to_edit.number_of_tabs,
        'item_type': item_to_edit.item_type,
        'expiry_date': item_to_edit.expiry_date, # Pass the date object directly
        'is_fixed_price': item_to_edit.is_fixed_price, 'fixed_sale_price': item_to_edit.fixed_sale_price,
        'sale_price': item_to_edit.sale_price, 'unit_price_per_tab': item_to_edit.unit_price_per_tab
    }
    return render_template('add_edit_inventory.html', title='Edit Inventory Item', item=item_data_for_form, user_role=session.get('role'), item_types=item_types_options, business_type=business_type, other_businesses=other_businesses)

# New route for admin to download inventory CSV for their business
@app.route('/inventory/download_csv')
def download_inventory_for_business():
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to download inventory.', 'danger')
        return redirect(url_for('inventory'))

    business_id = get_current_business_id()
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

# New route for admin to upload inventory CSV for their business
@app.route('/inventory/upload_csv', methods=['GET', 'POST'])
def upload_inventory_for_business():
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to upload inventory.', 'danger')
        return redirect(url_for('inventory'))

    business_id = get_current_business_id()
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
                    is_active = row.get('is_active', 'True').lower() == 'true'

                    if number_of_tabs <= 0:
                        errors.append(f"Skipping '{product_name}': 'Number of units/pieces per pack' must be greater than zero.")
                        continue

                    sale_price = 0.0
                    unit_price_per_tab_with_markup = 0.0

                    if is_fixed_price:
                        sale_price = fixed_sale_price
                        unit_price_per_tab_with_markup = fixed_sale_price / number_of_tabs
                    else:
                        cost_per_tab = purchase_price / number_of_tabs
                        if item_type == 'Provision Store':
                            unit_price_per_tab_with_markup = cost_per_tab * (1.10 if purchase_price >= 1000 else 1.08)
                        elif item_type == 'Hardware Material':
                            unit_price_per_tab_with_markup = cost_per_tab * 1.15
                        elif item_type == 'Supermarket':
                            unit_price_per_tab_with_markup = cost_per_tab * 1.20
                        else:
                            unit_price_per_tab_with_markup = cost_per_tab * 1.30
                        sale_price = unit_price_per_tab_with_markup * number_of_tabs 

                    existing_item = InventoryItem.query.filter_by(product_name=product_name, business_id=business.id).first()

                    if existing_item:
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
                        existing_item.is_active = is_active
                        updated_count += 1
                    else:
                        new_item = InventoryItem(
                            business_id=business.id,
                            product_name=product_name,
                            category=category,
                            purchase_price=purchase_price,
                            sale_price=sale_price,
                            current_stock=current_stock,
                            last_updated=datetime.now(),
                            batch_number=batch_number,
                            number_of_tabs=number_of_tabs,
                            unit_price_per_tab=unit_price_per_tab_with_markup,
                            item_type=item_type,
                            expiry_date=expiry_date_obj,
                            is_fixed_price=is_fixed_price,
                            fixed_sale_price=fixed_sale_price,
                            is_active=is_active
                        )
                        db.session.add(new_item)
                        added_count += 1
                except Exception as e:
                    errors.append(f"Error processing row for product '{row.get('product_name', 'N/A')}': {e}")
            
            if errors:
                db.session.rollback()
                flash(f'CSV upload completed with {added_count} items added, {updated_count} items updated, and {len(errors)} errors. Please check the errors below.', 'warning')
                for error in errors:
                    flash(f'Error: {error}', 'danger')
            else:
                db.session.commit()
                flash(f'CSV inventory uploaded successfully! {added_count} items added, {updated_count} items updated.', 'success')
            
            return redirect(url_for('inventory'))
        else:
            flash('Invalid file type. Please upload a CSV file.', 'danger')

    return render_template('upload_inventory_csv.html', business=business) # Re-use the super_admin template for simplicity


# New route for importing products from other businesses
@app.route('/inventory/import_from_other_businesses', methods=['POST'])
def import_products_from_other_businesses():
    if 'username' not in session or session.get('role') != 'admin' or not get_current_business_id():
        flash('You do not have permission to import products.', 'danger')
        return redirect(url_for('inventory'))

    current_business_id = get_current_business_id()
    current_business_type = session.get('business_type')
    source_business_id = request.form.get('source_business_id')

    if not source_business_id:
        flash('Please select a business to import from.', 'danger')
        return redirect(url_for('add_inventory')) # Redirect back to add_inventory to show the form

    source_business = Business.query.get(source_business_id)
    if not source_business or source_business.type != current_business_type:
        flash('Invalid source business selected or business types do not match.', 'danger')
        return redirect(url_for('add_inventory'))

    source_items = InventoryItem.query.filter_by(business_id=source_business_id, is_active=True).all()
    
    imported_count = 0
    skipped_count = 0
    skipped_products = []

    for item in source_items:
        existing_item = InventoryItem.query.filter_by(product_name=item.product_name, business_id=current_business_id).first()
        if existing_item:
            skipped_count += 1
            skipped_products.append(item.product_name)
        else:
            # Create a new item for the current business
            new_item = InventoryItem(
                business_id=current_business_id,
                product_name=item.product_name,
                category=item.category,
                purchase_price=item.purchase_price,
                current_stock=0.0, # Start with 0 stock, admin can add later
                last_updated=datetime.now(),
                batch_number=item.batch_number,
                number_of_tabs=item.number_of_tabs,
                item_type=item.item_type,
                expiry_date=item.expiry_date,
                is_fixed_price=item.is_fixed_price,
                is_active=True # Imported items are active
            )

            # Recalculate sale price and unit price based on current business's markup rules
            if new_item.is_fixed_price:
                new_item.fixed_sale_price = item.fixed_sale_price
                new_item.sale_price = item.fixed_sale_price
                new_item.unit_price_per_tab = item.fixed_sale_price / new_item.number_of_tabs if new_item.number_of_tabs > 0 else 0.0
            else:
                cost_per_tab = new_item.purchase_price / new_item.number_of_tabs if new_item.number_of_tabs > 0 else 0.0
                unit_price_per_tab_with_markup = 0.0
                if new_item.item_type == 'Provision Store':
                    unit_price_per_tab_with_markup = cost_per_tab * (1.10 if new_item.purchase_price >= 1000 else 1.08)
                elif new_item.item_type == 'Hardware Material':
                    unit_price_per_tab_with_markup = cost_per_tab * 1.15
                elif new_item.item_type == 'Supermarket':
                    unit_price_per_tab_with_markup = cost_per_tab * 1.20
                else: # Default to Pharmacy
                    unit_price_per_tab_with_markup = cost_per_tab * 1.30
                
                new_item.unit_price_per_tab = unit_price_per_tab_with_markup
                new_item.sale_price = unit_price_per_tab_with_markup * new_item.number_of_tabs
                new_item.fixed_sale_price = 0.0 # Ensure fixed_sale_price is 0 if not fixed

            db.session.add(new_item)
            imported_count += 1
    
    db.session.commit()

    if imported_count > 0:
        flash(f'Successfully imported {imported_count} products from {source_business.name}.', 'success')
    if skipped_count > 0:
        flash(f'Skipped {skipped_count} products because they already exist: {", ".join(skipped_products[:5])}{"..." if len(skipped_products) > 5 else ""}.', 'warning')
    if imported_count == 0 and skipped_count == 0:
        flash('No products found to import from the selected business.', 'info')

    return redirect(url_for('inventory'))


@app.route('/inventory/delete/<item_id>')
def delete_inventory(item_id):
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to delete inventory items or no business selected.', 'danger')
        return redirect(url_for('inventory'))

    business_id = get_current_business_id()
    item_to_delete = InventoryItem.query.filter_by(id=item_id, business_id=business_id).first_or_404()
    
    # Instead of deleting, mark as inactive (soft delete)
    if SaleRecord.query.filter_by(product_id=item_id).first():
        item_to_delete.is_active = False
        db.session.commit()
        flash(f'Inventory item "{item_to_delete.product_name}" marked as inactive because it has associated sales records. It will no longer appear in active inventory lists.', 'info')
    else:
        # If no sales records, proceed with hard delete (optional, but cleaner for truly unused items)
        db.session.delete(item_to_delete)
        db.session.commit()
        flash(f'Inventory item "{item_to_delete.product_name}" deleted permanently.', 'success')
    
    return redirect(url_for('inventory'))

# --- Daily Sales Management Routes ---

@app.route('/sales')
def sales():
    if 'username' not in session or not get_current_business_id():
        flash('Please log in and select a business to access this page.', 'warning')
        return redirect(url_for('login'))
    
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

        # Augment the sale record with expiry info
        sale_data = {
            'id': sale.id,
            'product_id': sale.product_id,
            'product_name': sale.product_name,
            'quantity_sold': sale.quantity_sold,
            'sale_unit_type': sale.sale_unit_type,
            'price_at_time_per_unit_sold': sale.price_at_time_per_unit_sold,
            'total_amount': sale.total_amount,
            'sale_date': sale.sale_date,
            'customer_phone': sale.customer_phone,
            'sales_person_name': sale.sales_person_name,
            'reference_number': sale.reference_number,
            'transaction_id': sale.transaction_id,
            'expiry_date': sale_item_expiry_date, # Pass expiry date
            'expires_soon': sale_item_expires_soon # Pass expiry status
        }

        if transaction_id not in transactions:
            transactions[transaction_id] = {
                'id': transaction_id,
                'sale_date': sale.sale_date.strftime('%Y-%m-%d %H:%M:%S'),
                'customer_phone': sale.customer_phone,
                'sales_person_name': sale.sales_person_name,
                'total_amount': 0.0,
                'items': [],
                'reference_number': sale.reference_number
            }
        transactions[transaction_id]['items'].append(sale_data)
        transactions[transaction_id]['total_amount'] += sale.total_amount

    sorted_transactions = sorted(list(transactions.values()), 
                                 key=lambda x: datetime.strptime(x['sale_date'], '%Y-%m-%d %H:%M:%S'), 
                                 reverse=True)
    
    # Calculate total for currently displayed sales
    total_displayed_sales = sum(t['total_amount'] for t in sorted_transactions)

    return render_template('sales_list.html', transactions=sorted_transactions, user_role=session.get('role'), business_type=session.get('business_type'), search_query=search_query, total_displayed_sales=total_displayed_sales)


@app.route('/sales/add', methods=['GET', 'POST'])
def add_sale():
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to add sales records or no business selected.', 'danger')
        return redirect(url_for('sales'))
    
    business_id = get_current_business_id()
    # Only show active inventory items for sale
    inventory_items = InventoryItem.query.filter_by(business_id=business_id, is_active=True).filter(InventoryItem.current_stock > 0).all()

    pharmacy_info = session.get('business_info', {
        'name': ENTERPRISE_NAME,
        'location': PHARMACY_LOCATION,
        'address': PHARMACY_ADDRESS,
        'contact': PHARMACY_CONTACT
    })

    if request.method == 'POST':
        customer_phone = request.form.get('customer_phone', '').strip()
        sales_person_name = request.form.get('sales_person_name', session.get('username', 'N/A')).strip()
        transaction_id = str(uuid.uuid4())
        overall_total_amount = 0.0
        sold_items_details = []

        product_ids = request.form.getlist('product_id[]')
        quantities_sold_raw = request.form.getlist('quantity_sold[]')
        sale_unit_types = request.form.getlist('sale_unit_type[]')
        price_types = request.form.getlist('price_type[]')
        custom_prices = request.form.getlist('custom_price[]')

        if not product_ids:
            flash('Please add at least one product to the sale.', 'danger')
            return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=inventory_items, sale={}, user_role=session.get('role'), pharmacy_info=pharmacy_info)

        for i in range(len(product_ids)):
            product_id = product_ids[i]
            quantity_sold_raw = float(quantities_sold_raw[i])
            sale_unit_type = sale_unit_types[i]
            price_type = price_types[i]
            custom_price_str = custom_prices[i] if i < len(custom_prices) else ''

            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()

            if not product:
                flash(f'Product with ID {product_id} not found in inventory. Sale aborted for this item.', 'danger')
                continue
            
            # Check if the product is active before allowing sale
            if not product.is_active:
                flash(f'Product "{product.product_name}" is inactive and cannot be sold.', 'danger')
                continue

            current_stock_packs = product.current_stock
            number_of_tabs_per_pack = float(product.number_of_tabs)
            
            price_at_time_per_unit_sold = 0.0
            total_amount_item = 0.0
            quantity_for_record = 0.0
            quantity_to_deduct_packs = 0.0

            base_sale_price_per_pack = product.sale_price
            base_unit_price_per_tab = product.unit_price_per_tab

            if product.is_fixed_price:
                base_sale_price_per_pack = product.fixed_sale_price
                base_unit_price_per_tab = product.fixed_sale_price / number_of_tabs_per_pack

            if session.get('role') == 'admin' and price_type == 'custom_price':
                try:
                    custom_price_value = float(custom_price_str)
                    if custom_price_value <= 0:
                        flash(f'Custom price for {product.product_name} must be positive. Using internal percentage.', 'warning')
                        price_at_time_per_unit_sold = base_unit_price_per_tab if sale_unit_type == 'tab' else base_sale_price_per_pack
                    else:
                        price_at_time_per_unit_sold = custom_price_value
                except ValueError:
                    flash(f'Invalid custom price for {product.product_name}. Using internal percentage.', 'warning')
                    price_at_time_per_unit_sold = base_unit_price_per_tab if sale_unit_type == 'tab' else base_sale_price_per_pack
            else:
                price_at_time_per_unit_sold = base_unit_price_per_tab if sale_unit_type == 'tab' else base_sale_price_per_pack


            if sale_unit_type == 'tab':
                quantity_sold_tabs = quantity_sold_raw
                available_tabs = current_stock_packs * number_of_tabs_per_pack

                if quantity_sold_tabs <= 0:
                    flash(f'Quantity of tabs sold for {product.product_name} must be at least 1. Skipping item.', 'danger')
                    continue
                if quantity_sold_tabs > available_tabs:
                    flash(f'Insufficient stock for {product.product_name}. Available: {available_tabs:.0f} tabs. Skipping item.', 'danger')
                    continue
                
                quantity_to_deduct_packs = quantity_sold_tabs / number_of_tabs_per_pack
                total_amount_item = quantity_sold_tabs * price_at_time_per_unit_sold
                quantity_for_record = quantity_sold_tabs
            else: # sale_unit_type == 'pack'
                quantity_sold_packs = quantity_sold_raw

                if quantity_sold_packs <= 0:
                    flash(f'Quantity of packs sold for {product.product_name} must be at least 1. Skipping item.', 'danger')
                    continue
                if quantity_sold_packs > current_stock_packs:
                    flash(f'Insufficient stock for {product.product_name}. Available: {current_stock_packs:.2f} packs. Skipping item.', 'danger')
                    continue
                
                quantity_to_deduct_packs = quantity_sold_packs
                total_amount_item = quantity_sold_packs * price_at_time_per_unit_sold
                quantity_for_record = quantity_sold_packs

            # Update stock
            product.current_stock -= quantity_to_deduct_packs
            
            new_sale_item = SaleRecord(
                business_id=business_id,
                product_id=product.id,
                product_name=product.product_name,
                quantity_sold=quantity_for_record,
                sale_unit_type=sale_unit_type,
                price_at_time_per_unit_sold=price_at_time_per_unit_sold,
                total_amount=total_amount_item,
                sale_date=datetime.now(),
                customer_phone=customer_phone,
                sales_person_name=sales_person_name,
                reference_number=str(uuid.uuid4())[:8].upper(),
                transaction_id=transaction_id
            )
            db.session.add(new_sale_item)
            overall_total_amount += total_amount_item
            sold_items_details.append(new_sale_item)

        if not sold_items_details:
            flash('No items were successfully added to the sale.', 'danger')
            db.session.rollback()
            return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=inventory_items, sale={}, user_role=session.get('role'), pharmacy_info=pharmacy_info)

        db.session.commit()
        flash('Sale record(s) added successfully and stock updated!', 'success')

        if customer_phone:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Receipt (Trans ID: {transaction_id[:8].upper()}):\n"
                f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Items:\n"
            )
            for item in sold_items_details:
                item_display_unit_text = "tab(s)" if item.sale_unit_type == 'tab' else "pack(s)"
                message += (
                    f"- {item.product_name} (Qty: {item.quantity_sold:.2f} {item_display_unit_text}, "
                    f"Unit Price: GH₵{item.price_at_time_per_unit_sold:.2f}, "
                    f"Total: GH₵{item.total_amount:.2f})\n"
                )
            message += f"Grand Total: GH₵{overall_total_amount:.2f}\n\n"
            message += f"Thank you for trading with us\n"
            message += f"From: {business_name_for_sms}"

            sms_payload = {
                'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': customer_phone,
                'from': ARKESEL_SENDER_ID, 'sms': message
            }
            try:
                sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload) 
                sms_result = sms_response.json()
                if sms_result.get('status') != 'success':
                    print(f"Arkesel SMS Error: {sms_result.get('message', 'Unknown error')}")
                    flash(f'Failed to send SMS receipt to {customer_phone}. Error: {sms_result.get("message", "Unknown error")}', 'warning')
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS: {e}')
                flash(f'Network error when trying to send SMS receipt.', 'warning')

        session['last_transaction_details'] = [{
            'product_name': item.product_name, 'quantity_sold': item.quantity_sold, 'sale_unit_type': item.sale_unit_type,
            'price_at_time_per_unit_sold': item.price_at_time_per_unit_sold, 'total_amount': item.total_amount
        } for item in sold_items_details]
        session['last_transaction_grand_total'] = overall_total_amount
        session['last_transaction_id'] = transaction_id
        session['last_transaction_customer_phone'] = customer_phone
        session['last_transaction_sales_person'] = sales_person_name
        session['last_transaction_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return redirect(url_for('add_sale', print_ready=True))

    default_sale = {
        'sales_person_name': session.get('username', 'N/A'),
        'customer_phone': '',
    }
    
    print_ready = request.args.get('print_ready', 'false').lower() == 'true'

    last_transaction_details = session.pop('last_transaction_details', [])
    last_transaction_grand_total = session.pop('last_transaction_grand_total', 0.0)
    last_transaction_id = session.pop('last_transaction_id', '')
    last_transaction_customer_phone = session.pop('last_transaction_customer_phone', '')
    last_transaction_sales_person = session.pop('last_transaction_sales_person', '')
    last_transaction_date = session.pop('last_transaction_date', '')

    return render_template('add_edit_sale.html', 
                           title='Add Sale Record', 
                           inventory_items=inventory_items, 
                           sale=default_sale, 
                           user_role=session.get('role'), 
                           pharmacy_info=pharmacy_info,
                           print_ready=print_ready,
                           last_transaction_details=last_transaction_details,
                           last_transaction_grand_total=last_transaction_grand_total,
                           last_transaction_id=last_transaction_id,
                           last_transaction_customer_phone=last_transaction_customer_phone,
                           last_transaction_sales_person=last_transaction_sales_person,
                           last_transaction_date=last_transaction_date,
                           business_type=session.get('business_type') # Pass business type
                           )

@app.route('/sales/edit/<sale_id>', methods=['GET', 'POST'])
def edit_sale(sale_id):
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to edit sales records or no business selected.', 'danger')
        return redirect(url_for('sales'))
    
    business_id = get_current_business_id()
    business_type = session.get('business_type')
    sale_to_edit = SaleRecord.query.filter_by(id=sale_id, business_id=business_id).first_or_404()
    product = InventoryItem.query.filter_by(id=sale_to_edit.product_id, business_id=business_id).first()

    if not product:
        flash('Associated product not found in inventory. Cannot edit sale.', 'danger')
        return redirect(url_for('sales'))

    available_inventory_items = InventoryItem.query.filter_by(business_id=business_id, is_active=True).all() # Only show active items

    pharmacy_info = session.get('business_info', {
        'name': ENTERPRISE_NAME,
        'location': PHARMACY_LOCATION,
        'address': PHARMACY_ADDRESS,
        'contact': PHARMACY_CONTACT
    })

    if request.method == 'POST':
        old_quantity_sold_record = sale_to_edit.quantity_sold
        old_sale_unit_type = sale_to_edit.sale_unit_type

        new_quantity_sold_raw = float(request.form.getlist('quantity_sold[]')[0])
        new_sale_unit_type = request.form.getlist('sale_unit_type[]')[0]
        
        product_id = request.form.getlist('product_id[]')[0]
        customer_phone = request.form.get('customer_phone', '').strip()
        sales_person_name = request.form.get('sales_person_name', sale_to_edit.sales_person_name).strip()
        
        price_type = request.form.getlist('price_type[]')[0] if request.form.getlist('price_type[]') else 'internal_percentage'
        custom_price_str = request.form.getlist('custom_price[]')[0] if request.form.getlist('custom_price[]') else ''

        product_updated = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
        if not product_updated:
            flash('Selected product not found in inventory.', 'danger')
            return render_template('add_edit_sale.html', title='Edit Sale Record', sale=request.form, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info, business_type=business_type)
        
        # Check if the product is active before allowing edit
        if not product_updated.is_active:
            flash(f'Product "{product_updated.product_name}" is inactive and cannot be edited in sales.', 'danger')
            return render_template('add_edit_sale.html', title='Edit Sale Record', sale=request.form, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info, business_type=business_type)


        current_stock_packs = product_updated.current_stock
        number_of_tabs_per_pack = float(product_updated.number_of_tabs)
        
        price_at_time_per_unit_sold = 0.0
        new_quantity_for_record = 0.0

        base_sale_price_per_pack = product_updated.sale_price
        base_unit_price_per_tab = product_updated.unit_price_per_tab

        if product_updated.is_fixed_price:
            base_sale_price_per_pack = product_updated.fixed_sale_price
            base_unit_price_per_tab = product_updated.fixed_sale_price / number_of_tabs_per_pack

        if session.get('role') == 'admin' and price_type == 'custom_price':
            try:
                custom_price_value = float(custom_price_str)
                if custom_price_value <= 0:
                    flash(f'Custom price for {product_updated.product_name} must be positive. Using internal percentage.', 'warning')
                    price_at_time_per_unit_sold = base_unit_price_per_tab if new_sale_unit_type == 'tab' else base_sale_price_per_pack
                else:
                    price_at_time_per_unit_sold = custom_price_value
            except ValueError:
                flash(f'Invalid custom price for {product_updated.product_name}. Using internal percentage.', 'warning')
                price_at_time_per_unit_sold = base_unit_price_per_tab if new_sale_unit_type == 'tab' else base_sale_price_per_pack
        else:
            price_at_time_per_unit_sold = base_unit_price_per_tab if new_sale_unit_type == 'tab' else base_sale_price_per_pack

        old_quantity_in_packs = old_quantity_sold_record / number_of_tabs_per_pack if old_sale_unit_type == 'tab' else old_quantity_sold_record
        
        new_total_amount_sold = 0.0
        
        if new_sale_unit_type == 'tab':
            new_quantity_sold_tabs = new_quantity_sold_raw
            if new_quantity_sold_tabs <= 0:
                flash('Quantity of tabs sold must be at least 1.', 'danger')
                return render_template('add_edit_sale.html', title='Edit Sale Record', sale=request.form, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info, business_type=business_type)

            new_quantity_in_packs = new_quantity_sold_tabs / number_of_tabs_per_pack
            new_total_amount_sold = new_quantity_sold_tabs * price_at_time_per_unit_sold
            new_quantity_for_record = new_quantity_sold_tabs
        else:
            new_quantity_sold_packs = new_quantity_sold_raw
            if new_quantity_sold_packs <= 0:
                flash('Quantity of packs sold must be at least 1.', 'danger')
                return render_template('add_edit_sale.html', title='Edit Sale Record', sale=request.form, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info, business_type=business_type)

            new_quantity_in_packs = new_quantity_sold_packs
            new_total_amount_sold = new_quantity_sold_packs * price_at_time_per_unit_sold
            new_quantity_for_record = new_quantity_sold_packs

        if session.get('role') == 'admin':
            adjusted_stock_after_revert = current_stock_packs + old_quantity_in_packs
            quantity_to_deduct_packs = new_quantity_in_packs 

            if adjusted_stock_after_revert - quantity_to_deduct_packs < 0:
                flash(f'Insufficient stock for {product_updated.product_name} to adjust sale quantity. Available: {adjusted_stock_after_revert:.2f} packs.', 'danger')
                return render_template('add_edit_sale.html', title='Edit Sale Record', sale=request.form, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info, business_type=business_type)
            
            product_updated.current_stock = adjusted_stock_after_revert - quantity_to_deduct_packs
            db.session.commit()
            flash('Inventory stock adjusted due to sale edit (Admin action).', 'info')
        else:
            flash('Sales personnel edits do not affect inventory stock. Only the sale record is updated.', 'warning')

        sale_to_edit.product_id = product_id
        sale_to_edit.product_name = product_updated.product_name
        sale_to_edit.quantity_sold = new_quantity_for_record
        sale_to_edit.sale_unit_type = new_sale_unit_type
        sale_to_edit.price_at_time_per_unit_sold = price_at_time_per_unit_sold
        sale_to_edit.total_amount = new_total_amount_sold
        sale_to_edit.sale_date = datetime.now()
        sale_to_edit.customer_phone = customer_phone
        sale_to_edit.sales_person_name = sales_person_name 
        sale_to_edit.reference_number = sale_to_edit.reference_number if sale_to_edit.reference_number else str(uuid.uuid4())[:8].upper()
        sale_to_edit.transaction_id = sale_to_edit.transaction_id if sale_to_edit.transaction_id else str(uuid.uuid4())

        db.session.commit()
        flash('Sale record updated successfully!', 'success')

        if customer_phone:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            # Determine display unit text for SMS
            display_unit_text = "tab(s)" if new_sale_unit_type == 'tab' else "pack(s)"
            message = (
                f"{business_name_for_sms} Receipt (Edited - Ref: {sale_to_edit.reference_number}):\n" 
                f"Item: {product_updated.product_name}\n"
                f"Qty: {new_quantity_for_record:.2f} {display_unit_text}\n"
                f"Unit Price: GH₵{price_at_time_per_unit_sold:.2f} per {new_sale_unit_type}\n"
                f"Total: GH₵{new_total_amount_sold:.2f}\n"
                f"Date: {sale_to_edit.sale_date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Thank you for trading with us\n"
                f"From: {business_name_for_sms}"
            )
            sms_payload = {
                'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': customer_phone,
                'from': ARKESEL_SENDER_ID, 'sms': message
            }
            try:
                sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
                sms_result = sms_response.json()
                if sms_result.get('status') != 'success':
                    print(f"Arkesel SMS Error: {sms_result.get('message', 'Unknown error')}")
                    flash(f'Failed to send SMS receipt to {customer_phone}. Error: {sms_result.get("message", "Unknown error")}', 'warning')
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS: {e}')
                flash(f'Network error when trying to send SMS receipt.', 'warning')

        return redirect(url_for('sales'))
    
    sale_data_for_form = {
        'id': sale_to_edit.id, 'product_id': sale_to_edit.product_id, 'product_name': sale_to_edit.product_name,
        'quantity_sold': sale_to_edit.quantity_sold, 'sale_unit_type': sale_to_edit.sale_unit_type,
        'price_at_time_per_unit_sold': sale_to_edit.price_at_time_per_unit_sold, 'total_amount': sale_to_edit.total_amount,
        'sale_date': sale_to_edit.sale_date.strftime('%Y-%m-%d %H:%M:%S'), 'customer_phone': sale_to_edit.customer_phone,
        'sales_person_name': sale_to_edit.sales_person_name, 'reference_number': sale_to_edit.reference_number,
        'transaction_id': sale_to_edit.transaction_id
    }

    calculated_internal_price = 0.0
    base_sale_price_per_pack = product.sale_price
    base_unit_price_per_tab = product.unit_price_per_tab

    if product.is_fixed_price:
        base_sale_price_per_pack = product.fixed_sale_price
        base_unit_price_per_tab = product.fixed_sale_price / product.number_of_tabs

    if sale_data_for_form['sale_unit_type'] == 'tab':
        calculated_internal_price = base_unit_price_per_tab
    else:
        calculated_internal_price = base_sale_price_per_pack
    
    if abs(sale_data_for_form['price_at_time_per_unit_sold'] - calculated_internal_price) < 0.001:
        sale_data_for_form['price_type'] = 'internal_percentage'
        sale_data_for_form['custom_price'] = ''
    else:
        sale_data_for_form['price_type'] = 'custom_price'
        sale_data_for_form['custom_price'] = f"{sale_data_for_form['price_at_time_per_unit_sold']:.2f}"

    return render_template('add_edit_sale.html', 
                           title='Edit Sale Record', 
                           sale=sale_data_for_form, 
                           inventory_items=available_inventory_items, 
                           user_role=session.get('role'), 
                           pharmacy_info=pharmacy_info,
                           print_ready=False,
                           last_transaction_details=[],
                           last_transaction_grand_total=0.0,
                           last_transaction_id='',
                           last_transaction_customer_phone='',
                           last_transaction_sales_person='',
                           last_transaction_date='',
                           business_type=business_type # Pass business type
                           )


@app.route('/sales/delete/<sale_id>')
def delete_sale(sale_id):
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to delete sales records or no business selected.', 'danger')
        return redirect(url_for('sales'))
    
    business_id = get_current_business_id()
    sale_to_delete = SaleRecord.query.filter_by(id=sale_id, business_id=business_id).first_or_404()
    
    product = InventoryItem.query.filter_by(id=sale_to_delete.product_id, business_id=business_id).first()

    if product:
        quantity_to_add_packs = sale_to_delete.quantity_sold / product.number_of_tabs if sale_to_delete.sale_unit_type == 'tab' else sale_to_delete.quantity_sold
            
        product.current_stock += quantity_to_add_packs
        db.session.commit()
        flash(f'Stock for {product.product_name} adjusted due to sale deletion. New stock: {product.current_stock:.2f} packs.', 'info')
    else:
        flash('Associated product for deleted sale not found in inventory. Stock not adjusted.', 'warning')

    db.session.delete(sale_to_delete)
    db.session.commit()
    flash('Sale record deleted successfully!', 'success')
    return redirect(url_for('sales'))


@app.route('/sales/return_item', methods=['GET', 'POST'])
def return_item():
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to process returns or no business selected.', 'danger')
        return redirect(url_for('sales'))
    
    business_id = get_current_business_id()

    if request.method == 'POST':
        ref_number = request.form['reference_number'].strip().upper()
        return_quantity_raw = float(request.form['return_quantity'])
        return_unit_type = request.form['return_unit_type']

        original_sale = SaleRecord.query.filter_by(reference_number=ref_number, business_id=business_id).first()

        if not original_sale:
            flash(f'Sale with Reference Number {ref_number} not found for this business.', 'danger')
            return render_template('return_item.html', user_role=session.get('role'), business_type=session.get('business_type'))
        
        product = InventoryItem.query.filter_by(id=original_sale.product_id, business_id=business_id).first()
        if not product:
            flash(f'Product {original_sale.product_name} from sale {ref_number} not found in inventory. Cannot process return.', 'danger')
            return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product, business_type=session.get('business_type'))

        original_quantity_sold_record = original_sale.quantity_sold
        original_sale_unit_type = original_sale.sale_unit_type
        
        number_of_tabs_per_pack = float(product.number_of_tabs)
        price_at_time_per_unit_sold = original_sale.price_at_time_per_unit_sold

        return_quantity_in_packs = 0.0
        returned_amount = 0.0
        display_unit_text = ""
        quantity_for_return_record = 0.0

        if return_unit_type == 'tab':
            if return_quantity_raw <= 0:
                flash('Return quantity of tabs must be at least 1.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product, business_type=session.get('business_type'))

            original_quantity_tabs = original_quantity_sold_record
            if original_sale_unit_type == 'pack':
                original_quantity_tabs = original_quantity_sold_record * number_of_tabs_per_pack

            if return_quantity_raw > original_quantity_tabs:
                flash(f'Cannot return {return_quantity_raw:.0f} tabs. Only {original_quantity_tabs:.0f} tabs were originally sold for this reference number.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product, business_type=session.get('business_type'))

            return_quantity_in_packs = return_quantity_raw / number_of_tabs_per_pack
            returned_amount = return_quantity_raw * price_at_time_per_unit_sold
            display_unit_text = "tab(s)"
            quantity_for_return_record = return_quantity_raw

        else: # return_unit_type == 'pack'
            if return_quantity_raw <= 0:
                flash('Return quantity of packs must be at least 1.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product, business_type=session.get('business_type'))
            
            original_quantity_packs = original_quantity_sold_record
            if original_sale_unit_type == 'tab':
                original_quantity_packs = original_quantity_sold_record / number_of_tabs_per_pack
            
            if return_quantity_raw > original_quantity_packs:
                flash(f'Cannot return {return_quantity_raw:.2f} packs. Only {original_quantity_packs:.2f} packs were originally sold for this reference number.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product, business_type=session.get('business_type'))

            return_quantity_in_packs = return_quantity_raw
            returned_amount = return_quantity_raw * price_at_time_per_unit_sold
            display_unit_text = "pack(s)"
            quantity_for_return_record = return_quantity_raw

        return_sale_record = SaleRecord(
            business_id=business_id,
            product_id=original_sale.product_id,
            product_name=original_sale.product_name,
            quantity_sold=-quantity_for_return_record,
            sale_unit_type=return_unit_type,
            price_at_time_per_unit_sold=price_at_time_per_unit_sold,
            total_amount=-returned_amount,
            sale_date=datetime.now(),
            customer_phone=original_sale.customer_phone,
            sales_person_name=session.get('username', 'N/A') + " (Return)",
            reference_number=f"RMA-{ref_number}",
            transaction_id=original_sale.transaction_id
        )
        db.session.add(return_sale_record)

        product.current_stock += return_quantity_in_packs
        db.session.commit()

        flash(f'Return processed for Reference Number {ref_number}. {return_quantity_raw:.2f} {display_unit_text} of {original_sale.product_name} returned. Total sales adjusted by GH₵{returned_amount:.2f}.', 'success')
        
        if original_sale.customer_phone:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Return Confirmation (Ref: {return_sale_record.reference_number}):\n"
                f"Item: {original_sale.product_name}\n"
                f"Qty Returned: {quantity_for_return_record:.2f} {display_unit_text}\n"
                f"Amount Refunded: GH₵{returned_amount:.2f}\n"
                f"Date: {return_sale_record.sale_date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"From: {business_name_for_sms}"
            )
            sms_payload = {
                'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': original_sale.customer_phone,
                'from': ARKESEL_SENDER_ID, 'sms': message
            }
            try:
                sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
                sms_result = sms_response.json()
                if sms_result.get('status') != 'success':
                    print(f"Arkesel SMS Error: {sms_result.get('message', 'Unknown error')}")
                    flash(f'Failed to send SMS return confirmation to {original_sale.customer_phone}. Error: {sms_result.get("message", "Unknown error")}', 'warning')
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS: {e}')
                flash(f'Network error when trying to send SMS return confirmation.', 'warning')

        return redirect(url_for('sales'))

    return render_template('return_item.html', user_role=session.get('role'), business_type=session.get('business_type'))


# --- Reporting and Statistics Routes ---

@app.route('/reports')
def reports():
    if 'username' not in session or not get_current_business_id():
        flash('Please log in and select a business to access this page.', 'warning')
        return redirect(url_for('login'))

    business_id = get_current_business_id()

    # Fetch inventory items as dictionaries directly from the query
    # This bypasses potential issues with SQLAlchemy's instance state management
    inventory_items_raw = db.session.query(
        InventoryItem.id,
        InventoryItem.product_name,
        InventoryItem.category,
        InventoryItem.purchase_price,
        InventoryItem.sale_price,
        InventoryItem.current_stock,
        InventoryItem.last_updated,
        InventoryItem.batch_number,
        InventoryItem.number_of_tabs,
        InventoryItem.unit_price_per_tab,
        InventoryItem.item_type,
        InventoryItem.expiry_date,
        InventoryItem.is_fixed_price,
        InventoryItem.fixed_sale_price,
        InventoryItem.is_active
    ).filter_by(business_id=business_id).all()

    # Convert query results (tuples/rows) to dictionaries
    inventory_items = []
    for item_tuple in inventory_items_raw:
        item_dict = {
            'id': item_tuple[0],
            'product_name': item_tuple[1],
            'category': item_tuple[2],
            'purchase_price': item_tuple[3],
            'sale_price': item_tuple[4],
            'current_stock': item_tuple[5],
            'last_updated': item_tuple[6],
            'batch_number': item_tuple[7],
            'number_of_tabs': item_tuple[8],
            'unit_price_per_tab': item_tuple[9],
            'item_type': item_tuple[10],
            'expiry_date': item_tuple[11],
            'is_fixed_price': item_tuple[12],
            'fixed_sale_price': item_tuple[13],
            'is_active': item_tuple[14]
        }
        inventory_items.append(item_dict)

    sales_records = SaleRecord.query.filter_by(business_id=business_id).all()

    # Prepare stock summary with expiry warnings
    stock_summary_with_expiry = []
    today = date.today()
    for item_dict in inventory_items: # Iterate over the dictionaries now
        item_dict['expires_soon'] = False
        expiry_date_obj = item_dict['expiry_date'] # This is already a date object from the query result

        if expiry_date_obj:
            time_to_expiry = expiry_date_obj - today
            if time_to_expiry.days <= 180 and time_to_expiry.days >= 0: # Within 6 months and not expired
                item_dict['expires_soon'] = True
            elif time_to_expiry.days < 0: # Already expired
                item_dict['expires_soon'] = 'Expired'
        stock_summary_with_expiry.append(item_dict)

    daily_sales = {}
    weekly_sales = {}
    monthly_sales = {}
    sales_per_person = {}

    total_cost_of_stock = 0.0
    total_potential_profit = 0.0

    # Only consider active inventory items for stock cost/profit calculations
    active_inventory_items_for_calc = [item for item in inventory_items if item['is_active']]

    for item in active_inventory_items_for_calc:
        total_cost_of_stock += item['purchase_price'] * item['current_stock']
        total_potential_profit += (item['sale_price'] - item['purchase_price']) * item['current_stock']


    for sale in sales_records:
        sale_date_obj = sale.sale_date
        total_amount = sale.total_amount
        sales_person = sale.sales_person_name if sale.sales_person_name else 'Unknown'

        day_key = sale_date_obj.strftime('%Y-%m-%d')
        daily_sales[day_key] = daily_sales.get(day_key, 0.0) + total_amount

        week_key = sale_date_obj.strftime('%Y-W%W')
        weekly_sales[week_key] = weekly_sales.get(week_key, 0.0) + total_amount

        month_key = sale_date_obj.strftime('%Y-%m')
        monthly_sales[month_key] = monthly_sales.get(month_key, 0.0) + total_amount

        sales_per_person[sales_person] = sales_per_person.get(sales_person, 0.0) + total_amount


    sorted_daily_sales = sorted(daily_sales.items())
    sorted_weekly_sales = sorted(weekly_sales.items())
    sorted_monthly_sales = sorted(monthly_sales.items())
    sorted_sales_per_person = sorted(sales_per_person.items())

    return render_template(
        'reports.html',
        stock_summary=stock_summary_with_expiry, # Pass the updated list
        daily_sales=sorted_daily_sales,
        weekly_sales=sorted_weekly_sales,
        monthly_sales=sorted_monthly_sales,
        sales_per_person=sorted_sales_per_person,
        total_cost_of_stock=total_cost_of_stock,
        total_potential_profit=total_potential_profit,
        user_role=session.get('role'),
        business_type=session.get('business_type') # Pass business type
    )

@app.route('/reports/send_daily_sms', methods=['POST'])
def send_daily_sms_report():
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to send daily SMS reports or no business selected.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    
    today = date.today()
    today_sales = SaleRecord.query.filter_by(business_id=business_id).filter(
        db.func.date(SaleRecord.sale_date) == today
    ).all()

    total_sales_amount = sum(s.total_amount for s in today_sales)
    total_items_sold = sum(s.quantity_sold for s in today_sales)
    
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
def companies():
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to manage companies or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    companies = Company.query.filter_by(business_id=business_id).all()
    return render_template('company_list.html', companies=companies, user_role=session.get('role'))

@app.route('/companies/add', methods=['GET', 'POST'])
def add_company():
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

        if Company.query.filter_by(name=name, business_id=business_id).first():
            flash('Company with this name already exists for this business.', 'danger')
            return render_template('add_edit_company.html', title='Add New Company', company=request.form)
        
        new_company = Company(
            business_id=business_id, name=name, contact_person=contact_person,
            phone=phone, email=email, address=address, balance=0.0
        )
        db.session.add(new_company)
        db.session.commit()
        flash(f'Company "{name}" added successfully!', 'success')
        return redirect(url_for('companies'))
    
    return render_template('add_edit_company.html', title='Add New Company', company={})

@app.route('/companies/edit/<company_id>', methods=['GET', 'POST'])
def edit_company(company_id):
    if 'username' not in session or session.get('role') not in ['admin'] or not get_current_business_id():
        flash('You do not have permission to edit companies or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    company_to_edit = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

    if request.method == 'POST':
        name = request.form['name'].strip()
        contact_person = request.form['contact_person'].strip()
        phone = request.form['phone'].strip()
        email = request.form['email'].strip()
        address = request.form['address'].strip()

        if Company.query.filter(Company.name == name, Company.business_id == business_id, Company.id != company_id).first():
            flash('Company with this name already exists for this business.', 'danger')
            return render_template('add_edit_company.html', title='Edit Company', company=request.form)

        company_to_edit.name = name
        company_to_edit.contact_person = contact_person
        company_to_edit.phone = phone
        company_to_edit.email = email
        company_to_edit.address = address
        db.session.commit()
        flash(f'Company "{name}" updated successfully!', 'success')
        return redirect(url_for('companies'))
    
    return render_template('add_edit_company.html', title='Edit Company', company=company_to_edit)

@app.route('/companies/delete/<company_id>')
def delete_company(company_id):
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

@app.route('/companies/transaction/<company_id>', methods=['GET', 'POST'])
def company_transaction(company_id):
    # Allow 'admin', 'viewer_admin', and 'sales' roles to record company transactions
    if 'username' not in session or session.get('role') not in ['admin', 'viewer_admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to record company transactions or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    company = Company.query.filter_by(id=company_id, business_id=business_id).first_or_404()

    if request.method == 'POST':
        transaction_type = request.form['type'] # 'Credit' or 'Debit'
        amount = float(request.form['amount'])
        description = request.form['description'].strip()
        
        if amount <= 0:
            flash('Amount must be positive.', 'danger')
            return render_template('company_transaction.html', company=company, transaction={}, user_role=session.get('role'))

        if transaction_type == 'Credit':
            company.balance += amount
            flash(f'GH₵{amount:.2f} credited to {company.name}. New balance: GH₵{company.balance:.2f}', 'success')
        elif transaction_type == 'Debit':
            company.balance -= amount
            flash(f'GH₵{amount:.2f} debited from {company.name}. New balance: GH₵{company.balance:.2f}', 'success')
        else:
            flash('Invalid transaction type.', 'danger')
            return render_template('company_transaction.html', company=company, transaction={}, user_role=session.get('role'))

        new_transaction = CompanyTransaction(
            company_id=company.id, business_id=business_id, type=transaction_type,
            amount=amount, description=description, recorded_by=session['username']
        )
        db.session.add(new_transaction)
        db.session.commit()
        return redirect(url_for('companies'))
    
    transactions = CompanyTransaction.query.filter_by(company_id=company.id).order_by(CompanyTransaction.date.desc()).all()
    return render_template('company_transaction.html', company=company, transactions=transactions, user_role=session.get('role'))


@app.route('/future_orders')
def future_orders():
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to view future orders or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    orders = FutureOrder.query.filter_by(business_id=business_id).order_by(FutureOrder.date_ordered.desc()).all()
    return render_template('future_order_list.html', orders=orders, user_role=session.get('role'))

@app.route('/future_orders/add', methods=['GET', 'POST'])
def add_future_order():
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to add future orders or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    inventory_items = InventoryItem.query.filter_by(business_id=business_id, item_type='Hardware Material', is_active=True).all() # Only active items

    if request.method == 'POST':
        customer_name = request.form['customer_name'].strip()
        customer_phone = request.form['customer_phone'].strip()
        expected_collection_date_str = request.form['expected_collection_date'].strip()
        expected_collection_date_obj = datetime.strptime(expected_collection_date_str, '%Y-%m-%d').date() if expected_collection_date_str else None
        
        product_ids = request.form.getlist('product_id[]')
        quantities_raw = request.form.getlist('quantity[]')
        unit_prices_raw = request.form.getlist('unit_price[]')
        unit_types = request.form.getlist('unit_type[]')

        order_items = []
        total_order_amount = 0.0

        if not product_ids:
            flash('Please add at least one item to the order.', 'danger')
            return render_template('add_future_order.html', title='Add Future Order', inventory_items=inventory_items, order={}, user_role=session.get('role'))

        for i in range(len(product_ids)):
            product_id = product_ids[i]
            quantity = float(quantities_raw[i])
            unit_price = float(unit_prices_raw[i])
            unit_type = unit_types[i]

            product = InventoryItem.query.filter_by(id=product_id, business_id=business_id).first()
            if not product:
                flash(f'Product with ID {product_id} not found in inventory. Skipping item.', 'warning')
                continue
            
            if not product.is_active: # Ensure product is active for future order
                flash(f'Product "{product.product_name}" is inactive and cannot be included in a future order.', 'danger')
                continue

            if quantity <= 0:
                flash(f'Quantity for {product.product_name} must be positive. Skipping item.', 'warning')
                continue

            item_total = quantity * unit_price
            total_order_amount += item_total
            order_items.append({
                'product_id': product.id,
                'product_name': product.product_name,
                'quantity': quantity,
                'unit_price': unit_price,
                'unit_type': unit_type,
                'item_total': item_total
            })
        
        if not order_items:
            flash('No valid items added to the future order.', 'danger')
            return render_template('add_future_order.html', title='Add Future Order', inventory_items=inventory_items, order={}, user_role=session.get('role'))

        new_future_order = FutureOrder(
            business_id=business_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            total_amount=total_order_amount,
            date_ordered=datetime.now(),
            expected_collection_date=expected_collection_date_obj,
            status='Pending',
            remaining_balance=total_order_amount # Initially, full amount is remaining
        )
        new_future_order.set_items(order_items) # Store items as JSON

        db.session.add(new_future_order)
        db.session.commit()
        flash('Future order added successfully! Stock will be deducted upon collection.', 'success')
        return redirect(url_for('future_orders'))

    return render_template('add_future_order.html', title='Add Future Order', inventory_items=inventory_items, order={}, user_role=session.get('role'))

@app.route('/future_orders/collect/<order_id>', methods=['GET', 'POST'])
def collect_future_order(order_id):
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or not get_current_business_id():
        flash('You do not have permission to collect future orders or no business selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if get_current_business_type() != 'Hardware':
        flash('This feature is only available for Hardware businesses.', 'warning')
        return redirect(url_for('dashboard'))

    business_id = get_current_business_id()
    order = FutureOrder.query.filter_by(id=order_id, business_id=business_id).first_or_404()

    if order.status == 'Collected':
        flash('This order has already been collected.', 'warning')
        return redirect(url_for('future_orders'))
    
    if order.remaining_balance > 0:
        flash(f'Cannot collect order with outstanding balance: GH₵{order.remaining_balance:.2f}. Please settle balance first.', 'danger')
        return redirect(url_for('future_orders'))

    # Deduct stock for each item in the order
    order_items = order.get_items()
    errors = []
    for item_data in order_items:
        product = InventoryItem.query.filter_by(id=item_data['product_id'], business_id=business_id).first()
        if not product:
            errors.append(f"Product {item_data['product_name']} not found in inventory. Stock not deducted for this item.")
            continue
        
        if not product.is_active: # Ensure product is active before collection
            errors.append(f"Product '{product.product_name}' is inactive and cannot be collected.")
            continue


        quantity_to_deduct_packs = item_data['quantity'] / product.number_of_tabs if item_data['unit_type'] == 'tab' else item_data['quantity']

        if product.current_stock < quantity_to_deduct_packs:
            errors.append(f"Insufficient stock for {product.product_name}. Available: {product.current_stock:.2f} packs. Cannot fully collect order.")
            # If partial collection is allowed, implement logic here. For now, we'll block.
            flash(f"Error: {product.product_name} has insufficient stock to fulfill the order. Please update stock or process partial collection manually.", 'danger')
            return redirect(url_for('future_orders'))
        
        product.current_stock -= quantity_to_deduct_packs
        db.session.add(product) # Mark product for update

        # Create a sale record for the collection
        new_sale_item = SaleRecord(
            business_id=business_id,
            product_id=product.id,
            product_name=product.product_name,
            quantity_sold=item_data['quantity'],
            sale_unit_type=item_data['unit_type'],
            price_at_time_per_unit_sold=item_data['unit_price'],
            total_amount=item_data['item_total'],
            sale_date=datetime.now(),
            customer_phone=order.customer_phone,
            sales_person_name=session.get('username', 'N/A') + " (Future Order Collection)",
            reference_number=order.id[:8].upper(), # Use order ID as reference
            transaction_id=order.id # Link sale to future order transaction
        )
        db.session.add(new_sale_item)

    if errors:
        db.session.rollback() # Rollback all changes if any stock issue
        for error in errors:
            flash(error, 'danger')
        return redirect(url_for('future_orders'))
    
    order.actual_collection_date = datetime.now()
    order.status = 'Collected'
    db.session.commit()
    flash(f'Future order for {order.customer_name} collected successfully! Stock deducted and sale recorded.', 'success')
    return redirect(url_for('future_orders'))

@app.route('/future_orders/payment/<order_id>', methods=['GET', 'POST'])
def future_order_payment(order_id):
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
            return render_template('future_order_payment.html', order=order, user_role=session.get('role'))
        
        if amount_paid > order.remaining_balance:
            flash(f'Amount paid (GH₵{amount_paid:.2f}) exceeds remaining balance (GH₵{order.remaining_balance:.2f}).', 'danger')
            return render_template('future_order_payment.html', order=order, user_role=session.get('role'))
        
        order.remaining_balance -= amount_paid
        db.session.commit()
        flash(f'Payment of GH₵{amount_paid:.2f} recorded for order {order.customer_name}. Remaining balance: GH₵{order.remaining_balance:.2f}', 'success')
        return redirect(url_for('future_orders'))
    
    return render_template('future_order_payment.html', order=order, user_role=session.get('role'))


# --- Database Initialization (run once to create tables) ---
with app.app_context():
    db.create_all()

# --- Main entry point ---
if __name__ == '__main__':
    app.run(debug=True)
