"""
Vercel serverless function entry point for Flask
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the Flask app
from app import app

def handler(req, res):
    """
    Vercel handler function
    req: Vercel request object
    res: Vercel response object
    """
    # Convert Vercel request to WSGI environ
    def start_response(status, headers):
        # Set status
        res.status(status)
        # Set headers
        for header in headers:
            res.setHeader(header[0], header[1])
        return res.write
    
    # Call Flask app with WSGI
    app(req.environ, start_response)
    
    return res

# Export
__all__ = ['handler']

