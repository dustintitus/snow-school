import os
import unittest
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['SECRET_KEY']='test-key'
os.environ['FLASK_ENV']='production'
from app import app
from models import db, User, Team, Program, AppSetting
from review_demo import seed_review_demo

class ReviewDemoTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, CSRF_ENABLED=False)
        self.ctx=app.app_context();self.ctx.push();db.drop_all();db.create_all()
    def tearDown(self):
        db.session.remove();self.ctx.pop()
    def test_explicit_enable_and_idempotent_without_password_reset(self):
        self.assertFalse(seed_review_demo(None))
        self.assertTrue(seed_review_demo('fictional-test-password-123456789'))
        coach=User.query.filter_by(username='apple_review_coach').one()
        original=coach.password_hash
        self.assertFalse(seed_review_demo('different-test-password-123456789'))
        self.assertEqual(coach.password_hash,original)
        self.assertLessEqual(len(Program.query.one().frequency_days), Program.frequency_days.type.length)
        self.assertEqual(User.query.count(),5)
        self.assertEqual(len(coach.managed_teams),1)
        self.assertTrue(all(x.instructor_id==coach.id for x in coach.managed_teams[0].students))
    def test_existing_name_is_not_repurposed(self):
        db.session.add(User(username='apple_review_coach',email='existing@example.com',full_name='Existing',user_type='parent',password_hash='existing'));db.session.commit()
        with self.assertRaises(ValueError):seed_review_demo('fictional-test-password-123456789')
        db.session.rollback()
        self.assertEqual(User.query.one().user_type,'parent')
        self.assertEqual(Program.query.count(),0)
    def test_reviewer_cannot_open_unassigned_records(self):
        seed_review_demo('fictional-test-password-123456789')
        coach=User.query.filter_by(username='apple_review_coach').one()
        other=User(username='other',email='other@example.com',full_name='Private',user_type='student',password_hash='!');db.session.add(other);db.session.commit()
        client=app.test_client()
        with client.session_transaction() as s:s['_user_id']=str(coach.id);s['_fresh']=True
        self.assertEqual(client.get('/admin/people').status_code,403)
        self.assertIn(client.get(f'/learning/participants/{other.id}').status_code,[403,404])
