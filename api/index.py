"""
Vercel serverless function entry point in api/ directory
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment
os.environ['FLASK_ENV'] = 'production'

# Import the Flask app
from app import app, db, User, Program
from werkzeug.security import generate_password_hash
from datetime import date

# Initialize database on cold start (production-safe)
def initialize_database():
    """Initialize database with tables and sample data"""
    try:
        with app.app_context():
            # Create all tables
            db.create_all()
            print("✓ Database tables created/verified")
            
            # Always create users (in-memory database starts fresh each time)
            print("Creating users...")
            users = [
                User(
                    username='admin',
                    email='admin@snowschool.com',
                    password_hash=generate_password_hash('password123', method='pbkdf2:sha256'),
                    user_type='admin',
                    full_name='Administrator'
                ),
                User(
                    username='instructor1',
                    email='instructor@snowschool.com',
                    password_hash=generate_password_hash('password123', method='pbkdf2:sha256'),
                    user_type='instructor',
                    full_name='John Instructor'
                ),
                User(
                    username='student1',
                    email='student@snowschool.com',
                    password_hash=generate_password_hash('password123', method='pbkdf2:sha256'),
                    user_type='student',
                    full_name='Jane Student'
                )
            ]
            
            # Clear existing users first (in case of reinitialization)
            User.query.delete()
            Program.query.delete()
            
            for user in users:
                db.session.add(user)
            
            # Create programs
            print("Creating programs...")
            programs = [
                Program(
                    name='Snowflakes',
                    description='Beginner program for young skiers',
                    frequency_type='consecutive',
                    frequency_value=8,
                    start_date=date.today(),
                    end_date=None
                ),
                Program(
                    name='High Flyers',
                    description='Advanced skiing program',
                    frequency_type='weekly',
                    frequency_value=6,
                    frequency_days='saturday',
                    start_date=date.today(),
                    end_date=None
                ),
                Program(
                    name='Trail Blazers',
                    description='Intermediate snowboarding',
                    frequency_type='consecutive',
                    frequency_value=8,
                    start_date=date.today(),
                    end_date=None
                ),
                Program(
                    name='LIT',
                    description='Leadership in Training program',
                    frequency_type='custom',
                    frequency_value=12,
                    frequency_days='monday,wednesday,friday',
                    start_date=date.today(),
                    end_date=None
                ),
                Program(
                    name='Adult',
                    description='Adult skiing and snowboarding',
                    frequency_type='weekly',
                    frequency_value=8,
                    frequency_days='sunday',
                    start_date=date.today(),
                    end_date=None
                ),
                Program(
                    name='Terrain Park',
                    description='Terrain park and freestyle program',
                    frequency_type='consecutive',
                    frequency_value=6,
                    start_date=date.today(),
                    end_date=None
                )
            ]
            
            for program in programs:
                db.session.add(program)
            
            db.session.commit()
            print("✓ Users and programs created")
            print("✓ Database initialization complete")
            return True
            
    except Exception as e:
        print(f"Database initialization error: {e}")
        return False

# Initialize database
initialize_database()

# Export the app for Vercel (@vercel/python handler expects 'app')
__all__ = ['app']
