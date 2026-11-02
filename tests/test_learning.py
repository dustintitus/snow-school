import unittest
from datetime import date, timedelta
import test_workflows
from app import app, MEDIA_CONSENT_VERSION
from models import db, User, ParentStudent, MediaConsent, Team
from learning import CARDS, seed_training, today
from learning_models import SkillObservation, ParticipantReport, TrainingWeek, TrainingReview, TrainingAttendance, SchoolGroup, PrivateLesson
from werkzeug.security import generate_password_hash

class LearningTests(unittest.TestCase):
    login_as = test_workflows.WorkflowTestCase.login_as
    # Shared fixture only; baseline workflow tests run in their own suite.
    def setUp(self):
        test_workflows.WorkflowTestCase.setUp(self)
        with app.app_context():
            admin=User(username='admin',email='a@test.invalid',password_hash=generate_password_hash('test'),full_name='Admin',user_type='admin')
            parent=User(username='parent',email='p@test.invalid',password_hash=generate_password_hash('test'),full_name='Parent',user_type='parent')
            db.session.add_all([admin,parent]); db.session.flush()
            self.admin_id=admin.id; self.parent_id=parent.id
            db.session.add(ParentStudent(parent_id=parent.id,student_id=self.student_id))
            db.session.add(MediaConsent(parent_id=parent.id,student_id=self.student_id,version=MEDIA_CONSENT_VERSION,status='declined'))
            seed_training(); db.session.commit()

    def observation(self, **changes):
        payload=dict(card='ski-1',skill_id='ski-1-1',session_date=today().isoformat(),week='1',status='learning',evidence='Walked in boots without help on flat snow.',achieved='3',attempted='4')
        payload.update(changes)
        return self.client.post(f'/learning/participants/{self.student_id}',data=payload)

    def test_observation_validation_and_owner_access(self):
        self.login_as(self.instructor_id)
        for change in [dict(achieved='5'),dict(skill_id='fake'),dict(status='passed'),dict(session_date=(today()+timedelta(days=1)).isoformat()),dict(evidence=''),dict(week='9')]:
            self.assertEqual(self.observation(**change).status_code,400)
        self.assertEqual(self.observation().status_code,302)
        self.assertEqual(self.client.get(f'/learning/participants/{self.student_id}').status_code,200)
        self.login_as(self.other_id)
        self.assertEqual(self.observation().status_code,403)
        with app.app_context(): self.assertEqual(SkillObservation.query.count(),1)

    def test_report_snapshot_and_family_visibility(self):
        self.login_as(self.instructor_id); self.observation()
        response=self.client.post(f'/learning/participants/{self.student_id}/reports',data=dict(card='ski-1',comments='Great effort.',next_steps='Keep practising walking.'))
        self.assertEqual(response.status_code,302); report_url=response.location
        self.login_as(self.parent_id)
        self.assertEqual(self.client.get(report_url).status_code,404)
        self.assertNotIn(b'Great effort',self.client.get(f'/learning/participants/{self.student_id}/reports').data)
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.post(report_url).status_code,403)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.post(report_url).status_code,302)
        self.login_as(self.parent_id)
        page=self.client.get(report_url); self.assertEqual(page.status_code,200)
        self.assertIn(b'Great effort',page.data); self.assertNotIn(b'Walked in boots without help',page.data)
        self.login_as(self.instructor_id); self.observation(status='mastered')
        with app.app_context(): self.assertEqual(ParticipantReport.query.one().snapshot['rows'][0]['status'],'learning')
        self.login_as(self.other_id); self.assertEqual(self.client.get(report_url).status_code,403)

    def test_training_locked_future_versioned_and_attendance_separate(self):
        with app.app_context():
            week=TrainingWeek.query.first(); wid=week.id
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get(f'/learning/training/{wid}').status_code,403)
        self.assertEqual(self.client.post(f'/learning/training/{wid}/review',data={'revision':1}).status_code,403)
        self.login_as(self.admin_id)
        payload=dict(title='Safety briefing',content='Review manual pages 34 and 36.',release_date=(today()+timedelta(days=1)).isoformat(),published='on',revision=1)
        self.assertEqual(self.client.post(f'/learning/training/{wid}',data=payload).status_code,302)
        self.login_as(self.instructor_id); self.assertEqual(self.client.get(f'/learning/training/{wid}').status_code,403)
        self.login_as(self.admin_id); payload.update(release_date=today().isoformat(),revision=2)
        self.assertEqual(self.client.post(f'/learning/training/{wid}',data=payload).status_code,302)
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.post(f'/learning/training/{wid}/review',data={'revision':2}).status_code,409)
        for _ in range(2): self.assertEqual(self.client.post(f'/learning/training/{wid}/review',data={'revision':3}).status_code,302)
        with app.app_context():
            self.assertEqual(TrainingReview.query.count(),1); self.assertEqual(TrainingAttendance.query.count(),0)
        self.assertEqual(self.client.post(f'/learning/training/{wid}/attendance',data={'instructor_id':self.instructor_id,'status':'present'}).status_code,403)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.post(f'/learning/training/{wid}/attendance',data={'instructor_id':self.instructor_id,'status':'present'}).status_code,302)
        self.assertEqual(self.client.get('/learning/training').status_code,200)

    def test_group_creation_and_handoff_preserve_evidence(self):
        self.login_as(self.instructor_id)
        r=self.client.post('/learning/groups/new',data=dict(school_name='Test School',name='Group A',sport='ski',start_date='2026-10-01',sessions=6,names='Alex Example\nRobin Example'))
        self.assertEqual(r.status_code,302)
        with app.app_context():
            group=SchoolGroup.query.one(); tid=group.team_id; sid=group.team.students[0].id
            self.assertEqual(group.team.program.frequency_value,6); self.assertEqual(len(group.team.students),2)
        r=self.client.post(f'/learning/participants/{sid}',data=dict(card='ski-1',skill_id='ski-1-1',session_date=today().isoformat(),week=1,status='learning',evidence='Baseline observation'))
        self.assertEqual(r.status_code,302)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.post(f'/learning/groups/{tid}/assign',data={'instructor_id':self.other_id}).status_code,302)
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get(f'/learning/participants/{sid}').status_code,403)
        self.login_as(self.other_id)
        r=self.client.get(f'/learning/participants/{sid}'); self.assertEqual(r.status_code,200); self.assertIn(b'Baseline observation',r.data)

    def test_private_assignment_and_incident_permissions(self):
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get('/learning/privates/new').status_code,403)
        self.assertEqual(self.client.post('/learning/incidents',data={'team_id':self.team_id,'occurred_at':f'{today()}T10:00','location':'Carpet','details':'Lost mitten','actions':'Supervisor contacted'}).status_code,302)
        self.login_as(self.other_id); self.assertNotIn(b'Lost mitten',self.client.get('/learning/incidents').data)
        self.login_as(self.admin_id); self.assertIn(b'Lost mitten',self.client.get('/learning/incidents').data)
        payload=dict(instructor_id=self.instructor_id,participant='Private Example',starts_at='2027-01-05T10:00',duration_minutes=60,meeting_point='Red flags',notes='Beginner')
        self.assertEqual(self.client.post('/learning/privates/new',data=payload).status_code,302)
        self.login_as(self.instructor_id); self.assertIn(b'Private Example',self.client.get('/learning/').data)
        self.login_as(self.other_id); self.assertNotIn(b'Private Example',self.client.get('/learning/').data)

    def test_all_staff_pages_render_and_seed_idempotent(self):
        self.login_as(self.admin_id)
        for path in ['/learning/','/learning/manual','/learning/manual?q=lift','/learning/training','/learning/training/1','/learning/groups/new','/learning/privates/new','/learning/incidents',f'/learning/participants/{self.student_id}',f'/learning/participants/{self.student_id}/reports']:
            self.assertEqual(self.client.get(path).status_code,200,path)
        with app.app_context(): seed_training(); self.assertEqual(TrainingWeek.query.count(),8)

    def test_new_mutations_require_csrf(self):
        app.config['CSRF_ENABLED']=True
        self.login_as(self.instructor_id)
        self.assertEqual(self.observation().status_code,400)
        app.config['CSRF_ENABLED']=False

