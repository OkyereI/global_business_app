# 🔄 Online/Offline Sync Setup Checklist

## 📋 Files That Must Be Identical in Both Apps:

### ✅ **1. models.py**
- **MUST HAVE**: `remote_id = db.Column(db.String(36), nullable=True)` in InventoryItem class
- **Location**: Line 128 in InventoryItem model
- **Purpose**: Links local items to remote items during sync

### ✅ **2. app.py** 
- **MUST HAVE**: Fixed `pull_inventory_data()` function
- **Key Changes**:
  - Uses `InventoryItem` model (not `Product`)
  - Uses `remote_id` for tracking
  - Proper field mapping for API responses
  - Status updates after successful sync

### ✅ **3. Database Migration**
- **File**: `migrations/versions/001_add_remote_id_to_inventory.py`
- **Purpose**: Adds `remote_id` column to existing `inventory_items` table
- **CRITICAL**: Must run on BOTH online and offline databases

## 🚀 **Setup Steps:**

### **For Your Online App:**
```bash
# 1. Pull latest from GitHub (already done)
git pull origin main

# 2. Run migration
flask db upgrade

# 3. Restart your online server
```

### **For Your Offline App:**
```bash
# 1. Copy these files from your online app to offline app:
#    - models.py (with remote_id field)
#    - app.py (with fixed sync logic)
#    - migrations/versions/001_add_remote_id_to_inventory.py

# 2. Run migration on offline database
flask db upgrade

# 3. Test the sync functionality
```

## 🔍 **Verification Steps:**

### **Check Database Schema:**
```sql
-- Run this on both databases to verify remote_id column exists:
.schema inventory_items
-- Should show: remote_id TEXT
```

### **Test Sync Process:**
1. **Online → Offline**: Click "Pull Inventory" in offline app
2. **Verify**: Check that inventory items appear
3. **Confirm**: "Total Products" count should update
4. **Check**: "Last Sync" timestamp should show current time

## ⚠️ **Important Notes:**

- **Same Code Base**: Online and offline apps must use identical sync logic
- **Database Compatibility**: Both databases need the `remote_id` column
- **API Consistency**: Ensure your online API returns the expected field names
- **Error Handling**: Check logs if sync fails after migration

## 🎯 **Expected Result:**
✅ Inventory sync should work perfectly between online ↔ offline
✅ No more "Total Products: 0" in offline app after sync
✅ Proper tracking of which items came from which remote source