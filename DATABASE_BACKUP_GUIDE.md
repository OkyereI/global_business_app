# Database Backup System Documentation

## Overview

The Database Backup System provides automatic and manual backup functionality for your offline business application. It ensures your critical business data is protected and can be recovered in case of system crashes or data corruption.

## Features

### 🔄 **Automatic Backups**
- **Frequency**: Every 6 hours automatically
- **Background Operation**: Runs in a separate thread without affecting app performance
- **Startup Backup**: Creates a backup every time the application starts
- **No User Intervention Required**: Runs silently in the background

### 📁 **Backup Storage**
- **Location**: Stored alongside your executable file in `database_backups/` folder
- **Portable**: Backups travel with your application when moved to different locations
- **Format**: Standard SQLite database files (.db extension)
- **Retention**: Keeps the last 10 backups automatically (configurable)

### 🛠️ **Manual Backup Control**
- **Instant Backups**: Create backups immediately with optional descriptions
- **Custom Naming**: Add descriptions to identify important backup points
- **Manual Triggers**: Create backups before important operations

### 🔧 **Disaster Recovery**
- **One-Click Restore**: Restore from any available backup
- **Emergency Restore**: Automatically restore from the latest backup
- **Safe Restoration**: Creates a backup of current data before restoring
- **Super Admin Only**: Only super administrators can restore backups for security

## How to Access

### Via Dashboard
1. Log into your application
2. Navigate to the dashboard
3. Click on **"Database Backup"** in the sidebar menu
4. The backup status page will show all available options

### Direct URL
- Visit: `http://localhost:5000/backup/status`

## Backup Types

### 1. **Startup Backups**
- **When**: Created every time the application starts
- **Naming**: `startup_backup.db`
- **Purpose**: Capture database state at application launch

### 2. **Automatic Backups**
- **When**: Every 6 hours while application is running
- **Naming**: `backup_YYYYMMDD_HHMMSS.db`
- **Purpose**: Regular data protection during normal operation

### 3. **Manual Backups**
- **When**: User-initiated through the interface
- **Naming**: `manual_YYYYMMDD_HHMMSS_description.db`
- **Purpose**: Important milestone backups (before major changes, updates, etc.)

## Using the Backup System

### Creating Manual Backups

1. **Navigate to Backup Page**
   ```
   Dashboard → Database Backup
   ```

2. **Create Backup**
   - Enter optional description (e.g., "Before inventory update")
   - Click "Create Backup"
   - System confirms successful creation

3. **Best Practices for Manual Backups**
   - Before major data imports
   - Before software updates
   - End of business day
   - Before system maintenance

### Restoring from Backups

⚠️ **Important**: Only super administrators can restore backups

1. **Access Backup List**
   - All available backups are shown with creation dates and sizes
   - Backups are sorted by newest first

2. **Choose Backup**
   - Click "Restore" button next to desired backup
   - Confirm the restoration action

3. **Restoration Process**
   - System creates backup of current database
   - Replaces current database with selected backup
   - Restart application for changes to take effect

### Emergency Recovery

If your database becomes corrupted:

1. **Access Backup Page** (if application still runs)
2. **Use Emergency Restore**
   - Automatically restores from latest backup
   - No user selection required

