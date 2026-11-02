import unittest
from datetime import date
from html.parser import HTMLParser

import test_workflows
from app import app
from models import db, User
from werkzeug.security import generate_password_hash


class NavigationLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href.startswith('/') and not href.startswith('/static/'):
                self.links.add(href)


class AdminNavigationTests(unittest.TestCase):
    login_as = test_workflows.WorkflowTestCase.login_as

    def setUp(self):
        test_workflows.WorkflowTestCase.setUp(self)
        with app.app_context():
            admin = User(username='admin', email='admin@test.invalid',
                         password_hash=generate_password_hash('test'),
                         full_name='Administrator', user_type='admin')
            db.session.add(admin)
            db.session.commit()
            self.admin_id = admin.id

    def test_launcher_and_sidebar_destinations_render_for_admin(self):
        self.login_as(self.admin_id)
        home = self.client.get('/dashboard')
        self.assertEqual(home.status_code, 200)
        self.assertIn(b'What do you need to do?', home.data)
        links = NavigationLinks()
        links.feed(home.get_data(as_text=True))
        for href in sorted(links.links - {'/'}):
            with self.subTest(href=href):
                self.assertEqual(self.client.get(href).status_code, 200)

    def test_admin_destinations_reject_other_roles_and_anonymous(self):
        for path in ['/admin/overview', '/admin/people', '/admin/sessions']:
            self.assertEqual(self.client.get(path).status_code, 302)
        for user_id in [self.instructor_id, self.student_id]:
            self.login_as(user_id)
            for path in ['/admin/overview', '/admin/people', '/admin/sessions']:
                self.assertEqual(self.client.get(path).status_code, 403)
            self.assertNotIn(b'aria-label="Admin navigation"', self.client.get('/dashboard').data)

    def test_people_filters_and_progression_links(self):
        self.login_as(self.admin_id)
        page = self.client.get('/admin/people?role=student&q=Riley')
        self.assertIn(b'Riley Rider', page.data)
        self.assertNotIn(b'Coach North', page.data)
        for path in [f'/learning/participants/{self.student_id}',
                     f'/learning/participants/{self.student_id}/reports',
                     f'/admin/view_student_evaluations/{self.student_id}']:
            self.assertIn(path.encode(), page.data)
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertIn(b'No people match', self.client.get('/admin/people?q=%25').data)
        self.assertEqual(self.client.get('/admin/people?role=invalid').status_code, 400)

    def test_session_selection_preserves_date_without_writing(self):
        self.login_as(self.admin_id)
        page = self.client.get('/admin/sessions?date=2026-02-07')
        path = f'/teams/{self.team_id}/session?date=2026-02-07'
        self.assertIn(path.encode(), page.data)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/admin/sessions?date=invalid').status_code, 302)


if __name__ == '__main__':
    unittest.main()
