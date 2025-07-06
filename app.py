# app.py - Enhanced Flask Application for Pharmaceutical Store Administrator

from flask import Flask, render_template, request, redirect, url_for, flash, session
import csv
import os
import uuid
from datetime import datetime, date # Import date for daily reports
import requests # Import the requests library for API calls
from dotenv import load_dotenv # Import load_dotenv
import json # Import json for specific error handling

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_super_secret_key_here') # Get secret key from .env or use fallback

# --- Global User Management (for super admin) ---
# Super admin credentials (for managing businesses)
SUPER_ADMIN_USERNAME = os.getenv('SUPER_ADMIN_USERNAME', 'superadmin')
SUPER_ADMIN_PASSWORD = os.getenv('SUPER_ADMIN_PASSWORD', 'superpassword')

# --- Arkesel SMS API Configuration ---
ARKESEL_API_KEY = os.getenv('ARKESEL_API_KEY', 'b0FrYkNNVlZGSmdrendVT3hwUHk') # Get API key from .env
ARKESEL_SENDER_ID = os.getenv('ARKESEL_SENDER_ID', 'PHARMACY') # Get Sender ID from .env
ARKESEL_SMS_URL = "https://sms.arkesel.com/sms/api" 
ADMIN_PHONE_NUMBER = os.getenv('ADMIN_PHONE_NUMBER', '233547096268') # Get admin phone from .env
# Global pharmacy info (will be overridden by business-specific info if available)
# These are fallbacks if business_info is not set in session
ENTERPRISE_NAME = os.getenv('ENTERPRISE_NAME', 'Zion Business Center') 
PHARMACY_LOCATION = os.getenv('PHARMACY_LOCATION', 'Kenyasi, Ghana')
PHARMACY_ADDRESS = os.getenv('PHARMACY_ADDRESS', '123 Main St, Kenyasi')
PHARMACY_CONTACT = os.getenv('PHARMACY_CONTACT', '+233547096268')


# --- CSV Database Configuration ---
CSV_DIR = 'data'
BUSINESSES_FILE = os.path.join(CSV_DIR, 'businesses.csv')
INVENTORY_FILE_NAME = 'inventory.csv'
SALES_FILE_NAME = 'sales.csv'
USERS_FILE_NAME = 'users.csv' # For business-specific users

# Ensure the base data directory exists
if not os.path.exists(CSV_DIR):
    os.makedirs(CSV_DIR)

# --- CSV Helper Functions (Generalized) ---

def _init_csv_file(filepath, headers):
    """Initializes a CSV file with headers if it doesn't exist."""
    if not os.path.exists(filepath):
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)

def _load_csv_file(filepath):
    """Loads data from a CSV file into a list of dictionaries."""
    data = []
    if os.path.exists(filepath):
        with open(filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    return data

def _save_csv_file(filepath, data, headers):
    """Saves a list of dictionaries to a CSV file."""
    # Ensure directory exists before saving
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)

def init_businesses_csv():
    """Initializes the main businesses CSV file."""
    # Added new headers for business contact information
    _init_csv_file(BUSINESSES_FILE, ['id', 'name', 'address', 'location', 'contact'])

def load_businesses():
    """Loads all registered businesses."""
    businesses = _load_csv_file(BUSINESSES_FILE)
    # Ensure all businesses have the new fields, provide defaults if missing (for old data)
    for business in businesses:
        business['address'] = business.get('address', '')
        business['location'] = business.get('location', '')
        business['contact'] = business.get('contact', '')
    return businesses

def save_businesses(businesses):
    """Saves all registered businesses."""
    # Updated headers for saving
    _save_csv_file(BUSINESSES_FILE, businesses, ['id', 'name', 'address', 'location', 'contact'])

def init_business_data_files(business_id):
    """Initializes CSV files for a new business."""
    business_dir = os.path.join(CSV_DIR, business_id)
    os.makedirs(business_dir, exist_ok=True)

    # Added 'expiry_date' to inventory headers
    _init_csv_file(os.path.join(business_dir, INVENTORY_FILE_NAME), 
                   ['id', 'product_name', 'category', 'purchase_price', 'sale_price', 'current_stock', 
                    'last_updated', 'batch_number', 'number_of_tabs', 'unit_price_per_tab', 'item_type', 'expiry_date'])
    _init_csv_file(os.path.join(business_dir, SALES_FILE_NAME), 
                   ['id', 'product_id', 'product_name', 'quantity_sold', 'sale_unit_type', 
                    'price_at_time_per_unit_sold', 'total_amount', 'sale_date', 'customer_phone', 
                    'sales_person_name', 'reference_number'])
    _init_csv_file(os.path.join(business_dir, USERS_FILE_NAME), 
                   ['username', 'password', 'role'])

# --- Business-specific data access functions ---

def load_inventory_for_business(business_id):
    filepath = os.path.join(CSV_DIR, business_id, INVENTORY_FILE_NAME)
    data = _load_csv_file(filepath)
    # Convert numeric fields to float/int after loading
    for row in data:
        row['purchase_price'] = float(row.get('purchase_price', 0.0))
        row['sale_price'] = float(row.get('sale_price', 0.0))
        row['current_stock'] = float(row.get('current_stock', 0.0))
        row['number_of_tabs'] = int(row.get('number_of_tabs', 1))
        row['unit_price_per_tab'] = float(row.get('unit_price_per_tab', 0.0))
        row['item_type'] = row.get('item_type', 'Pharmacy') # Default for old entries
        row['expiry_date'] = row.get('expiry_date', '') # Load new expiry_date field
    return data

def save_inventory_for_business(business_id, items):
    filepath = os.path.join(CSV_DIR, business_id, INVENTORY_FILE_NAME)
    # Format numeric fields back to string for saving
    formatted_items = []
    for item in items:
        formatted_item = item.copy()
        formatted_item['purchase_price'] = f"{item['purchase_price']:.2f}"
        formatted_item['sale_price'] = f"{item['sale_price']:.2f}"
        formatted_item['current_stock'] = f"{item['current_stock']:.2f}"
        formatted_item['number_of_tabs'] = str(item['number_of_tabs'])
        formatted_item['unit_price_per_tab'] = f"{item['unit_price_per_tab']:.2f}"
        formatted_items.append(formatted_item)
    # Updated headers for saving, including 'expiry_date'
    _save_csv_file(filepath, formatted_items, 
                   ['id', 'product_name', 'category', 'purchase_price', 'sale_price', 'current_stock', 
                    'last_updated', 'batch_number', 'number_of_tabs', 'unit_price_per_tab', 'item_type', 'expiry_date'])

def load_sales_for_business(business_id):
    filepath = os.path.join(CSV_DIR, business_id, SALES_FILE_NAME)
    data = _load_csv_file(filepath)
    # Convert numeric fields to float after loading
    for row in data:
        row['quantity_sold'] = float(row.get('quantity_sold', 0.0))
        row['price_at_time_per_unit_sold'] = float(row.get('price_at_time_per_unit_sold', 0.0))
        row['total_amount'] = float(row.get('total_amount', 0.0))
        row['reference_number'] = row.get('reference_number', '') # Default for old entries
        row['sale_unit_type'] = row.get('sale_unit_type', 'pack') # Default for old entries
    return data

def save_sales_for_business(business_id, sales_records):
    filepath = os.path.join(CSV_DIR, business_id, SALES_FILE_NAME)
    # Format numeric fields back to string for saving
    formatted_sales = []
    for sale in sales_records:
        formatted_sale = sale.copy()
        formatted_sale['quantity_sold'] = f"{sale['quantity_sold']:.2f}"
        formatted_sale['price_at_time_per_unit_sold'] = f"{sale['price_at_time_per_unit_sold']:.2f}"
        formatted_sale['total_amount'] = f"{sale['total_amount']:.2f}"
        formatted_sales.append(formatted_sale)
    _save_csv_file(filepath, formatted_sales, 
                   ['id', 'product_id', 'product_name', 'quantity_sold', 'sale_unit_type', 
                    'price_at_time_per_unit_sold', 'total_amount', 'sale_date', 'customer_phone', 
                    'sales_person_name', 'reference_number'])

