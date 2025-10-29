#!/usr/bin/env python3
"""
Script to set up Neon database with users and programs
Run this script with your Neon DATABASE_URL environment variable
"""

import os
import sys
from werkzeug.security import generate_password_hash
from datetime import datetime, date

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, User, Program, Team

def setup_neon_database():
    """Set up Neon database with initial data"""
    
    # Check if DATABASE_URL is set
    if not os.environ.get('DATABASE_URL'):
        print("❌ Error: DATABASE_URL environment variable not set")
        print("Please set your Neon database URL:")
        print("export DATABASE_URL='postgresql://username:password@host:port/database'")
        return False
    
    print(f"🔗 Connecting to database: {os.environ['DATABASE_URL'][:50]}...")
    
    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            print("✅ Database tables created/verified")
            
            # Check if users already exist
            existing_users = User.query.count()
            if existing_users > 0:
                print(f"⚠️  Found {existing_users} existing users. Skipping user creation.")
            else:
                # Create users
                users = [
                    {
                        'username': 'admin',
                        'email': 'admin@snowschool.com',
                        'password': 'password123',
                        'user_type': 'admin',
                        'full_name': 'Administrator'
                    },
                    {
                        'username': 'instructor1',
                        'email': 'instructor@snowschool.com',
                        'password': 'password123',
                        'user_type': 'instructor',
                        'full_name': 'John Instructor'
                    },
                    {
                        'username': 'student1',
                        'email': 'student@snowschool.com',
                        'password': 'password123',
                        'user_type': 'student',
                        'full_name': 'Jane Student'
                    }
                ]
                
                for user_data in users:
                    user = User(
                        username=user_data['username'],
                        email=user_data['email'],
                        password_hash=generate_password_hash(user_data['password'], method='pbkdf2:sha256'),
                        user_type=user_data['user_type'],
                        full_name=user_data['full_name']
                    )
                    db.session.add(user)
                
                db.session.commit()
                print("✅ Users created successfully")
            
            # Check if programs already exist
            existing_programs = Program.query.count()
            if existing_programs > 0:
                print(f"⚠️  Found {existing_programs} existing programs. Skipping program creation.")
            else:
                # Create programs
                programs = [
                    {
                        'name': 'Snowflakes',
                        'description': 'Beginner program for young skiers',
                        'frequency_type': 'consecutive',
                        'frequency_value': 8
                    },
                    {
                        'name': 'High Flyers',
                        'description': 'Advanced skiing program',
                        'frequency_type': 'weekly',
                        'frequency_value': 6,
                        'frequency_days': 'saturday'
                    },
                    {
                        'name': 'Trail Blazers',
                        'description': 'Intermediate snowboarding',
                        'frequency_type': 'consecutive',
                        'frequency_value': 8
                    },
                    {
                        'name': 'LIT',
                        'description': 'Leadership in Training program',
                        'frequency_type': 'custom',
                        'frequency_value': 12,
                        'frequency_days': 'monday,wednesday,friday'
                    },
                    {
                        'name': 'Adult',
                        'description': 'Adult skiing and snowboarding',
                        'frequency_type': 'weekly',
                        'frequency_value': 8,
                        'frequency_days': 'sunday'
                    },
                    {
                        'name': 'Terrain Park',
                        'description': 'Terrain park and freestyle program',
                        'frequency_type': 'consecutive',
                        'frequency_value': 6
                    }
                ]
                
                for prog_data in programs:
                    program = Program(
                        name=prog_data['name'],
                        description=prog_data['description'],
                        frequency_type=prog_data['frequency_type'],
                        frequency_value=prog_data['frequency_value'],
                        frequency_days=prog_data.get('frequency_days'),
                        start_date=date.today(),
                        end_date=None
                    )
                    db.session.add(program)
                
                db.session.commit()
                print("✅ Programs created successfully")
            
            # Verify setup
            user_count = User.query.count()
            program_count = Program.query.count()
            
            print(f"\n🎉 Neon database setup complete!")
            print(f"📊 Users: {user_count}")
            print(f"📊 Programs: {program_count}")
            print(f"\n🔑 Login credentials:")
            print(f"   Admin: admin / password123")
            print(f"   Instructor: instructor1 / password123")
            print(f"   Student: student1 / password123")
            
            return True
            
        except Exception as e:
            print(f"❌ Error setting up database: {e}")
            db.session.rollback()
            return False

if __name__ == '__main__':
    print("🚀 Setting up Neon database for Snow School...")
    success = setup_neon_database()
    if success:
        print("\n✅ Setup complete! You can now deploy to Vercel.")
    else:
        print("\n❌ Setup failed. Please check your DATABASE_URL and try again.")
        sys.exit(1)
