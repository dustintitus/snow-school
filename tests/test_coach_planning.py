import os
import unittest
from datetime import date
from unittest.mock import patch
from types import SimpleNamespace
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['FLASK_ENV'] = 'production'
from coaching import teaching_context
from app import app, CURRENT_SEASON
from models import db, User, Program, Team, AppSetting
from learning_models import SkillObservation

class WeekContextTests(unittest.TestCase):
    def program(self, **changes):
        data = dict(start_date=date(2026, 1, 3), end_date=date(2026, 3, 31), frequency_type='weekly', frequency_value=8, frequency_days='saturday')
        data.update(changes)
        return SimpleNamespace(**data)

    def test_evaluation_weeks_and_boundaries(self):
        for day, week, evaluation in [(3, 1, False), (24, 4, True), (31, 5, False)]:
            ctx = teaching_context(self.program(), date(2026, 1, day))
            self.assertEqual((ctx['week'], ctx['evaluation']), (week, evaluation))
        self.assertTrue(teaching_context(self.program(), date(2026, 2, 21))['evaluation'])
        for day in [date(2026, 1, 2), date(2026, 2, 28), date(2026, 4, 1)]:
            ctx = teaching_context(self.program(), day)
            self.assertIsNone(ctx['week'])
            self.assertFalse(ctx['evaluation'])

    def test_missing_schedule_and_nonweekly_do_not_invent_week(self):
        for changes in [dict(start_date=None), dict(frequency_days=None), dict(frequency_days='nonsense'), dict(frequency_type='daily')]:
            self.assertIsNone(teaching_context(self.program(**changes), date(2026, 1, 24))['week'])

    def test_week_anchored_to_first_class_day(self):
        ctx = teaching_context(self.program(start_date=date(2026, 1, 1)), date(2026, 1, 22))
        self.assertEqual(ctx['week'], 3)
        self.assertFalse(ctx['scheduled'])

class CoachPlanningTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, CSRF_ENABLED=False)
        self.client = app.test_client()
        with app.app_context():
            db.drop_all(); db.create_all()
            coach = User(username='coach', full_name='Jordan North', email='coach@example.com', password_hash='unused', user_type='instructor')
            other = User(username='other', full_name='Other Coach', email='other@example.com', password_hash='unused', user_type='instructor')
            program = Program(name='Ski Saturdays', start_date=date(2026,1,3), end_date=date(2026,2,21), frequency_type='weekly', frequency_value=8, frequency_days='saturday')
            db.session.add_all([coach, other, program]); db.session.flush()
            team = Team(name='Snow Explorers', program_id=program.id, instructor_id=coach.id)
            db.session.add(team); db.session.flush()
            child = User(username='learner', full_name='Riley Rider', email='learner@example.com', password_hash='unused', user_type='student', team_id=team.id)
            db.session.add(child); db.session.flush()
            self.coach, self.other, self.team, self.child = coach.id, other.id, team.id, child.id
            for day, status in [(date(2026,1,10), 'learning'), (date(2026,2,1), 'mastered')]:
                db.session.add(SkillObservation(student_id=child.id,instructor_id=coach.id,season=CURRENT_SEASON,card_key='ski-1',skill_id='ski-1-1',session_date=day,week=2,status=status,evidence='Observed in class'))
            db.session.commit()
        self.login(self.coach)

    def login(self, user_id):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user_id); session['_fresh'] = True

    def test_dashboard_tasks_and_evaluation_windows(self):
        for day, expected in [('2026-01-17',False),('2026-01-24',True),('2026-02-21',True),('2026-02-28',False)]:
            with patch('learning.today', return_value=date.fromisoformat(day)):
                response = self.client.get('/coach?date='+day)
            self.assertEqual(response.status_code,200)
            self.assertIn(b'<strong>Evaluations</strong>',response.data)
            self.assertEqual(b'aria-disabled="true"' not in response.data, expected)
            self.assertNotIn(b'Coach companion',response.data)
            self.assertNotIn(b'Your day on the hill',response.data)
            self.assertIn(b'Welcome, Jordan.',response.data)
            self.assertIn(f'date={day}#attendance'.encode(),response.data)

    def test_attendance_coaching_buttons_follow_evaluation_window(self):
        for day, enabled in [('2026-01-17', False), ('2026-01-24', True),
                             ('2026-01-31', False), ('2026-02-21', True),
                             ('2026-02-28', False)]:
            with patch('learning.today', return_value=date.fromisoformat(day)):
                response = self.client.get(f'/teams/{self.team}/session?date={day}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b'athlete-coaching-actions' in response.data, enabled)
            self.assertEqual(b'>Progression card</a>' in response.data, enabled)
            if enabled:
                self.assertIn(f'/evaluate/{self.child}?date={day}'.encode(), response.data)
            self.assertIn(b'Save attendance', response.data)
            self.assertIn(b'Session note', response.data)

    def test_plan_uses_observations_as_of_selected_date(self):
        with patch('learning.today', return_value=date(2026,1,24)):
            response = self.client.get(f'/teams/{self.team}/lesson-plan?date=2026-01-24')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Mobility: move in boots',response.data)
        self.assertIn(b'Open evaluation',response.data)
        response = self.client.get(f'/teams/{self.team}/lesson-plan?date=2026-02-07&card=ski-1')
        self.assertIn(b'No skills currently marked',response.data)
        self.assertNotIn(b'Open evaluation',response.data)

    def test_admin_intervals_and_direct_evaluation_guard(self):
        with app.app_context():
            program_id = db.session.get(Team, self.team).program_id
            admin = User(username='admin',full_name='Admin',email='admin@example.com',password_hash='unused',user_type='admin')
            db.session.add(admin); db.session.commit(); admin_id = admin.id
        endpoint = f'/admin/programs/{program_id}/evaluation-schedule'
        self.assertEqual(self.client.post(endpoint,data={'evaluation_weeks':'3, 6'}).status_code,403)
        self.login(admin_id)
        self.assertEqual(self.client.post(endpoint,data={'evaluation_weeks':'6, 3, 3'}).status_code,302)
        with app.app_context():
            self.assertEqual(db.session.get(AppSetting,f'evaluation-weeks:{program_id}').value,'3,6')
        self.client.post(endpoint,data={'evaluation_weeks':'0, nope'})
        with app.app_context():
            self.assertEqual(db.session.get(AppSetting,f'evaluation-weeks:{program_id}').value,'3,6')
        self.login(self.coach)
        with patch('learning.today',return_value=date(2026,1,17)):
            self.assertEqual(self.client.get(f'/evaluate/{self.child}').status_code,200)
            self.assertNotIn(b'aria-disabled="true"',self.client.get('/coach?date=2026-01-24').data)
        with patch('learning.today',return_value=date(2026,1,24)):
            self.assertIn(b'aria-disabled="true"',self.client.get('/coach?date=2026-01-17').data)
            for method in [self.client.get,self.client.post]:
                self.assertEqual(method(f'/evaluate/{self.child}?date=2026-01-17').status_code,403)
        self.login(admin_id)
        self.client.post(endpoint,data={'evaluation_weeks':''})
        self.login(self.coach)
        with patch('learning.today',return_value=date(2026,1,17)):
            self.assertIn(b'Not scheduled by your administrator',self.client.get('/coach').data)
            self.assertEqual(self.client.get(f'/evaluate/{self.child}').status_code,403)

    def test_plan_authorization_and_bad_inputs(self):
        for query in ['date=bad', 'card=bad']:
            self.assertEqual(self.client.get(f'/teams/{self.team}/lesson-plan?{query}').status_code,400)
        for user_id in [self.other,self.child]:
            self.login(user_id)
            self.assertEqual(self.client.get(f'/teams/{self.team}/lesson-plan').status_code,403)
        self.login(self.other)
        self.assertNotIn(b'Snow Explorers',self.client.get('/coach').data)
        self.assertIn(b'Your classes will appear here',self.client.get('/coach').data)

if __name__ == '__main__': unittest.main()
