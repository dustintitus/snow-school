#!/usr/bin/env python3
"""
Test script to verify Neon database connection and users
"""

import os
import sys
from werkzeug.security import check_password_hash

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, User

def test_neon_connection():
    """Test Neon database connection and user authentication"""
    
    print("🔍 Testing Neon database connection...")
    
    # Check environment
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not set")
        return False
    
    print(f"✅ DATABASE_URL found: {database_url[:50]}...")
    
    with app.app_context():
        try:
            # Test database connection
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            print("✅ Database connection successful")
            
            # Check users
            users = User.query.all()
            print(f"📊 Found {len(users)} users in database:")
            
            for user in users:
                print(f"   - {user.username} ({user.user_type}) - {user.email}")
                
                # Test password verification
                password_check = check_password_hash(user.password_hash, 'password123')
                print(f"     Password check: {'✅' if password_check else '❌'}")
                
                if user.username == 'admin':
                    print(f"     Hash: {user.password_hash[:50]}...")
            
            # Test specific admin login
            admin = User.query.filter_by(username='admin').first()
            if admin:
                print(f"\n🔑 Admin user test:")
                print(f"   Username: {admin.username}")
                print(f"   Email: {admin.email}")
                print(f"   User type: {admin.user_type}")
                print(f"   Password verification: {check_password_hash(admin.password_hash, 'password123')}")
                
                # Test with different passwords
                test_passwords = ['password123', 'password', 'admin', 'wrong']
                for pwd in test_passwords:
                    result = check_password_hash(admin.password_hash, pwd)
                    print(f"   '{pwd}': {'✅' if result else '❌'}")
            else:
                print("❌ Admin user not found!")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            return False

if __name__ == '__main__':
    print("🧪 Neon Database Connection Test")
    print("=" * 50)
    
    success = test_neon_connection()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Test completed successfully!")
        print("If login still doesn't work, the issue might be:")
        print("1. Vercel environment variables not set correctly")
        print("2. Vercel deployment not using the latest code")
        print("3. Session/cookie issues")
    else:
        print("❌ Test failed. Check your DATABASE_URL and try again.")
