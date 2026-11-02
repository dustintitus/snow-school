import unittest
from test_admin_assistant import AssistantTests
from models import db, AdminTask
from app import app


class TaskTests(unittest.TestCase):
    setUp = AssistantTests.setUp
    login_as = AssistantTests.login_as

    def test_task_lifecycle_and_filters(self):
        self.login_as(self.admin_id)
        fields = dict(title='Review roster', notes='Confirm placement', priority='high', status='todo', owner_id=str(self.admin_id), due_date='2026-01-01')
        self.assertEqual(self.client.post('/admin/tasks', data=fields).status_code, 302)
        with app.app_context():
            task_id = AdminTask.query.one().id
        page = self.client.get('/admin/tasks?owner=mine').data
        self.assertIn(b'Review roster', page)
        self.assertIn(b'Overdue', page)
        self.assertNotIn(b'Review roster', self.client.get('/admin/tasks?owner=unassigned').data)
        fields['status'] = 'done'
        self.assertEqual(self.client.post(f'/admin/tasks/{task_id}', data=fields).status_code, 302)
        self.assertNotIn(b'Review roster', self.client.get('/admin/tasks').data)
        self.assertIn(b'Review roster', self.client.get('/admin/tasks?status=done').data)

    def test_task_permissions_validation_and_csrf(self):
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.get('/admin/tasks').status_code, 403)
        self.assertEqual(self.client.post('/admin/tasks', data={'title': 'No'}).status_code, 403)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.post('/admin/tasks', data={'title': 'Invalid', 'owner_id': self.student_id}).status_code, 400)
        self.assertEqual(self.client.post('/admin/tasks', data={'title': 'Invalid', 'due_date': 'bad'}).status_code, 400)
        app.config['CSRF_ENABLED'] = True
        try:
            self.assertEqual(self.client.post('/admin/tasks', data={'title': 'No token'}).status_code, 400)
        finally:
            app.config['CSRF_ENABLED'] = False
        with app.app_context():
            self.assertEqual(AdminTask.query.count(), 0)

    def test_assistant_draft_does_not_save_and_escapes_content(self):
        self.login_as(self.admin_id)
        response = self.client.post('/admin/tasks', data={'action': 'draft', 'title': 'Plan <script>bad</script>', 'notes': 'Review details'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Plan &lt;script&gt;bad&lt;/script&gt;', response.data)
        self.assertIn(b'Review details', response.data)
        with app.app_context():
            self.assertEqual(AdminTask.query.count(), 0)
