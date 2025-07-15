# app.py - Enhanced Flask Application for Pharmaceutical Store Administrator with PostgreSQL

from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
import psycopg2 # PostgreSQL adapter
from psycopg2 import extras # For DictCursor
import os
import uuid
from datetime import datetime, date
import requests
from dotenv import load_dotenv
import json
import io

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_super_secret_key_here')

# --- Global User Management (for super admin) ---
SUPER_ADMIN_USERNAME = os.getenv('SUPER_ADMIN_USERNAME', 'superadmin')
SUPER_ADMIN_PASSWORD = os.getenv('SUPER_ADMIN_PASSWORD', 'superpassword')

# --- Arkesel SMS API Configuration ---
ARKESEL_API_KEY = os.getenv('ARKESEL_API_KEY', 'YOUR_ARKESEL_API_KEY')
ARKESEL_SENDER_ID = os.getenv('ARKESEL_SENDER_ID', 'PHARMACY')
ARKESEL_SMS_URL = "https://sms.arkesel.com/sms/api" 
ADMIN_PHONE_NUMBER = os.getenv('ADMIN_PHONE_NUMBER', '233543169389')

# Global pharmacy info (will be overridden by business-specific info if available)
ENTERPRISE_NAME = os.getenv('ENTERPRISE_NAME', 'My Pharmacy') 
PHARMACY_LOCATION = os.getenv('PHARMACY_LOCATION', 'Accra, Ghana')
PHARMACY_ADDRESS = os.getenv('PHARMACY_ADDRESS', '123 Main St, City')
PHARMACY_CONTACT = os.getenv('PHARMACY_CONTACT', '+233543169389')

# --- PostgreSQL Database Configuration ---
DB_NAME = os.getenv('DB_NAME', 'pharmacy_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')

def get_db_connection():
    """Establishes and returns a PostgreSQL database connection."""
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        return conn
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        flash("Failed to connect to the database. Please check configuration.", "danger")
        return None