def load_users_for_business(business_id):
    filepath = os.path.join(CSV_DIR, business_id, USERS_FILE_NAME)
    return _load_csv_file(filepath)

def save_users_for_business(business_id, users):
    filepath = os.path.join(CSV_DIR, business_id, USERS_FILE_NAME)
    _save_csv_file(filepath, users, ['username', 'password', 'role'])

# Initialize the main businesses CSV file on app startup
init_businesses_csv()

# --- Authentication Routes ---

@app.route('/')
def index():
    """Redirects to the login page if not logged in, otherwise to the dashboard."""
    if 'username' in session:
        if session.get('role') == 'super_admin':
            return redirect(url_for('super_admin_dashboard'))
        elif 'business_id' in session:
            return redirect(url_for('dashboard'))
        else: # Logged in but no business selected (e.g., after logout from a business)
            return redirect(url_for('business_selection'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # 1. Check for Super Admin
        if username == SUPER_ADMIN_USERNAME and password == SUPER_ADMIN_PASSWORD:
            session.clear() # Clear any previous session
            session['username'] = username
            session['role'] = 'super_admin'
            flash(f'Welcome, Super Admin!', 'success')
            return redirect(url_for('super_admin_dashboard'))

        # 2. Check for Business-specific users
        businesses = load_businesses()
        authenticated = False
        for business in businesses:
            business_id = business['id']
            business_users = load_users_for_business(business_id)
            for user_data in business_users:
                if user_data['username'] == username and user_data['password'] == password:
                    session.clear() # Clear any previous session
                    session['username'] = username
                    session['role'] = user_data['role']
                    session['business_id'] = business_id
                    session['business_name'] = business['name'] # Store business name for display
                    # Store full business info in session for easy access
                    session['business_info'] = {
                        'name': business['name'],
                        'address': business['address'],
                        'location': business['location'],
                        'contact': business['contact']
                    }
                    authenticated = True
                    break
            if authenticated:
                break
        
        if authenticated:
            flash(f'Welcome, {username} ({session["role"].replace("_", " ").title()}) to {session["business_name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logs out the current user."""
    session.pop('username', None)
    session.pop('role', None)
    session.pop('business_id', None)
    session.pop('business_name', None)
    session.pop('business_info', None) # Clear business info from session
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/business_selection', methods=['GET', 'POST'])
def business_selection():
    """Allows authenticated users (not super admin) to select a business."""
    if 'username' not in session or session.get('role') == 'super_admin':
        flash('Please log in or you are a Super Admin.', 'warning')
        return redirect(url_for('login'))

    businesses = load_businesses()
    user_businesses = [] # Businesses this user belongs to
    
    # Filter businesses to only show ones the current user has an account in
    current_username = session['username']
    for business in businesses:
        business_users = load_users_for_business(business['id'])
        if any(user['username'] == current_username for user in business_users):
            user_businesses.append(business)

    if request.method == 'POST':
        selected_business_id = request.form['business_id']
        selected_business = next((b for b in businesses if b['id'] == selected_business_id), None)

        if selected_business:
            # Re-verify user's role for this business
            business_users = load_users_for_business(selected_business_id)
            user_data = next((u for u in business_users if u['username'] == session['username']), None)
            
            if user_data:
                session['business_id'] = selected_business_id
                session['business_name'] = selected_business['name']
                session['role'] = user_data['role'] # Update role in case it changed
                session['business_info'] = { # Update business info in session
                    'name': selected_business['name'],
                    'address': selected_business['address'],
                    'location': selected_business['location'],
                    'contact': selected_business['contact']
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
    """Main dashboard for business-specific users."""
    if 'username' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))
    if session.get('role') == 'super_admin':
        return redirect(url_for('super_admin_dashboard'))
    if 'business_id' not in session:
        return redirect(url_for('business_selection')) # Force selection if not set

    return render_template('dashboard.html', 
                           username=session['username'], 
                           user_role=session.get('role'),
                           business_name=session.get('business_name'))

# --- Super Admin Routes ---

@app.route('/super_admin_dashboard')
def super_admin_dashboard():
    """Dashboard for the super admin to manage businesses."""
    if session.get('role') != 'super_admin':
        flash('Access denied. Super Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    businesses = load_businesses()
    return render_template('super_admin_dashboard.html', businesses=businesses, user_role=session.get('role'))

@app.route('/super_admin/add_business', methods=['GET', 'POST'])
def add_business():
    """Allows super admin to add a new business."""
    if session.get('role') != 'super_admin':
        flash('Access denied. Super Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        business_name = request.form['business_name'].strip()
        business_address = request.form['business_address'].strip()
        business_location = request.form['business_location'].strip()
        business_contact = request.form['business_contact'].strip()
        initial_admin_username = request.form['initial_admin_username'].strip()
        initial_admin_password = request.form['initial_admin_password'].strip()

        businesses = load_businesses()
        if any(b['name'].lower() == business_name.lower() for b in businesses):
            flash('Business with this name already exists.', 'danger')
            return render_template('add_edit_business.html', title='Add New Business', business={
                'name': business_name,
                'address': business_address,
                'location': business_location,
                'contact': business_contact,
                'initial_admin_username': initial_admin_username,
                'initial_admin_password': initial_admin_password
            })
        
        new_business_id = str(uuid.uuid4())
        businesses.append({
            'id': new_business_id, 
            'name': business_name,
            'address': business_address,
            'location': business_location,
            'contact': business_contact
        })
        save_businesses(businesses)

        # Initialize data files for the new business
        init_business_data_files(new_business_id)

        # Add initial admin user for this business
        business_users = [{'username': initial_admin_username, 'password': initial_admin_password, 'role': 'admin'}]
        save_users_for_business(new_business_id, business_users)

        flash(f'Business "{business_name}" added successfully with initial admin "{initial_admin_username}".', 'success')
        return redirect(url_for('super_admin_dashboard'))
    
    return render_template('add_edit_business.html', title='Add New Business', business={})

@app.route('/super_admin/edit_business/<business_id>', methods=['GET', 'POST'])
def edit_business(business_id):
    """Allows super admin to edit an existing business's details."""
    if session.get('role') != 'super_admin':
        flash('Access denied. Super Admin role required.', 'danger')
        return redirect(url_for('login'))

    businesses = load_businesses()
    business_to_edit = next((b for b in businesses if b['id'] == business_id), None)

    if not business_to_edit:
        flash('Business not found.', 'danger')
        return redirect(url_for('super_admin_dashboard'))

    # Load the initial admin user for this business to pre-fill their credentials
    business_users = load_users_for_business(business_id)
    initial_admin = next((u for u in business_users if u['role'] == 'admin'), None)

    if request.method == 'POST':
        new_business_name = request.form['business_name'].strip()
        new_business_address = request.form['business_address'].strip()
        new_business_location = request.form['business_location'].strip()
        new_business_contact = request.form['business_contact'].strip()
        new_initial_admin_username = request.form['initial_admin_username'].strip()
        new_initial_admin_password = request.form['initial_admin_password'].strip()

        # Check for duplicate business name, excluding the current business being edited
        if any(b['name'].lower() == new_business_name.lower() and b['id'] != business_id for b in businesses):
            flash('Business with this name already exists.', 'danger')
            # Pass current form data back to template
            return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit["name"]}', business={
                'id': business_id,
                'name': new_business_name,
                'address': new_business_address,
                'location': new_business_location,
                'contact': new_business_contact,
                'initial_admin_username': new_initial_admin_username,
                'initial_admin_password': new_initial_admin_password
            })

        business_to_edit['name'] = new_business_name
        business_to_edit['address'] = new_business_address
        business_to_edit['location'] = new_business_location
        business_to_edit['contact'] = new_business_contact
        save_businesses(businesses)

        # Update initial admin user details
        if initial_admin:
            # Check for username change and potential conflict
            if initial_admin['username'] != new_initial_admin_username:
                if any(u['username'] == new_initial_admin_username for u in business_users if u['username'] != initial_admin['username']):
                    flash('New admin username already exists for this business. Business details updated, but admin username not changed.', 'warning')
                else:
                    initial_admin['username'] = new_initial_admin_username
            initial_admin['password'] = new_initial_admin_password
            save_users_for_business(business_id, business_users)
            flash(f'Business "{new_business_name}" and admin credentials updated successfully!', 'success')
        else:
            flash(f'Business "{new_business_name}" updated successfully, but initial admin not found/updated.', 'warning')
        
        return redirect(url_for('super_admin_dashboard'))

    # For GET request, prepare data to pre-fill the form
    business_data_for_form = business_to_edit.copy()
    if initial_admin:
        business_data_for_form['initial_admin_username'] = initial_admin['username']
        business_data_for_form['initial_admin_password'] = initial_admin['password'] # SECURITY WARNING
    else:
        business_data_for_form['initial_admin_username'] = ''
        business_data_for_form['initial_admin_password'] = ''

    return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit["name"]}', business=business_data_for_form)


