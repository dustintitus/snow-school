"""Connection authorization and minimal-data export regression tests."""
import json
import unittest
from datetime import date, datetime
from unittest.mock import patch
import test_workflows
from app import app
from models import db, AppSetting, User
from staff_portal import StaffProfile, StaffAvailability
from availability_sync import SETTING_KEY, WORKBOOK_ID


class AvailabilitySyncTests(unittest.TestCase):
    login_as = test_workflows.WorkflowTestCase.login_as

    def setUp(self):
        test_workflows.WorkflowTestCase.setUp(self)
        with app.app_context():
            admin=User(username='admin',email='admin@test.invalid',password_hash='unused',full_name='Admin',user_type='admin')
            db.session.add(admin);db.session.flush();self.admin_id=admin.id
            db.session.add(AppSetting(key=SETTING_KEY,value=json.dumps(dict(enabled=True,audience='123-abc.apps.googleusercontent.com',email='sync@test.invalid'))))
            db.session.add_all([
                StaffProfile(user_id=self.instructor_id,active=True,availability_submitted_at=datetime(2026,10,26,12)),
                StaffProfile(user_id=self.other_id,active=True),
                StaffAvailability(user_id=self.instructor_id,day=date(2026,12,1),morning=True,afternoon=False,evening=True),
                StaffAvailability(user_id=self.instructor_id,day=date(2026,11,30),morning=True),
                StaffAvailability(user_id=self.other_id,day=date(2026,12,1),morning=True)])
            db.session.commit()

    def get_feed(self,token='a.b.c',workbook=WORKBOOK_ID):
        return self.client.get('/api/integrations/availability',query_string={'workbook':workbook},headers={'Authorization':'Bearer '+token})

    def test_disabled_and_missing_credentials_fail_closed(self):
        self.assertEqual(self.get_feed(token='').status_code,401)
        with app.app_context():
            db.session.delete(db.session.get(AppSetting,SETTING_KEY));db.session.commit()
        self.assertEqual(self.get_feed().status_code,503)

    @patch('availability_sync.verify_google_identity',return_value={'email':'sync@test.invalid','email_verified':True})
    def test_feed_only_exports_reviewed_season_and_minimal_fields(self,verify):
        result=self.get_feed()
        self.assertEqual(result.status_code,200)
        verify.assert_called_once_with('a.b.c','123-abc.apps.googleusercontent.com')
        rows=result.json['rows'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['date'],'2026-12-01')
        self.assertTrue(rows[0]['morning']);self.assertFalse(rows[0]['afternoon'])
        self.assertEqual(set(rows[0]),{'user_id','name','email','date','weekday','active','morning','afternoon','evening','submitted_at'})
        self.assertEqual(result.headers['Cache-Control'],'private, no-store')
        self.assertEqual(self.get_feed(workbook='other').status_code,403)

    @patch('availability_sync.verify_google_identity',return_value={'email':'wrong@test.invalid','email_verified':True})
    def test_other_google_account_is_denied(self,verify):
        self.assertEqual(self.get_feed().status_code,403)

    @patch('availability_sync.verify_google_identity',return_value={'email':'sync@test.invalid','email_verified':True})
    def test_reviewed_demo_instructors_are_excluded(self,verify):
        with app.app_context():
            for username in ('instructor1','apple_review_coach',*(f'demo_coach_{n}' for n in range(1,6))):
                user=User(username=username,email=username+'@demo.invalid',password_hash='unused',full_name='Jordan Parker',user_type='instructor')
                db.session.add(user);db.session.flush()
                db.session.add(StaffProfile(user_id=user.id,active=True,availability_submitted_at=datetime(2026,10,26,12)))
                db.session.add(StaffAvailability(user_id=user.id,day=date(2026,12,1),morning=True))
            db.session.commit()
        self.assertEqual([r['user_id'] for r in self.get_feed().json['rows']],[self.instructor_id])

    @patch('availability_sync.verify_google_identity',return_value={'email':'sync@test.invalid','email_verified':False})
    def test_unverified_google_email_is_denied(self,verify):
        self.assertEqual(self.get_feed().status_code,403)

    @patch('availability_sync.verify_google_identity',side_effect=ValueError('invalid'))
    def test_invalid_signature_expiry_or_audience_is_denied(self,verify):
        self.assertEqual(self.get_feed().status_code,401)

    def test_only_admin_can_configure_and_csrf_is_required(self):
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get('/admin/integrations/availability').status_code,403)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.get('/admin/integrations/availability').status_code,200)
        app.config['CSRF_ENABLED']=True
        try:
            response=self.client.post('/admin/integrations/availability',data=dict(audience='123-abc.apps.googleusercontent.com',email='sync@test.invalid',enabled='on'))
            self.assertEqual(response.status_code,400)
        finally:app.config['CSRF_ENABLED']=False

    def test_admin_configures_public_identity_only(self):
        self.login_as(self.admin_id)
        response=self.client.post('/admin/integrations/availability',data=dict(audience='456-defg.apps.googleusercontent.com',email='SYNC@test.invalid',enabled='on'))
        self.assertEqual(response.status_code,302)
        with app.app_context():
            settings=json.loads(db.session.get(AppSetting,SETTING_KEY).value)
            self.assertEqual(settings['email'],'sync@test.invalid')
            self.assertNotIn('token',settings)

    @patch.dict('os.environ', {'GOOGLE_AVAILABILITY_AUDIENCE':'hosting-client.apps.googleusercontent.com',
                              'GOOGLE_AVAILABILITY_EMAIL':'SYNC@test.invalid',
                              'GOOGLE_AVAILABILITY_ENABLED':'true'})
    @patch('availability_sync.verify_google_identity',return_value={'email':'sync@test.invalid','email_verified':True})
    def test_hosting_config_bootstraps_only_when_no_admin_setting(self,verify):
        with app.app_context():
            db.session.delete(db.session.get(AppSetting,SETTING_KEY));db.session.commit()
        self.assertEqual(self.get_feed().status_code,200)
        verify.assert_called_once_with('a.b.c','hosting-client.apps.googleusercontent.com')
        with app.app_context():
            db.session.add(AppSetting(key=SETTING_KEY,value=json.dumps(dict(enabled=False))));db.session.commit()
        self.assertEqual(self.get_feed().status_code,503)

if __name__=='__main__':unittest.main()
