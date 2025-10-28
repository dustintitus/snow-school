"""
Vercel serverless function entry point
"""
import sys
from pathlib import Path
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set FLASK_ENV before importing app
if 'FLASK_ENV' not in os.environ:
    os.environ['FLASK_ENV'] = 'production'

# Import Flask app - Vercel expects 'app' variable
from app import app

# Vercel's Python runtime expects 'app' to be the Flask application
# This will be detected automatically by Vercel's @vercel/python handler