def init_db():
    """Initializes the database by creating tables if they don't exist."""
    conn = get_db_connection()
    if conn is None:
        return

    try:
        cur = conn.cursor()

        # Businesses table (main table for super admin)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                address VARCHAR(255),
                location VARCHAR(255),
                contact VARCHAR(255)
            );
        """)

        # Users table (business-specific users)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(255) NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL,
                business_id UUID NOT NULL,
                PRIMARY KEY (username, business_id),
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
            );
        """)

        # Inventory table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id UUID PRIMARY KEY,
                business_id UUID NOT NULL,
                product_name VARCHAR(255) NOT NULL,
                category VARCHAR(255),
                purchase_price NUMERIC(10, 2) NOT NULL,
                sale_price NUMERIC(10, 2) NOT NULL,
                current_stock NUMERIC(10, 2) NOT NULL,
                last_updated TIMESTAMP NOT NULL,
                batch_number VARCHAR(255),
                number_of_tabs INTEGER NOT NULL,
                unit_price_per_tab NUMERIC(10, 2) NOT NULL,
                item_type VARCHAR(50) NOT NULL,
                expiry_date VARCHAR(10), -- Storing as VARCHAR for flexibility 'YYYY-MM-DD'
                is_fixed_price BOOLEAN DEFAULT FALSE,
                fixed_sale_price NUMERIC(10, 2) DEFAULT 0.00,
                UNIQUE (product_name, business_id),
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
            );
        """)

        # Sales table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id UUID PRIMARY KEY,
                business_id UUID NOT NULL,
                product_id UUID NOT NULL,
                product_name VARCHAR(255) NOT NULL,
                quantity_sold NUMERIC(10, 2) NOT NULL,
                sale_unit_type VARCHAR(50) NOT NULL,
                price_at_time_per_unit_sold NUMERIC(10, 2) NOT NULL,
                total_amount NUMERIC(10, 2) NOT NULL,
                sale_date TIMESTAMP NOT NULL,
                customer_phone VARCHAR(255),
                sales_person_name VARCHAR(255) NOT NULL,
                reference_number VARCHAR(255) UNIQUE,
                transaction_id UUID NOT NULL,
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
                -- FOREIGN KEY (product_id) REFERENCES inventory(id) ON DELETE SET NULL -- Optional, if you want to link sales to inventory items
            );
        """)

        # Companies table (debtors)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id UUID PRIMARY KEY,
                business_id UUID NOT NULL,
                name VARCHAR(255) NOT NULL UNIQUE,
                contact_person VARCHAR(255),
                phone VARCHAR(255),
                email VARCHAR(255),
                address VARCHAR(255),
                balance NUMERIC(10, 2) DEFAULT 0.00,
                UNIQUE (name, business_id),
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
            );
        """)

        # Company Transactions table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS company_transactions (
                id UUID PRIMARY KEY,
                business_id UUID NOT NULL,
                company_id UUID NOT NULL,
                date TIMESTAMP NOT NULL,
                type VARCHAR(50) NOT NULL, -- 'Credit' or 'Debit'
                amount NUMERIC(10, 2) NOT NULL,
                description TEXT,
                recorded_by VARCHAR(255),
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            );
        """)

        # Future Orders table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS future_orders (
                id UUID PRIMARY KEY,
                business_id UUID NOT NULL,
                customer_name VARCHAR(255) NOT NULL,
                customer_phone VARCHAR(255),
                items_json TEXT NOT NULL, -- Store JSON string of items
                total_amount NUMERIC(10, 2) NOT NULL,
                amount_paid NUMERIC(10, 2) NOT NULL,
                date_ordered TIMESTAMP NOT NULL,
                expected_collection_date DATE,
                actual_collection_date TIMESTAMP,
                status VARCHAR(50) NOT NULL, -- e.g., 'Pending', 'Collected', 'Cancelled'
                FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
            );
        """)

        conn.commit()
        print("Database tables initialized successfully.")
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Error initializing database: {e}")
        flash("Error initializing database tables.", "danger")
    finally:
        if conn:
            cur.close()
            conn.close()

# Initialize the database on app startup
init_db()

# --- Database Helper Functions ---

def fetch_all(query, params=None):
    conn = get_db_connection()
    if conn is None:
        return []
    try:
        # Use DictCursor to fetch rows as dictionaries
        cur = conn.cursor(cursor_factory=extras.DictCursor)
        cur.execute(query, params)
        rows = cur.fetchall()
        # Convert DictRow objects to regular dictionaries
        return [dict(row) for row in rows]
    except psycopg2.Error as e:
        print(f"Database fetch error: {e}")
        flash("Error fetching data from database.", "danger")
        return []
    finally:
        if conn:
            cur.close()
            conn.close()

def execute_query(query, params=None, fetch_result=False):
    conn = get_db_connection()
    if conn is None:
        return None if fetch_result else False
    try:
        cur = conn.cursor(cursor_factory=extras.DictCursor if fetch_result else None)
        cur.execute(query, params)
        if fetch_result:
            result = cur.fetchone()
            return dict(result) if result else None
        conn.commit()
        return True
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Database execution error: {e}")
        flash("Error performing database operation.", "danger")
        return None if fetch_result else False
    finally:
        if conn:
            cur.close()
            conn.close()

# --- Business Data Access Functions (PostgreSQL) ---

def load_businesses():
    """Loads all registered businesses from the database."""
    query = "SELECT id, name, address, location, contact FROM businesses ORDER BY name;"
    return fetch_all(query)

def save_business(business):
    """Saves a single business (insert or update)."""
    query = """
        INSERT INTO businesses (id, name, address, location, contact)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name, address = EXCLUDED.address, 
            location = EXCLUDED.location, contact = EXCLUDED.contact;
    """
    params = (
        business['id'], business['name'], business['address'],
        business['location'], business['contact']
    )
    return execute_query(query, params)

def delete_business_from_db(business_id):
    """Deletes a business and all its associated data (due to CASCADE)."""
    query = "DELETE FROM businesses WHERE id = %s;"
    return execute_query(query, (business_id,))

def load_inventory_for_business(business_id):
    """Loads inventory items for a specific business."""
    query = """
        SELECT id, product_name, category, purchase_price, sale_price, current_stock,
               last_updated, batch_number, number_of_tabs, unit_price_per_tab,
               item_type, expiry_date, is_fixed_price, fixed_sale_price
        FROM inventory
        WHERE business_id = %s
        ORDER BY product_name;
    """
    return fetch_all(query, (business_id,))

def save_inventory_item_for_business(business_id, item):
    """Saves a single inventory item (insert or update)."""
    query = """
        INSERT INTO inventory (id, business_id, product_name, category, purchase_price,
                               sale_price, current_stock, last_updated, batch_number,
                               number_of_tabs, unit_price_per_tab, item_type, expiry_date,
                               is_fixed_price, fixed_sale_price)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET product_name = EXCLUDED.product_name, category = EXCLUDED.category,
            purchase_price = EXCLUDED.purchase_price, sale_price = EXCLUDED.sale_price,
            current_stock = EXCLUDED.current_stock, last_updated = EXCLUDED.last_updated,
            batch_number = EXCLUDED.batch_number, number_of_tabs = EXCLUDED.number_of_tabs,
            unit_price_per_tab = EXCLUDED.unit_price_per_tab, item_type = EXCLUDED.item_type,
            expiry_date = EXCLUDED.expiry_date, is_fixed_price = EXCLUDED.is_fixed_price,
            fixed_sale_price = EXCLUDED.fixed_sale_price;
    """
    params = (
        item['id'], business_id, item['product_name'], item['category'],
        item['purchase_price'], item['sale_price'], item['current_stock'],
        item['last_updated'], item['batch_number'], item['number_of_tabs'],
        item['unit_price_per_tab'], item['item_type'], item['expiry_date'],
        item['is_fixed_price'], item['fixed_sale_price']
    )
    return execute_query(query, params)

def delete_inventory_item_for_business(business_id, item_id):
    """Deletes an inventory item for a specific business."""
    query = "DELETE FROM inventory WHERE business_id = %s AND id = %s;"
    return execute_query(query, (business_id, item_id))

def load_sales_for_business(business_id):
    """Loads sales records for a specific business."""
    query = """
        SELECT id, product_id, product_name, quantity_sold, sale_unit_type,
               price_at_time_per_unit_sold, total_amount, sale_date, customer_phone,
               sales_person_name, reference_number, transaction_id
        FROM sales
        WHERE business_id = %s
        ORDER BY sale_date DESC;
    """
    return fetch_all(query, (business_id,))

def save_sales_record_for_business(business_id, sale_record):
    """Saves a single sales record (insert or update)."""
    query = """
        INSERT INTO sales (id, business_id, product_id, product_name, quantity_sold,
                           sale_unit_type, price_at_time_per_unit_sold, total_amount,
                           sale_date, customer_phone, sales_person_name, reference_number,
                           transaction_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET product_id = EXCLUDED.product_id, product_name = EXCLUDED.product_name,
            quantity_sold = EXCLUDED.quantity_sold, sale_unit_type = EXCLUDED.sale_unit_type,
            price_at_time_per_unit_sold = EXCLUDED.price_at_time_per_unit_sold,
            total_amount = EXCLUDED.total_amount, sale_date = EXCLUDED.sale_date,
            customer_phone = EXCLUDED.customer_phone, sales_person_name = EXCLUDED.sales_person_name,
            reference_number = EXCLUDED.reference_number, transaction_id = EXCLUDED.transaction_id;
    """
    params = (
        sale_record['id'], business_id, sale_record['product_id'], sale_record['product_name'],
        sale_record['quantity_sold'], sale_record['sale_unit_type'],
        sale_record['price_at_time_per_unit_sold'], sale_record['total_amount'],
        sale_record['sale_date'], sale_record['customer_phone'],
        sale_record['sales_person_name'], sale_record['reference_number'],
        sale_record['transaction_id']
    )
    return execute_query(query, params)

def delete_sales_record_for_business(business_id, sale_id):
    """Deletes a sales record for a specific business."""
    query = "DELETE FROM sales WHERE business_id = %s AND id = %s;"
    return execute_query(query, (business_id, sale_id))

def load_users_for_business(business_id):
    """Loads users for a specific business."""
    query = "SELECT username, password, role FROM users WHERE business_id = %s ORDER BY username;"
    return fetch_all(query, (business_id,))

def save_user_for_business(business_id, user):
    """Saves a single user for a business (insert or update)."""
    query = """
        INSERT INTO users (username, password, role, business_id)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (username, business_id) DO UPDATE
        SET password = EXCLUDED.password, role = EXCLUDED.role;
    """
    params = (user['username'], user['password'], user['role'], business_id)
    return execute_query(query, params)

def delete_user_for_business(business_id, username):
    """Deletes a user for a specific business."""
    query = "DELETE FROM users WHERE business_id = %s AND username = %s;"
    return execute_query(query, (business_id, username))

def load_companies_for_business(business_id):
    """Loads companies (debtors) for a specific business."""
    query = """
        SELECT id, name, contact_person, phone, email, address, balance
        FROM companies
        WHERE business_id = %s
        ORDER BY name;
    """
    return fetch_all(query, (business_id,))

def save_company_for_business(business_id, company):
    """Saves a single company (insert or update)."""
    query = """
        INSERT INTO companies (id, business_id, name, contact_person, phone, email, address, balance)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name, contact_person = EXCLUDED.contact_person,
            phone = EXCLUDED.phone, email = EXCLUDED.email,
            address = EXCLUDED.address, balance = EXCLUDED.balance;
    """
    params = (
        company['id'], business_id, company['name'], company['contact_person'],
        company['phone'], company['email'], company['address'], company['balance']
    )
    return execute_query(query, params)

def delete_company_for_business(business_id, company_id):
    """Deletes a company and its transactions for a specific business."""
    query = "DELETE FROM companies WHERE business_id = %s AND id = %s;"
    return execute_query(query, (business_id, company_id))

def load_company_transactions_for_business(business_id):
    """Loads company transactions for a specific business."""
    query = """
        SELECT id, company_id, date, type, amount, description, recorded_by
        FROM company_transactions
        WHERE business_id = %s
        ORDER BY date DESC;
    """
    return fetch_all(query, (business_id,))

def save_company_transaction_for_business(business_id, transaction):
    """Saves a single company transaction."""
    query = """
        INSERT INTO company_transactions (id, business_id, company_id, date, type, amount, description, recorded_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """
    params = (
        transaction['id'], business_id, transaction['company_id'], transaction['date'],
        transaction['type'], transaction['amount'], transaction['description'],
        transaction['recorded_by']
    )
    return execute_query(query, params)

def load_future_orders_for_business(business_id):
    """Loads future orders for a specific business."""
    query = """
        SELECT id, customer_name, customer_phone, items_json, total_amount,
               amount_paid, date_ordered, expected_collection_date, actual_collection_date, status
        FROM future_orders
        WHERE business_id = %s
        ORDER BY date_ordered DESC;
    """
    return fetch_all(query, (business_id,))

def save_future_order_for_business(business_id, order):
    """Saves a single future order (insert or update)."""
    query = """
        INSERT INTO future_orders (id, business_id, customer_name, customer_phone, items_json,
                                   total_amount, amount_paid, date_ordered, expected_collection_date,
                                   actual_collection_date, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET customer_name = EXCLUDED.customer_name, customer_phone = EXCLUDED.customer_phone,
            items_json = EXCLUDED.items_json, total_amount = EXCLUDED.total_amount,
            amount_paid = EXCLUDED.amount_paid, date_ordered = EXCLUDED.date_ordered,
            expected_collection_date = EXCLUDED.expected_collection_date,
            actual_collection_date = EXCLUDED.actual_collection_date, status = EXCLUDED.status;
    """
    params = (
        order.id, business_id, order.customer_name, order.customer_phone, order.items_json,
        order.total_amount, order.amount_paid, order.date_ordered,
        order.expected_collection_date, order.actual_collection_date, order.status
    )
    return execute_query(query, params)

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
            business_id = str(business['id']) # Ensure UUID is string for comparison
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
                        'address': business.get('address', ''),
                        'location': business.get('location', ''),
                        'contact': business.get('contact', '')
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
        business_users = load_users_for_business(str(business['id'])) # Ensure business.id is string
        if any(user['username'] == current_username for user in business_users):
            user_businesses.append(business)

    if request.method == 'POST':
        selected_business_id = request.form['business_id']
        selected_business = next((b for b in businesses if str(b['id']) == selected_business_id), None)

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
                    'address': selected_business.get('address', ''),
                    'location': selected_business.get('location', ''),
                    'contact': selected_business.get('contact', '')
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
        new_business = {
            'id': new_business_id, 
            'name': business_name,
            'address': business_address,
            'location': business_location,
            'contact': business_contact
        }
        if not save_business(new_business):
            flash('Failed to add business to database.', 'danger')
            return render_template('add_edit_business.html', title='Add New Business', business=request.form)

        # Add initial admin user for this business
        initial_admin_user = {'username': initial_admin_username, 'password': initial_admin_password, 'role': 'admin'}
        if not save_user_for_business(new_business_id, initial_admin_user):
            flash('Failed to add initial admin user. Business added but user creation failed.', 'warning')
        
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
    business_to_edit = next((b for b in businesses if str(b['id']) == business_id), None)

    if not business_to_edit:
        flash('Business not found.', 'danger')
        return redirect(url_for('super_admin_dashboard'))

    business_users = load_users_for_business(business_id)
    initial_admin = next((u for u in business_users if u['role'] == 'admin'), None)

    if request.method == 'POST':
        new_business_name = request.form['business_name'].strip()
        new_business_address = request.form['business_address'].strip()
        new_business_location = request.form['business_location'].strip()
        new_business_contact = request.form['business_contact'].strip()
        new_initial_admin_username = request.form['initial_admin_username'].strip()
        new_initial_admin_password = request.form['initial_admin_password'].strip()

        if any(b['name'].lower() == new_business_name.lower() and str(b['id']) != business_id for b in businesses):
            flash('Business with this name already exists.', 'danger')
            return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit["name"]}', business={
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
        
        if not save_business(business_to_edit):
            flash('Failed to update business details in database.', 'danger')
            return render_template('add_edit_business.html', title=f'Edit Business: {business_to_edit["name"]}', business=request.form)

        if initial_admin:
            if initial_admin['username'] != new_initial_admin_username:
                if any(u['username'] == new_initial_admin_username for u in business_users if u['username'] != initial_admin['username']):
                    flash('New admin username already exists for this business. Business details updated, but admin username not changed.', 'warning')
                else:
                    delete_user_for_business(business_id, initial_admin['username']) # Delete old username entry
                    initial_admin['username'] = new_initial_admin_username
            initial_admin['password'] = new_initial_admin_password
            
            if not save_user_for_business(business_id, initial_admin):
                flash('Failed to update initial admin user. Business updated but user credentials might be outdated.', 'warning')
            
            flash(f'Business "{new_business_name}" and admin credentials updated successfully!', 'success')
        else:
            flash(f'Business "{new_business_name}" updated successfully, but initial admin not found/updated.', 'warning')
        
        return redirect(url_for('super_admin_dashboard'))

    business_data_for_form = business_to_edit.copy()
    if initial_admin:
        business_data_for_form['initial_admin_username'] = initial_admin['username']
        business_data_for_form['initial_admin_password'] = initial_admin['password']
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
    business = next((b for b in businesses if str(b['id']) == business_id), None)

    if not business:
        flash('Business not found.', 'danger')
        return redirect(url_for('super_admin_dashboard'))

    business_users = load_users_for_business(business_id)
    initial_admin = next((u for u in business_users if u['role'] == 'admin'), None)

    return render_template('view_business_details.html', business=business, initial_admin=initial_admin)


@app.route('/super_admin/delete_business/<business_id>')
def delete_business(business_id):
    """Allows super admin to delete a business and all its data."""
    if session.get('role') != 'super_admin':
        flash('Access denied. Super Admin role required.', 'danger')
        return redirect(url_for('login'))
    
    if delete_business_from_db(business_id):
        flash(f'Business (ID: {business_id}) and its data deleted successfully!', 'success')
    else:
        flash('Business not found or failed to delete.', 'danger')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/super_admin/download_inventory/<business_id>')
def download_inventory_csv(business_id):
    """Allows super admin to download the inventory for a specific business as a CSV."""
    if session.get('role') != 'super_admin':
        flash('Access denied. Super Admin role required.', 'danger')
        return redirect(url_for('login'))

    businesses = load_businesses()
    business = next((b for b in businesses if str(b['id']) == business_id), None)

    if not business:
        flash('Business not found.', 'danger')
        return redirect(url_for('super_admin_dashboard'))

    inventory_items = load_inventory_for_business(business_id)

    si = io.StringIO()
    headers = ['id', 'product_name', 'category', 'purchase_price', 'sale_price', 'current_stock', 
               'last_updated', 'batch_number', 'number_of_tabs', 'unit_price_per_tab', 'item_type', 
               'expiry_date', 'is_fixed_price', 'fixed_sale_price']
    
    writer = csv.DictWriter(si, fieldnames=headers)
    writer.writeheader()
    
    for item in inventory_items:
        row_to_write = {key: str(item.get(key, '')) for key in headers}
        # Format numeric fields to 2 decimal places for consistency in CSV
        for num_key in ['purchase_price', 'sale_price', 'current_stock', 'unit_price_per_tab', 'fixed_sale_price']:
            if num_key in item and item[num_key] is not None:
                row_to_write[num_key] = f"{float(item[num_key]):.2f}"
        
        # Format datetime objects to string for CSV
        if isinstance(item.get('last_updated'), datetime):
            row_to_write['last_updated'] = item['last_updated'].strftime('%Y-%m-%d %H:%M:%S')
        
        writer.writerow(row_to_write)

    output = si.getvalue()
    si.close()

    response = Response(output, mimetype='text/csv')
    response.headers["Content-Disposition"] = f"attachment; filename={business['name'].replace(' ', '_')}_inventory_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return response

@app.route('/super_admin/upload_inventory/<business_id>', methods=['GET', 'POST'])
def upload_inventory_csv(business_id):
    """Allows super admin to upload inventory for a specific business via CSV."""
    if session.get('role') != 'super_admin':
        flash('Access denied. Super Admin role required.', 'danger')
        return redirect(url_for('login'))

    businesses = load_businesses()
    business = next((b for b in businesses if str(b['id']) == business_id), None)

    if not business:
        flash('Business not found.', 'danger')
        return redirect(url_for('super_admin_dashboard'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        if file and file.filename.endswith('.csv'):
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"))
                csv_reader = csv.DictReader(stream)
                
                expected_headers = ['id', 'product_name', 'category', 'purchase_price', 'sale_price', 'current_stock', 
                                    'last_updated', 'batch_number', 'number_of_tabs', 'unit_price_per_tab', 'item_type', 
                                    'expiry_date', 'is_fixed_price', 'fixed_sale_price']
                
                if not all(header in csv_reader.fieldnames for header in expected_headers):
                    flash(f'CSV is missing required headers. Expected: {", ".join(expected_headers)}', 'danger')
                    return render_template('upload_inventory.html', business=business)

                # Fetch current inventory to check for existing items
                current_inventory_items = load_inventory_for_business(business_id)
                inventory_dict = {item['id']: item for item in current_inventory_items}
                inventory_name_dict = {item['product_name'].lower(): item for item in current_inventory_items}

                rows_processed = 0
                rows_added = 0
                rows_updated = 0

                for row in csv_reader:
                    rows_processed += 1
                    try:
                        # Attempt to find by ID first, then by name
                        existing_item = inventory_dict.get(uuid.UUID(row['id'])) if row.get('id') else None
                        if not existing_item and row.get('product_name'):
                            existing_item = inventory_name_dict.get(row['product_name'].lower())

                        item_id = str(uuid.uuid4()) # Default for new items
                        if existing_item:
                            item_id = str(existing_item['id']) # Use existing ID for updates
                        elif row.get('id'): # If ID provided in CSV for a new item, use it
                            item_id = row['id']

                        # Convert boolean string to actual boolean
                        is_fixed_price_bool = row.get('is_fixed_price', 'False').lower() == 'true'

                        item_data = {
                            'id': uuid.UUID(item_id), # Ensure UUID type
                            'product_name': row.get('product_name', '').strip(),
                            'category': row.get('category', '').strip(),
                            'purchase_price': float(row.get('purchase_price', 0.0)),
                            'sale_price': float(row.get('sale_price', 0.0)),
                            'current_stock': float(row.get('current_stock', 0.0)),
                            'last_updated': datetime.now(), # Always update timestamp on upload
                            'batch_number': row.get('batch_number', '').strip(),
                            'number_of_tabs': int(float(row.get('number_of_tabs', 1))),
                            'unit_price_per_tab': float(row.get('unit_price_per_tab', 0.0)),
                            'item_type': row.get('item_type', 'Pharmacy').strip(),
                            'expiry_date': row.get('expiry_date', '').strip(),
                            'is_fixed_price': is_fixed_price_bool,
                            'fixed_sale_price': float(row.get('fixed_sale_price', 0.0))
                        }

                        if not item_data['product_name']:
                            flash(f'Skipping row {rows_processed}: Product Name is required.', 'warning')
                            continue
                        if item_data['number_of_tabs'] <= 0:
                            flash(f'Skipping row {rows_processed}: Number of Tabs must be greater than zero for {item_data["product_name"]}.', 'warning')
                            continue
                        
                        # Save/update item in DB
                        success = save_inventory_item_for_business(business_id, item_data)
                        if success:
                            if existing_item:
                                rows_updated += 1
                            else:
                                rows_added += 1
                        else:
                            flash(f'Failed to save item {item_data["product_name"]} from row {rows_processed}.', 'danger')

                    except (ValueError, KeyError, psycopg2.Error) as e:
                        flash(f'Error processing row {rows_processed}: {e}. Skipping row.', 'danger')
                
                flash(f'Inventory upload complete! Processed {rows_processed} rows. Added {rows_added} new items, updated {rows_updated} existing items.', 'success')

            except Exception as e:
                flash(f'Error processing CSV file: {e}', 'danger')
        else:
            flash('Invalid file type. Please upload a CSV file.', 'danger')
        
        return redirect(url_for('super_admin_dashboard'))
    
    return render_template('upload_inventory.html', business=business)


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

        user_data = {'username': new_username, 'password': new_password, 'role': new_role}

        if user_to_edit: # Editing an existing user
            # Check if username changed and if new username conflicts
            if new_username != username and any(u['username'] == new_username for u in users):
                flash('Username already exists.', 'danger')
                return render_template('add_edit_business_user.html', title=title, user=request.form, user_role=session.get('role'))
            
            # If username changed, delete old record before inserting new one
            if new_username != username:
                delete_user_for_business(business_id, username)
            
            if save_user_for_business(business_id, user_data):
                flash(f'User "{new_username}" updated successfully!', 'success')
            else:
                flash(f'Failed to update user "{new_username}".', 'danger')

        else: # Adding a new user
            if any(u['username'] == new_username for u in users):
                flash('Username already exists.', 'danger')
                return render_template('add_edit_business_user.html', title=title, user=request.form, user_role=session.get('role'))
            
            if save_user_for_business(business_id, user_data):
                flash(f'User "{new_username}" added successfully!', 'success')
            else:
                flash(f'Failed to add user "{new_username}".', 'danger')
        
        return redirect(url_for('manage_business_users'))

    return render_template('add_edit_business_user.html', title=title, user=user_to_edit, user_role=session.get('role'))

@app.route('/delete_business_user/<username>')
def delete_business_user_route(username): # Renamed to avoid conflict with helper function
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

    if delete_user_for_business(business_id, username):
        flash(f'User "{username}" deleted successfully!', 'success')
    else:
        flash('User not found or failed to delete.', 'danger')
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
        business_id = session['business_id']
        items = load_inventory_for_business(business_id)
        product_name = request.form['product_name'].strip()
        category = request.form['category'].strip()
        purchase_price = float(request.form['purchase_price'])
        added_stock = float(request.form['current_stock'])
        batch_number = request.form['batch_number'].strip()
        number_of_tabs = int(request.form['number_of_tabs'])
        item_type = request.form['item_type']
        expiry_date = request.form['expiry_date'].strip()
        is_fixed_price = 'is_fixed_price' in request.form
        fixed_sale_price = float(request.form['fixed_sale_price']) if is_fixed_price else 0.0

        if number_of_tabs <= 0:
            flash('Number of tabs must be greater than zero.', 'danger')
            return render_template('add_edit_inventory.html', title='Add Inventory Item', item=request.form, user_role=session.get('role'), item_types=['Pharmacy', 'Provision Store'])

        sale_price = 0.0
        unit_price_per_tab_with_markup = 0.0

        if is_fixed_price:
            sale_price = fixed_sale_price
            unit_price_per_tab_with_markup = fixed_sale_price / number_of_tabs
        else:
            cost_per_tab = purchase_price / number_of_tabs
            if item_type == 'Provision Store':
                if purchase_price >= 1000:
                    unit_price_per_tab_with_markup = cost_per_tab * 1.10
                else:
                    unit_price_per_tab_with_markup = cost_per_tab * 1.08
            else:
                unit_price_per_tab_with_markup = cost_per_tab * 1.30
            
            sale_price = unit_price_per_tab_with_markup * number_of_tabs 

        existing_item = next((item for item in items if item['product_name'].strip().lower() == product_name.lower()), None)

        if existing_item:
            existing_item['current_stock'] = existing_item['current_stock'] + added_stock
            existing_item['category'] = category
            existing_item['purchase_price'] = purchase_price
            existing_item['sale_price'] = sale_price
            existing_item['last_updated'] = datetime.now() # Store as datetime object
            existing_item['batch_number'] = batch_number
            existing_item['number_of_tabs'] = number_of_tabs
            existing_item['unit_price_per_tab'] = unit_price_per_tab_with_markup
            existing_item['item_type'] = item_type
            existing_item['expiry_date'] = expiry_date
            existing_item['is_fixed_price'] = is_fixed_price
            existing_item['fixed_sale_price'] = fixed_sale_price
            
            if save_inventory_item_for_business(business_id, existing_item):
                flash(f'Stock for {product_name} updated successfully! New stock: {existing_item["current_stock"]:.2f}', 'success')
            else:
                flash(f'Failed to update stock for {product_name}.', 'danger')
        else:
            new_item = {
                'id': uuid.uuid4(),
                'product_name': product_name,
                'category': category,
                'purchase_price': purchase_price,
                'sale_price': sale_price,
                'current_stock': added_stock,
                'last_updated': datetime.now(), # Store as datetime object
                'batch_number': batch_number,
                'number_of_tabs': number_of_tabs,
                'unit_price_per_tab': unit_price_per_tab_with_markup,
                'item_type': item_type,
                'expiry_date': expiry_date,
                'is_fixed_price': is_fixed_price,
                'fixed_sale_price': fixed_sale_price
            }
            if save_inventory_item_for_business(business_id, new_item):
                flash('Inventory item added successfully!', 'success')
            else:
                flash('Failed to add inventory item.', 'danger')
        
        return redirect(url_for('inventory'))
    
    default_item = {
        'product_name': '', 'category': '', 'purchase_price': 0.0, 'current_stock': 0.0,
        'batch_number': '', 'number_of_tabs': 1, 'item_type': 'Pharmacy', 'expiry_date': '',
        'is_fixed_price': False, 'fixed_sale_price': 0.0, 'sale_price': 0.0, 'unit_price_per_tab': 0.0
    }
    return render_template('add_edit_inventory.html', title='Add Inventory Item', item=default_item, user_role=session.get('role'), item_types=['Pharmacy', 'Provision Store'])

@app.route('/inventory/edit/<item_id>', methods=['GET', 'POST'])
def edit_inventory(item_id):
    """Edits an existing inventory item or updates its stock. Restricted to Admin."""
    if 'username' not in session or session.get('role') not in ['admin'] or 'business_id' not in session:
        flash('You do not have permission to edit inventory items.', 'danger')
        return redirect(url_for('inventory'))

    business_id = session['business_id']
    items = load_inventory_for_business(business_id)
    item_to_edit = next((item for item in items if str(item['id']) == item_id), None)

    if not item_to_edit:
        flash('Inventory item not found.', 'danger')
        return redirect(url_for('inventory'))

    if request.method == 'POST':
        item_to_edit['product_name'] = request.form['product_name'].strip()
        item_to_edit['category'] = request.form['category'].strip()
        purchase_price = float(request.form['purchase_price'])
        number_of_tabs = int(request.form['number_of_tabs'])
        item_type = request.form['item_type']
        expiry_date = request.form['expiry_date'].strip()
        is_fixed_price = 'is_fixed_price' in request.form
        fixed_sale_price = float(request.form['fixed_sale_price']) if is_fixed_price else 0.0

        if number_of_tabs <= 0:
            flash('Number of tabs must be greater than zero.', 'danger')
            return render_template('add_edit_inventory.html', title='Edit Inventory Item', item=item_to_edit, user_role=session.get('role'), item_types=['Pharmacy', 'Provision Store'])

        sale_price = 0.0
        unit_price_per_tab_with_markup = 0.0

        if is_fixed_price:
            sale_price = fixed_sale_price
            unit_price_per_tab_with_markup = fixed_sale_price / number_of_tabs
        else:
            cost_per_tab = purchase_price / number_of_tabs
            if item_type == 'Provision Store':
                if purchase_price >= 1000:
                    unit_price_per_tab_with_markup = cost_per_tab * 1.10
                else:
                    unit_price_per_tab_with_markup = cost_per_tab * 1.08
            else:
                unit_price_per_tab_with_markup = cost_per_tab * 1.30
            
            sale_price = unit_price_per_tab_with_markup * number_of_tabs 
        
        item_to_edit['purchase_price'] = purchase_price
        item_to_edit['sale_price'] = sale_price
        item_to_edit['current_stock'] = float(request.form['current_stock'])
        item_to_edit['last_updated'] = datetime.now() # Store as datetime object
        item_to_edit['batch_number'] = request.form['batch_number'].strip()
        item_to_edit['number_of_tabs'] = number_of_tabs
        item_to_edit['unit_price_per_tab'] = unit_price_per_tab_with_markup
        item_to_edit['item_type'] = item_type
        item_to_edit['expiry_date'] = expiry_date
        item_to_edit['is_fixed_price'] = is_fixed_price
        item_to_edit['fixed_sale_price'] = fixed_sale_price
        
        if save_inventory_item_for_business(business_id, item_to_edit):
            flash('Inventory item updated successfully!', 'success')
        else:
            flash('Failed to update inventory item.', 'danger')
        return redirect(url_for('inventory'))

    return render_template('add_edit_inventory.html', title='Edit Inventory Item', item=item_to_edit, user_role=session.get('role'), item_types=['Pharmacy', 'Provision Store'])

@app.route('/inventory/delete/<item_id>')
def delete_inventory(item_id):
    """Deletes an inventory item. Restricted to Admin."""
    if 'username' not in session or session.get('role') not in ['admin'] or 'business_id' not in session:
        flash('You do not have permission to delete inventory items.', 'danger')
        return redirect(url_for('inventory'))

    business_id = session['business_id']
    if delete_inventory_item_for_business(business_id, uuid.UUID(item_id)):
        flash('Inventory item deleted successfully!', 'success')
    else:
        flash('Inventory item not found or failed to delete.', 'danger')
    return redirect(url_for('inventory'))

# --- Daily Sales Management Routes ---

@app.route('/sales')
def sales():
    """Displays the list of sales records. Groups by transaction_id for display."""
    if 'username' not in session or 'business_id' not in session:
        flash('Please log in and select a business to access this page.', 'warning')
        return redirect(url_for('login'))
    
    sales_records = load_sales_for_business(session['business_id'])
    
    transactions = {}
    total_displayed_sales = 0.0
    for sale in sales_records:
        transaction_id = str(sale.get('transaction_id', 'N/A'))
        if transaction_id not in transactions:
            transactions[transaction_id] = {
                'id': transaction_id,
                'sale_date': sale['sale_date'],
                'customer_phone': sale['customer_phone'],
                'sales_person_name': sale['sales_person_name'],
                'total_amount': 0.0,
                'items': [],
                'reference_number': sale['reference_number']
            }
        transactions[transaction_id]['items'].append(sale)
        transactions[transaction_id]['total_amount'] += float(sale['total_amount'])
        total_displayed_sales += float(sale['total_amount'])

    sorted_transactions = sorted(list(transactions.values()), 
                                 key=lambda x: x['sale_date'], # sale_date is already datetime object
                                 reverse=True)

    return render_template('sales_list.html', 
                           transactions=sorted_transactions, 
                           user_role=session.get('role'),
                           total_displayed_sales=total_displayed_sales)


@app.route('/sales/add', methods=['GET', 'POST'])
def add_sale():
    """Adds a new sales record for multiple items. Accessible by Admin and Sales."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to add sales records.', 'danger')
        return redirect(url_for('sales'))
    
    business_id = session['business_id']
    inventory_items = load_inventory_for_business(business_id)
    available_inventory_items = [item for item in inventory_items if item['current_stock'] > 0]

    pharmacy_info = session.get('business_info', {
        'name': ENTERPRISE_NAME,
        'location': PHARMACY_LOCATION,
        'address': PHARMACY_ADDRESS,
        'contact': PHARMACY_CONTACT
    })

    if request.method == 'POST':
        sales_records = load_sales_for_business(business_id)
        customer_phone = request.form.get('customer_phone', '').strip()
        sales_person_name = request.form.get('sales_person_name', session.get('username', 'N/A')).strip()
        transaction_id = uuid.uuid4() # UUID object for transaction_id
        overall_total_amount = 0.0
        sold_items_details = []

        product_ids = request.form.getlist('product_id[]')
        quantities_sold_raw = request.form.getlist('quantity_sold[]')
        sale_unit_types = request.form.getlist('sale_unit_type[]')
        price_types = request.form.getlist('price_type[]')
        custom_prices = request.form.getlist('custom_price[]')

        if not product_ids:
            flash('Please add at least one product to the sale.', 'danger')
            return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=available_inventory_items, sale={}, user_role=session.get('role'), pharmacy_info=pharmacy_info)

        updated_inventory_items = [] # To store items that need stock updates
        
        for i in range(len(product_ids)):
            product_id = product_ids[i]
            quantity_sold_raw = float(quantities_sold_raw[i])
            sale_unit_type = sale_unit_types[i]
            price_type = price_types[i]
            custom_price_str = custom_prices[i] if i < len(custom_prices) else ''

            product = next((item for item in inventory_items if str(item['id']) == product_id), None)

            if not product:
                flash(f'Product with ID {product_id} not found in inventory. Sale aborted for this item.', 'danger')
                continue

            current_stock_packs = float(product['current_stock'])
            number_of_tabs_per_pack = float(product['number_of_tabs'])
            
            price_at_time_per_unit_sold = 0.0
            total_amount_item = 0.0
            quantity_for_record = 0.0
            quantity_to_deduct_packs = 0.0
            display_unit_text = ""

            base_sale_price_per_pack = float(product['sale_price'])
            base_unit_price_per_tab = float(product['unit_price_per_tab'])

            if product.get('is_fixed_price'):
                base_sale_price_per_pack = float(product['fixed_sale_price'])
                base_unit_price_per_tab = float(product['fixed_sale_price']) / number_of_tabs_per_pack

            if session.get('role') == 'admin' and price_type == 'custom_price':
                try:
                    custom_price_value = float(custom_price_str)
                    if custom_price_value <= 0:
                        flash(f'Custom price for {product["product_name"]} must be positive. Using internal percentage.', 'warning')
                        price_at_time_per_unit_sold = base_unit_price_per_tab if sale_unit_type == 'tab' else base_sale_price_per_pack
                    else:
                        price_at_time_per_unit_sold = custom_price_value
                except ValueError:
                    flash(f'Invalid custom price for {product["product_name"]}. Using internal percentage.', 'warning')
                    price_at_time_per_unit_sold = base_unit_price_per_tab if sale_unit_type == 'tab' else base_sale_price_per_pack
            else:
                price_at_time_per_unit_sold = base_unit_price_per_tab if sale_unit_type == 'tab' else base_sale_price_per_pack


            if sale_unit_type == 'tab':
                quantity_sold_tabs = quantity_sold_raw
                available_tabs = current_stock_packs * number_of_tabs_per_pack

                if quantity_sold_tabs <= 0:
                    flash(f'Quantity of tabs sold for {product["product_name"]} must be at least 1. Skipping item.', 'danger')
                    continue
                if quantity_sold_tabs > available_tabs:
                    flash(f'Insufficient stock for {product["product_name"]}. Available: {available_tabs:.0f} tabs. Skipping item.', 'danger')
                    continue
                
                quantity_to_deduct_packs = quantity_sold_tabs / number_of_tabs_per_pack
                total_amount_item = quantity_sold_tabs * price_at_time_per_unit_sold
                display_unit_text = "tab(s)"
                quantity_for_record = quantity_sold_tabs
            else: # sale_unit_type == 'pack'
                quantity_sold_packs = quantity_sold_raw

                if quantity_sold_packs <= 0:
                    flash(f'Quantity of packs sold for {product["product_name"]} must be at least 1. Skipping item.', 'danger')
                    continue
                if quantity_sold_packs > current_stock_packs:
                    flash(f'Insufficient stock for {product["product_name"]}. Available: {current_stock_packs:.2f} packs. Skipping item.', 'danger')
                    continue
                
                quantity_to_deduct_packs = quantity_sold_packs
                total_amount_item = quantity_sold_packs * price_at_time_per_unit_sold
                display_unit_text = "pack(s)"
                quantity_for_record = quantity_sold_packs

            # Update stock in the product dictionary
            product['current_stock'] = current_stock_packs - quantity_to_deduct_packs
            updated_inventory_items.append(product) # Add to list for batch update

            new_sale_item = {
                'id': uuid.uuid4(),
                'product_id': uuid.UUID(product_id), # Ensure UUID type
                'product_name': product['product_name'],
                'quantity_sold': quantity_for_record,
                'sale_unit_type': sale_unit_type,
                'price_at_time_per_unit_sold': price_at_time_per_unit_sold,
                'total_amount': total_amount_item,
                'sale_date': datetime.now(), # Store as datetime object
                'customer_phone': customer_phone,
                'sales_person_name': sales_person_name,
                'reference_number': str(uuid.uuid4())[:8].upper(),
                'transaction_id': transaction_id # Store as UUID object
            }
            if save_sales_record_for_business(business_id, new_sale_item):
                overall_total_amount += total_amount_item
                sold_items_details.append(new_sale_item)
            else:
                flash(f'Failed to save sale for {product["product_name"]}.', 'danger')

        # Save all updated inventory items
        for item in updated_inventory_items:
            save_inventory_item_for_business(business_id, item)

        if not sold_items_details:
            flash('No items were successfully added to the sale.', 'danger')
            return render_template('add_edit_sale.html', title='Add Sale Record', inventory_items=available_inventory_items, sale={}, user_role=session.get('role'), pharmacy_info=pharmacy_info)

        flash('Sale record(s) added successfully and stock updated!', 'success')

        if customer_phone:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Receipt (Trans ID: {str(transaction_id)[:8].upper()}):\n"
                f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Items:\n"
            )
            for item in sold_items_details:
                item_display_unit_text = "tab(s)" if item['sale_unit_type'] == 'tab' else "pack(s)"
                message += (
                    f"- {item['product_name']} (Qty: {item['quantity_sold']:.2f} {item_display_unit_text}, "
                    f"Unit Price: GH₵{item['price_at_time_per_unit_sold']:.2f}, "
                    f"Total: GH₵{item['total_amount']:.2f})\n"
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
                sms_result = {}
                if sms_response.status_code == 200:
                    try:
                        sms_result = sms_response.json()
                    except json.JSONDecodeError:
                        print(f"Arkesel SMS JSON Decode Error: {sms_response.text}")
                        flash(f'Failed to send SMS receipt to {customer_phone}. API returned non-JSON response.', 'warning')
                else:
                    print(f"Arkesel SMS API Error (Status {sms_response.status_code}): {sms_response.text}")
                    flash(f'Failed to send SMS receipt to {customer_phone}. API error.', 'warning')
            except requests.exceptions.RequestException as e:
                print(f'Network error sending SMS: {e}')
                flash(f'Network error when trying to send SMS receipt.', 'warning')

        session['last_transaction_details'] = sold_items_details 
        session['last_transaction_grand_total'] = overall_total_amount
        session['last_transaction_id'] = str(transaction_id) # Store as string for session
        session['last_transaction_customer_phone'] = customer_phone
        session['last_transaction_sales_person'] = sales_person_name
        session['last_transaction_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return redirect(url_for('add_sale', print_ready=True))

    default_sale = {
        'sales_person_name': session.get('username', 'N/A'),
        'customer_phone': '',
    }
    
    print_ready_param = request.args.get('print_ready')
    print_ready = print_ready_param is not None and print_ready_param.lower() == 'true'

    last_transaction_details = session.pop('last_transaction_details', [])
    last_transaction_grand_total = session.pop('last_transaction_grand_total', 0.0)
    last_transaction_id = session.pop('last_transaction_id', '')
    last_transaction_customer_phone = session.pop('last_transaction_customer_phone', '')
    last_transaction_sales_person = session.pop('last_transaction_sales_person', '')
    last_transaction_date = session.pop('last_transaction_date', '')

    return render_template('add_edit_sale.html', 
                           title='Add Sale Record', 
                           inventory_items=available_inventory_items, 
                           sale=default_sale, 
                           user_role=session.get('role'), 
                           pharmacy_info=pharmacy_info,
                           print_ready=print_ready,
                           last_transaction_details=last_transaction_details,
                           last_transaction_grand_total=last_transaction_grand_total,
                           last_transaction_id=last_transaction_id,
                           last_transaction_customer_phone=last_transaction_customer_phone,
                           last_transaction_sales_person=last_transaction_sales_person,
                           last_transaction_date=last_transaction_date
                           )

@app.route('/sales/edit/<sale_id>', methods=['GET', 'POST'])
def edit_sale(sale_id):
    """Edits an existing sales record. Accessible by Admin and Sales.
       Sales personnel edits do NOT affect inventory stock.
    """
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to edit sales records.', 'danger')
        return redirect(url_for('sales'))
    
    business_id = session['business_id']
    sales_records = load_sales_for_business(business_id)
    inventory_items = load_inventory_for_business(business_id)
    sale_to_edit = next((sale for sale in sales_records if str(sale['id']) == sale_id), None)

    if not sale_to_edit:
        flash('Sale record not found.', 'danger')
        return redirect(url_for('sales'))

    available_inventory_items = inventory_items 

    pharmacy_info = session.get('business_info', {
        'name': ENTERPRISE_NAME,
        'location': PHARMACY_LOCATION,
        'address': PHARMACY_ADDRESS,
        'contact': PHARMACY_CONTACT
    })

    if request.method == 'POST':
        old_quantity_sold_record = float(sale_to_edit['quantity_sold'])
        old_sale_unit_type = sale_to_edit['sale_unit_type']

        new_quantity_sold_raw = float(request.form.getlist('quantity_sold[]')[0])
        new_sale_unit_type = request.form.getlist('sale_unit_type[]')[0]
        
        product_id = request.form.getlist('product_id[]')[0]
        customer_phone = request.form.get('customer_phone', '').strip()
        sales_person_name = request.form.get('sales_person_name', sale_to_edit.get('sales_person_name', 'N/A')).strip()
        
        price_type = request.form.getlist('price_type[]')[0] if request.form.getlist('price_type[]') else 'internal_percentage'
        custom_price_str = request.form.getlist('custom_price[]')[0] if request.form.getlist('custom_price[]') else ''


        product = next((item for item in inventory_items if str(item['id']) == product_id), None)
        if not product:
            flash('Selected product not found in inventory.', 'danger')
            form_data = request.form.to_dict()
            form_data['quantity_sold'] = new_quantity_sold_raw
            form_data['reference_number'] = sale_to_edit.get('reference_number', '')
            return render_template('add_edit_sale.html', title='Edit Sale Record', sale=form_data, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info)

        current_stock_packs = float(product['current_stock'])
        number_of_tabs_per_pack = float(product['number_of_tabs'])
        
        price_at_time_per_unit_sold = 0.0
        display_unit_text = ""
        new_quantity_for_record = 0.0

        base_sale_price_per_pack = float(product['sale_price'])
        base_unit_price_per_tab = float(product['unit_price_per_tab'])

        if product.get('is_fixed_price'):
            base_sale_price_per_pack = float(product['fixed_sale_price'])
            base_unit_price_per_tab = float(product['fixed_sale_price']) / number_of_tabs_per_pack

        if session.get('role') == 'admin' and price_type == 'custom_price':
            try:
                custom_price_value = float(custom_price_str)
                if custom_price_value <= 0:
                    flash(f'Custom price for {product["product_name"]} must be positive. Using internal percentage.', 'warning')
                    price_at_time_per_unit_sold = base_unit_price_per_tab if new_sale_unit_type == 'tab' else base_sale_price_per_pack
                else:
                    price_at_time_per_unit_sold = custom_price_value
            except ValueError:
                flash(f'Invalid custom price for {product["product_name"]}. Using internal percentage.', 'warning')
                price_at_time_per_unit_sold = base_unit_price_per_tab if new_sale_unit_type == 'tab' else base_sale_price_per_pack
        else:
            price_at_time_per_unit_sold = base_unit_price_per_tab if new_sale_unit_type == 'tab' else base_sale_price_per_pack


        old_quantity_in_packs = 0.0
        if old_sale_unit_type == 'tab':
            old_quantity_in_packs = old_quantity_sold_record / number_of_tabs_per_pack
        else:
            old_quantity_in_packs = old_quantity_sold_record
        
        new_total_amount_sold = 0.0
        
        if new_sale_unit_type == 'tab':
            new_quantity_sold_tabs = new_quantity_sold_raw
            if new_quantity_sold_tabs <= 0:
                flash('Quantity of tabs sold must be at least 1.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = new_quantity_sold_raw
                form_data['reference_number'] = sale_to_edit.get('reference_number', '')
                return render_template('add_edit_sale.html', title='Edit Sale Record', sale=form_data, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info)

            new_quantity_in_packs = new_quantity_sold_tabs / number_of_tabs_per_pack
            new_total_amount_sold = new_quantity_sold_tabs * price_at_time_per_unit_sold
            display_unit_text = "tab(s)"
            new_quantity_for_record = new_quantity_sold_tabs
        else:
            new_quantity_sold_packs = new_quantity_sold_raw
            if new_quantity_sold_packs <= 0:
                flash('Quantity of packs sold must be at least 1.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = new_quantity_sold_raw
                form_data['reference_number'] = sale_to_edit.get('reference_number', '')
                return render_template('add_edit_sale.html', title='Edit Sale Record', sale=form_data, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info)

            new_quantity_in_packs = new_quantity_sold_packs
            new_total_amount_sold = new_quantity_sold_packs * price_at_time_per_unit_sold
            display_unit_text = "pack(s)"
            new_quantity_for_record = new_quantity_sold_packs


        if session.get('role') == 'admin':
            adjusted_stock_after_revert = current_stock_packs + old_quantity_in_packs
            quantity_to_deduct_packs = new_quantity_in_packs 

            if adjusted_stock_after_revert - quantity_to_deduct_packs < 0:
                flash(f'Insufficient stock for {product["product_name"]} to adjust sale quantity. Available: {adjusted_stock_after_revert:.2f} packs.', 'danger')
                form_data = request.form.to_dict()
                form_data['quantity_sold'] = new_quantity_sold_raw
                form_data['reference_number'] = sale_to_edit.get('reference_number', '')
                return render_template('add_edit_sale.html', title='Edit Sale Record', sale=form_data, inventory_items=available_inventory_items, user_role=session.get('role'), pharmacy_info=pharmacy_info)
            
            product['current_stock'] = adjusted_stock_after_revert - quantity_to_deduct_packs
            if save_inventory_item_for_business(business_id, product):
                flash('Inventory stock adjusted due to sale edit (Admin action).', 'info')
            else:
                flash('Failed to adjust inventory stock.', 'danger')
        else:
            flash('Sales personnel edits do not affect inventory stock. Only the sale record is updated.', 'warning')

        sale_to_edit['product_id'] = uuid.UUID(product_id)
        sale_to_edit['product_name'] = product['product_name']
        sale_to_edit['quantity_sold'] = new_quantity_for_record
        sale_to_edit['sale_unit_type'] = new_sale_unit_type
        sale_to_edit['price_at_time_per_unit_sold'] = price_at_time_per_unit_sold
        sale_to_edit['total_amount'] = new_total_amount_sold
        sale_to_edit['sale_date'] = datetime.now()
        sale_to_edit['customer_phone'] = customer_phone
        sale_to_edit['sales_person_name'] = sales_person_name 
        sale_to_edit['reference_number'] = sale_to_edit.get('reference_number', '')
        sale_to_edit['transaction_id'] = sale_to_edit.get('transaction_id', '')


        if save_sales_record_for_business(business_id, sale_to_edit):
            flash('Sale record updated successfully!', 'success')
        else:
            flash('Failed to update sale record.', 'danger')

        if customer_phone:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Receipt (Edited - Ref: {sale_to_edit['reference_number']}):\n" 
                f"Item: {product['product_name']}\n"
                f"Qty: {new_quantity_for_record:.2f} {display_unit_text}\n"
                f"Unit Price: GH₵{price_at_time_per_unit_sold:.2f} per {new_sale_unit_type}\n"
                f"Total: GH₵{new_total_amount_sold:.2f}\n"
                f"Date: {sale_to_edit['sale_date'].strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Thank you for trading with us\n"
                f"From: {business_name_for_sms}"
            )
            sms_payload = {
                'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': customer_phone,
                'from': ARKESEL_SENDER_ID, 'sms': message
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
    
    if 'customer_phone' not in sale_to_edit:
        sale_to_edit['customer_phone'] = ''
    if 'sales_person_name' not in sale_to_edit:
        sale_to_edit['sales_person_name'] = session.get('username', 'N/A')
    if 'sale_unit_type' not in sale_to_edit:
        sale_to_edit['sale_unit_type'] = 'pack'
    if 'quantity_sold' not in sale_to_edit:
        sale_to_edit['quantity_sold'] = float(sale_to_edit.get('quantity_sold', 0.0))
    if 'reference_number' not in sale_to_edit:
        sale_to_edit['reference_number'] = ''
    if 'transaction_id' not in sale_to_edit:
        sale_to_edit['transaction_id'] = ''

    product_for_edit = next((item for item in inventory_items if str(item['id']) == str(sale_to_edit['product_id'])), None)
    if product_for_edit:
        calculated_internal_price = 0.0
        if product_for_edit.get('is_fixed_price'):
            base_sale_price_per_pack = float(product_for_edit['fixed_sale_price'])
            base_unit_price_per_tab = float(product_for_edit['fixed_sale_price']) / float(product_for_edit['number_of_tabs'])
        else:
            base_sale_price_per_pack = float(product_for_edit['sale_price'])
            base_unit_price_per_tab = float(product_for_edit['unit_price_per_tab'])

        if sale_to_edit['sale_unit_type'] == 'tab':
            calculated_internal_price = base_unit_price_per_tab
        else:
            calculated_internal_price = base_sale_price_per_pack
        
        if abs(float(sale_to_edit['price_at_time_per_unit_sold']) - calculated_internal_price) < 0.001:
            sale_to_edit['price_type'] = 'internal_percentage'
            sale_to_edit['custom_price'] = ''
        else:
            sale_to_edit['price_type'] = 'custom_price'
            sale_to_edit['custom_price'] = f"{float(sale_to_edit['price_at_time_per_unit_sold']):.2f}"
    else:
        sale_to_edit['price_type'] = 'internal_percentage'
        sale_to_edit['custom_price'] = ''

    return render_template('add_edit_sale.html', 
                           title='Edit Sale Record', 
                           sale=sale_to_edit, 
                           inventory_items=available_inventory_items, 
                           user_role=session.get('role'), 
                           pharmacy_info=pharmacy_info,
                           print_ready=False,
                           last_transaction_details=[],
                           last_transaction_grand_total=0.0,
                           last_transaction_id='',
                           last_transaction_customer_phone='',
                           last_transaction_sales_person='',
                           last_transaction_date=''
                           )


@app.route('/sales/delete/<sale_id>')
def delete_sale(sale_id):
    """Deletes a sales record and adjusts stock (dangerous for real systems). Accessible by Admin and Sales."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to delete sales records.', 'danger')
        return redirect(url_for('sales'))
    
    business_id = session['business_id']
    sales_records = load_sales_for_business(business_id)
    inventory_items = load_inventory_for_business(business_id)
    
    sale_to_delete = next((sale for sale in sales_records if str(sale['id']) == sale_id), None)
    
    if not sale_to_delete:
        flash('Sale record not found.', 'danger')
        return redirect(url_for('sales'))

    product_id = str(sale_to_delete['product_id'])
    quantity_sold_record = float(sale_to_delete['quantity_sold'])
    sale_unit_type = sale_to_delete.get('sale_unit_type', 'pack')

    product = next((item for item in inventory_items if str(item['id']) == product_id), None)

    if product:
        quantity_to_add_packs = 0.0
        if sale_unit_type == 'tab':
            quantity_to_add_packs = quantity_sold_record / float(product['number_of_tabs'])
        else:
            quantity_to_add_packs = quantity_sold_record
            
        product['current_stock'] = float(product['current_stock']) + quantity_to_add_packs
        if save_inventory_item_for_business(business_id, product):
            flash(f'Stock for {product["product_name"]} adjusted due to sale deletion. New stock: {float(product["current_stock"]):.2f} packs.', 'info')
        else:
            flash('Failed to adjust inventory stock after sale deletion.', 'danger')
    else:
        flash('Associated product for deleted sale not found in inventory. Stock not adjusted.', 'warning')

    if delete_sales_record_for_business(business_id, uuid.UUID(sale_id)):
        flash('Sale record deleted successfully!', 'success')
    else:
        flash('Sale record not found or failed to delete.', 'danger')
    return redirect(url_for('sales'))


@app.route('/sales/return_item', methods=['GET', 'POST'])
def return_item():
    """Handles customer returns and adjusts sales/inventory."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to process returns.', 'danger')
        return redirect(url_for('sales'))
    
    business_id = session['business_id']

    if request.method == 'POST':
        ref_number = request.form['reference_number'].strip().upper()
        return_quantity_raw = float(request.form['return_quantity'])
        return_unit_type = request.form['return_unit_type']

        sales_records = load_sales_for_business(business_id)
        inventory_items = load_inventory_for_business(business_id)

        original_sale = next((s for s in sales_records if s.get('reference_number', '').upper() == ref_number), None)

        if not original_sale:
            flash(f'Sale with Reference Number {ref_number} not found.', 'danger')
            return render_template('return_item.html', user_role=session.get('role'))
        
        product = next((item for item in inventory_items if str(item['id']) == str(original_sale['product_id'])), None)
        if not product:
            flash(f'Product {original_sale["product_name"]} from sale {ref_number} not found in inventory. Cannot process return.', 'danger')
            return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product)

        original_quantity_sold_record = float(original_sale['quantity_sold'])
        original_sale_unit_type = original_sale['sale_unit_type']
        
        number_of_tabs_per_pack = float(product['number_of_tabs'])
        price_at_time_per_unit_sold = float(original_sale['price_at_time_per_unit_sold'])

        return_quantity_in_packs = 0.0
        returned_amount = 0.0
        display_unit_text = ""
        quantity_for_return_record = 0.0

        if return_unit_type == 'tab':
            if return_quantity_raw <= 0:
                flash('Return quantity of tabs must be at least 1.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product)

            original_quantity_tabs = original_quantity_sold_record
            if original_sale_unit_type == 'pack':
                original_quantity_tabs = original_quantity_sold_record * number_of_tabs_per_pack

            if return_quantity_raw > original_quantity_tabs:
                flash(f'Cannot return {return_quantity_raw:.0f} tabs. Only {original_quantity_tabs:.0f} tabs were originally sold for this reference number.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product)

            return_quantity_in_packs = return_quantity_raw / number_of_tabs_per_pack
            returned_amount = return_quantity_raw * price_at_time_per_unit_sold
            display_unit_text = "tab(s)"
            quantity_for_return_record = return_quantity_raw

        else: # return_unit_type == 'pack'
            if return_quantity_raw <= 0:
                flash('Return quantity of packs must be at least 1.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product)
            
            original_quantity_packs = original_quantity_sold_record
            if original_sale_unit_type == 'tab':
                original_quantity_packs = original_quantity_sold_record / number_of_tabs_per_pack
            
            if return_quantity_raw > original_quantity_packs:
                flash(f'Cannot return {return_quantity_raw:.2f} packs. Only {original_quantity_packs:.2f} packs were originally sold for this reference number.', 'danger')
                return render_template('return_item.html', user_role=session.get('role'), original_sale=original_sale, product=product)

            return_quantity_in_packs = return_quantity_raw
            returned_amount = return_quantity_raw * price_at_time_per_unit_sold
            display_unit_text = "pack(s)"
            quantity_for_return_record = return_quantity_raw

        return_sale_record = {
            'id': uuid.uuid4(),
            'reference_number': f"RMA-{ref_number}",
            'product_id': original_sale['product_id'],
            'product_name': original_sale['product_name'],
            'quantity_sold': -quantity_for_return_record,
            'sale_unit_type': return_unit_type,
            'price_at_time_per_unit_sold': price_at_time_per_unit_sold,
            'total_amount': -returned_amount,
            'sale_date': datetime.now(),
            'customer_phone': original_sale.get('customer_phone', 'N/A'),
            'sales_person_name': session.get('username', 'N/A') + " (Return)",
            'transaction_id': original_sale.get('transaction_id', uuid.uuid4()) # Ensure it's a UUID object
        }
        
        if save_sales_record_for_business(business_id, return_sale_record):
            product['current_stock'] = float(product['current_stock']) + return_quantity_in_packs
            if save_inventory_item_for_business(business_id, product):
                flash(f'Return processed for Reference Number {ref_number}. {return_quantity_raw:.2f} {display_unit_text} of {original_sale["product_name"]} returned. Total sales adjusted by GH₵{returned_amount:.2f}.', 'success')
            else:
                flash('Failed to adjust inventory stock for return.', 'danger')
        else:
            flash('Failed to record return sale.', 'danger')

        if original_sale.get('customer_phone'):
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Return Confirmation (Ref: {return_sale_record['reference_number']}):\n"
                f"Item: {original_sale['product_name']}\n"
                f"Qty Returned: {quantity_for_return_record:.2f} {display_unit_text}\n"
                f"Amount Refunded: GH₵{returned_amount:.2f}\n"
                f"Date: {return_sale_record['sale_date'].strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"From: {business_name_for_sms}"
            )
            sms_payload = {
                'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': original_sale['customer_phone'],
                'from': ARKESEL_SENDER_ID, 'sms': message
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

    business_id = session['business_id']
    inventory_items = load_inventory_for_business(business_id)
    sales_records = load_sales_for_business(business_id)

    stock_summary = inventory_items 

    daily_sales = {}
    weekly_sales = {}
    monthly_sales = {}
    sales_per_person = {}

    total_cost_of_stock = 0.0
    total_potential_profit = 0.0

    for item in inventory_items:
        total_cost_of_stock += float(item['purchase_price']) * float(item['current_stock'])
        total_potential_profit += (float(item['sale_price']) - float(item['purchase_price'])) * float(item['current_stock'])


    for sale in sales_records:
        sale_date_obj = sale['sale_date'] # Already datetime object
        total_amount = float(sale['total_amount'])
        sales_person = sale.get('sales_person_name', 'Unknown')

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
        stock_summary=stock_summary,
        daily_sales=sorted_daily_sales,
        weekly_sales=sorted_weekly_sales,
        monthly_sales=sorted_monthly_sales,
        sales_per_person=sorted_sales_per_person,
        total_cost_of_stock=total_cost_of_stock,
        total_potential_profit=total_potential_profit,
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
        if sale['sale_date'].date() == today # Compare date part of datetime object
    ]

    total_sales_amount = sum(float(s['total_amount']) for s in today_sales)
    total_items_sold = sum(float(s['quantity_sold']) for s in today_sales)
    
    product_sales_summary = {}
    for sale in today_sales:
        product_name = sale['product_name']
        quantity = float(sale['quantity_sold'])
        unit_type = sale.get('sale_unit_type', 'pack')
        
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

# --- Companies (Debtors) Management Routes ---

@app.route('/companies')
def companies():
    """Displays the list of companies (debtors)."""
    if 'username' not in session or 'business_id' not in session:
        flash('Please log in and select a business to access this page.', 'warning')
        return redirect(url_for('login'))
    
    companies_data = load_companies_for_business(session['business_id'])
    return render_template('company_list.html', companies=companies_data, user_role=session.get('role'))

@app.route('/companies/add', methods=['GET', 'POST'])
def add_company():
    """Adds a new company."""
    if 'username' not in session or session.get('role') not in ['admin'] or 'business_id' not in session:
        flash('You do not have permission to add companies.', 'danger')
        return redirect(url_for('companies'))
        
    business_id = session['business_id']
    if request.method == 'POST':
        companies_data = load_companies_for_business(business_id)
        name = request.form['name'].strip()
        contact_person = request.form['contact_person'].strip()
        phone = request.form['phone'].strip()
        email = request.form['email'].strip()
        address = request.form['address'].strip()

        if any(c['name'].lower() == name.lower() for c in companies_data):
            flash('Company with this name already exists.', 'danger')
            return render_template('add_edit_company.html', title='Add New Company', company=request.form)

        new_company = {
            'id': uuid.uuid4(),
            'name': name,
            'contact_person': contact_person,
            'phone': phone,
            'email': email,
            'address': address,
            'balance': 0.0
        }
        if save_company_for_business(business_id, new_company):
            flash('Company added successfully!', 'success')
        else:
            flash('Failed to add company.', 'danger')
        return redirect(url_for('companies'))
    
    return render_template('add_edit_company.html', title='Add New Company')

@app.route('/companies/edit/<company_id>', methods=['GET', 'POST'])
def edit_company(company_id):
    """Edits an existing company."""
    if 'username' not in session or session.get('role') not in ['admin'] or 'business_id' not in session:
        flash('You do not have permission to edit companies.', 'danger')
        return redirect(url_for('companies'))

    business_id = session['business_id']
    companies_data = load_companies_for_business(business_id)
    company_to_edit = next((c for c in companies_data if str(c['id']) == company_id), None)

    if not company_to_edit:
        flash('Company not found.', 'danger')
        return redirect(url_for('companies'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        contact_person = request.form['contact_person'].strip()
        phone = request.form['phone'].strip()
        email = request.form['email'].strip()
        address = request.form['address'].strip()

        if any(c['name'].lower() == name.lower() and str(c['id']) != company_id for c in companies_data):
            flash('Company with this name already exists.', 'danger')
            return render_template('add_edit_company.html', title='Edit Company', company=request.form)

        company_to_edit['name'] = name
        company_to_edit['contact_person'] = contact_person
        company_to_edit['phone'] = phone
        company_to_edit['email'] = email
        company_to_edit['address'] = address
        
        if save_company_for_business(business_id, company_to_edit):
            flash('Company updated successfully!', 'success')
        else:
            flash('Failed to update company.', 'danger')
        return redirect(url_for('companies'))
    
    return render_template('add_edit_company.html', title='Edit Company', company=company_to_edit)

@app.route('/companies/delete/<company_id>')
def delete_company(company_id):
    """Deletes a company and its transactions."""
    if 'username' not in session or session.get('role') not in ['admin'] or 'business_id' not in session:
        flash('You do not have permission to delete companies.', 'danger')
        return redirect(url_for('companies'))

    business_id = session['business_id']
    if delete_company_for_business(business_id, uuid.UUID(company_id)):
        flash('Company and its transactions deleted successfully!', 'success')
    else:
        flash('Company not found or failed to delete.', 'danger')
    return redirect(url_for('companies'))

@app.route('/companies/transactions/<company_id>', methods=['GET', 'POST'])
def company_transaction(company_id):
    """Manages transactions for a specific company (debtor)."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to manage company transactions.', 'danger')
        return redirect(url_for('login'))
    
    business_id = session['business_id']
    companies_data = load_companies_for_business(business_id)
    company = next((c for c in companies_data if str(c['id']) == company_id), None)

    if not company:
        flash('Company not found.', 'danger')
        return redirect(url_for('companies'))

    transactions_data = load_company_transactions_for_business(business_id)
    company_transactions = [t for t in transactions_data if str(t['company_id']) == company_id]
    
    company_transactions = sorted(company_transactions, key=lambda x: x['date'], reverse=True)

    pharmacy_info = session.get('business_info', {
        'name': ENTERPRISE_NAME,
        'location': PHARMACY_LOCATION,
        'address': PHARMACY_ADDRESS,
        'contact': PHARMACY_CONTACT
    })

    print_ready = False
    last_company_transaction_details = None
    last_company_transaction_id = None

    if request.method == 'POST':
        if session.get('role') not in ['admin', 'sales']:
            flash('You do not have permission to record company transactions.', 'danger')
            return redirect(url_for('company_transaction', company_id=company_id))

        transaction_type = request.form['type'].strip()
        amount = float(request.form['amount'])
        description = request.form.get('description', '').strip()
        send_sms_receipt = 'send_sms_receipt' in request.form

        if amount <= 0:
            flash('Amount must be greater than zero.', 'danger')
            return redirect(url_for('company_transaction', company_id=company_id))

        if transaction_type == 'Credit':
            company['balance'] -= amount
        elif transaction_type == 'Debit':
            company['balance'] += amount
        else:
            flash('Invalid transaction type.', 'danger')
            return redirect(url_for('company_transaction', company_id=company_id))

        transaction_id = uuid.uuid4()
        new_transaction = {
            'id': transaction_id,
            'company_id': uuid.UUID(company_id),
            'date': datetime.now(),
            'type': transaction_type,
            'amount': amount,
            'description': description,
            'recorded_by': session.get('username', 'N/A')
        }
        
        if save_company_for_business(business_id, company) and save_company_transaction_for_business(business_id, new_transaction):
            flash(f'Transaction recorded successfully! New balance for {company["name"]}: GH₵{company["balance"]:.2f}', 'success')

            print_ready = True
            last_company_transaction_details = {
                'company_name': company['name'],
                'date': new_transaction['date'].strftime('%Y-%m-%d %H:%M:%S'),
                'transaction_type': new_transaction['type'],
                'amount': new_transaction['amount'],
                'description': new_transaction['description'],
                'recorded_by': new_transaction['recorded_by'],
                'new_balance': company['balance']
            }
            last_company_transaction_id = str(new_transaction['id'])

            if send_sms_receipt and company['phone']:
                business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
                message = (
                    f"{business_name_for_sms} Transaction Receipt:\n"
                    f"Company: {company['name']}\n"
                    f"Date: {new_transaction['date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Type: {transaction_type}\n"
                    f"Amount: GH₵{amount:.2f}\n"
                    f"Description: {description if description else 'N/A'}\n"
                    f"New Balance: GH₵{company['balance']:.2f}\n\n"
                    f"From: {business_name_for_sms}"
                )
                sms_payload = {
                    'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': company['phone'],
                    'from': ARKESEL_SENDER_ID, 'sms': message
                }
                try:
                    sms_response = requests.get(ARKESEL_SMS_URL, params=sms_payload)
                    sms_result = {}
                    if sms_response.status_code == 200:
                        try:
                            sms_result = sms_response.json()
                        except json.JSONDecodeError:
                            print(f"Arkesel SMS JSON Decode Error: {sms_response.text}")
                            flash(f'Failed to send SMS receipt to {company["phone"]}. API returned non-JSON response.', 'warning')
                    else:
                        print(f"Arkesel SMS API Error (Status {sms_response.status_code}): {sms_response.text}")
                        flash(f'Failed to send SMS receipt to {company["phone"]}. API error.', 'warning')
                except requests.exceptions.RequestException as e:
                    print(f'Network error sending SMS: {e}')
                    flash(f'Network error when trying to send SMS receipt.', 'warning')
        else:
            flash('Failed to record transaction.', 'danger')
        
        return render_template('company_transaction.html', 
                               company=company, 
                               transactions=company_transactions, 
                               user_role=session.get('role'),
                               pharmacy_info=pharmacy_info,
                               print_ready=print_ready,
                               last_company_transaction_details=last_company_transaction_details,
                               last_company_transaction_id=last_company_transaction_id)


    return render_template('company_transaction.html', 
                           company=company, 
                           transactions=company_transactions, 
                           user_role=session.get('role'),
                           pharmacy_info=pharmacy_info,
                           print_ready=print_ready,
                           last_company_transaction_details=None,
                           last_company_transaction_id=None)

# --- Future Orders / Layaway Routes ---
class FutureOrderItem:
    def __init__(self, product_id, product_name, quantity, unit_type, unit_price, item_total):
        self.product_id = product_id
        self.product_name = product_name
        self.quantity = float(quantity)
        self.unit_type = unit_type
        self.unit_price = float(unit_price)
        self.item_total = float(item_total)

    def to_dict(self):
        return {
            "product_id": str(self.product_id), # Convert UUID to string for JSON
            "product_name": self.product_name,
            "quantity": self.quantity,
            "unit_type": self.unit_type,
            "unit_price": self.unit_price,
            "item_total": self.item_total
        }

class FutureOrder:
    def __init__(self, id, customer_name, customer_phone, items_json, total_amount, amount_paid, 
                 date_ordered, expected_collection_date, actual_collection_date, status):
        self.id = id
        self.customer_name = customer_name
        self.customer_phone = customer_phone
        self.items_json = items_json
        self.total_amount = float(total_amount)
        self.amount_paid = float(amount_paid)
        self.remaining_balance = self.total_amount - self.amount_paid
        
        self.date_ordered = date_ordered # Already datetime object from DB
        self.expected_collection_date = expected_collection_date # Already date object from DB
        self.actual_collection_date = actual_collection_date # Already datetime object or None from DB
        
        self.status = status

    def get_items(self):
        if self.items_json:
            items_data = json.loads(self.items_json)
            # Convert product_id back to UUID if needed for internal logic
            return [FutureOrderItem(product_id=uuid.UUID(item['product_id']), **{k: v for k, v in item.items() if k != 'product_id'}) for item in items_data]
        return []

    def to_dict(self):
        return {
            'id': str(self.id), # Convert UUID to string for saving
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'items_json': self.items_json,
            'total_amount': self.total_amount,
            'amount_paid': self.amount_paid,
            'date_ordered': self.date_ordered,
            'expected_collection_date': self.expected_collection_date,
            'actual_collection_date': self.actual_collection_date,
            'status': self.status
        }

@app.route('/future_orders')
def future_orders():
    """Displays the list of future orders (layaway)."""
    if 'username' not in session or 'business_id' not in session:
        flash('Please log in and select a business to access this page.', 'warning')
        return redirect(url_for('login'))
    
    orders_data = load_future_orders_for_business(session['business_id'])
    orders = [FutureOrder(**o) for o in orders_data] # Convert raw dicts to FutureOrder objects
    orders = sorted(orders, key=lambda x: x.date_ordered if x.date_ordered else datetime.min, reverse=True)
    return render_template('future_order_list.html', orders=orders, user_role=session.get('role'))

@app.route('/future_orders/add', methods=['GET', 'POST'])
def add_future_order():
    """Adds a new future order. Accessible by Admin and Sales."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to add future orders.', 'danger')
        return redirect(url_for('future_orders'))
        
    business_id = session['business_id']
    inventory_items = load_inventory_for_business(business_id)
    available_inventory_items = [item for item in inventory_items if float(item['current_stock']) > 0]

    if request.method == 'POST':
        customer_name = request.form['customer_name'].strip()
        customer_phone = request.form.get('customer_phone', '').strip()
        expected_collection_date_str = request.form.get('expected_collection_date', '').strip()
        expected_collection_date = datetime.strptime(expected_collection_date_str, '%Y-%m-%d').date() if expected_collection_date_str else None
        total_amount = float(request.form['total_amount'])

        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        unit_prices = request.form.getlist('unit_price[]')
        unit_types = request.form.getlist('unit_type[]')
        item_totals = request.form.getlist('item_total[]')

        if not product_ids:
            flash('Please add at least one item to the order.', 'danger')
            return render_template('add_future_order.html', title='Add New Future Order', 
                                   inventory_items=available_inventory_items, order=request.form)

        order_items_list = []
        for i in range(len(product_ids)):
            product_id = product_ids[i]
            quantity = float(quantities[i])
            unit_price = float(unit_prices[i])
            unit_type = unit_types[i]
            item_total = float(item_totals[i])

            product = next((item for item in inventory_items if str(item['id']) == product_id), None)
            if not product:
                flash(f'Product with ID {product_id} not found in inventory. Order creation failed.', 'danger')
                return render_template('add_future_order.html', title='Add New Future Order', 
                                       inventory_items=available_inventory_items, order=request.form)
            
            order_items_list.append(FutureOrderItem(
                product_id=uuid.UUID(product_id), # Store as UUID object in FutureOrderItem
                product_name=product['product_name'],
                quantity=quantity,
                unit_type=unit_type,
                unit_price=unit_price,
                item_total=item_total
            ).to_dict())

        new_order = FutureOrder(
            id=uuid.uuid4(),
            customer_name=customer_name,
            customer_phone=customer_phone,
            items_json=json.dumps(order_items_list),
            total_amount=total_amount,
            amount_paid=0.0,
            date_ordered=datetime.now(),
            expected_collection_date=expected_collection_date,
            actual_collection_date=None,
            status='Pending'
        )

        if save_future_order_for_business(business_id, new_order):
            flash('Future order created successfully! Customer can now make payments.', 'success')
        else:
            flash('Failed to create future order.', 'danger')
        return redirect(url_for('future_orders'))
    
    return render_template('add_future_order.html', title='Add New Future Order', inventory_items=available_inventory_items)

@app.route('/future_orders/payment/<order_id>', methods=['GET', 'POST'])
def future_order_payment(order_id):
    """Records a payment for a future order. Accessible by Admin and Sales."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to record payments for future orders.', 'danger')
        return redirect(url_for('future_orders'))
    
    business_id = session['business_id']
    orders_data = load_future_orders_for_business(business_id)
    order_to_pay = next((FutureOrder(**o) for o in orders_data if str(o['id']) == order_id), None)

    if not order_to_pay:
        flash('Future order not found.', 'danger')
        return redirect(url_for('future_orders'))
    
    if order_to_pay.status == 'Collected':
        flash('This order has already been collected and fully paid.', 'warning')
        return redirect(url_for('future_orders'))

    if request.method == 'POST':
        amount_paid_now = float(request.form['amount_paid'])

        if amount_paid_now <= 0:
            flash('Amount to pay must be greater than zero.', 'danger')
            return redirect(url_for('future_order_payment', order_id=order_id))
        
        if amount_paid_now > order_to_pay.remaining_balance:
            flash(f'Amount exceeds remaining balance. Max amount: GH₵{order_to_pay.remaining_balance:.2f}', 'danger')
            return redirect(url_for('future_order_payment', order_id=order_id))
        
        order_to_pay.amount_paid += amount_paid_now
        order_to_pay.remaining_balance = order_to_pay.total_amount - order_to_pay.amount_paid

        if order_to_pay.remaining_balance <= 0.01:
            order_to_pay.remaining_balance = 0.0
            flash(f'Payment recorded. Order is now fully paid! New balance: GH₵{order_to_pay.remaining_balance:.2f}', 'success')
        else:
            flash(f'Payment recorded. Remaining balance: GH₵{order_to_pay.remaining_balance:.2f}', 'success')
        
        if save_future_order_for_business(business_id, order_to_pay):
            if order_to_pay.customer_phone:
                business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
                message = (
                    f"{business_name_for_sms} Payment Receipt (Order: {str(order_to_pay.id)[:8].upper()}):\n"
                    f"Customer: {order_to_pay.customer_name}\n"
                    f"Amount Paid: GH₵{amount_paid_now:.2f}\n"
                    f"Total Order: GH₵{order_to_pay.total_amount:.2f}\n"
                    f"Remaining Balance: GH₵{order_to_pay.remaining_balance:.2f}\n"
                    f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"From: {business_name_for_sms}"
                )
                sms_payload = {
                    'action': 'send-sms', 'api_key': ARKESEL_API_KEY, 'to': order_to_pay.customer_phone,
                    'from': ARKESEL_SENDER_ID, 'sms': message
                }
                try:
                    requests.get(ARKESEL_SMS_URL, params=sms_payload)
                except requests.exceptions.RequestException as e:
                    print(f'Network error sending SMS for payment: {e}')
                    flash(f'Network error when trying to send SMS payment receipt.', 'warning')
        else:
            flash('Failed to record payment.', 'danger')

        return redirect(url_for('future_orders'))

    return render_template('future_order_payment.html', order=order_to_pay, user_role=session.get('role'))

@app.route('/future_orders/collect/<order_id>')
def collect_future_order(order_id):
    """Marks a future order as collected and deducts stock. Accessible by Admin and Sales."""
    if 'username' not in session or session.get('role') not in ['admin', 'sales'] or 'business_id' not in session:
        flash('You do not have permission to collect future orders.', 'danger')
        return redirect(url_for('future_orders'))
    
    business_id = session['business_id']
    orders_data = load_future_orders_for_business(business_id)
    order_to_collect = next((FutureOrder(**o) for o in orders_data if str(o['id']) == order_id), None)

    if not order_to_collect:
        flash('Future order not found.', 'danger')
        return redirect(url_for('future_orders'))

    if order_to_collect.status == 'Collected':
        flash('This order has already been collected.', 'warning')
        return redirect(url_for('future_orders'))
    
    if order_to_collect.remaining_balance > 0:
        flash(f'Order has an outstanding balance of GH₵{order_to_collect.remaining_balance:.2f}. Please record full payment before collection.', 'danger')
        return redirect(url_for('future_order_payment', order_id=order_to_collect.id))

    inventory_items = load_inventory_for_business(business_id)
    
    for order_item in order_to_collect.get_items():
        product = next((item for item in inventory_items if str(item['id']) == str(order_item.product_id)), None)
        if not product:
            flash(f'Product "{order_item.product_name}" not found in inventory. Cannot collect order.', 'danger')
            return redirect(url_for('future_orders'))
        
        quantity_to_deduct_packs = 0.0
        if order_item.unit_type == 'tab':
            quantity_to_deduct_packs = order_item.quantity / float(product['number_of_tabs'])
        else:
            quantity_to_deduct_packs = order_item.quantity
        
        if float(product['current_stock']) < quantity_to_deduct_packs:
            flash(f'Insufficient stock for "{product["product_name"]}". Available: {float(product["current_stock"]):.2f} packs. Cannot collect order.', 'danger')
            return redirect(url_for('future_orders'))
        
        product['current_stock'] = float(product['current_stock']) - quantity_to_deduct_packs
        if not save_inventory_item_for_business(business_id, product):
            flash(f'Failed to deduct stock for {product["product_name"]}. Collection aborted.', 'danger')
            return redirect(url_for('future_orders'))
    
    order_to_collect.status = 'Collected'
    order_to_collect.actual_collection_date = datetime.now()
    if save_future_order_for_business(business_id, order_to_collect):
        flash(f'Order {str(order_to_collect.id)[:8].upper()} collected successfully and stock deducted!', 'success')
        
        if order_to_collect.customer_phone:
            business_name_for_sms = session.get('business_info', {}).get('name', ENTERPRISE_NAME)
            message = (
                f"{business_name_for_sms} Order Collection Confirmation:\n"
                f"Order ID: {str(order_to_collect.id)[:8].upper()}\n"
                f"Customer: {order_to_collect.customer_name}\n"
                f"Total Amount: GH₵{order_to_collect.total_amount:.2f}\n"
                f"Collected On: {order_to_collect.actual_collection_date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Thank you for your business!\n"
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

# --- Main entry point ---
if __name__ == '__main__':
    app.run(debug=True)
