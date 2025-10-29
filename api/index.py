"""
Vercel serverless function entry point in api/ directory
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment
if 'FLASK_ENV' not in os.environ:
    os.environ['FLASK_ENV'] = 'production'

# Import the Flask app
from app import app, db, User, Program
from werkzeug.security import generate_password_hash
from datetime import date

# Initialize database on cold start (production-safe)
try:
    with app.app_context():
        # Create all tables
        db.create_all()
        print("✓ Database tables created/verified")
        
        # Check if users exist, if not create them
        if User.query.count() == 0:
            print("Creating initial users...")
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
            print("✓ Users created")
        
        # Check if programs exist, if not create them
        if Program.query.count() == 0:
            print("Creating initial programs...")
            programs = [
                {
                    'name': 'Snowflakes',
                    'description': 'Beginner program for young skiers',
                    'frequency_type': 'consecutive',
                    'frequency_value': 8,
                    'start_date': date.today(),
                    'end_date': None
                },
                {
                    'name': 'High Flyers',
                    'description': 'Advanced skiing program',
                    'frequency_type': 'weekly',
                    'frequency_value': 6,
                    'frequency_days': 'saturday',
                    'start_date': date.today(),
                    'end_date': None
                },
                {
                    'name': 'Trail Blazers',
                    'description': 'Intermediate snowboarding',
                    'frequency_type': 'consecutive',
                    'frequency_value': 8,
                    'start_date': date.today(),
                    'end_date': None
                },
                {
                    'name': 'LIT',
                    'description': 'Leadership in Training program',
                    'frequency_type': 'custom',
                    'frequency_value': 12,
                    'frequency_days': 'monday,wednesday,friday',
                    'start_date': date.today(),
                    'end_date': None
                },
                {
                    'name': 'Adult',
                    'description': 'Adult skiing and snowboarding',
                    'frequency_type': 'weekly',
                    'frequency_value': 8,
                    'frequency_days': 'sunday',
                    'start_date': date.today(),
                    'end_date': None
                },
                {
                    'name': 'Terrain Park',
                    'description': 'Terrain park and freestyle program',
                    'frequency_type': 'consecutive',
                    'frequency_value': 6,
                    'start_date': date.today(),
                    'end_date': None
                }
            ]
            
            for prog_data in programs:
                program = Program(
                    name=prog_data['name'],
                    description=prog_data['description'],
                    frequency_type=prog_data['frequency_type'],
                    frequency_value=prog_data['frequency_value'],
                    frequency_days=prog_data.get('frequency_days'),
                    start_date=prog_data['start_date'],
                    end_date=prog_data['end_date']
                )
                db.session.add(program)
            
            db.session.commit()
            print("✓ Programs created")
        
        print("✓ Database initialization complete")
        
except Exception as e:
    print(f"Database initialization error: {e}")

# Export the app for Vercel (@vercel/python handler expects 'app')
__all__ = ['app']
