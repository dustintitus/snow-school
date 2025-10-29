#!/usr/bin/env python3
"""
Simple test script to verify Vercel deployment
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_vercel_setup():
    """Test if the Vercel setup is working"""
    
    print("🧪 Testing Vercel Setup")
    print("=" * 40)
    
    # Check environment
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print(f"FLASK_ENV: {os.environ.get('FLASK_ENV', 'Not set')}")
    
    try:
        # Test imports
        print("\n📦 Testing imports...")
        from app import app
        print("✅ Flask app imported successfully")
        
        from app import db
        print("✅ Database imported successfully")
        
        from app import User, Program
        print("✅ Models imported successfully")
        
        # Test app configuration
        print(f"\n⚙️  App configuration:")
        print(f"   Debug: {app.debug}")
        print(f"   Database URI: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        
        # Test database connection
        print(f"\n🔗 Testing database connection...")
        with app.app_context():
            try:
                db.session.execute(db.text('SELECT 1'))
                print("✅ Database connection successful")
                
                # Check tables
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                print(f"✅ Tables found: {tables}")
                
                # Check if users exist
                user_count = User.query.count()
                print(f"✅ Users in database: {user_count}")
                
                if user_count > 0:
                    admin = User.query.filter_by(username='admin').first()
                    if admin:
                        print(f"✅ Admin user found: {admin.username}")
                    else:
                        print("❌ Admin user not found")
                
            except Exception as e:
                print(f"❌ Database error: {e}")
                return False
        
        print(f"\n🎉 All tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

if __name__ == '__main__':
    success = test_vercel_setup()
    if not success:
        sys.exit(1)
