from extensions import db # <<< THIS MUST BE THE CORRECT IMPORT FOR 'db'

# ... (the rest of your imports in models.py, like UserMixin, datetime, etc.) ...
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import uuid
import json
from sqlalchemy import Index, func

class Business(db.Model):
    __tablename__ = 'businesses'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), unique=True, nullable=False)
    type = db.Column(db.String(50), nullable=False)
    address = db.Column(db.String(200), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    contact = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    last_synced_at = db.Column(db.DateTime, default=datetime.utcnow)
    remote_id = db.Column(db.String(36), nullable=True)
    
    # Use back_populates to explicitly link to the 'business' relationship in the User model
    users = db.relationship('User', back_populates='business', lazy=True)
    
    # The rest of your relationships should also be defined with back_populates
    inventory_items = db.relationship('InventoryItem', back_populates='business', lazy=True)
    sales_records = db.relationship('SalesRecord', back_populates='business', lazy=True)
    rental_records = db.relationship('RentalRecord', back_populates='business', lazy=True)
    creditors = db.relationship('Creditor', back_populates='business', lazy=True)
    debtors = db.relationship('Debtor', back_populates='business', lazy=True)
    hirable_items = db.relationship('HirableItem', back_populates='business', lazy=True)
    # company_transactions = db.relationship('CompanyTransaction', back_populates='business', lazy=True)
    future_orders = db.relationship('FutureOrder', back_populates='business', lazy=True)
    company_transactions = db.relationship('CompanyTransaction', back_populates='business', lazy=True)
    return_records = db.relationship('ReturnRecord', back_populates='business', lazy=True)
    def __repr__(self):
        return f'<Business {self.name} ({self.type})>'

class User(UserMixin,db.Model):
    __tablename__ = 'user'
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False)
    _password_hash = db.Column('password', db.String(225), nullable=False)
    role = db.Column(db.String(50), default='user')
    business_id = db.Column(db.String, db.ForeignKey('businesses.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    company_transactions = db.relationship('CompanyTransaction', back_populates='recorder', lazy=True)

    # Relationship to Business
    business = db.relationship('Business', back_populates='users')

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    def get_id(self):
        """
        Required method for Flask-Login to get a user's ID.
        """
        return str(self.id)

    @password.setter
    def password(self, password):
        self._password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def verify_password(self, password):
        return check_password_hash(self._password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

#
# models.py (locate your InventoryItem model)

class SalesRecord(db.Model):
    __tablename__ = 'sales_records'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    transaction_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    customer_phone = db.Column(db.String(20), nullable=True)
    sales_person_name = db.Column(db.String(100), nullable=False)
    grand_total_amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=True)
    
    items_sold_json = db.Column(db.Text, nullable=False, default='[]') 
    
    is_synced = db.Column(db.Boolean, nullable=False, default=False)
    receipt_number = db.Column(db.String(50), unique=True, nullable=True)
    reference_number = db.Column(db.String(100), nullable=True)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False) 
    
    # Foreign key relationship - CORRECTED TO USE back_populates
    business = db.relationship('Business', back_populates='sales_records') # <<< UPDATED LINE

    def set_items_sold(self, items_list):
        self.items_sold_json = json.dumps(items_list)

    def get_items_sold(self):
        if self.items_sold_json:
            return json.loads(self.items_sold_json)
        return []

    def __repr__(self):
        return f'<SalesRecord {self.receipt_number or self.id} - GH₵{self.grand_total_amount:.2f}>'
class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    sale_price = db.Column(db.Float, nullable=False)
    current_stock = db.Column(db.Float, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    batch_number = db.Column(db.String(100), nullable=True)
    number_of_tabs = db.Column(db.Integer, default=1, nullable=False)
    unit_price_per_tab = db.Column(db.Float, default=0.0, nullable=False)
    item_type = db.Column(db.String(50), nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    is_fixed_price = db.Column(db.Boolean, default=False, nullable=False)
    fixed_sale_price = db.Column(db.Float, default=0.0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    barcode = db.Column(db.String(100), nullable=True)
    markup_percentage_pharmacy = db.Column(db.Float, default=0.0, nullable=False)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False)
    remote_id = db.Column(db.String(36), nullable=True)  # For tracking remote inventory items
    
    business = db.relationship('Business', back_populates='inventory_items')

    __table_args__ = (
        db.UniqueConstraint('product_name', 'business_id', name='_product_name_business_uc'),
        # CORRECTED LINE: Composite unique index on business_id and barcode
        db.Index('idx_unique_active_barcode', 'business_id', 'barcode', unique=True, postgresql_where=db.text('barcode IS NOT NULL')),
    )

    def __repr__(self):
        return f'<InventoryItem {self.product_name} ({self.current_stock})>'

class Creditor(db.Model):
    __tablename__ = 'creditors'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    company_name = db.Column(db.String(255), nullable=False)
    contact_person = db.Column(db.String(100), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    amount_owed = db.Column(db.Float, nullable=False)
    date_incurred = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default='Outstanding', nullable=False)
    notes = db.Column(db.Text, nullable=True)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False)
    
    # ADD THIS RELATIONSHIP
    business = db.relationship('Business', back_populates='creditors')

    def __repr__(self):
        return f'<Creditor {self.company_name} - {self.amount_owed}>'
 
class Debtor(db.Model):
    __tablename__ = 'debtors'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    customer_name = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    amount_due = db.Column(db.Float, nullable=False)
    date_incurred = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default='Outstanding', nullable=False)
    notes = db.Column(db.Text, nullable=True)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False)

    # ADD THIS CRUCIAL RELATIONSHIP
    business = db.relationship('Business', back_populates='debtors')

    def __repr__(self):
        return f'<Debtor {self.customer_name} - {self.amount_due}>'