@app.route('/super_admin/view_business_details/<business_id>')
def view_business_details(business_id):
    """Allows super admin to view details of a registered business, including initial admin credentials."""
    if session.get('role') != 'super_admin':
        flash('Access denied. Super Admin role required.', 'danger')
        return redirect(url_for('login'))

    businesses = load_businesses()
    business = next((b for b in businesses if b['id'] == business_id), None)

    if not business:
        flash('Business not found.', 'danger')
        return redirect(url_for('super_admin_dashboard'))

    # Load users for this specific business to find the initial admin
    business_users = load_users_for_business(business_id)
    initial_admin = next((u for u in business_users if u['role'] == 'admin'), None)

    # SECURITY WARNING: Displaying plain text passwords is a security risk.
    # In a real application, passwords should be hashed and never displayed.
    # This is implemented as per user request for demonstration purposes.
    return render_template('view_business_details.html', business=business, initial_admin=initial_admin)


@app.route('/super_admin/delete_business/<business_id>')
def delete_business(business_id):
    """Allows super admin to delete a business and all its data."""
    if session.get('role') != 'super_admin':
        flash('Access denied. Super Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    businesses = load_businesses()
    original_len = len(businesses)
    businesses = [b for b in businesses if b['id'] != business_id]

    if len(businesses) < original_len:
        save_businesses(businesses)
        # Delete the business's data directory
        business_dir = os.path.join(CSV_DIR, business_id)
        if os.path.exists(business_dir):
            import shutil
            shutil.rmtree(business_dir) # DANGER: This permanently deletes data
            flash(f'Business and its data (ID: {business_id}) deleted successfully!', 'success')
        else:
            flash(f'Business (ID: {business_id}) deleted, but data directory not found.', 'warning')
    else:
        flash('Business not found.', 'danger')
    return redirect(url_for('super_admin_dashboard'))


# --- Business User Management (Admin & Viewer Admin) ---

@app.route('/manage_business_users')
def manage_business_users():
    """Allows business admin/viewer admin to manage users within their business."""
    if 'username' not in session or session.get('role') not in ['admin', 'viewer_admin']:
        flash('You do not have permission to manage users.', 'danger')
        return redirect(url_for('dashboard'))
    if 'business_id' not in session:
        flash('No business selected.', 'warning')
        return redirect(url_for('business_selection'))

    business_id = session['business_id']
    users = load_users_for_business(business_id)
    return render_template('manage_business_users.html', users=users, user_role=session.get('role'))

@app.route('/add_edit_business_user', methods=['GET', 'POST'])
@app.route('/add_edit_business_user/<username>', methods=['GET', 'POST'])
def add_edit_business_user(username=None):
    """Allows business admin/viewer admin to add/edit users within their business."""
    if 'username' not in session or session.get('role') not in ['admin', 'viewer_admin']:
        flash('You do not have permission to manage users.', 'danger')
        return redirect(url_for('dashboard'))
    if 'business_id' not in session:
        flash('No business selected.', 'warning')
        return redirect(url_for('business_selection'))

    business_id = session['business_id']
    users = load_users_for_business(business_id)
    user_to_edit = None
    if username:
        user_to_edit = next((u for u in users if u['username'] == username), None)
        if not user_to_edit:
            flash('User not found.', 'danger')
            return redirect(url_for('manage_business_users'))
        # Viewer admin cannot edit admin users
        if session.get('role') == 'viewer_admin' and user_to_edit['role'] == 'admin':
            flash('Viewer admins cannot edit admin users.', 'danger')
            return redirect(url_for('manage_business_users'))

    title = 'Add New User' if not username else f'Edit User: {username}'

    if request.method == 'POST':
        new_username = request.form['username'].strip()
        new_password = request.form['password'].strip()
        new_role = request.form['role'].strip()

        # Viewer admin can only add/edit 'sales' users
        if session.get('role') == 'viewer_admin' and new_role != 'sales':
            flash('Viewer admins can only add/edit sales users.', 'danger')
            return render_template('add_edit_business_user.html', title=title, user=request.form, user_role=session.get('role'))

        if user_to_edit: # Editing an existing user
            if new_username != username and any(u['username'] == new_username for u in users):
                flash('Username already exists.', 'danger')
                return render_template('add_edit_business_user.html', title=title, user=request.form, user_role=session.get('role'))
            
            user_to_edit['username'] = new_username
            user_to_edit['password'] = new_password
            user_to_edit['role'] = new_role
            flash(f'User "{new_username}" updated successfully!', 'success')
        else: # Adding a new user
            if any(u['username'] == new_username for u in users):
                flash('Username already exists.', 'danger')
                return render_template('add_edit_business_user.html', title=title, user=request.form, user_role=session.get('role'))
            
            users.append({'username': new_username, 'password': new_password, 'role': new_role})
            flash(f'User "{new_username}" added successfully!', 'success')
        
        save_users_for_business(business_id, users)
        return redirect(url_for('manage_business_users'))

    return render_template('add_edit_business_user.html', title=title, user=user_to_edit, user_role=session.get('role'))

@app.route('/delete_business_user/<username>')
def delete_business_user(username):
    """Allows business admin to delete users within their business."""
    if 'username' not in session or session.get('role') != 'admin': # Only full admin can delete users
        flash('You do not have permission to delete users.', 'danger')
        return redirect(url_for('dashboard'))
    if 'business_id' not in session:
        flash('No business selected.', 'warning')
        return redirect(url_for('business_selection'))

    business_id = session['business_id']
    users = load_users_for_business(business_id)
    
    # Prevent admin from deleting themselves or other admins
    user_to_delete = next((u for u in users if u['username'] == username), None)
    if user_to_delete and user_to_delete['role'] == 'admin':
        flash('Cannot delete another admin user or yourself.', 'danger')
        return redirect(url_for('manage_business_users'))

    original_len = len(users)
    users = [u for u in users if u['username'] != username]
    if len(users) < original_len:
        save_users_for_business(business_id, users)
        flash(f'User "{username}" deleted successfully!', 'success')
    else:
        flash('User not found.', 'danger')
    return redirect(url_for('manage_business_users'))


# --- Inventory Management Routes ---

@app.route('/inventory')
def inventory():
    """Displays the list of inventory items."""
    if 'username' not in session or 'business_id' not in session:
        flash('Please log in and select a business to access this page.', 'warning')
        return redirect(url_for('login'))
    
    items = load_inventory_for_business(session['business_id'])
    return render_template('inventory_list.html', items=items, user_role=session.get('role'))

@app.route('/inventory/add', methods=['GET', 'POST'])
def add_inventory():
    """Adds a new inventory item. Restricted to Admin."""
    if 'username' not in session or session.get('role') not in ['admin'] or 'business_id' not in session:
        flash('You do not have permission to add inventory items.', 'danger')
        return redirect(url_for('inventory'))
        
    if request.method == 'POST':
        items = load_inventory_for_business(session['business_id'])
        product_name = request.form['product_name'].strip()
        category = request.form['category'].strip()
        purchase_price = float(request.form['purchase_price'])
        added_stock = float(request.form['current_stock']) # Store stock as float
        batch_number = request.form['batch_number'].strip()
        number_of_tabs = int(request.form['number_of_tabs']) # Get number of tabs
        item_type = request.form['item_type'] # Get new item type
        expiry_date = request.form['expiry_date'].strip() # Get new expiry_date

        if number_of_tabs <= 0:
            flash('Number of tabs must be greater than zero.', 'danger')
            return render_template('add_edit_inventory.html', title='Add Inventory Item', item=request.form, user_role=session.get('role'))

        # Calculate unit price per tab with conditional markup
        cost_per_tab = purchase_price / number_of_tabs
        unit_price_per_tab_with_markup = 0.0

        if item_type == 'Provision Store':
            if purchase_price >= 1000:
                unit_price_per_tab_with_markup = cost_per_tab * 1.10 # 10% markup
            else:
                unit_price_per_tab_with_markup = cost_per_tab * 1.08 # 8% markup
        else: # Default to Pharmacy or any other type
            unit_price_per_tab_with_markup = cost_per_tab * 1.30 # 30% markup (original logic)
        
        sale_price = unit_price_per_tab_with_markup * number_of_tabs 

        # Check if the product already exists by name (case-insensitive)
        existing_item = next((item for item in items if item['product_name'].strip().lower() == product_name.lower()), None)

        if existing_item:
            existing_item['current_stock'] = existing_item['current_stock'] + added_stock # Add as float
            existing_item['category'] = category
            existing_item['purchase_price'] = purchase_price
            existing_item['sale_price'] = sale_price # Use calculated total sale price
            existing_item['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            existing_item['batch_number'] = batch_number
            existing_item['number_of_tabs'] = number_of_tabs # Update number of tabs
            existing_item['unit_price_per_tab'] = unit_price_per_tab_with_markup # Store new field
            existing_item['item_type'] = item_type # Update item type
            existing_item['expiry_date'] = expiry_date # Update expiry_date
            flash(f'Stock for {product_name} updated successfully! New stock: {existing_item["current_stock"]:.2f}', 'success')
        else:
            new_item = {
                'id': str(uuid.uuid4()),
                'product_name': product_name,
                'category': category,
                'purchase_price': purchase_price,
                'sale_price': sale_price, # Use calculated total sale price
                'current_stock': added_stock, # Store as float
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'batch_number': batch_number,
                'number_of_tabs': number_of_tabs, # Add number of tabs
                'unit_price_per_tab': unit_price_per_tab_with_markup, # Add new field
                'item_type': item_type, # Add new item type
                'expiry_date': expiry_date # Add new expiry_date
            }
            items.append(new_item)
            flash('Inventory item added successfully!', 'success')
        
        save_inventory_for_business(session['business_id'], items)
        return redirect(url_for('inventory'))
    return render_template('add_edit_inventory.html', title='Add Inventory Item', item={}, user_role=session.get('role'))

@app.route('/inventory/edit/<item_id>', methods=['GET', 'POST'])
def edit_inventory(item_id):
    """Edits an existing inventory item or updates its stock. Restricted to Admin."""
    if 'username' not in session or session.get('role') not in ['admin'] or 'business_id' not in session:
        flash('You do not have permission to edit inventory items.', 'danger')
        return redirect(url_for('inventory'))

    items = load_inventory_for_business(session['business_id'])
    item_to_edit = next((item for item in items if item['id'] == item_id), None)

    if not item_to_edit:
        flash('Inventory item not found.', 'danger')
        return redirect(url_for('inventory'))

    if request.method == 'POST':
        item_to_edit['product_name'] = request.form['product_name'].strip()
        item_to_edit['category'] = request.form['category'].strip()
        purchase_price = float(request.form['purchase_price']) # Get updated purchase price
        number_of_tabs = int(request.form['number_of_tabs']) # Get updated number of tabs
        item_type = request.form['item_type'] # Get new item type
        expiry_date = request.form['expiry_date'].strip() # Get new expiry_date

        if number_of_tabs <= 0:
            flash('Number of tabs must be greater than zero.', 'danger')
            # Retain current item data to repopulate the form
            return render_template('add_edit_inventory.html', title='Edit Inventory Item', item=item_to_edit, user_role=session.get('role'))


        # Calculate unit price per tab with conditional markup
        cost_per_tab = purchase_price / number_of_tabs
        unit_price_per_tab_with_markup = 0.0

        if item_type == 'Provision Store':
            if purchase_price >= 1000:
                unit_price_per_tab_with_markup = cost_per_tab * 1.10 # 10% markup
            else:
                unit_price_per_tab_with_markup = cost_per_tab * 1.08 # 8% markup
        else: # Default to Pharmacy or any other type
            unit_price_per_tab_with_markup = cost_per_tab * 1.30 # 30% markup (original logic)
        
        sale_price = unit_price_per_tab_with_markup * number_of_tabs 
        
        item_to_edit['purchase_price'] = purchase_price
        item_to_edit['sale_price'] = sale_price # Use calculated total sale price
        item_to_edit['current_stock'] = float(request.form['current_stock']) # Store stock as float
        item_to_edit['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        item_to_edit['batch_number'] = request.form['batch_number'].strip()
        item_to_edit['number_of_tabs'] = number_of_tabs # Update number of tabs
        item_to_edit['unit_price_per_tab'] = unit_price_per_tab_with_markup # Store new field
        item_to_edit['item_type'] = item_type # Update item type
        item_to_edit['expiry_date'] = expiry_date # Update expiry_date
        save_inventory_for_business(session['business_id'], items)
        flash('Inventory item updated successfully!', 'success')
        return redirect(url_for('inventory'))

    return render_template('add_edit_inventory.html', title='Edit Inventory Item', item=item_to_edit, user_role=session.get('role'))

@app.route('/inventory/delete/<item_id>')
def delete_inventory(item_id):
    """Deletes an inventory item. Restricted to Admin."""
    if 'username' not in session or session.get('role') not in ['admin'] or 'business_id' not in session:
        flash('You do not have permission to delete inventory items.', 'danger')
        return redirect(url_for('inventory'))

    items = load_inventory_for_business(session['business_id'])
    original_len = len(items)
    items = [item for item in items if item['id'] != item_id]
    if len(items) < original_len:
        save_inventory_for_business(session['business_id'], items)
        flash('Inventory item deleted successfully!', 'success')
    else:
        flash('Inventory item not found.', 'danger')
    return redirect(url_for('inventory'))

# --- Daily Sales Management Routes ---

@app.route('/sales')
def sales():
    """Displays the list of sales records."""
    if 'username' not in session or 'business_id' not in session:
        flash('Please log in and select a business to access this page.', 'warning')
        return redirect(url_for('login'))
    
    sales_records = load_sales_for_business(session['business_id'])
    # Sort sales records by date in descending order
    sales_records.sort(key=lambda x: datetime.strptime(x['sale_date'], '%Y-%m-%d %H:%M:%S'), reverse=True)
    return render_template('sales_list.html', sales=sales_records, user_role=session.get('role'))

@app.route('/sales/add', methods=['GET', 'POST'])
def add_sale():
    """Adds a new sales record. Accessible by Admin and Sales."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to add sales records.', 'danger')
        return redirect(url_for('sales'))
    
    inventory_items = load_inventory_for_business(session['business_id'])
    # Filter out inventory items with 0 stock for selection (consider partial packs for tabs)
    available_inventory_items = [item for item in inventory_items if item['current_stock'] > 0]

    # Use business-specific pharmacy info from session
    pharmacy_info = session.get('business_info', {
        'name': ENTERPRISE_NAME, # Fallback to global if not in session
        'location': PHARMACY_LOCATION,
        'address': PHARMACY_ADDRESS,
        'contact': PHARMACY_CONTACT
    })

    if request.method == 'POST':
        sales_records = load_sales_for_business(session['business_id'])
        product_id = request.form['product_id']
        quantity_sold_raw = float(request.form['quantity_sold']) # Read quantity as float
        sale_unit_type = request.form['sale_unit_type'] # 'pack' or 'tab'
        customer_phone = request.form.get('customer_phone', '').strip()
        sales_person_name = request.form.get('sales_person_name', session.get('username', 'N/A')).strip()


        # Find the product in inventory to get current stock and prices
        product = next((item for item in inventory_items if item['id'] == product_id), None)

        if not product:
            flash('Selected product not found in inventory.', 'danger')
            # For POST request, return request.form to pre-fill fields
            form_data = request.form.to_dict()
            form_data['quantity_sold'] = quantity_sold_raw # Ensure float value is passed back
            return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=available_inventory_items, sale=form_data, user_role=session.get('role'), pharmacy_info=pharmacy_info)

        current_stock_packs = product['current_stock']
        number_of_tabs_per_pack = float(product['number_of_tabs']) # Cast to float for calculation
        sale_price_per_pack = product['sale_price']
        unit_price_per_tab = product['unit_price_per_tab']

        # Determine actual quantity for deduction and total amount calculation
        quantity_to_deduct_packs = 0.0
        total_amount_sold = 0.0
        price_at_time_per_unit_sold = 0.0
        display_unit_text = ""
        quantity_for_record = 0.0

        if sale_unit_type == 'tab':
            # Selling by tabs
            quantity_sold_tabs = quantity_sold_raw # quantity_sold_raw is number of tabs
            available_tabs = current_stock_packs * number_of_tabs_per_pack

            if quantity_sold_tabs <= 0:
                flash('Quantity of tabs sold must be at least 1.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = quantity_sold_raw
                return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=available_inventory_items, sale=form_data, user_role=session.get('role'), pharmacy_info=pharmacy_info)

            if quantity_sold_tabs > available_tabs:
                flash(f'Insufficient stock for {product["product_name"]}. Available: {available_tabs:.0f} tabs.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = quantity_sold_raw
                return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=available_inventory_items, sale=form_data, user_role=session.get('role'), pharmacy_info=pharmacy_info)
            
            quantity_to_deduct_packs = quantity_sold_tabs / number_of_tabs_per_pack
            total_amount_sold = quantity_sold_tabs * unit_price_per_tab
            price_at_time_per_unit_sold = unit_price_per_tab
            display_unit_text = "tab(s)"
            quantity_for_record = quantity_sold_tabs # Store tabs for record if type is tab
        else: # sale_unit_type == 'pack'
            # Selling by packs
            quantity_sold_packs = quantity_sold_raw # quantity_sold_raw is number of packs

            if quantity_sold_packs <= 0:
                flash('Quantity of packs sold must be at least 1.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = quantity_sold_raw
                return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=available_inventory_items, sale=form_data, user_role=session.get('role'), pharmacy_info=pharmacy_info)

            if quantity_sold_packs > current_stock_packs:
                flash(f'Insufficient stock for {product["product_name"]}. Available: {current_stock_packs:.2f} packs.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = quantity_sold_raw
                return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=available_inventory_items, sale=form_data, user_role=session.get('role'), pharmacy_info=pharmacy_info)
            
            quantity_to_deduct_packs = quantity_sold_packs
            total_amount_sold = quantity_sold_packs * sale_price_per_pack
            price_at_time_per_unit_sold = sale_price_per_pack
            display_unit_text = "pack(s)"
            quantity_for_record = quantity_sold_packs # Store packs for record if type is pack


        # Update stock
        product['current_stock'] = current_stock_packs - quantity_to_deduct_packs
        save_inventory_for_business(session['business_id'], inventory_items) # Save updated inventory

        new_sale = {
            'id': str(uuid.uuid4()),
            'reference_number': str(uuid.uuid4())[:8].upper(), # Generate a short unique reference number
            'product_id': product_id,
            'product_name': product['product_name'],
            'quantity_sold': quantity_for_record, # Store actual quantity sold in selected unit
            'sale_unit_type': sale_unit_type, # Store 'pack' or 'tab'
            'price_at_time_per_unit_sold': price_at_time_per_unit_sold, # Store price of that unit (tab or pack)
            'total_amount': total_amount_sold,
            'sale_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'customer_phone': customer_phone,
            'sales_person_name': sales_person_name
        }
        sales_records.append(new_sale)
        save_sales_for_business(session['business_id'], sales_records)
        flash('Sale record added successfully and stock updated!', 'success')

        # Send SMS receipt if phone number is provided and valid
        if customer_phone:
            # Get dynamic business name from session
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Receipt (Ref: {new_sale['reference_number']}):\n" 
                f"Item: {product['product_name']}\n"
                f"Qty: {quantity_for_record:.2f} {display_unit_text}\n"
                f"Unit Price: GH₵{price_at_time_per_unit_sold:.2f} per {sale_unit_type}\n"
                f"Total: GH₵{total_amount_sold:.2f}\n"
                f"Date: {new_sale['sale_date']}\n\n"
                f"Thank you for trading with us\n"
                f"From: {business_name_for_sms}" # Use dynamic business name
            )
            sms_payload = {
                'action': 'send-sms',
                'api_key': ARKESEL_API_KEY,
                'to': customer_phone,
                'from': ARKESEL_SENDER_ID,
                'sms': message
            }
            try:
                sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload) 
                sms_result = {}
                if sms_response.status_code == 200:
                    try:
                        sms_result = sms_response.json()
                    except json.JSONDecodeError:
                        print(f"Arkesel SMS JSON Decode Error: {sms_response.text}")
                        flash(f'Failed to send SMS receipt to {customer_phone}. API returned non-JSON response.', 'warning')
                        # It's important to still redirect even if SMS fails, so the sale is recorded
                        return redirect(url_for('sales')) 
                else:
                    print(f"Arkesel SMS API Error (Status {sms_response.status_code}): {sms_response.text}")
                    flash(f'Failed to send SMS receipt to {customer_phone}. API error.', 'warning')
                    return redirect(url_for('sales'))

                if sms_result and sms_result.get('status') == 'success':
                    flash(f'SMS receipt sent to {customer_phone} successfully!', 'info')
                else:
                    print(f'Arkesel SMS Error: {sms_result.get("message", "Unknown error")}')
                    flash(f'Failed to send SMS receipt to {customer_phone}. Error: {sms_result.get("message", "Unknown error")}', 'warning')
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS: {e}')
                flash(f'Network error when trying to send SMS receipt.', 'warning')

        return redirect(url_for('sales'))
    
    # Default values for initial GET request
    default_sale = {
        'sales_person_name': session.get('username', 'N/A'),
        'sale_unit_type': 'pack', # Default to 'pack'
        'quantity_sold': '', # Ensure quantity field is empty initially
        'reference_number': '' # Initialize for display (though it will be generated on POST)
    }
    return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=available_inventory_items, sale=default_sale, user_role=session.get('role'), pharmacy_info=pharmacy_info)

@app.route('/sales/edit/<sale_id>', methods=['GET', 'POST'])
def edit_sale(sale_id):
    """Edits an existing sales record. Accessible by Admin and Sales.
       Sales personnel edits do NOT affect inventory stock.
    """
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to edit sales records.', 'danger')
        return redirect(url_for('sales'))
    
    sales_records = load_sales_for_business(session['business_id'])
    inventory_items = load_inventory_for_business(session['business_id'])
    sale_to_edit = next((sale for sale in sales_records if sale['id'] == sale_id), None)

    if not sale_to_edit:
        flash('Sale record not found.', 'danger')
        return redirect(url_for('sales'))

    available_inventory_items = inventory_items 

    # Use business-specific pharmacy info from session
    pharmacy_info = session.get('business_info', {
        'name': ENTERPRISE_NAME, # Fallback to global if not in session
        'location': PHARMACY_LOCATION,
        'address': PHARMACY_ADDRESS,
        'contact': PHARMACY_CONTACT
    })

    if request.method == 'POST':
        old_quantity_sold_record = sale_to_edit['quantity_sold']
        old_sale_unit_type = sale_to_edit['sale_unit_type']

        new_quantity_sold_raw = float(request.form['quantity_sold'])
        new_sale_unit_type = request.form['sale_unit_type']
        
        product_id = request.form['product_id']
        customer_phone = request.form.get('customer_phone', '').strip()
        sales_person_name = request.form.get('sales_person_name', sale_to_edit.get('sales_person_name', 'N/A')).strip()


        product = next((item for item in inventory_items if item['id'] == product_id), None)
        if not product:
            flash('Selected product not found in inventory.', 'danger')
            # For POST request, return request.form to pre-fill fields
            form_data = request.form.to_dict()
            form_data['quantity_sold'] = new_quantity_sold_raw
            form_data['reference_number'] = sale_to_edit.get('reference_number', '') # Preserve ref num
            return render_template('add_edit_sale.html', title='Edit Sale Record', sale=form_data, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info)

        current_stock_packs = product['current_stock']
        number_of_tabs_per_pack = float(product['number_of_tabs']) # Cast to float for calculation
        sale_price_per_pack = product['sale_price']
        unit_price_per_tab = product['unit_price_per_tab']

        # Convert old sale quantity to packs for stock reversal
        old_quantity_in_packs = 0.0
        if old_sale_unit_type == 'tab':
            old_quantity_in_packs = old_quantity_sold_record / number_of_tabs_per_pack
        else: # 'pack'
            old_quantity_in_packs = old_quantity_sold_record
        
        # Calculate new quantities and total
        quantity_to_deduct_packs = 0.0
        new_total_amount_sold = 0.0
        new_price_at_time_per_unit_sold = 0.0
        display_unit_text = ""
        new_quantity_for_record = 0.0

        if new_sale_unit_type == 'tab':
            new_quantity_sold_tabs = new_quantity_sold_raw
            if new_quantity_sold_tabs <= 0:
                flash('Quantity of tabs sold must be at least 1.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = new_quantity_sold_raw
                form_data['reference_number'] = sale_to_edit.get('reference_number', '') # Preserve ref num
                return render_template('add_edit_sale.html', title='Edit Sale Record', sale=form_data, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info)

            new_quantity_in_packs = new_quantity_sold_tabs / number_of_tabs_per_pack
            new_total_amount_sold = new_quantity_sold_tabs * unit_price_per_tab
            new_price_at_time_per_unit_sold = unit_price_per_tab
            display_unit_text = "tab(s)"
            new_quantity_for_record = new_quantity_sold_tabs
        else: # new_sale_unit_type == 'pack'
            new_quantity_sold_packs = new_quantity_sold_raw
            if new_quantity_sold_packs <= 0:
                flash('Quantity of packs sold must be at least 1.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = new_quantity_sold_raw
                form_data['reference_number'] = sale_to_edit.get('reference_number', '') # Preserve ref num
                return render_template('add_edit_sale.html', title='Edit Sale Record', sale=form_data, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info)

            new_quantity_in_packs = new_quantity_sold_packs
            new_total_amount_sold = new_quantity_sold_packs * sale_price_per_pack
            new_price_at_time_per_unit_sold = sale_price_per_pack
            display_unit_text = "pack(s)"
            new_quantity_for_record = new_quantity_sold_packs


        if session.get('role') == 'admin':
            # Revert old stock, then apply new deduction
            adjusted_stock_after_revert = current_stock_packs + old_quantity_in_packs
            quantity_to_deduct_packs = new_quantity_in_packs 

            if adjusted_stock_after_revert - quantity_to_deduct_packs < 0:
                flash(f'Insufficient stock for {product["product_name"]} to adjust sale quantity. Available: {adjusted_stock_after_revert:.2f} packs.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = new_quantity_sold_raw
                form_data['reference_number'] = sale_to_edit.get('reference_number', '') # Preserve ref num
                return render_template('add_edit_sale.html', title='Edit Sale Record', sale=form_data, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info)
            
            product['current_stock'] = adjusted_stock_after_revert - quantity_to_deduct_packs
            save_inventory_for_business(session['business_id'], inventory_items)
            flash('Inventory stock adjusted due to sale edit (Admin action).', 'info')
        else:
            flash('Sales personnel edits do not affect inventory stock. Only the sale record is updated.', 'warning')

        sale_to_edit['product_id'] = product_id
        sale_to_edit['product_name'] = product['product_name']
        sale_to_edit['quantity_sold'] = new_quantity_for_record
        sale_to_edit['sale_unit_type'] = new_sale_unit_type
        sale_to_edit['price_at_time_per_unit_sold'] = new_price_at_time_per_unit_sold
        sale_to_edit['total_amount'] = new_total_amount_sold
        sale_to_edit['sale_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sale_to_edit['customer_phone'] = customer_phone
        sale_to_edit['sales_person_name'] = sales_person_name 
        # Preserve reference number on edit
        sale_to_edit['reference_number'] = sale_to_edit.get('reference_number', '')

        save_sales_for_business(session['business_id'], sales_records)
        flash('Sale record updated successfully!', 'success')

        # Send SMS receipt if phone number is provided
        if customer_phone:
            # Get dynamic business name from session
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Receipt (Edited - Ref: {sale_to_edit['reference_number']}):\n" 
                f"Item: {product['product_name']}\n"
                f"Qty: {new_quantity_for_record:.2f} {display_unit_text}\n"
                f"Unit Price: GH₵{new_price_at_time_per_unit_sold:.2f} per {new_sale_unit_type}\n"
                f"Total: GH₵{new_total_amount_sold:.2f}\n"
                f"Date: {sale_to_edit['sale_date']}\n\n"
                f"Thank you for trading with us\n"
                f"From: {business_name_for_sms}" # Use dynamic business name
            )
            sms_payload = {
                'action': 'send-sms',
                'api_key': ARKESEL_API_KEY,
                'to': customer_phone,
                'from': ARKESEL_SENDER_ID,
                'sms': message
            }
            try:
                sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
                sms_result = {}
                if sms_response.status_code == 200:
                    try:
                        sms_result = sms_response.json()
                    except json.JSONDecodeError:
                        print(f"Arkesel SMS JSON Decode Error: {sms_response.text}")
                        flash(f'Failed to send SMS receipt to {customer_phone}. API returned non-JSON response.', 'warning')
                        return redirect(url_for('sales'))
                else:
                    print(f"Arkesel SMS API Error (Status {sms_response.status_code}): {sms_response.text}")
                    flash(f'Failed to send SMS receipt to {customer_phone}. API error.', 'warning')
                    return redirect(url_for('sales'))

                if sms_result and sms_result.get('status') == 'success':
                    flash(f'SMS receipt sent to {customer_phone} successfully!', 'info')
                else:
                    print(f'Arkesel SMS Error: {sms_result.get("message", "Unknown error")}')
                    flash(f'Failed to send SMS receipt to {customer_phone}. Please check phone number format.', 'warning')
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS: {e}')
                flash(f'Network error when trying to send SMS receipt.', 'warning')

        return redirect(url_for('sales'))
    
    # Default values for initial GET request (edit mode)
    if 'customer_phone' not in sale_to_edit:
        sale_to_edit['customer_phone'] = ''
    if 'sales_person_name' not in sale_to_edit:
        sale_to_edit['sales_person_name'] = session.get('username', 'N/A')
    # Ensure sale_unit_type and quantity_sold are present for editing existing records
    if 'sale_unit_type' not in sale_to_edit:
        sale_to_edit['sale_unit_type'] = 'pack' # Default for old records
    if 'quantity_sold' not in sale_to_edit: # Fallback for old records without explicit quantity_sold
        sale_to_edit['quantity_sold'] = float(sale_to_edit.get('quantity_sold', 0.0))
    if 'reference_number' not in sale_to_edit: # Fallback for old records without explicit reference_number
        sale_to_edit['reference_number'] = ''
    
    return render_template('add_edit_sale.html', title='Edit Sale Record', sale=sale_to_edit, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info)


@app.route('/sales/delete/<sale_id>')
def delete_sale(sale_id):
    """Deletes a sales record and adjusts stock (dangerous for real systems). Accessible by Admin and Sales."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to delete sales records.', 'danger')
        return redirect(url_for('sales'))
    
    sales_records = load_sales_for_business(session['business_id'])
    inventory_items = load_inventory_for_business(session['business_id'])
    
    sale_to_delete = next((sale for sale in sales_records if sale['id'] == sale_id), None)
    
    if not sale_to_delete:
        flash('Sale record not found.', 'danger')
        return redirect(url_for('sales'))

    product_id = sale_to_delete['product_id']
    quantity_sold_record = sale_to_delete['quantity_sold']
    sale_unit_type = sale_to_delete.get('sale_unit_type', 'pack') # Default to pack for old records

    product = next((item for item in inventory_items if item['id'] == product_id), None)

    if product:
        # Determine quantity to add back to stock based on original sale unit type
        quantity_to_add_packs = 0.0
        if sale_unit_type == 'tab':
            # Convert tabs sold back to packs for stock adjustment
            quantity_to_add_packs = quantity_sold_record / float(product['number_of_tabs']) # Cast to float
        else: # 'pack'
            quantity_to_add_packs = quantity_sold_record
            
        product['current_stock'] = product['current_stock'] + quantity_to_add_packs
        save_inventory_for_business(session['business_id'], inventory_items)
        # Ensure product["current_stock"] is treated as float for formatting
        flash(f'Stock for {product["product_name"]} adjusted due to sale deletion. New stock: {float(product["current_stock"]):.2f} packs.', 'info')
    else:
        flash('Associated product for deleted sale not found in inventory. Stock not adjusted.', 'warning')


    original_len = len(sales_records)
    sales_records = [sale for sale in sales_records if sale['id'] != sale_id]
    if len(sales_records) < original_len:
        save_sales_for_business(session['business_id'], sales_records)
        flash('Sale record deleted successfully!', 'success')
    else:
        flash('Sale record not found.', 'danger')
    return redirect(url_for('sales'))


@app.route('/sales/return_item', methods=['GET', 'POST'])
def return_item():
    """Handles customer returns and adjusts sales/inventory."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to process returns.', 'danger')
        return redirect(url_for('sales'))
    
    if request.method == 'POST':
        ref_number = request.form['reference_number'].strip().upper()
        return_quantity_raw = float(request.form['return_quantity']) # Quantity to return
        return_unit_type = request.form['return_unit_type'] # 'pack' or 'tab'

        sales_records = load_sales_for_business(session['business_id'])
        inventory_items = load_inventory_for_business(session['business_id'])

        # Find the original sale record by reference number
        original_sale = next((s for s in sales_records if s.get('reference_number', '').upper() == ref_number), None)

        if not original_sale:
            flash(f'Sale with Reference Number {ref_number} not found.', 'danger')
            return render_template('return_item.html', user_role=session.get('role'))
        
        # Ensure the product from the original sale still exists in inventory
        product = next((item for item in inventory_items if item['id'] == original_sale['product_id']), None)
        if not product:
            flash(f'Product {original_sale["product_name"]} from sale {ref_number} not found in inventory. Cannot process return.', 'danger')
            return render_template('return_item.html', user_role=session.get('role'))

        original_quantity_sold_record = original_sale['quantity_sold']
        original_sale_unit_type = original_sale['sale_unit_type']
        
        number_of_tabs_per_pack = float(product['number_of_tabs']) # Cast to float for calculation
        price_at_time_per_unit_sold = original_sale['price_at_time_per_unit_sold']

        # Determine actual quantity returned in terms of base units (packs)
        return_quantity_in_packs = 0.0
        returned_amount = 0.0
        display_unit_text = ""

        if return_unit_type == 'tab':
            # Returning by tabs
            if return_quantity_raw <= 0:
                flash('Return quantity of tabs must be at least 1.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product)

            # Check if returned tabs exceed original sale quantity (converted to tabs)
            original_quantity_tabs = original_quantity_sold_record
            if original_sale_unit_type == 'pack':
                original_quantity_tabs = original_quantity_sold_record * number_of_tabs_per_pack

            if return_quantity_raw > original_quantity_tabs:
                flash(f'Cannot return {return_quantity_raw:.0f} tabs. Only {original_quantity_tabs:.0f} tabs were originally sold for this reference number.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product)

            return_quantity_in_packs = return_quantity_raw / number_of_tabs_per_pack
            returned_amount = return_quantity_raw * price_at_time_per_unit_sold # Use price_at_time_per_unit_sold
            display_unit_text = "tab(s)"
            quantity_for_return_record = return_quantity_raw

        else: # return_unit_type == 'pack'
            # Returning by packs
            if return_quantity_raw <= 0:
                flash('Return quantity of packs must be at least 1.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product)
            
            # Check if returned packs exceed original sale quantity (converted to packs)
            original_quantity_packs = original_quantity_sold_record
            if original_sale_unit_type == 'tab':
                original_quantity_packs = original_quantity_sold_record / number_of_tabs_per_pack
            
            if return_quantity_raw > original_quantity_packs:
                flash(f'Cannot return {return_quantity_raw:.2f} packs. Only {original_quantity_packs:.2f} packs were originally sold for this reference number.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product)

            return_quantity_in_packs = return_quantity_raw
            returned_amount = return_quantity_raw * price_at_time_per_unit_sold # Use price_at_time_per_unit_sold
            display_unit_text = "pack(s)"
            quantity_for_return_record = return_quantity_raw

        # Create a new "negative" sale record for the return
        # This effectively deducts the returned amount from total sales reports
        return_sale_record = {
            'id': str(uuid.uuid4()),
            'reference_number': f"RMA-{ref_number}", # RMA = Return Merchandise Authorization
            'product_id': original_sale['product_id'],
            'product_name': original_sale['product_name'],
            'quantity_sold': -quantity_for_return_record, # Store as negative quantity
            'sale_unit_type': return_unit_type, # Store return unit type
            'price_at_time_per_unit_sold': price_at_time_per_unit_sold, # Price is same as original sale's unit price
            'total_amount': -returned_amount, # Store as negative amount
            'sale_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'customer_phone': original_sale.get('customer_phone', 'N/A'),
            'sales_person_name': session.get('username', 'N/A') + " (Return)"
        }
        sales_records.append(return_sale_record)
        save_sales_for_business(session['business_id'], sales_records)

        # Update inventory stock - add items back
        product['current_stock'] = product['current_stock'] + return_quantity_in_packs
        save_inventory_for_business(session['business_id'], inventory_items)

        flash(f'Return processed for Reference Number {ref_number}. {return_quantity_raw:.2f} {display_unit_text} of {original_sale["product_name"]} returned. Total sales adjusted by GH₵{returned_amount:.2f}.', 'success')
        
        # Send SMS notification for return
        if original_sale.get('customer_phone'):
            # Get dynamic business name from session
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Return Confirmation (Ref: {return_sale_record['reference_number']}):\n"
                f"Item: {original_sale['product_name']}\n"
                f"Qty Returned: {quantity_for_return_record:.2f} {display_unit_text}\n"
                f"Amount Refunded: GH₵{returned_amount:.2f}\n"
                f"Date: {return_sale_record['sale_date']}\n\n"
                f"From: {business_name_for_sms}" # Use dynamic business name
            )
            sms_payload = {
                'action': 'send-sms',
                'api_key': ARKESEL_API_KEY,
                'to': original_sale['customer_phone'],
                'from': ARKESEL_SENDER_ID,
                'sms': message
            }
            try:
                sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
                sms_result = {}
                if sms_response.status_code == 200:
                    try:
                        sms_result = sms_response.json()
                    except json.JSONDecodeError:
                        print(f"Arkesel SMS JSON Decode Error: {sms_response.text}")
                        flash(f'Failed to send SMS return confirmation to {original_sale["customer_phone"]}. API returned non-JSON response.', 'warning')
                else:
                    print(f"Arkesel SMS API Error (Status {sms_response.status_code}): {sms_response.text}")
                    flash(f'Failed to send SMS return confirmation to {original_sale["customer_phone"]}. API error.', 'warning')
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS: {e}')
                flash(f'Network error when trying to send SMS return confirmation.', 'warning')

        return redirect(url_for('sales'))

    return render_template('return_item.html', user_role=session.get('role'))


# --- Reporting and Statistics Routes ---

@app.route('/reports')
def reports():
    """Displays various statistics and reports."""
    if 'username' not in session or 'business_id' not in session:
        flash('Please log in and select a business to access this page.', 'warning')
        return redirect(url_for('login'))

    inventory_items = load_inventory_for_business(session['business_id'])
    sales_records = load_sales_for_business(session['business_id'])

    # 1. Statistics of Stocks Available
    stock_summary = [
        {'product_name': item['product_name'], 'current_stock': f"{item['current_stock']:.2f}"}
        for item in inventory_items
    ]

    # 2. Sales per Day, Week, Month
    daily_sales = {}
    weekly_sales = {}
    monthly_sales = {}
    sales_per_person = {} # Dictionary to hold sales per personnel

    for sale in sales_records:
        sale_date_obj = datetime.strptime(sale['sale_date'], '%Y-%m-%d %H:%M:%S')
        total_amount = float(sale['total_amount'])
        sales_person = sale.get('sales_person_name', 'Unknown') # Get sales person, default to 'Unknown'

        # Daily
        day_key = sale_date_obj.strftime('%Y-%m-%d')
        daily_sales[day_key] = daily_sales.get(day_key, 0.0) + total_amount

        # Weekly (using ISO week number)
        week_key = sale_date_obj.strftime('%Y-W%W')
        weekly_sales[week_key] = weekly_sales.get(week_key, 0.0) + total_amount

        # Monthly
        month_key = sale_date_obj.strftime('%Y-%m')
        monthly_sales[month_key] = monthly_sales.get(month_key, 0.0) + total_amount

        # Sales per personnel
        sales_per_person[sales_person] = sales_per_person.get(sales_person, 0.0) + total_amount


    # Sort sales reports by date/name
    sorted_daily_sales = sorted(daily_sales.items())
    sorted_weekly_sales = sorted(weekly_sales.items())
    sorted_monthly_sales = sorted(monthly_sales.items())
    sorted_sales_per_person = sorted(sales_per_person.items()) # Sorted sales per personnel

    return render_template(
        'reports.html',
        stock_summary=stock_summary,
        daily_sales=sorted_daily_sales,
        weekly_sales=sorted_weekly_sales,
        monthly_sales=sorted_monthly_sales,
        sales_per_person=sorted_sales_per_person, # Pass sales per personnel to template
        user_role=session.get('role')
    )

@app.route('/reports/send_daily_sms', methods=['POST'])
def send_daily_sms_report():
    """Generates and sends a daily sales report via SMS to the admin."""
    if 'username' not in session or session.get('role') not in ['admin'] or 'business_id' not in session:
        flash('You do not have permission to send daily SMS reports.', 'danger')
        return redirect(url_for('dashboard'))

    sales_records = load_sales_for_business(session['business_id'])
    
    today = date.today()
    today_sales = [
        sale for sale in sales_records 
        if datetime.strptime(sale['sale_date'], '%Y-%m-%d %H:%M:%S').date() == today
    ]

    total_sales_amount = sum(float(s['total_amount']) for s in today_sales)
    total_items_sold = sum(float(s['quantity_sold']) for s in today_sales) # Sum as float now
    
    # Create a summary of products sold today
    product_sales_summary = {}
    for sale in today_sales:
        product_name = sale['product_name']
        quantity = float(sale['quantity_sold']) # Read as float
        unit_type = sale.get('sale_unit_type', 'pack') # Default for old records
        
        # Aggregate based on product name and unit type
        key = f"{product_name} ({unit_type})"
        product_sales_summary[key] = product_sales_summary.get(key, 0.0) + quantity

    # Get dynamic business name from session
    business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)

    # Format the message
    message = f"Daily Sales Report ({today.strftime('%Y-%m-%d')}):\n"
    message += f"Total Revenue: GH₵{total_sales_amount:.2f}\n"
    message += f"Total Items Sold (approx): {total_items_sold:.2f}\n" # Note approx due to mixed units
    if product_sales_summary:
        message += "Product Breakdown:\n"
        for product_key, qty in product_sales_summary.items():
            message += f"- {product_key}: {qty:.2f} units\n"
    else:
        message += "No sales recorded today."

    message += f"\nThank you for trading with us\n"
    message += f"From: {business_name_for_sms}" # Use dynamic business name

    if not ADMIN_PHONE_NUMBER:
        flash('Admin phone number is not configured for SMS reports.', 'danger')
        return redirect(url_for('reports'))

    sms_payload = {
        'action': 'send-sms',
        'api_key': ARKESEL_API_KEY,
        'to': ADMIN_PHONE_NUMBER,
        'from': ARKESEL_SENDER_ID,
        'sms': message
    }

    try:
        sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
        sms_result = {}
        if sms_response.status_code == 200:
            try:
                sms_result = sms_response.json()
            except json.JSONDecodeError:
                print(f"Arkesel SMS JSON Decode Error: {sms_response.text}")
                flash(f'Failed to send daily sales report SMS. API returned non-JSON response.', 'danger')
                return redirect(url_for('reports'))
        else:
            print(f"Arkesel SMS API Error (Status {sms_response.status_code}): {sms_response.text}")
            flash(f'Failed to send daily sales report SMS. API error (Status {sms_response.status_code}).', 'danger')
            return redirect(url_for('reports'))

        if sms_result and sms_result.get('status') == 'success':
            flash('Daily sales report SMS sent to admin successfully!', 'success')
        else:
            print(f'Arkesel SMS Error: {sms_result.get("message", "Unknown error")}')
            flash(f'Failed to send daily sales report SMS. Error: {sms_result.get("message", "Unknown error")}', 'danger')
    except requests.exceptions.RequestException as e:
        print(f'Network error sending SMS: {e}')
        flash(f'Network error when trying to send daily sales report SMS: {e}', 'danger')

    return redirect(url_for('reports'))

# --- Main entry point ---
if __name__ == '__main__':
    app.run(debug=True)
