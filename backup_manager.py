"""
Database Backup Manager for Offline Business App
Automatically creates and manages database backups alongside the executable
"""

import os
import sys
import shutil
import sqlite3
import datetime
import logging
from pathlib import Path
import threading
import time
import schedule
from typing import Optional, List

class DatabaseBackupManager:
    """Manages automatic database backups for the offline application"""
    
    def __init__(self, db_path: str, max_backups: int = 10):
        """
        Initialize the backup manager
        
        Args:
            db_path: Path to the main database file
            max_backups: Maximum number of backups to keep (default: 10)
        """
        self.db_path = db_path
        self.max_backups = max_backups
        
        # Determine the backup directory (same as executable)
        if getattr(sys, 'frozen', False):
            # Running as PyInstaller executable
            self.backup_dir = Path(sys.executable).parent / "database_backups"
        else:
            # Running in development
            self.backup_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "database_backups"
        
        # Create backup directory if it doesn't exist
        self.backup_dir.mkdir(exist_ok=True)
        
        # Setup logging
        self.logger = self._setup_logging()
        
        # Background scheduler
        self.scheduler_running = False
        self.scheduler_thread = None
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for backup operations"""
        logger = logging.getLogger('backup_manager')
        logger.setLevel(logging.INFO)
        
        # Create file handler in backup directory
        log_file = self.backup_dir / "backup.log"
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not logger.handlers:
            logger.addHandler(handler)
        
        return logger
    
    def create_backup(self, backup_name: Optional[str] = None) -> bool:
        """
        Create a database backup
        
        Args:
            backup_name: Optional custom backup name, otherwise uses timestamp
            
        Returns:
            bool: True if backup was successful, False otherwise
        """
        try:
            # Check if database exists
            if not os.path.exists(self.db_path):
                self.logger.warning(f"Database file not found: {self.db_path}")
                return False
            
            # Generate backup filename
            if backup_name is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"backup_{timestamp}.db"
            
            backup_path = self.backup_dir / backup_name
            
            # Create backup using SQLite backup API (safer than file copy)
            self._create_sqlite_backup(self.db_path, str(backup_path))
            
            self.logger.info(f"Database backup created: {backup_path}")
            
            # Clean up old backups
            self._cleanup_old_backups()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create backup: {str(e)}")
            return False
    
    def _create_sqlite_backup(self, source_db: str, backup_path: str):
        """Create a proper SQLite backup using the backup API"""
        # Connect to source database
        source_conn = sqlite3.connect(source_db)
        
        # Connect to backup database
        backup_conn = sqlite3.connect(backup_path)
        
        try:
            # Use SQLite backup API
            source_conn.backup(backup_conn)
            self.logger.info(f"SQLite backup completed: {backup_path}")
        finally:
            source_conn.close()
            backup_conn.close()
    
    def _cleanup_old_backups(self):
        """Remove old backups to maintain max_backups limit"""
        try:
            # Get all backup files
            backup_files = list(self.backup_dir.glob("backup_*.db"))
            
            # Sort by creation time (newest first)
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove excess backups
            if len(backup_files) > self.max_backups:
                for old_backup in backup_files[self.max_backups:]:
                    old_backup.unlink()
                    self.logger.info(f"Removed old backup: {old_backup}")
                    
        except Exception as e:
            self.logger.error(f"Failed to cleanup old backups: {str(e)}")
    
    def list_backups(self) -> List[dict]:
        """
        List all available backups
        
        Returns:
            List of backup info dictionaries
        """
        backups = []
        try:
            backup_files = list(self.backup_dir.glob("backup_*.db"))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            for backup_file in backup_files:
                stat = backup_file.stat()
                backups.append({
                    'filename': backup_file.name,
                    'path': str(backup_file),
                    'size': stat.st_size,
                    'created': datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
                
        except Exception as e:
            self.logger.error(f"Failed to list backups: {str(e)}")
            
        return backups
    
    def restore_backup(self, backup_filename: str) -> bool:
        """
        Restore database from a backup
        
        Args:
            backup_filename: Name of the backup file to restore
            
        Returns:
            bool: True if restore was successful, False otherwise
        """
        try:
            backup_path = self.backup_dir / backup_filename
            
            if not backup_path.exists():
                self.logger.error(f"Backup file not found: {backup_path}")
                return False
            
            # Create a backup of current database before restoring
            current_backup_name = f"pre_restore_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            if os.path.exists(self.db_path):
                self.create_backup(current_backup_name)
            
            # Restore the backup
            shutil.copy2(str(backup_path), self.db_path)
            
            self.logger.info(f"Database restored from backup: {backup_filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to restore backup: {str(e)}")
            return False
    
    def start_automatic_backups(self, interval_hours: int = 6):
        """
        Start automatic backup scheduler
        
        Args:
            interval_hours: Backup interval in hours (default: 6 hours)
        """
        if self.scheduler_running:
            self.logger.warning("Automatic backup scheduler is already running")
            return
        
        # Schedule automatic backups
        schedule.every(interval_hours).hours.do(self.create_backup)
        
        # Start scheduler in background thread
        self.scheduler_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        self.logger.info(f"Automatic backup scheduler started (every {interval_hours} hours)")
    
    def stop_automatic_backups(self):
        """Stop automatic backup scheduler"""
        self.scheduler_running = False
        schedule.clear()
        self.logger.info("Automatic backup scheduler stopped")
    
    def _run_scheduler(self):
        """Run the backup scheduler in background"""
        while self.scheduler_running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def get_backup_status(self) -> dict:
        """Get backup system status"""
        backups = self.list_backups()
        
        return {
            'backup_directory': str(self.backup_dir),
            'database_path': self.db_path,
            'total_backups': len(backups),
            'max_backups': self.max_backups,
            'latest_backup': backups[0] if backups else None,
            'scheduler_running': self.scheduler_running,
            'backup_directory_exists': self.backup_dir.exists(),
            'database_exists': os.path.exists(self.db_path)
        }
    
    def create_manual_backup(self, description: str = "") -> bool:
        """
        Create a manual backup with description
        
        Args:
            description: Optional description for the backup
            
        Returns:
            bool: True if backup was successful
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if description:
            # Sanitize description for filename
            clean_desc = "".join(c for c in description if c.isalnum() or c in (' ', '-', '_')).rstrip()
            clean_desc = clean_desc.replace(' ', '_')[:30]  # Limit length
            backup_name = f"manual_{timestamp}_{clean_desc}.db"
        else:
            backup_name = f"manual_{timestamp}.db"
        
        return self.create_backup(backup_name)
    
    def emergency_restore(self) -> bool:
        """
        Emergency restore from the latest backup (for crash recovery)
        
        Returns:
            bool: True if emergency restore was successful
        """
        try:
            backups = self.list_backups()
            
            if not backups:
                self.logger.error("No backups available for emergency restore")
                return False
            
            latest_backup = backups[0]['filename']
            self.logger.warning(f"Performing emergency restore from: {latest_backup}")
            
            return self.restore_backup(latest_backup)
            
        except Exception as e:
            self.logger.error(f"Emergency restore failed: {str(e)}")
            return False


