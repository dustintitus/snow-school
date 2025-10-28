"""
Vercel serverless function entry point
This file is required by Vercel to properly handle Flask applications
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set production environment
os.environ['FLASK_ENV'] = 'production'

from app import app, db

# Ensure tables are created when the function starts
try:
    with app.app_context():
        db.create_all()
except Exception as e:
    print(f"Warning: Could not create database tables: {e}")

# Export the app for Vercel
# Vercel will automatically handle WSGI
handler = app