class HirableItem(db.Model):
    __tablename__ = 'hirable_items'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    item_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    rental_price_per_day = db.Column(db.Float, nullable=False)
    current_stock = db.Column(db.Integer, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False)

    # --- ADD THIS CRUCIAL RELATIONSHIP ---
    business = db.relationship('Business', back_populates='hirable_items')

    def __repr__(self):
        return f'<HirableItem {self.item_name} (Stock: {self.current_stock})>'

class CompanyTransaction(db.Model):
    __tablename__ = 'company_transactions'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False) # 'income' or 'expense'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    transaction_date = db.Column(db.Date, nullable=False)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False)
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), nullable=False)
    recorded_by = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=True)

    # This relationship links it back to the Business model
    business = db.relationship('Business', back_populates='company_transactions')
    company = db.relationship('Company', back_populates='company_transactions')
    recorder = db.relationship('User', back_populates='company_transactions')

    def __repr__(self):
        return f'<CompanyTransaction {self.transaction_type} - {self.amount}>'

class RentalRecord(db.Model):
    __tablename__ = 'rental_records'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    hirable_item_id = db.Column(db.String(36), db.ForeignKey('hirable_items.id'), nullable=False)
    item_name_at_rent = db.Column(db.String(255), nullable=False)
    customer_name = db.Column(db.String(255), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    rental_price_per_day_at_rent = db.Column(db.Float, nullable=False)
    rent_date = db.Column(db.Date, default=date.today, nullable=False)
    return_date = db.Column(db.Date, nullable=True)
    total_rental_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='Active', nullable=False)
    notes = db.Column(db.Text, nullable=True)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False)
    due_date = db.Column(db.Date, nullable=True)

    # --- ADD THIS CRUCIAL RELATIONSHIP ---
    # This links back to the 'Business' model, matching the 'rental_records' back_populates
    business = db.relationship('Business', back_populates='rental_records')
    date_recorded = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    hirable_item = db.relationship('HirableItem', backref='rental_records_rel', lazy=True)

    def __repr__(self):
        return f'<RentalRecord {self.item_name_at_rent} - {self.customer_name}>'

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Removed the self-referencing company_id column as it is not needed.
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False) # Removed unique constraint to allow companies with the same name in different businesses
    contact_person = db.Column(db.String(100), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    # Correct relationship to link back to the Business model
    business = db.relationship('Business', backref='companies', lazy=True)
    
    # Correct relationship to link to CompanyTransaction model
    # This assumes you have added 'company_id' column to CompanyTransaction model as previously advised.
    company_transactions = db.relationship('CompanyTransaction', back_populates='company', lazy=True)

    def calculate_current_balance(self):
        """
        Calculates the current balance for this company based on its transactions.
        A positive balance means the company owes your business.
        'Credit' (e.g., business supplies company, company owes business) increases balance.
        'Debit' (e.g., company pays business, company's debt to business decreases) decreases balance.
        """
        # We query the company_transactions relationship directly for efficiency
        # This will automatically filter by this company's ID (self.id)
        total_debits = db.session.query(func.sum(db.case(
            (CompanyTransaction.transaction_type == 'Debit', CompanyTransaction.amount),
            else_=0
        ))).filter(CompanyTransaction.company_id == self.id).scalar() or 0.0

        total_credits = db.session.query(func.sum(db.case(
            (CompanyTransaction.transaction_type == 'Credit', CompanyTransaction.amount),
            else_=0
        ))).filter(CompanyTransaction.company_id == self.id).scalar() or 0.0

        balance = total_credits - total_debits
        return float(balance)

    @property
    def total_creditors_amount(self):
        """
        Calculates the total amount the business owes this company (creditor balance).
        Returns a positive value if the company is a net creditor to the business, otherwise 0.
        """
        current_balance = self.calculate_current_balance()
        return abs(current_balance) if current_balance < 0 else 0.0

    @property
    def total_debtors_amount(self):
        """
        Calculates the total amount this company owes the business (debtor balance).
        Returns a positive value if the company is a net debtor to the business, otherwise 0.
        """
        current_balance = self.calculate_current_balance()
        return current_balance if current_balance > 0 else 0.0

    def __repr__(self):
        return f'<Company {self.name}>'


class FutureOrder(db.Model):
    __tablename__ = 'future_orders'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), nullable=True)
    customer_name = db.Column(db.String(255), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=True)
    order_details = db.Column(db.Text, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    remaining_balance = db.Column(db.Float, nullable=False, default=0.0) # This is the updated line
    order_date = db.Column(db.Date, default=date.today, nullable=False)
    pickup_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default='Pending', nullable=False)
    notes = db.Column(db.Text, nullable=True)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False)

    company = db.relationship('Company', backref='future_orders_rel', lazy=True)
    business = db.relationship('Business', back_populates='future_orders')

    def set_order_details(self, details_list):
        self.order_details = json.dumps(details_list)

    def get_order_details(self):
        if self.order_details:
            return json.loads(self.order_details)
        return []

    def __repr__(self):
        return f'<FutureOrder {self.customer_name} - {self.total_amount}>'

