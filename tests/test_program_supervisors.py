from test_workflows import WorkflowTestCase
from app import app
from models import db, Program, ProgramSupervisor, User, Team, Attendance, ClassSession
from learning_models import SchoolGroup


class SupervisorTestCase(WorkflowTestCase):
    def setUp(self):
        super().setUp()
        with app.app_context():
            admin = User(username='admin', email='admin@example.test', password_hash='synthetic', full_name='Admin', user_type='admin')
            db.session.add(admin)
            db.session.flush()
            self.admin_id = admin.id
            self.program_id = db.session.get(Team, self.team_id).program_id
            other_program = Program(name='Other School Program', frequency_type='daily')
            db.session.add(other_program)
            db.session.flush()
            other_team = Team(name='Other School Class', program_id=other_program.id, instructor_id=self.instructor_id)
            db.session.add(other_team)
            db.session.flush()
            db.session.add(SchoolGroup(team_id=other_team.id, school_name='Other School', season='2026-2027', created_by=admin.id))
            self.other_program_id, self.other_team_id = other_program.id, other_team.id
            db.session.add(ProgramSupervisor(program_id=self.program_id, user_id=self.other_id, assigned_by=admin.id))
            db.session.commit()

    def test_supervisor_reads_only_assigned_program(self):
        self.login_as(self.other_id)
        page = self.client.get('/coach')
        self.assertIn(b'Program supervision', page.data)
        self.assertIn(b'Saturday Snowflakes', page.data)
        self.assertNotIn(b'Other School Class', page.data)
        page = self.client.get(f'/coach/supervision/classes/{self.team_id}')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Riley Rider', page.data)
        self.assertNotIn(b'Take attendance', page.data)
        self.assertEqual(self.client.get(f'/coach/supervision/classes/{self.other_team_id}').status_code, 403)
        self.assertEqual(self.client.post(f'/coach/supervision/classes/{self.team_id}').status_code, 405)

    def test_supervision_does_not_grant_writes_or_private_history(self):
        self.login_as(self.other_id)
        for path, data in [
            (f'/attendance/{self.team_id}/record', {'session_date':'2026-02-07', f'attended_{self.student_id}':'on'}),
            (f'/teams/{self.team_id}/session/status', {'session_date':'2026-02-07','status':'completed'}),
            (f'/evaluate/{self.student_id}', {}),
            (f'/participants/{self.student_id}/media', {}),
        ]:
            self.assertIn(self.client.post(path, data=data).status_code, (302,403))
        self.assertEqual(self.client.get(f'/teams/{self.team_id}/lesson-plan').status_code,403)
        with app.app_context():
            self.assertEqual(Attendance.query.count(),0)
            self.assertEqual(ClassSession.query.count(),0)

    def test_admin_assignment_multiple_programs_and_revocation(self):
        self.login_as(self.other_id)
        path=f'/admin/programs/{self.other_program_id}/supervisor'
        self.assertEqual(self.client.post(path,data={'supervisor_id':self.other_id}).status_code,403)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.get('/admin/programs').status_code,200)
        self.assertEqual(self.client.post(path,data={'supervisor_id':self.student_id}).status_code,400)
        self.assertEqual(self.client.post(path,data={'supervisor_id':self.other_id}).status_code,302)
        self.login_as(self.other_id)
        self.assertEqual(self.client.get(f'/coach/supervision/classes/{self.other_team_id}').status_code,200)
        self.assertEqual(self.client.get(f'/coach/supervision/classes/{self.team_id}').status_code,200)
        self.login_as(self.admin_id)
        self.client.post(path,data={'supervisor_id':''})
        self.login_as(self.other_id)
        self.assertEqual(self.client.get(f'/coach/supervision/classes/{self.other_team_id}').status_code,403)

    def test_owner_keeps_workspace_rights_when_also_supervisor(self):
        with app.app_context():
            db.session.get(ProgramSupervisor,self.program_id).user_id=self.instructor_id
            db.session.commit()
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get(f'/coach/supervision/classes/{self.team_id}').status_code,200)
        self.assertEqual(self.client.post(f'/teams/{self.team_id}/session/status',data={'session_date':'2026-02-07','status':'completed'}).status_code,302)
        with app.app_context():self.assertEqual(ClassSession.query.count(),1)

    def test_assignment_requires_csrf_and_nonstaff_cannot_read(self):
        self.login_as(self.admin_id)
        with app.app_context():
            before = db.session.get(ProgramSupervisor,self.program_id).user_id
        app.config['CSRF_ENABLED'] = True
        try:
            self.assertEqual(self.client.post(f'/admin/programs/{self.program_id}/supervisor',data={'supervisor_id':''}).status_code,400)
        finally:
            app.config['CSRF_ENABLED'] = False
        with app.app_context():
            self.assertEqual(db.session.get(ProgramSupervisor,self.program_id).user_id,before)
        self.login_as(self.student_id)
        self.assertEqual(self.client.get(f'/coach/supervision/classes/{self.team_id}').status_code,403)

    def test_supervision_appears_in_classes_tab(self):
        self.login_as(self.other_id)
        page = self.client.get('/coach/classes')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Program supervision', page.data)
        self.assertIn(b'Saturday Snowflakes', page.data)
        self.assertNotIn(b'Other School Class', page.data)

    def test_inactive_staff_and_noninstructors_are_ineligible(self):
        from staff_portal import profile_for
        with app.app_context():
            profile_for(self.other_id).active = False
            db.session.commit()
        self.login_as(self.admin_id)
        path=f'/admin/programs/{self.program_id}/supervisor'
        for user_id in (self.other_id, self.student_id, self.admin_id, 999999):
            self.assertEqual(self.client.post(path,data={'supervisor_id':user_id}).status_code,400)
        self.login_as(self.other_id)
        self.assertEqual(self.client.get('/coach').status_code,403)
        self.assertEqual(self.client.get(f'/coach/supervision/classes/{self.team_id}').status_code,403)

    def test_assignment_replacement_removes_previous_supervisor(self):
        self.login_as(self.admin_id)
        self.client.post(f'/admin/programs/{self.program_id}/supervisor',data={'supervisor_id':self.instructor_id})
        self.login_as(self.other_id)
        self.assertEqual(self.client.get(f'/coach/supervision/classes/{self.team_id}').status_code,403)
        self.assertNotIn(b'Program supervision',self.client.get('/coach').data)

    def test_supervisor_cannot_read_learner_history_media_or_exports(self):
        from models import Evaluation, ParticipantMedia
        from learning_models import ParticipantReport
        from datetime import datetime, date
        from unittest.mock import patch
        with app.app_context():
            report = ParticipantReport(student_id=self.student_id,season='2026-2027',card_key='test',snapshot={},comments='PRIVATE HISTORY',next_steps='PRIVATE NEXT',author_id=self.instructor_id)
            evaluation = Evaluation(student_id=self.student_id,instructor_id=self.instructor_id,sport_type='skier',level=1,skills_score=1,attitude_score=1,performance_score=1,created_at=datetime.now())
            media = ParticipantMedia(student_id=self.student_id,uploader_id=self.instructor_id,blob_url='https://example.invalid/private',blob_pathname='private',content_type='image/png',byte_size=1)
            db.session.add_all([report,evaluation,media])
            db.session.add(Attendance(student_id=self.student_id,team_id=self.other_team_id,session_date=date(2026,2,7),attended=True,notes='OTHER PROGRAM SECRET',recorded_by=self.instructor_id))
            db.session.commit()
            report_id,evaluation_id,media_id=report.id,evaluation.id,media.id
        self.login_as(self.other_id)
        with patch('app.BlobClient') as blob:
            for path in [f'/learning/participants/{self.student_id}', f'/learning/participants/{self.student_id}/reports',f'/learning/reports/{report_id}',f'/participants/{self.student_id}/certificate/{report_id}',f'/participant-media/{media_id}',f'/evaluations/{evaluation_id}',f'/admin/view_student_evaluations/{self.student_id}', '/admin/imports/999/source',f'/teams/{self.other_team_id}/session',f'/attendance/{self.other_team_id}']:
                response=self.client.get(path)
                self.assertIn(response.status_code,(302,403),path)
                self.assertNotIn(b'PRIVATE HISTORY',response.data)
            blob.assert_not_called()
        response=self.client.get(f'/coach/supervision/classes/{self.team_id}?date=2026-02-07')
        self.assertNotIn(b'OTHER PROGRAM SECRET',response.data)
        self.assertIn(b'Not recorded',response.data)
