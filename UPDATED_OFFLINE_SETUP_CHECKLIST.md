# Updated Offline App Setup Checklist (with Backup System)

## ✅ Essential Files to Copy/Update

### 1. **Core Application Files**
- [ ] Copy updated `app.py` from workspace to offline app directory
- [ ] Copy updated `models.py` from workspace to offline app directory  
- [ ] Copy `backup_manager.py` from workspace to offline app directory (NEW)
- [ ] Copy updated `requirements.txt` from workspace to offline app directory

### 2. **Template Files** 
- [ ] Copy all template files from `templates/` directory
- [ ] Ensure `backup_status.html` template is included (NEW)

### 3. **Database Schema Update**
- [ ] Navigate to your offline app directory: `cd ~/offline_app`
- [ ] Activate virtual environment: `source env/bin/activate` (Linux/Mac) or `env\Scripts\activate` (Windows)
- [ ] Install new dependencies: `pip install -r requirements.txt`
- [ ] Run database migration: `flask db upgrade`

### 4. **New Dependencies (Added to requirements.txt)**
- [ ] Verify `schedule==1.2.0` is installed for automatic backups

## 🔧 Database Backup System Setup

### **What's New**
The offline app now includes a comprehensive database backup system that:
- ✅ Automatically creates backups every 6 hours
- ✅ Creates startup backups when app launches  
- ✅ Allows manual backup creation with descriptions
- ✅ Provides one-click restore functionality
- ✅ Stores backups alongside the executable file
- ✅ Maintains backup logs for monitoring

### **Access the Backup System**
1. **Via Dashboard**: Click "Database Backup" in the sidebar
2. **Direct URL**: Visit `http://localhost:5000/backup/status`

### **Backup Storage Location**
- **Development**: `~/offline_app/database_backups/`
- **Executable**: Same folder as your `.exe` file in `database_backups/`

## 🛡️ Critical Synchronization Requirements

### **Both Apps Must Be Identical**
- [ ] **Same app.py version** - Contains inventory sync fixes and backup system
- [ ] **Same models.py version** - Contains `remote_id` field for sync
- [ ] **Same database schema** - Run `flask db upgrade` on both databases
- [ ] **Same template files** - Ensures UI consistency

### **Why This Matters**
- 🔄 **Online/Offline Sync**: Both apps must have identical `remote_id` fields
- 📊 **Data Integrity**: Schema mismatches will break synchronization  
- 🔧 **Feature Parity**: Both apps need same functionality and UI

## 📋 Step-by-Step Setup Process

### **Step 1: Update Code Files**
```bash
# Navigate to offline app directory
cd ~/offline_app

# Copy updated files (adjust paths as needed)
cp /path/to/workspace/app.py .
cp /path/to/workspace/models.py .
cp /path/to/workspace/backup_manager.py .
cp /path/to/workspace/requirements.txt .
cp -r /path/to/workspace/templates/ .
```

### **Step 2: Install Dependencies**
```bash
# Activate virtual environment
source env/bin/activate  # Linux/Mac
# OR
env\Scripts\activate     # Windows

# Install/update packages
pip install -r requirements.txt
```

### **Step 3: Update Database Schema**
```bash
# Run database migration to add remote_id column
flask db upgrade
```

### **Step 4: Test Backup System**
```bash
# Start the application
python app.py

# Navigate to backup page in browser
# http://localhost:5000/backup/status

# Create a test backup to verify functionality
```

## 🔍 Verification Checklist

### **Database Schema Check**
```sql
-- Verify remote_id column exists in all tables
PRAGMA table_info(sales_records);
PRAGMA table_info(inventory_items);
-- Should show remote_id column with UUID type
```

### **Backup System Check**
- [ ] Backup status page loads without errors
- [ ] Automatic backup scheduler shows "Active"
- [ ] Can create manual backup successfully
- [ ] Backup files appear in `database_backups/` folder
- [ ] Backup logs show successful operations

### **Sync Readiness Check**
- [ ] Both online and offline apps have identical `app.py`
- [ ] Both databases have `remote_id` columns
- [ ] Both apps can run without errors
- [ ] Template files are consistent between apps

## ⚠️ Important Notes

### **Backup System Benefits**
- 🛡️ **Data Protection**: Automatic backup every 6 hours
- 🔄 **Disaster Recovery**: One-click restore from backups
- 📁 **Portable**: Backups stored with executable
- 🔒 **Secure**: Only super admin can restore backups

### **Flask Command Issues**
If you get "flask: command not found":
```bash
# Option 1: Use python module
python -m flask db upgrade

# Option 2: Ensure Flask is installed
pip install flask flask-migrate flask-sqlalchemy

# Option 3: Check virtual environment activation
which python  # Should show env/bin/python path
```

### **PyInstaller Integration**
The backup system is fully compatible with PyInstaller:
- ✅ Detects executable vs development environment
- ✅ Uses correct backup paths automatically
- ✅ Included in executable bundle

## 📞 Troubleshooting

### **Common Issues**

**Issue**: Database migration fails
**Solution**: Ensure you're in the correct directory and virtual environment is activated

**Issue**: Backup system doesn't initialize  
**Solution**: Check that `schedule` package is installed: `pip install schedule==1.2.0`

**Issue**: Templates not loading
**Solution**: Verify all template files are copied, especially `backup_status.html`

**Issue**: Remote_id column missing
**Solution**: Run `flask db upgrade` again, check migration files exist

### **Verification Commands**
```bash
# Check if in virtual environment
echo $VIRTUAL_ENV

# Check Flask installation
python -c "import flask; print(flask.__version__)"

# Check database schema
python -c "from app import app; from models import SalesRecord; print([c.name for c in SalesRecord.__table__.columns])"

# Test backup system
python -c "from backup_manager import DatabaseBackupManager; print('Backup system importable')"
```

## ✅ Final Checklist

- [ ] All files copied to offline app directory
- [ ] Dependencies installed with `pip install -r requirements.txt`  
- [ ] Database migrated with `flask db upgrade`
- [ ] Backup system accessible via dashboard
- [ ] Both online and offline apps running identical code
- [ ] Test backup creation works
- [ ] Test sync functionality between apps

**Once all items are checked, your offline app will have:**
- ✅ Full synchronization capability with online app
- ✅ Automatic database backup protection  
- ✅ Manual backup and restore functionality
- ✅ Enhanced data security and disaster recovery