class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False) # Phone number as unique identifier
    email = db.Column(db.String(120), unique=False, nullable=True) # Email can be optional and not unique
    address = db.Column(db.String(255), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Add other customer-related fields as needed

    # Relationship to Business (optional, but good for clarity)
    business = db.relationship('Business', backref='customers', lazy=True)

    def __repr__(self):
        return f'<Customer {self.customer_name} ({self.phone_number})>'

class ReturnRecord(db.Model):
    __tablename__ = 'return_records'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = db.Column(db.String(36), db.ForeignKey('businesses.id'), nullable=False)
    original_receipt_number = db.Column(db.String(50), nullable=False)  # The original sale receipt
    return_receipt_number = db.Column(db.String(50), unique=True, nullable=False)  # Unique return receipt
    return_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    customer_phone = db.Column(db.String(20), nullable=True)
    customer_name = db.Column(db.String(255), nullable=True)
    processed_by = db.Column(db.String(100), nullable=False)  # Staff member who processed return
    return_reason = db.Column(db.String(255), nullable=True)  # Reason for return
    total_refund_amount = db.Column(db.Float, nullable=False, default=0.0)
    payment_method = db.Column(db.String(50), nullable=True)  # How refund was given
    
    # JSON field to store returned items details
    returned_items_json = db.Column(db.Text, nullable=False, default='[]')
    
    notes = db.Column(db.Text, nullable=True)
    is_synced = db.Column(db.Boolean, default=False, nullable=False)
    synced_to_remote = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationship to Business
    business = db.relationship('Business', back_populates='return_records')
    
    def set_returned_items(self, items_list):
        """Store returned items as JSON"""
        self.returned_items_json = json.dumps(items_list)
    
    def get_returned_items(self):
        """Retrieve returned items from JSON"""
        if self.returned_items_json:
            return json.loads(self.returned_items_json)
        return []
    
    def __repr__(self):
        return f'<ReturnRecord {self.return_receipt_number} - GH₵{self.total_refund_amount:.2f}>'

