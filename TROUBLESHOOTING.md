# Troubleshooting Guide for PyInstaller Flask App Issues

## Common Issues When Packaging Flask Apps with PyInstaller

### 1. **Database Path Issues** ⚠️
**Problem**: Database can't be created or accessed in packaged app

**Solutions**:
- ✅ Use writable location outside the bundle for SQLite databases
- ✅ Create database directory if it doesn't exist
- ✅ Check write permissions in the target directory

**Fixed in**: `fixed_app.py` - proper path handling with `get_app_paths()`

### 2. **Template/Static Files Not Found** ⚠️
**Problem**: Flask can't find templates or static files in packaged app

**Solutions**:
- ✅ Pass correct `template_folder` and `static_folder` to Flask constructor
- ✅ Use `sys._MEIPASS` for bundled resources
- ✅ Include templates/static in PyInstaller spec file

**Fixed in**: `fixed_app.py` - Flask constructor with proper folder paths

### 3. **Environment Variables Not Loading** ⚠️
**Problem**: `.env` file not found or loaded in packaged app

**Solutions**:
- ✅ Search multiple locations for `.env` file
- ✅ Check executable directory, bundle directory, and current directory
- ✅ Provide fallback defaults for critical variables

**Fixed in**: `improved_env_loader.py` - comprehensive environment loading

### 4. **Import Path Issues** ⚠️
**Problem**: Python modules not found in packaged app

**Solutions**:
- ✅ Use relative imports where possible
- ✅ Add hidden imports to PyInstaller spec
- ✅ Check `sys.path` configuration

### 5. **Permission Errors** ⚠️
**Problem**: App can't write files or create directories

**Solutions**:
- ✅ Run as administrator on Windows
- ✅ Use user-writable directories (e.g., AppData, Documents)
- ✅ Check antivirus/security software blocking

## Step-by-Step Troubleshooting

### Step 1: Identify the Error
1. Run the packaged app from command line to see full error messages
2. Check if it's a startup error or runtime error
3. Note any file path or permission errors

### Step 2: Test with Fixed Files
1. Replace your current files with the improved versions:
   - `fixed_app.py` → `app.py`
   - `improved_env_loader.py` → `env_loader.py`
   - `improved_db_initializer.py` → `db_initializer.py`

### Step 3: Ensure Proper .env File
1. Place `.env` file in the same directory as your executable
2. Verify all required environment variables are set
3. Run the test script to validate environment loading

### Step 4: Check File Structure
Your app directory should look like:
```
your_app/
├── your_app.exe          # Your packaged executable
├── .env                  # Environment variables file
├── instance/             # Will be created automatically
│   └── instance_data.db  # SQLite database (created automatically)
├── templates/            # If you have templates
└── static/              # If you have static files
```

### Step 5: PyInstaller Build Recommendations

Update your PyInstaller command or spec file:

```bash
# Basic command
pyinstaller --onefile --add-data ".env;." --add-data "templates;templates" --add-data "static;static" app.py

# For hidden imports
pyinstaller --onefile --hidden-import=flask_sqlalchemy --hidden-import=flask_migrate --add-data ".env;." app.py
```

### Step 6: Test Environment
Run the environment test script:
```bash
python improved_env_loader.py
```

## Common Error Messages and Solutions

### "No such file or directory: '.env'"
**Solution**: Place `.env` file in the same directory as the executable

### "Permission denied" when creating database
**Solution**: 
- Run as administrator
- Use a different directory for the database
- Check antivirus settings

### "Template not found"
**Solution**: Ensure templates are included in PyInstaller build and Flask constructor has correct `template_folder`

### "Module not found" errors
**Solution**: Add missing modules to PyInstaller hidden imports

### "Database is locked" or "Database file is corrupt"
**Solution**: 
- Ensure only one instance of the app is running
- Delete and recreate the database file
- Check file permissions

## Testing Your Fixed App

1. **Development Test**:
   ```bash
   python fixed_app.py
   ```

2. **Package Test**:
   ```bash
   pyinstaller --onefile --add-data ".env;." --add-data "templates;templates" fixed_app.py
   ```

3. **Run Packaged App**:
   ```bash
   # Copy .env to dist directory
   copy .env dist/
   
   # Run the executable
   cd dist
   ./fixed_app.exe
   ```

## Additional Debugging

### Enable Detailed Logging
Add to your app:
```python
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app_debug.log'),
        logging.StreamHandler()
    ]
)
```

### Check File Permissions
```python
import os
db_path = "path/to/your/database.db"
db_dir = os.path.dirname(db_path)
print(f"Directory exists: {os.path.exists(db_dir)}")
print(f"Directory writable: {os.access(db_dir, os.W_OK)}")
print(f"Database exists: {os.path.exists(db_path)}")
if os.path.exists(db_path):
    print(f"Database writable: {os.access(db_path, os.W_OK)}")
```

### Environment Variables Debug
```python
import os
print("Environment Variables:")
for key, value in os.environ.items():
    if any(term in key.upper() for term in ['FLASK', 'DB', 'SECRET']):
        print(f"{key}: {value}")
```

## Contact and Support

If you're still experiencing issues after following this guide:
1. Run the app from command line and capture the full error output
2. Check the file structure and permissions
3. Verify the `.env` file is in the correct location
4. Test with the improved files provided

The improved files address the most common PyInstaller + Flask issues and should resolve the majority of packaging problems.
