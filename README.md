# Global Business App

A Flask-based desktop business management application with inventory management, sales tracking, and remote synchronization capabilities.

## Features

- **Inventory Management**: Track products, stock levels, and pricing
- **Sales Recording**: Record and manage sales transactions
- **User Management**: Multi-user support with authentication
- **Remote Sync**: Synchronize data with remote servers
- **Desktop Application**: Can be packaged as a standalone executable
- **Business Dashboard**: Analytics and reporting features

## Installation

### Development Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/OkyereI/global_business_app.git
   cd global_business_app
   ```

2. Create a virtual environment:
   ```bash
   python -m venv env
   source env/bin/activate  # On Windows: env\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your configuration:
   ```env
   FLASK_SECRET_KEY=your_secret_key_here
   ONLINE_FLASK_APP_BASE_URL=https://your-server.com
   REMOTE_ADMIN_API_KEY=your_api_key
   ENTERPRISE_NAME=Your Business Name
   DB_TYPE=sqlite
   ```

5. Run the application:
   ```bash
   python app.py
   ```

### Building Executable

To create a standalone executable:

```bash
python -m PyInstaller --onefile --add-data "templates;templates" --add-data "static;static" --add-data ".env;." --icon "gbt.png" --hidden-import "flask_sqlalchemy" --hidden-import "flask_migrate" --hidden-import "flask_wtf" --hidden-import "flask_login" --hidden-import "extensions" --hidden-import "models" --hidden-import "sync_api" --hidden-import "env_loader" --hidden-import "browser_launcher" --hidden-import "db_initializer" --name "GlobalBusinessApp" app.py
```

## Project Structure

```
global_business_app/
├── app.py                 # Main Flask application
├── models.py              # Database models
├── extensions.py          # Flask extensions setup
├── env_loader.py          # Environment variable loader
├── db_initializer.py      # Database initialization
├── sync_api.py            # Remote synchronization
├── browser_launcher.py    # Browser automation
├── templates/             # HTML templates
├── static/                # CSS, JS, images
├── instance/              # Database and instance files
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Configuration

The application uses environment variables for configuration. Create a `.env` file in the project root:

```env
# Flask Configuration
FLASK_SECRET_KEY=your_secret_key_here
FLASK_ENV=production

# Database
DB_TYPE=sqlite

# Remote Sync
ONLINE_FLASK_APP_BASE_URL=https://your-server.com
REMOTE_ADMIN_API_KEY=your_api_key

# Business Information
ENTERPRISE_NAME=Your Business Name
PHARMACY_LOCATION=Your Location
PHARMACY_ADDRESS=Your Address
PHARMACY_CONTACT=Your Phone

# SMS Configuration (optional)
ARKESEL_API_KEY=your_sms_api_key
ARKESEL_SENDER_ID=your_sender_id
ADMIN_PHONE_NUMBER=your_admin_phone
```

## Usage

1. **First Run**: The application will create the database and default admin user
2. **Login**: Use the admin credentials to access the dashboard
3. **Setup Business**: Configure your business information
4. **Add Inventory**: Start adding products and managing inventory
5. **Record Sales**: Process sales transactions
6. **Sync Data**: Use the sync feature to backup/restore data

## Troubleshooting

### PyInstaller Issues

- Ensure `.env` file is in the same directory as the executable
- Check that the `instance` folder has write permissions
- Review the `TROUBLESHOOTING.md` file for common issues

### Database Issues

- The application creates a SQLite database in the `instance` folder
- For packaged apps, the database is created next to the executable
- Ensure write permissions for the application directory

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is proprietary software. All rights reserved.

## Support

For support and questions, please contact the development team.

---

**Author**: MiniMax Agent  
**Last Updated**: 2025-09-22
