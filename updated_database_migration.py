#!/usr/bin/env python3
"""
Fixed Migration Script for Price Range Fields - SQLAlchemy 2.x Compatible
This script properly handles existing data when adding new columns
"""

import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# Add the current directory to Python path
sys.path.insert(0, os.getcwd())

try:
    from app import app, db
except ImportError:
    print("Error: Could not import app and db from app.py")
    print("Make sure you're running this from your project directory")
    sys.exit(1)

def fix_price_range_migration():
    """
    Properly add price range fields to existing inventory_items table
    """
    print("=== Fixed Price Range Migration ===")
    print("This will safely add price range fields to your existing data")
    
    with app.app_context():
        try:
            # Check if columns already exist (using session.execute instead of engine.execute)
            result = db.session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'inventory_items' AND column_name = 'use_price_range'"
            ))
            
            if result.fetchone():
                print(" Price range columns already exist. Skipping migration.")
                return True
            
            print(" Adding price range columns with proper defaults...")
            
            # Add columns with DEFAULT values to handle existing data
            migration_sql = """
            ALTER TABLE inventory_items 
            ADD COLUMN use_price_range BOOLEAN DEFAULT FALSE NOT NULL,
            ADD COLUMN min_sale_price FLOAT DEFAULT 0.0 NOT NULL,
            ADD COLUMN preferred_sale_price FLOAT DEFAULT 0.0 NOT NULL,
            ADD COLUMN max_sale_price FLOAT DEFAULT 0.0 NOT NULL;
            """
            
            db.session.execute(text(migration_sql))
            db.session.commit()
            
            print(" Migration completed successfully!")
            print(" All existing inventory items now have:")
            print("   - use_price_range = False (fixed pricing)")
            print("   - min_sale_price = 0.0")
            print("   - preferred_sale_price = 0.0")
            print("   - max_sale_price = 0.0")
            
            return True
            
        except Exception as e:
            print(f" Migration failed: {str(e)}")
            db.session.rollback()
            return False

def rollback_price_range_migration():
    """
    Remove price range fields if they exist
    """
    print("=== Rollback Price Range Migration ===")
    
    with app.app_context():
        try:
            # Check if columns exist before trying to drop them
            result = db.session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'inventory_items' AND column_name = 'use_price_range'"
            ))
            
            if not result.fetchone():
                print("✓ Price range columns don't exist. Nothing to rollback.")
                return True
            
            print(" Removing price range columns...")
            
            rollback_sql = """
            ALTER TABLE inventory_items 
            DROP COLUMN IF EXISTS use_price_range,
            DROP COLUMN IF EXISTS min_sale_price,
            DROP COLUMN IF EXISTS preferred_sale_price,
            DROP COLUMN IF EXISTS max_sale_price;
            """
            
            db.session.execute(text(rollback_sql))
            db.session.commit()
            
            print(" Rollback completed successfully!")
            return True
            
        except Exception as e:
            print(f" Rollback failed: {str(e)}")
            db.session.rollback()
            return False

def check_columns():
    """
    Check current state of price range columns
    """
    print("=== Checking Current Database State ===")
    
    with app.app_context():
        try:
            result = db.session.execute(text(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = 'inventory_items' AND column_name IN ('use_price_range', 'min_sale_price', 'preferred_sale_price', 'max_sale_price') "
                "ORDER BY column_name"
            ))
            
            columns = result.fetchall()
            
            if not columns:
                print(" No price range columns found in inventory_items table")
                return False
            else:
                print(" Found price range columns:")
                for col in columns:
                    print(f"   - {col[0]} ({col[1]}) - Nullable: {col[2]}, Default: {col[3]}")
                return True
                
        except Exception as e:
            print(f" Error checking columns: {str(e)}")
            return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Price Range Migration Fix Tool (SQLAlchemy 2.x Compatible)")
    print("="*60)
    print("1. Fix migration (add columns properly)")
    print("2. Rollback migration (remove columns)")
    print("3. Check current database state")
    print("4. Exit")
    
    while True:
        try:
            choice = input("\nEnter your choice (1-4): ").strip()
            
            if choice == '1':
                success = fix_price_range_migration()
                if success:
                    print("\n You can now update your models.py and restart your app!")
                break
            elif choice == '2':
                success = rollback_price_range_migration()
                if success:
                    print("\n Database rolled back to previous state.")
                break
            elif choice == '3':
                check_columns()
                continue
            elif choice == '4':
                print(" Exiting...")
                break
            else:
                print(" Invalid choice. Please enter 1, 2, 3, or 4.")
                
        except KeyboardInterrupt:
            print("\n Exiting...")
            break
        except Exception as e:
            print(f" Error: {str(e)}")
