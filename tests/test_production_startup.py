"""Production entrypoint uses the real SQLite schema and synthetic records."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from contextlib import ExitStack

import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['FLASK_ENV'] = 'production'
from app import app
from models import db, User, AppSetting, ProgramSupervisor


class ProductionStartupTests(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def load_entrypoint(self):
        spec = importlib.util.spec_from_file_location('schema_only_entrypoint', Path(__file__).resolve().parents[1] / 'api' / 'index.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_startup_creates_missing_schema_and_preserves_existing_records_without_seeds(self):
        user = User(username='existing',email='existing@example.test',full_name='Existing Coach',user_type='instructor',password_hash='synthetic-original-hash')
        db.session.add_all([user, AppSetting(key='existing-marker',value='unchanged')])
        db.session.commit()
        user_id = user.id
        ProgramSupervisor.__table__.drop(bind=db.engine)
        seed_names = ('seed_horseshoe_catalogue','seed_step_rip_curriculum','seed_demo_operations','seed_horseshoe_showcase','seed_demo_accounts','seed_demo_parent')
        with ExitStack() as stack:
            seeds = [stack.enter_context(patch('app.'+name,side_effect=AssertionError('Production startup must not seed'))) for name in seed_names]
            review = stack.enter_context(patch('review_demo.seed_review_demo',side_effect=AssertionError('Production startup must not seed')))
            self.load_entrypoint()
            for seed in [*seeds,review]:seed.assert_not_called()
        self.assertEqual(ProgramSupervisor.query.count(),0)
        self.assertEqual(User.query.count(),1)
        self.assertEqual(db.session.get(User,user_id).password_hash,'synthetic-original-hash')
        self.assertEqual(AppSetting.query.count(),1)
        self.assertEqual(db.session.get(AppSetting,'existing-marker').value,'unchanged')

    def test_schema_failure_prevents_startup(self):
        with patch.object(db,'create_all',side_effect=RuntimeError('synthetic database failure')):
            with self.assertRaisesRegex(RuntimeError,'Production schema initialization failed'):
                self.load_entrypoint()
