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
from app import app

# Export the app for Vercel (@vercel/python handler expects 'app')
__all__ = ['app']
