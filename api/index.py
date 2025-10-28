"""
Vercel serverless function entry point
"""
from app import app

def handler(req, res):
    # Simple WSGI handler for Vercel
    return app(req, res)

# Export for Vercel
app_handler = app

