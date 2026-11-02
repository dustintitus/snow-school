import unittest
from unittest.mock import patch
import test_workflows
from app import app
from models import db, User


class AssistantTests(unittest.TestCase):
    login_as = test_workflows.WorkflowTestCase.login_as

    def setUp(self):
        test_workflows.WorkflowTestCase.setUp(self)
        with app.app_context():
            user = User(username='admin', email='admin@test.invalid', full_name='Admin',
                        user_type='admin', password_hash='unused')
            db.session.add(user)
            db.session.commit()
            self.admin_id = user.id

    def test_role_access_and_widget(self):
        self.assertEqual(self.client.post('/admin/assistant/chat').status_code, 302)
        self.login_as(self.instructor_id)
        self.assertEqual(self.client.post('/admin/assistant/chat').status_code, 403)
        self.assertNotIn(b'id="assistant-toggle"', self.client.get('/dashboard').data)
        self.login_as(self.admin_id)
        self.assertIn(b'id="assistant-toggle"', self.client.get('/dashboard').data)

    @patch('admin_assistant.credentials', return_value='test')
    @patch('admin_assistant.ask_openai', return_value='There is one student.')
    def test_aggregate_context_and_validation(self, ask, key):
        self.login_as(self.admin_id)
        response = self.client.post('/admin/assistant/chat', data={'message': 'How many students?'})
        self.assertEqual(response.status_code, 200)
        context = ask.call_args.args[1]
        self.assertEqual(context['users_by_role']['student'], 1)
        self.assertNotIn('Riley', str(context))
        self.assertNotIn('@', str(context))
        self.assertEqual(self.client.post('/admin/assistant/chat', data={'message': 'Again'}).status_code, 429)
        self.assertEqual(self.client.post('/admin/assistant/chat', data={'message': 'x', 'history': '{}'}).status_code, 400)

    def test_csrf_required(self):
        self.login_as(self.admin_id)
        app.config['CSRF_ENABLED'] = True
        try:
            self.assertEqual(self.client.post('/admin/assistant/chat', data={'message': 'Hello'}).status_code, 400)
        finally:
            app.config['CSRF_ENABLED'] = False

    @patch('admin_assistant.credentials', return_value='test')
    @patch('admin_assistant.ask_openai', side_effect=TimeoutError)
    def test_failure_is_actionable(self, ask, key):
        self.login_as(self.admin_id)
        response = self.client.post('/admin/assistant/chat', data={'message': 'Hello'})
        self.assertEqual(response.status_code, 502)
        self.assertIn('temporarily unavailable', response.json['error'])