3. **Manual Recovery** (if application won't start)
   - Navigate to your application folder
   - Open `database_backups/` folder
   - Copy the most recent backup file
   - Rename it to replace your main database file

## Technical Details

### Backup Locations

#### Development Environment
```
your_project_folder/
├── app.py
├── business_data.db          # Main database
└── database_backups/         # Backup folder
    ├── backup.log           # Backup operation log
    ├── startup_backup.db
    ├── backup_20250922_143000.db
    ├── manual_20250922_150000_inventory_update.db
    └── ...
```

#### Executable Environment (PyInstaller)
```
your_executable_folder/
├── BusinessApp.exe           # Your executable
├── business_data.db         # Main database
└── database_backups/        # Backup folder
    ├── backup.log
    ├── startup_backup.db
    └── ...
```

### Backup File Format
- **Type**: SQLite database files
- **Compression**: None (preserves data integrity)
- **Compatibility**: Can be opened with any SQLite tool
- **Verification**: Uses SQLite's built-in backup API for integrity

### System Requirements
- **Disk Space**: Each backup is typically the same size as your main database
- **Memory**: Minimal impact during backup creation
- **Performance**: No noticeable impact on application speed

## Configuration Options

The backup system is pre-configured with sensible defaults:

### Current Settings
- **Backup Frequency**: 6 hours
- **Maximum Backups**: 10 files
- **Startup Backup**: Enabled
- **Background Operation**: Enabled

### Customizing Settings

To modify backup behavior, edit `backup_manager.py`:

```python
# Change backup frequency (in hours)
backup_manager.start_automatic_backups(interval_hours=12)  # 12 hours instead of 6

# Change maximum backup retention
backup_manager = DatabaseBackupManager(db_path, max_backups=20)  # Keep 20 backups
```

## Monitoring and Logs

### Backup Status Information
The backup status page shows:
- Total number of backups
- Automatic backup scheduler status
- Database health status
- Latest backup creation time
- Backup directory location

### Log Files
- **Location**: `database_backups/backup.log`
- **Content**: All backup operations, errors, and status messages
- **Format**: Timestamped entries with severity levels

### Log Example
```
2025-09-22 14:30:00 - INFO - Database backup created: backup_20250922_143000.db
2025-09-22 14:30:01 - INFO - Removed old backup: backup_20250921_083000.db
2025-09-22 20:30:00 - INFO - Automatic backup scheduler started (every 6 hours)
```

## Troubleshooting

### Common Issues

#### 1. **Backup Creation Fails**
**Symptoms**: Error message "Failed to create backup"
**Solutions**:
- Check disk space availability
- Ensure database is not locked by another process
- Review `backup.log` for specific error details

#### 2. **Automatic Backups Not Running**
**Symptoms**: Backup status shows "Inactive"
**Solutions**:
- Restart the application
- Check if application is running continuously
- Verify `schedule` package is installed

#### 3. **Cannot Access Backup Directory**
**Symptoms**: Backup directory not found or accessible
**Solutions**:
- Ensure application has write permissions
- Check if antivirus is blocking file creation
- Verify backup directory path in logs

#### 4. **Restore Operation Fails**
**Symptoms**: "Failed to restore backup" message
**Solutions**:
- Ensure backup file exists and is not corrupted
- Check file permissions
- Try manual file copy as fallback

### Recovery Procedures

#### Complete System Recovery
1. **Locate Backup Files**
   - Find `database_backups/` folder
   - Identify the most recent or relevant backup

2. **Manual Database Replacement**
   ```bash
   # Stop the application first
   # Navigate to application folder
   cp database_backups/backup_YYYYMMDD_HHMMSS.db business_data.db
   # Restart application
   ```

3. **Verify Recovery**
   - Start application
   - Check data integrity
   - Verify all features work correctly

## Security Considerations

### Access Control
- **Backup Creation**: All authenticated users
- **Backup Restoration**: Super administrators only
- **Emergency Restore**: Super administrators only

### Data Protection
- **Backup Files**: Stored locally with same security as main database
- **Transfer Security**: No network transmission of backup files
- **Encryption**: Uses same encryption level as main database

### Best Practices
1. **Regular Testing**: Periodically test backup restoration
2. **External Copies**: Manually copy important backups to external drives
3. **Access Logs**: Monitor who accesses backup functionality
4. **Secure Storage**: Keep backup directory secure from unauthorized access

## Integration with Existing System

### PyInstaller Compatibility
- **Automatic Detection**: Detects if running as executable or in development
- **Path Resolution**: Uses correct paths for both environments
- **Bundle Integration**: Backup system is included in executable bundle

### Sync Compatibility
- **Online/Offline Sync**: Backups include `remote_id` fields for sync compatibility
- **Restoration Safety**: Restored databases maintain sync relationships
- **Conflict Prevention**: Backups preserve sync status and metadata

## Support and Maintenance

### Regular Maintenance
- **Weekly**: Review backup logs for any errors
- **Monthly**: Test restore procedure with non-critical backup
- **Quarterly**: Clean up very old backups manually if needed

### System Updates
When updating the application:
1. Create manual backup before update
2. Test backup system after update
3. Verify backup directory is preserved

### Getting Help
If you encounter issues:
1. Check the backup logs in `database_backups/backup.log`
2. Verify disk space and permissions
3. Test with manual backup creation
4. Contact support with specific error messages and log entries

## Conclusion

The Database Backup System provides comprehensive protection for your business data with minimal user intervention. The automatic backup schedule ensures regular protection, while manual backup options give you control for important operations. The restore functionality provides peace of mind knowing your data can be recovered quickly in case of any issues.

Remember to periodically test the restore functionality to ensure your backups are working correctly and your data can be recovered when needed.