def initialize_backup_system(app, db_path: str):
    """
    Initialize backup system for Flask app
    
    Args:
        app: Flask application instance
        db_path: Path to the database file
    """
    backup_manager = DatabaseBackupManager(db_path)
    
    # Store backup manager in app context
    app.backup_manager = backup_manager
    
    # Create initial backup on startup
    backup_manager.create_backup("startup_backup.db")
    
    # Start automatic backups every 6 hours
    backup_manager.start_automatic_backups(interval_hours=6)
    
    return backup_manager


# Example usage in Flask routes
def add_backup_routes(app):
    """Add backup management routes to Flask app"""
    
    @app.route('/backup/create', methods=['POST'])
    def create_manual_backup():
        """Create a manual backup"""
        from flask import request, jsonify, flash, redirect, url_for
        
        description = request.form.get('description', '')
        success = app.backup_manager.create_manual_backup(description)
        
        if success:
            flash('Manual backup created successfully!', 'success')
        else:
            flash('Failed to create backup. Check logs for details.', 'danger')
        
        return redirect(url_for('backup_status'))
    
    @app.route('/backup/status')
    def backup_status():
        """Show backup status page"""
        from flask import render_template
        
        status = app.backup_manager.get_backup_status()
        backups = app.backup_manager.list_backups()
        
        return render_template('backup_status.html', status=status, backups=backups)
    
    @app.route('/backup/restore/<backup_filename>')
    def restore_backup(backup_filename):
        """Restore from a specific backup"""
        from flask import flash, redirect, url_for
        
        success = app.backup_manager.restore_backup(backup_filename)
        
        if success:
            flash(f'Database restored from backup: {backup_filename}', 'success')
        else:
            flash('Failed to restore backup. Check logs for details.', 'danger')
        
        return redirect(url_for('backup_status'))


if __name__ == "__main__":
    # Test the backup system
    test_db = "test_database.db"
    backup_manager = DatabaseBackupManager(test_db)
    
    print("Backup System Test")
    print(f"Backup directory: {backup_manager.backup_dir}")
    print(f"Status: {backup_manager.get_backup_status()}")