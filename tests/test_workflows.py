import os
import unittest
from datetime import date

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['FLASK_ENV'] = 'production'

from app import app
from models import db, Attendance, Program, Team, User
from werkzeug.security import generate_password_hash


class WorkflowTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            CSRF_ENABLED=False,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SERVER_NAME='localhost',
        )
        self.client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()
            program = Program(name='Snowflakes', frequency_type='weekly', frequency_value=8, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
            instructor = User(username='coach', email='coach@example.com', password_hash=generate_password_hash('password123'), full_name='Coach North', user_type='instructor')
            other = User(username='other', email='other@example.com', password_hash=generate_password_hash('password123'), full_name='Coach South', user_type='instructor')
            db.session.add_all([program, instructor, other])
            db.session.flush()
            team = Team(name='Saturday Snowflakes', program_id=program.id, instructor_id=instructor.id, team_type='class')
            db.session.add(team)
            db.session.flush()
            student = User(username='rider', email='rider@example.com', password_hash=generate_password_hash('password123'), full_name='Riley Rider', user_type='student', team_id=team.id, instructor_id=None, participates_skier=True)
            db.session.add(student)
            db.session.commit()
            self.instructor_id = instructor.id
            self.other_id = other.id
            self.team_id = team.id
            self.student_id = student.id

    def login_as(self, user_id):
        with self.client.session_transaction() as flask_session:
            flask_session['_user_id'] = str(user_id)
            flask_session['_fresh'] = True

    def test_team_owner_can_open_session_and_legacy_assignment_is_not_required(self):
        self.login_as(self.instructor_id)
        response = self.client.get(f'/teams/{self.team_id}/session?date=2026-02-07')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Saturday Snowflakes', response.data)
        evaluation_page = self.client.get(f'/evaluate/{self.student_id}')
        self.assertEqual(evaluation_page.status_code, 200)

    def test_other_instructor_cannot_open_team_session(self):
        self.login_as(self.other_id)
        response = self.client.get(f'/teams/{self.team_id}/session')
        self.assertEqual(response.status_code, 302)

    def test_session_attendance_is_upserted(self):
        self.login_as(self.instructor_id)
        payload = {'session_date': '2026-02-07', 'return_to': 'session', f'attended_{self.student_id}': 'on', f'notes_{self.student_id}': 'Strong balance'}
        first = self.client.post(f'/attendance/{self.team_id}/record', data=payload)
        second = self.client.post(f'/attendance/{self.team_id}/record', data=payload)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        with app.app_context():
            self.assertEqual(Attendance.query.count(), 1)
            self.assertEqual(Attendance.query.first().notes, 'Strong balance')

    def test_logout_requires_post(self):
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get('/logout').status_code, 405)
        self.assertEqual(self.client.post('/logout').status_code, 302)

    def test_health_does_not_expose_internal_counts(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'users', response.data)
        self.assertNotIn(b'programs', response.data)


class CsrfTestCase(unittest.TestCase):
    def test_post_without_token_is_rejected(self):
        app.config.update(TESTING=True, CSRF_ENABLED=True)
        client = app.test_client()
        response = client.post('/login', data={'username': 'nobody', 'password': 'password'})
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
