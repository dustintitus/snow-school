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
from app import app, db, seed_demo_accounts, seed_demo_operations, seed_horseshoe_catalogue, seed_step_rip_curriculum

# Initialize database on cold start (production-safe)
def initialize_database():
    """Create missing tables without mutating existing production records."""
    try:
        with app.app_context():
            # Create all tables
            db.create_all()
            seed_horseshoe_catalogue()
            seed_step_rip_curriculum()
            seed_demo_operations()
            seed_demo_accounts(
                os.environ.get('DEMO_ACCOUNT_SEED_VERSION'),
                {
                    'admin': os.environ.get('DEMO_ADMIN_PASSWORD'),
                    'instructor1': os.environ.get('DEMO_INSTRUCTOR_PASSWORD'),
                    'student1': os.environ.get('DEMO_STUDENT_PASSWORD'),
                },
            )
            print("✓ Database tables created/verified without altering records")
            return True
            
    except Exception as e:
        print(f"Database initialization error: {e}")
        return False

# Initialize database
initialize_database()

# Export the app for Vercel (@vercel/python handler expects 'app')
__all__ = ['app']
