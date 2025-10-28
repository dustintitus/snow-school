"""
Vercel serverless function entry point
This file is required by Vercel to properly handle Flask applications
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app

# Export the app for Vercel
# Vercel will automatically handle WSGI
handler = app

