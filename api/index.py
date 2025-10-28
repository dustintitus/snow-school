"""
Vercel serverless function entry point for Flask
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from werkzeug.wrappers import Request, Response
from werkzeug.middleware.proxy_fix import ProxyFix

# Import the Flask app
from app import app as flask_app

# Add proxy fix for Vercel
app = ProxyFix(flask_app, x_for=1, x_proto=1, x_host=1, x_port=1)

def handler(request):
    """Vercel serverless handler"""
    return Response.from_app(app, request.environ, buffered=True)

# Export for Vercel
__all__ = ['handler']

