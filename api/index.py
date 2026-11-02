"""Vercel entry point: production startup creates schema, never demo records."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['FLASK_ENV'] = 'production'

from app import app, db


def initialize_database():
    """Add missing tables only; catalogue/account/demo seeding is explicit work."""
    try:
        with app.app_context():
            db.create_all()
    except Exception:
        app.logger.error('Production schema initialization failed')
        raise RuntimeError('Production schema initialization failed') from None
    app.logger.info('Production schema verified; no seed routines executed')
    return True


initialize_database()
__all__ = ['app']
