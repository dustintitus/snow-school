import unittest
from datetime import timedelta
from unittest.mock import patch
import test_workflows
from app import app
from models import db, User, Team, Program, Enrollment, Attendance
from operations import ClassCoverage, RosterMove, save_setting
from learning import today
from learning_models import PrivateLesson
from notification_models import NotificationRecipient

class MeetingOperationsTests(unittest.TestCase):
    login_as = test_workflows.WorkflowTestCase.login_as
    def setUp(self):
        test_workflows.WorkflowTestCase.setUp(self)
        with app.app_context():
            admin = User(username='admin',email='admin@test.invalid',password_hash='unused',full_name='Administrator',user_type='admin')
            db.session.add(admin); db.session.commit(); self.admin_id=admin.id
        self.login_as(self.admin_id)
    def cover(self, **extra):
        data=dict(action='coverage',team_id=self.team_id,instructor_id=self.other_id,session_date=today().isoformat(),reason='Regular coach away')
        data.update(extra)
        return self.client.post('/operations/',data=data)
    def test_coverage_preserves_owner_and_expires(self):
        self.assertEqual(self.cover().status_code,302)
        with app.app_context():
            self.assertEqual(db.session.get(Team,self.team_id).instructor_id,self.instructor_id)
            self.assertEqual(ClassCoverage.query.count(),1)
            self.assertEqual(NotificationRecipient.query.count(),2)
        self.login_as(self.other_id)
        self.assertIn(b'Saturday Snowflakes',self.client.get('/coach').data)
        self.assertEqual(self.client.get(f'/teams/{self.team_id}/session').status_code,200)
        self.assertEqual(self.client.post(f'/attendance/{self.team_id}/record',data={'session_date':today().isoformat(),f'attended_{self.student_id}':'on'}).status_code,302)
        with app.app_context(): self.assertEqual(Attendance.query.count(),1)
        with patch('learning.today',return_value=today()+timedelta(days=1)):
            self.assertEqual(self.client.get(f'/learning/participants/{self.student_id}').status_code,403)
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get(f'/learning/participants/{self.student_id}').status_code,403)
    def test_qualification_override_and_reassignment(self):
        with app.app_context():
            team=db.session.get(Team,self.team_id)
            save_setting(f'program-operations:{team.program_id}',{'minimum_level':1}); db.session.commit()
        self.assertEqual(self.cover().status_code,400)
        self.assertEqual(self.cover(override_reason='Approved by supervisor for this class').status_code,302)
        self.assertEqual(self.cover(instructor_id=self.instructor_id,override_reason='Returning regular coach').status_code,302)
        with app.app_context(): self.assertEqual(ClassCoverage.query.count(),1)
    def test_move_cross_program_preserves_attendance_and_registration_history(self):
        with app.app_context():
            old=db.session.get(Team,self.team_id)
            db.session.add(Enrollment(student_id=self.student_id,team_id=old.id,program_id=old.program_id,season='2026-2027'))
            program=Program(name='High Flyers');db.session.add(program);db.session.flush()
            team=Team(name='High Flyers Beginners',program_id=program.id,instructor_id=self.other_id);db.session.add(team);db.session.commit(); destination=team.id
        self.assertEqual(self.client.post('/operations/',data=dict(action='move',student_id=self.student_id,team_id=destination,reason='Progression')).status_code,302)
        with app.app_context():
            self.assertEqual(db.session.get(User,self.student_id).team_id,destination)
            self.assertEqual(RosterMove.query.count(),1)
            self.assertEqual(sorted(row.status for row in Enrollment.query.all()),['registered','transferred'])
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.post('/operations/',data=dict(action='move')).status_code,403)
    def test_private_visible_only_on_assigned_coach_day_and_notifies(self):
        starts=today().isoformat()+'T10:00'
        self.assertEqual(self.client.post('/learning/privates/new',data=dict(instructor_id=self.other_id,participant='Customer One & Customer Two',starts_at=starts,duration_minutes=60,meeting_point='Base lodge',notes='Semi-private ski',lesson_type='semi-private')).status_code,302)
        self.login_as(self.other_id)
        self.assertIn(b'Customer One &amp; Customer Two',self.client.get('/coach').data)
        self.assertNotIn(b'Customer One',self.client.get('/coach?date='+ (today()+timedelta(days=1)).isoformat()).data)
        self.login_as(self.instructor_id)
        self.assertNotIn(b'Customer One',self.client.get('/coach').data)
        with app.app_context(): self.assertEqual(NotificationRecipient.query.count(),1)
    def test_cancel_csrf_native_portal_and_date_boundary(self):
        self.assertEqual(self.cover().status_code,302)
        self.login_as(self.other_id)
        headers={'User-Agent':'SnowSchoolCoach/1.0'}
        self.assertIn(b'Saturday Snowflakes',self.client.get('/coach',headers=headers).data)
        different=(today()+timedelta(days=1)).isoformat()
        self.assertEqual(self.client.post(f'/attendance/{self.team_id}/record',data={'session_date':different}).status_code,403)
        self.assertEqual(self.client.post(f'/teams/{self.team_id}/session/status',data={'session_date':different,'status':'on_hill'}).status_code,403)
        self.login_as(self.admin_id)
        with app.app_context(): coverage_id=ClassCoverage.query.one().id
        self.assertEqual(self.client.post('/operations/',data={'action':'cancel_coverage','coverage_id':coverage_id}).status_code,302)
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get(f'/teams/{self.team_id}/session').status_code,200)
        self.login_as(self.admin_id)
        app.config['CSRF_ENABLED']=True
        try:
            self.assertEqual(self.cover().status_code,400)
        finally:
            app.config['CSRF_ENABLED']=False

    def test_settings_page_and_automatic_and_manual_registration(self):
        self.assertEqual(self.client.get('/operations/').status_code,200)
        with app.app_context(): program_id=db.session.get(Team,self.team_id).program_id
        self.assertEqual(self.client.post('/operations/',data=dict(action='program',program_id=program_id,placement='automatic',default_team_id=self.team_id,minimum_level=1)).status_code,302)
        payload=dict(username='new-student',email='new@test.invalid',password='long-password',full_name='New Learner',user_type='student',program_id=program_id)
        self.assertEqual(self.client.post('/register',data=payload).status_code,302)
        with app.app_context(): self.assertEqual(User.query.filter_by(username='new-student').one().team_id,self.team_id)
        self.client.post('/operations/',data=dict(action='program',program_id=program_id,placement='manual',minimum_level=0))
        payload.update(username='manual',email='manual@test.invalid')
        self.assertEqual(self.client.post('/register',data=payload).status_code,302)
        with app.app_context():
            student=User.query.filter_by(username='manual').one()
            self.assertIsNone(student.team_id)
            self.assertIsNone(Enrollment.query.filter_by(student_id=student.id).one().team_id)

if __name__ == '__main__': unittest.main()
