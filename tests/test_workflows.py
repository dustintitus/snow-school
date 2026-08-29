import os
import unittest
from datetime import date

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['FLASK_ENV'] = 'production'

from app import app, build_admin_dashboard, seed_demo_accounts, seed_demo_operations, seed_horseshoe_catalogue
from models import db, AppSetting, Attendance, ClassSession, Enrollment, Program, ProgramProfile, Team, User
from werkzeug.security import check_password_hash, generate_password_hash


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

    def test_coach_companion_only_shows_owned_teams(self):
        self.login_as(self.instructor_id)
        response = self.client.get('/coach?date=2026-02-07')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Saturday Snowflakes', response.data)
        self.assertIn(b'Coach companion', response.data)

    def test_coach_can_update_class_status(self):
        self.login_as(self.instructor_id)
        response = self.client.post(f'/teams/{self.team_id}/session/status', data={
            'session_date': '2026-02-07', 'status': 'on_hill',
            'meeting_point': 'Magic Carpet gate', 'coach_note': 'Working on balance'
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            class_session = ClassSession.query.one()
            self.assertEqual(class_session.status, 'on_hill')
            self.assertEqual(class_session.meeting_point, 'Magic Carpet gate')

    def test_other_instructor_cannot_update_class_status(self):
        self.login_as(self.other_id)
        response = self.client.post(f'/teams/{self.team_id}/session/status', data={
            'session_date': '2026-02-07', 'status': 'completed'
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(ClassSession.query.count(), 0)

    def test_logout_requires_post(self):
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get('/logout').status_code, 405)
        self.assertEqual(self.client.post('/logout').status_code, 302)

    def test_health_does_not_expose_internal_counts(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'users', response.data)
        self.assertNotIn(b'programs', response.data)

    def test_site_is_blocked_from_search_indexing(self):
        response = self.client.get('/')
        self.assertEqual(response.headers['X-Robots-Tag'], 'noindex, nofollow, noarchive, nosnippet')
        self.assertIn(b'<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">', response.data)
        robots = self.client.get('/robots.txt')
        self.assertEqual(robots.mimetype, 'text/plain')
        self.assertEqual(robots.data, b'User-agent: *\nDisallow: /\n')

    def test_mobile_login_redirects_coach_to_requested_local_path(self):
        response = self.client.post('/login', data={
            'username': 'coach',
            'password': 'password123',
            'next': '/coach',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/coach'))

    def test_login_rejects_external_redirects(self):
        response = self.client.post('/login', data={
            'username': 'coach',
            'password': 'password123',
            'next': 'https://example.com/phishing',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/dashboard'))

    def test_versioned_demo_seed_resets_accounts_only_once(self):
        with app.app_context():
            passwords = {'admin': 'new-admin', 'instructor1': 'new-coach', 'student1': 'new-student'}
            self.assertTrue(seed_demo_accounts('test-v1', passwords))
            coach = User.query.filter_by(username='instructor1').one()
            self.assertTrue(check_password_hash(coach.password_hash, 'new-coach'))
            self.assertEqual(coach.user_type, 'instructor')
            self.assertFalse(seed_demo_accounts('test-v1', passwords))
            self.assertIsNotNone(db.session.get(AppSetting, 'demo-account-seed:test-v1'))

    def test_horseshoe_catalogue_seed_is_idempotent_and_backfills_enrollment(self):
        with app.app_context():
            self.assertTrue(seed_horseshoe_catalogue('test-catalogue'))
            self.assertFalse(seed_horseshoe_catalogue('test-catalogue'))
            self.assertEqual(ProgramProfile.query.filter_by(season='2026-2027', is_active=True).count(), 11)
            self.assertIsNotNone(Program.query.filter_by(name='Adult Social Ski + Snowboard').first())
            self.assertEqual(Enrollment.query.filter_by(student_id=self.student_id, season='2026-2027').count(), 1)

    def test_dashboard_retention_uses_prior_enrollment_history(self):
        with app.app_context():
            seed_horseshoe_catalogue('dashboard-catalogue')
            current = Enrollment.query.filter_by(student_id=self.student_id, season='2026-2027').one()
            db.session.add(Enrollment(student_id=self.student_id, program_id=current.program_id, team_id=self.team_id, season='2025-2026', status='completed'))
            db.session.commit()
            dashboard = build_admin_dashboard()
            self.assertEqual(dashboard['registered'], 1)
            self.assertEqual(dashboard['returning'], 1)
            self.assertEqual(dashboard['returning_rate'], 100)
            self.assertEqual(dashboard['average_seasons'], 2.0)

    def test_admin_dashboard_and_program_catalogue_render(self):
        with app.app_context():
            admin = User(username='ops-admin', email='ops@example.com', password_hash=generate_password_hash('password123'), full_name='Operations Admin', user_type='admin')
            db.session.add(admin)
            db.session.commit()
            admin_id = admin.id
            seed_horseshoe_catalogue('render-catalogue')
        self.login_as(admin_id)
        dashboard = self.client.get('/dashboard')
        programs = self.client.get('/admin/programs')
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'Snow School overview', dashboard.data)
        self.assertIn(b'Returning guests', dashboard.data)
        self.assertEqual(programs.status_code, 200)
        self.assertIn(b'Adult Social Ski + Snowboard', programs.data)
        self.assertIn(b'Need capacity', programs.data)

    def test_demo_operations_populate_every_program_without_duplicates(self):
        with app.app_context():
            seed_horseshoe_catalogue('operations-catalogue')
            self.assertTrue(seed_demo_operations('test-operations'))
            first_counts = (Team.query.filter(Team.name.like('[Demo]%')).count(), User.query.filter(User.username.like('demo_student_%')).count(), Attendance.query.count())
            self.assertFalse(seed_demo_operations('test-operations'))
            self.assertEqual(first_counts, (Team.query.filter(Team.name.like('[Demo]%')).count(), User.query.filter(User.username.like('demo_student_%')).count(), Attendance.query.count()))
            self.assertEqual(first_counts[0], 16)
            self.assertGreater(first_counts[1], 80)
            dashboard = build_admin_dashboard()
            self.assertGreater(dashboard['registered'], 80)
            self.assertGreater(dashboard['returning'], 0)
            self.assertGreater(dashboard['waitlisted'], 0)
            self.assertEqual(dashboard['history_seasons'], 3)
            self.assertEqual(dashboard['capacity_missing'], 0)


class CsrfTestCase(unittest.TestCase):
    def test_post_without_token_is_rejected(self):
        app.config.update(TESTING=True, CSRF_ENABLED=True)
        client = app.test_client()
        response = client.post('/login', data={'username': 'nobody', 'password': 'password'})
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
