"""Oct 23 acceptance and privacy regression tests against isolated SQLite data."""
from datetime import date, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import test_workflows
from app import app, MEDIA_CONSENT_VERSION
from models import db, User, Team, Program, ParentStudent, MediaConsent, ParticipantMedia
from learning_models import SchoolGroup, ParticipantReport, PrivateLesson
from staff_portal import (StaffProfile, StaffDocument, StaffAvailability, OnboardingRequirement,
    OnboardingAcknowledgment, ParticipantDetails, PrivateParticipant, StaffInvitation,
    CompletionApproval, profile_for, SEASON_START, SEASON_END, send_invitation)
from notifications import create_message, process_outbox
from notification_models import PushDevice, PushDelivery, NotificationPreference
from learning import today

class KarenReviewTests(unittest.TestCase):
    login_as = test_workflows.WorkflowTestCase.login_as

    def setUp(self):
        test_workflows.WorkflowTestCase.setUp(self)
        with app.app_context():
            admin = User(username='admin',email='admin@test.invalid',password_hash='unused',full_name='School Admin',user_type='admin')
            parent = User(username='parent',email='parent@test.invalid',password_hash='unused',full_name='Parent One',user_type='parent')
            outsider = User(username='unlinked',email='unlinked@test.invalid',password_hash='unused',full_name='Unlinked Parent',user_type='parent')
            db.session.add_all([admin,parent,outsider]);db.session.flush()
            self.admin_id,self.parent_id,self.outsider_id=admin.id,parent.id,outsider.id
            db.session.add(ParentStudent(parent_id=parent.id,student_id=self.student_id))
            db.session.add(MediaConsent(parent_id=parent.id,student_id=self.student_id,version=MEDIA_CONSENT_VERSION,status='accepted'))
            db.session.commit()
        self.login_as(self.instructor_id)

    def support_data(self, share=True):
        self.login_as(self.admin_id)
        response=self.client.post(f'/admin/participants/{self.student_id}/support',data=dict(birthdate='2018-01-16',special_needs='on',instructor_notes='Needs quiet instructions',contact_name='Guardian',phone='555-123-4567',share_contact='on' if share else ''))
        self.assertEqual(response.status_code,302)
        self.login_as(self.instructor_id)

    def test_classes_include_future_groups_and_privates_without_other_coach(self):
        with app.app_context():
            program=Program(name='Future program',start_date=date(2027,1,1));db.session.add(program);db.session.flush()
            group=Team(name='Future School Group',program_id=program.id,instructor_id=self.instructor_id);db.session.add(group);db.session.flush()
            db.session.add(SchoolGroup(team_id=group.id,school_name='School One',season='2026-2027',created_by=self.admin_id))
            db.session.add(PrivateLesson(instructor_id=self.instructor_id,participant='Future private participant',starts_at=datetime(2027,1,10,10),duration_minutes=60,meeting_point='Lodge',notes='Private coaching',created_by=self.admin_id))
            db.session.add(PrivateLesson(instructor_id=self.other_id,participant='Other coach only',starts_at=datetime(2027,1,10,10),duration_minutes=60,meeting_point='Lodge',notes='Private',created_by=self.admin_id));db.session.commit()
        response=self.client.get('/coach/classes')
        self.assertEqual(response.status_code,200)
        for text in [b'Saturday Snowflakes',b'Future School Group',b'Future private participant',b'Classes',b'Privates',b'School Groups']:self.assertIn(text,response.data)
        self.assertNotIn(b'Other coach only',response.data)

    def test_contact_visibility_requires_admin_flag_and_current_assignment(self):
        self.support_data(False)
        response=self.client.get(f'/teams/{self.team_id}/session')
        self.assertIn(b'Needs quiet instructions',response.data);self.assertNotIn(b'555-123-4567',response.data)
        self.support_data(True)
        self.assertIn(b'555-123-4567',self.client.get(f'/teams/{self.team_id}/session').data)
        self.assertNotIn(b'rider@example.com',self.client.get('/dashboard').data)
        self.assertNotIn(b'rider@example.com',self.client.get(f'/admin/view_student_evaluations/{self.student_id}').data)
        self.login_as(self.other_id)
        self.assertEqual(self.client.get(f'/admin/participants/{self.student_id}/support').status_code,403)
        self.assertNotIn(b'555-123-4567',self.client.get('/coach/classes').data)
        self.login_as(self.admin_id)
        self.assertIn(b'rider@example.com',self.client.get(f'/admin/view_student_evaluations/{self.student_id}').data)

    def test_private_support_and_capture_access_expires_after_lesson_day(self):
        self.support_data(True)
        with app.app_context():
            lesson=PrivateLesson(instructor_id=self.other_id,participant='Riley',starts_at=datetime.combine(today(),datetime.min.time())+timedelta(hours=10),duration_minutes=60,meeting_point='Lodge',notes='Quiet lesson',created_by=self.admin_id)
            db.session.add(lesson);db.session.flush();db.session.add(PrivateParticipant(lesson_id=lesson.id,student_id=self.student_id));db.session.commit()
        self.login_as(self.other_id)
        self.assertIn(b'555-123-4567',self.client.get('/coach').data)
        with patch('staff_portal.today',return_value=today()+timedelta(days=1)):
            self.assertNotIn(b'555-123-4567',self.client.get('/coach/classes').data)

    def test_full_season_and_replacement_save(self):
        response=self.client.get('/coach/availability');self.assertEqual(response.status_code,200)
        self.assertEqual(response.data.count(b'name="slots"'),360)
        self.assertEqual((SEASON_END-SEASON_START).days+1,120)
        response=self.client.post('/coach/availability',data={'reviewed':'on','slots':['2026-12-01_morning','2027-03-30_evening']});self.assertEqual(response.status_code,302)
        with app.app_context():
            self.assertEqual(StaffAvailability.query.count(),120)
            self.assertTrue(StaffAvailability.query.filter_by(day=SEASON_START).one().morning)
            self.assertTrue(profile_for(self.instructor_id).availability_submitted_at)
        self.assertEqual(self.client.post('/coach/availability',data={'reviewed':'on','slots':['2027-03-31_morning']}).status_code,400)
        self.assertEqual(self.client.post('/coach/availability',data={'reviewed':'on'}).status_code,302)
        with app.app_context():self.assertFalse(any(r.morning or r.afternoon or r.evening for r in StaffAvailability.query.all()))
        self.login_as(self.other_id)
        self.assertEqual(self.client.get(f'/staff/{self.instructor_id}/availability').status_code,403)

    def test_admin_availability_and_staff_pages_render(self):
        self.login_as(self.admin_id)
        for path in ['/admin/staff','/admin/availability','/admin/availability?date=2027-01-10',f'/staff/{self.instructor_id}/profile',f'/staff/{self.instructor_id}/onboarding']:
            self.assertEqual(self.client.get(path).status_code,200,path)
        self.assertEqual(self.client.get('/admin/availability?date=garbage').status_code,400)

    def test_sop_training_revision_and_external_completion(self):
        self.login_as(self.admin_id)
        payload=dict(title='Lift safety SOP',content='Approved school safety instructions',active='on',requires_training='on',resource_url='https://example.com/lift-safety')
        self.assertEqual(self.client.post('/admin/staff',data=payload).status_code,302)
        with app.app_context(): req_id=OnboardingRequirement.query.one().id
        self.login_as(self.instructor_id)
        ack=dict(requirement_id=req_id,revision='1',signed_name='Coach North',acknowledge='on')
        self.assertEqual(self.client.post('/coach/onboarding',data=ack).status_code,400)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.post(f'/staff/{self.instructor_id}/onboarding',data=dict(requirement_id=req_id,revision='1',action='clear_training')).status_code,302)
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.post('/coach/onboarding',data=ack).status_code,302)
        self.assertEqual(self.client.post('/coach/onboarding',data=ack).status_code,302)
        self.login_as(self.admin_id)
        payload.update(requirement_id=req_id,content='Updated approved instructions')
        self.client.post('/admin/staff',data=payload)
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.post('/coach/onboarding',data=ack).status_code,409)
        with app.app_context():self.assertEqual(OnboardingAcknowledgment.query.count(),1)
        self.assertIn(b'Updated approved instructions',self.client.get('/coach/onboarding').data)

    def test_first_login_opens_onboarding(self):
        self.client.post('/logout')
        response=self.client.post('/login',data=dict(username='coach',password='password123',next='https://example.com'))
        self.assertIn('/coach/onboarding',response.location)
        self.assertEqual(self.client.get(response.location).status_code,200)

    @patch('staff_portal.BlobClient')
    def test_staff_documents_are_private_reviewed_and_expire(self,blob):
        blob.return_value.put.return_value=SimpleNamespace(url='https://private.invalid/cert')
        self.assertEqual(self.client.post('/coach/profile',data=dict(action='upload',kind='CSIA',label='Level 2',document=(BytesIO(b'%PDF-test'),'certificate.pdf','application/pdf'))).status_code,302)
        with app.app_context():doc_id=StaffDocument.query.one().id
        self.login_as(self.other_id)
        self.assertEqual(self.client.get(f'/staff/documents/{doc_id}').status_code,403)
        self.assertEqual(self.client.post(f'/staff/{self.instructor_id}/profile',data=dict(action='review',document_id=doc_id)).status_code,403)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.post(f'/staff/{self.instructor_id}/profile',data=dict(action='review',document_id=doc_id)).status_code,302)
        with app.app_context():self.assertEqual(StaffDocument.query.one().reviewed_by,self.admin_id)
        blob.return_value.get.return_value=SimpleNamespace(status_code=200,content=b'%PDF-test')
        self.assertEqual(self.client.get(f'/staff/documents/{doc_id}').headers['Cache-Control'],'private, no-store')

    def test_inactive_account_denies_existing_session_and_new_login(self):
        with app.app_context():profile_for(self.instructor_id).active=False;db.session.commit()
        self.assertEqual(self.client.get('/coach').status_code,403)
        self.client.post('/logout')
        response=self.client.post('/login',data=dict(username='coach',password='password123'))
        self.assertIn(b'inactive',response.data)

    @patch.dict('os.environ',{'SMTP_HOST':'smtp.invalid','SMTP_FROM':'school@example.com'})
    @patch('staff_portal.smtplib.SMTP')
    def test_welcome_email_single_use_setup(self,smtp):
        with app.app_context():
            status=send_invitation(db.session.get(User,self.instructor_id));self.assertEqual(status,'accepted')
        message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertNotIn('password123',message.get_content())
        token=message.get_content().split('/welcome/')[1].split()[0]
        self.client.post('/logout')
        self.assertEqual(self.client.get('/welcome/'+token).status_code,200)
        self.assertEqual(self.client.post('/welcome/'+token,data=dict(password='new-password-123',confirm_password='new-password-123')).status_code,302)
        self.assertEqual(self.client.get('/welcome/'+token).status_code,404)
        self.assertEqual(self.client.post('/login',data=dict(username='coach',password='new-password-123')).status_code,302)

    @patch.dict('os.environ',{'SMTP_HOST':'','SMTP_FROM':''})
    def test_missing_mail_configuration_is_visible(self):
        with app.app_context():self.assertEqual(send_invitation(db.session.get(User,self.instructor_id)),'not_configured')

    @patch('app.BlobClient')
    def test_group_video_creates_separate_participant_records_and_checks_all_consents(self,blob):
        blob.return_value.put.return_value=SimpleNamespace(url='https://private.invalid/video',pathname='private/video')
        with app.app_context():
            second=User(username='second',email='second@test.invalid',password_hash='unused',full_name='Second Child',user_type='student',team_id=self.team_id)
            db.session.add(second);db.session.flush();second_id=second.id
            db.session.add(ParentStudent(parent_id=self.parent_id,student_id=second.id));db.session.commit()
        def post():return self.client.post(f'/participants/{self.student_id}/media',data={'media':(BytesIO(b'\x1a\x45\xdf\xa3test-video'),'capture.webm','video/webm'),'student_ids':[str(self.student_id),str(second_id)]})
        self.assertEqual(post().status_code,403);blob.return_value.put.assert_not_called()
        with app.app_context():db.session.add(MediaConsent(parent_id=self.parent_id,student_id=second_id,version=MEDIA_CONSENT_VERSION,status='accepted'));db.session.commit()
        response=post();self.assertEqual(response.status_code,200);self.assertEqual(response.json['participant_count'],2)
        with app.app_context():self.assertEqual(ParticipantMedia.query.count(),2)
        self.login_as(self.outsider_id)
        self.assertEqual(self.client.get('/participant-media/'+str(response.json['media_id'])).status_code,403)
        self.login_as(self.parent_id)
        blob.return_value.get.return_value=SimpleNamespace(status_code=200,content=b'\x1a\x45\xdf\xa3test-video')
        self.assertEqual(self.client.get('/participant-media/'+str(response.json['media_id'])).mimetype,'video/webm')
        self.assertIn(b'<video',self.client.get(f'/parent/children/{self.student_id}').data)

    def test_family_lookup_and_certificate_require_link_issued_report_and_completion(self):
        self.support_data()
        with app.app_context():
            report=ParticipantReport(student_id=self.student_id,season='2026-2027',card_key='ski-1',snapshot={'name':'Ski Level 1','participant':'Riley Rider','class':'Snowflakes','rows':[]},comments='Well done',next_steps='Practise turns',author_id=self.instructor_id)
            db.session.add(report);db.session.commit();report_id=report.id
        path=f'/participants/{self.student_id}/certificate/{report_id}'
        self.login_as(self.parent_id)
        self.assertEqual(self.client.get('/parent/lookup').status_code,200)
        response=self.client.post('/parent/lookup',data=dict(participant_name=' riley rider ',birthdate='2018-01-16'))
        self.assertIn('/parent/children/',response.location)
        self.assertEqual(self.client.get(path).status_code,404)
        with app.app_context():
            report=db.session.get(ParticipantReport,report_id);report.issued_at=datetime.utcnow();report.issued_by=self.admin_id;db.session.commit()
        self.assertEqual(self.client.get(path).status_code,404)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.post(f'/reports/{report_id}/completion',data={'completed_on':today().isoformat()}).status_code,302)
        self.login_as(self.parent_id)
        response=self.client.get(path);self.assertEqual(response.status_code,200);self.assertTrue(response.data.startswith(b'%PDF-'))
        self.assertIn('attachment',response.headers['Content-Disposition'])
        self.login_as(self.outsider_id)
        response=self.client.post('/parent/lookup',data=dict(participant_name='Riley Rider',birthdate='2018-01-16'))
        self.assertIn(b'could not match',response.data)
        self.assertEqual(self.client.get(path).status_code,403)

    @patch('notifications.expo_request',return_value={'data':[{'status':'ok','id':'push-ticket'}]})
    def test_push_reaches_active_devices_without_daily_app_open(self,send):
        with app.app_context():
            db.session.add(NotificationPreference(user_id=self.instructor_id,push_enabled=True,school_enabled=True))
            db.session.add(PushDevice(user_id=self.instructor_id,token='ExpoPushToken[active-device1234]',session_key='session',active=True,updated_at=datetime.utcnow()-timedelta(days=7)))
            db.session.flush();create_message('school','School update','Open your inbox',[self.instructor_id],'test-old-device',self.admin_id);db.session.commit()
            process_outbox();self.assertEqual(PushDelivery.query.one().status,'ticket')
            self.assertEqual(send.call_args.args[1][0]['data']['path'],'/notifications')

    @patch('staff_portal.send_invitation',return_value='not_configured')
    def test_new_instructor_queues_welcome_and_displays_mail_failure(self,send):
        self.login_as(self.admin_id)
        response=self.client.post('/register',data=dict(username='new-coach',email='new-coach@test.invalid',password='initial-test-password',full_name='New Coach',user_type='instructor'),follow_redirects=True)
        self.assertEqual(response.status_code,200)
        self.assertIn(b'welcome email not sent',response.data)
        send.assert_called_once()
        with app.app_context(): self.assertEqual(User.query.filter_by(username='new-coach').one().user_type,'instructor')

    def test_availability_months_are_in_season_order(self):
        page=self.client.get('/coach/availability').data
        self.assertLess(page.index(b'December 2026'),page.index(b'January 2027'))
        self.assertLess(page.index(b'January 2027'),page.index(b'March 2027'))

    def test_sop_history_preserves_previously_signed_text(self):
        from staff_portal import RequirementRevision
        self.login_as(self.admin_id)
        self.client.post('/admin/staff',data=dict(title='SOP',content='Original instructions',active='on'))
        with app.app_context(): req_id=OnboardingRequirement.query.one().id
        self.client.post('/admin/staff',data=dict(requirement_id=req_id,title='SOP',content='New instructions',active='on'))
        with app.app_context(): self.assertEqual([r.content for r in RequirementRevision.query.order_by(RequirementRevision.revision).all()],['Original instructions','New instructions'])
        response=self.client.get(f'/admin/requirements/{req_id}/history')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Original instructions',response.data)
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get(f'/admin/requirements/{req_id}/history').status_code,403)

    def test_csrf_is_required_on_new_workflows(self):
        app.config['CSRF_ENABLED']=True
        try:
            self.assertEqual(self.client.post('/coach/availability',data={'reviewed':'on'}).status_code,400)
            self.assertEqual(self.client.post('/coach/onboarding',data={}).status_code,400)
        finally:app.config['CSRF_ENABLED']=False

if __name__=='__main__':unittest.main()
