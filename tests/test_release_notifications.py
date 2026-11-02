import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from werkzeug.security import generate_password_hash
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['FLASK_ENV'] = 'production'
from app import app
from models import db, User, Program, Team
from notification_models import Notification, NotificationRecipient, NotificationPreference, PushDevice, PushDelivery, NotificationWorkerLease
from notifications import create_message, generate_events, process_outbox
from coaching import guidance_sections

NATIVE = {'User-Agent': 'Mozilla SnowSchoolCoach/1.0'}
TOKEN = 'ExpoPushToken[abcdefghijklmnop]'

class ReleaseNotificationTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, CSRF_ENABLED=False)
        self.client = app.test_client()
        with app.app_context():
            db.drop_all(); db.create_all()
            for name, role in [('admin','admin'),('coach','instructor'),('other','instructor'),('parent','parent'),('child','student')]:
                db.session.add(User(username=name, full_name=name.title(), email=name+'@example.com', password_hash=generate_password_hash('test-password'), user_type=role))
            program = Program(name='Saturdays',start_date=date(2026,1,3),end_date=date(2026,2,21),frequency_type='weekly',frequency_value=8,frequency_days='saturday')
            db.session.add(program);db.session.flush()
            self.ids = {u.username:u.id for u in User.query.all()}
            team = Team(name='Fictional Demo Class', program_id=program.id, instructor_id=self.ids['coach'])
            db.session.add(team);db.session.commit();self.team_id=team.id
        self.login('coach')

    def login(self, name):
        with self.client.session_transaction() as s:
            s['_user_id']=str(self.ids[name]);s['_fresh']=True

    def register(self):
        ctx = self.client.get('/api/notifications/context').json
        return self.client.post('/api/notifications/device',data={'token':TOKEN,'session_key':ctx['session_key'],'enabled':'true'})

    def prepare_push(self):
        self.client.post('/notifications/settings',data={'push':'on','school':'on','schedule':'on','evaluation':'on'})
        self.register()
        with app.app_context():
            create_message('school','Private title','Learner details never on lock screen',[self.ids['coach']],'fixture')
            db.session.commit()

    def test_native_restored_roles_are_blocked_web_unaffected(self):
        for name in ['parent','child']:
            self.login(name)
            for path in ['/dashboard','/coach','/parent/media-consent','/notifications','/api/notifications/context']:
                self.assertEqual(self.client.get(path,headers=NATIVE).status_code,403)
            self.assertNotEqual(self.client.get('/dashboard').status_code,403)
            self.assertEqual(self.client.get('/login',headers=NATIVE).status_code,403)
            self.assertEqual(self.client.post('/logout',headers=NATIVE).status_code,302)
            self.assertIn(b'Coach &amp; staff sign-in',self.client.get('/login',headers=NATIVE).data)

    def test_native_password_login_cannot_bypass_role_guard(self):
        self.client.post('/logout')
        self.client.post('/login',headers=NATIVE,data={'username':'parent','password':'test-password','next':'/coach'})
        self.assertEqual(self.client.get('/dashboard',headers=NATIVE).status_code,403)
        self.assertEqual(self.client.post('/logout',headers=NATIVE).location,'/login')

    def test_staff_context_and_server_navigation_hiding(self):
        for name in ['admin','coach']:
            self.login(name)
            self.assertEqual(self.client.get('/dashboard',headers=NATIVE).status_code,200)
        self.assertIn(b'.coach-bottom-nav{display:none',self.client.get('/dashboard',headers=NATIVE).data)

    def test_preview_send_authorization_recipients_and_replay(self):
        path='/admin/notifications'
        self.assertEqual(self.client.post(path,data={}).status_code,403)
        self.login('admin')
        response=self.client.post(path,data={'category':'school','title':'School update','body':'Tomorrow','scope':'selected','staff_ids':[str(self.ids['coach'])]})
        self.assertEqual(response.status_code,200)
        with self.client.session_transaction() as s: key=s['notification_draft_key']
        with app.app_context():self.assertEqual(Notification.query.count(),0)
        self.assertEqual(self.client.post(path,data={'action':'send','key':key}).status_code,302)
        self.assertEqual(self.client.post(path,data={'action':'send','key':key}).status_code,400)
        with app.app_context():
            self.assertEqual(Notification.query.count(),1)
            self.assertEqual([r.user_id for r in NotificationRecipient.query.all()],[self.ids['coach']])
        self.login('coach');self.assertIn(b'School update',self.client.get('/notifications').data)
        self.login('other');self.assertNotIn(b'School update',self.client.get('/notifications').data)
        self.assertEqual(self.client.post('/notifications/1/read').status_code,404)

    def test_long_draft_and_changed_recipient_require_new_preview(self):
        self.login('admin')
        self.client.post('/admin/notifications',data={'category':'school','title':'Long notice','body':'Message '*500,'scope':'selected','staff_ids':[str(self.ids['coach'])]})
        with self.client.session_transaction() as s:
            key=s['notification_draft_key'];self.assertNotIn('notification_draft',s)
        with app.app_context():
            coach=db.session.get(User,self.ids['coach']);coach.user_type='parent';db.session.commit()
        self.assertEqual(self.client.post('/admin/notifications',data={'action':'send','key':key}).status_code,409)
        with app.app_context():self.assertEqual(Notification.query.count(),0)

    def test_invalid_parent_recipient_is_rejected(self):
        self.login('admin')
        self.assertEqual(self.client.post('/admin/notifications',data={'category':'school','title':'x','body':'x','scope':'selected','staff_ids':[str(self.ids['parent'])]}).status_code,400)

    def test_preferences_do_not_hide_inbox_and_read_persists(self):
        with app.app_context():
            create_message('school','Message','Body',[self.ids['coach']],'event');db.session.commit()
        self.client.post('/notifications/settings',data={})
        self.assertIn(b'Message',self.client.get('/notifications').data)
        self.assertEqual(self.client.get('/api/notifications/context').json['unread'],1)
        self.client.post('/notifications/1/read')
        self.assertEqual(self.client.get('/api/notifications/context').json['unread'],0)

    def test_device_session_validation_and_logout(self):
        self.assertEqual(self.register().status_code,200)
        self.assertEqual(self.client.post('/api/notifications/device',data={'token':TOKEN,'session_key':'old','enabled':'true'}).status_code,409)
        self.client.post('/logout')
        with app.app_context():self.assertFalse(PushDevice.query.one().active)

    def test_device_account_switch_reassigns_without_old_delivery(self):
        self.prepare_push()
        self.login('other')
        self.register()
        with app.app_context(),patch('notifications.expo_request') as send:
            process_outbox();send.assert_not_called()
            self.assertEqual(PushDelivery.query.one().status,'skipped')

    def test_device_permission_revocation(self):
        self.register();self.client.post('/api/notifications/device-disable')
        with app.app_context():self.assertFalse(PushDevice.query.one().active)

    def test_push_payload_privacy_and_receipts(self):
        self.prepare_push()
        with app.app_context(),patch('notifications.expo_request',return_value={'data':[{'status':'ok','id':'ticket'}]}) as send:
            process_outbox()
            payload=send.call_args.args[1][0]
            self.assertNotIn('Learner',str(payload));self.assertNotIn('Private title',str(payload))
            row=PushDelivery.query.one();self.assertEqual(row.status,'ticket');row.retry_at=datetime.utcnow()-timedelta(seconds=1);db.session.commit()
        with app.app_context(),patch('notifications.expo_request',return_value={'data':{'ticket':{'status':'ok'}}}):
            process_outbox();self.assertEqual(PushDelivery.query.one().status,'accepted')

    def test_disabled_category_skips_queued_push(self):
        self.prepare_push();self.client.post('/notifications/settings',data={'push':'on'})
        with app.app_context(),patch('notifications.expo_request') as send:
            process_outbox();send.assert_not_called();self.assertEqual(PushDelivery.query.one().status,'skipped')

    def test_provider_invalid_token_and_unknown_send(self):
        self.prepare_push()
        with app.app_context(),patch('notifications.expo_request',return_value={'data':[{'status':'error','details':{'error':'DeviceNotRegistered'}}]}):
            process_outbox();self.assertFalse(PushDevice.query.one().active)
        with app.app_context():
            row=PushDelivery.query.one();row.status='pending';row.device.active=True;row.retry_at=None;db.session.commit()
        with app.app_context(),patch('notifications.expo_request',side_effect=TimeoutError):
            process_outbox();self.assertEqual(PushDelivery.query.one().status,'unknown')

    def test_automatic_events_are_once_per_evaluation_week(self):
        with app.app_context(),patch('learning.today',return_value=date(2026,1,24)):
            generate_events();generate_events();self.assertEqual(Notification.query.filter_by(category='evaluation').count(),1)
        with app.app_context(),patch('learning.today',return_value=date(2026,1,25)):
            generate_events();self.assertEqual(Notification.query.filter_by(category='evaluation').count(),1)
            team=db.session.get(Team,self.team_id);team.program.frequency_days='sunday';db.session.commit()
            generate_events();generate_events();self.assertEqual(Notification.query.filter_by(category='schedule').count(),1)

    def test_cron_requires_secret_and_csrf_applies_to_bridge(self):
        self.assertEqual(self.client.get('/api/cron/notifications').status_code,401)
        app.config['CSRF_ENABLED']=True
        try:
            self.assertEqual(self.client.post('/api/notifications/device',data={}).status_code,400)
            self.assertEqual(self.client.post('/admin/notifications',data={}).status_code,400)
        finally:app.config['CSRF_ENABLED']=False

    def test_worker_authentication_and_overlap_lease(self):
        with patch.dict(os.environ, {'CRON_SECRET':'fixture-secret'}), patch('notifications.generate_events') as events, patch('notifications.process_outbox',return_value=0):
            self.assertEqual(self.client.get('/api/cron/notifications',headers={'Authorization':'Bearer wrong'}).status_code,401)
            self.assertEqual(self.client.get('/api/cron/notifications',headers={'Authorization':'Bearer fixture-secret'}).status_code,200)
            events.assert_called_once()
            with app.app_context():
                lease=db.session.get(NotificationWorkerLease,'notifications');lease.until=datetime.utcnow()+timedelta(minutes=1);db.session.commit()
            response=self.client.get('/api/cron/notifications',headers={'Authorization':'Bearer fixture-secret'})
            self.assertTrue(response.json['busy']);events.assert_called_once()

    def test_batch_delivery_and_explicitly_disabled_registration(self):
        self.prepare_push()
        with app.app_context():
            ctx=PushDevice.query.one()
            second=PushDevice(user_id=ctx.user_id,session_key=ctx.session_key,token='ExpoPushToken[seconddevice12345]',active=True)
            db.session.add(second);db.session.flush()
            db.session.add(PushDelivery(recipient_id=NotificationRecipient.query.one().id,device_id=second.id));db.session.commit()
        with app.app_context(),patch('notifications.expo_request',return_value={'data':[{'status':'ok','id':'one'},{'status':'ok','id':'two'}]}) as send:
            process_outbox();self.assertEqual(len(send.call_args.args[1]),2)
            self.assertEqual(PushDelivery.query.filter_by(status='ticket').count(),2)
            first=PushDelivery.query.first();first.status='pending';first.retry_at=None;first.device.updated_at=datetime.utcnow()-timedelta(days=2);first.device.active=False;db.session.commit()
        with app.app_context(),patch('notifications.expo_request') as send:
            process_outbox();send.assert_not_called();self.assertEqual(PushDelivery.query.first().status,'skipped')

    def test_notification_school_time_and_public_help(self):
        from notifications import school_datetime
        self.assertEqual(school_datetime(datetime(2026,10,4,0,15)),'Oct 03, 2026')
        self.client.post('/logout')
        for path in ['/support','/privacy']:
            response=self.client.get(path);self.assertEqual(response.status_code,200);self.assertIn(b'dustin.titus@gmail.com',response.data)

    def test_all_guidance_lines_preserved(self):
        from learning import CARDS
        for card in CARDS.values():
            source=[line.strip() for line in card['guidance'].splitlines() if line.strip()]
            rendered=[]
            for section in guidance_sections(card['guidance']):
                rendered.append(section['heading']);rendered.extend(section['practices'])
            self.assertEqual(source,rendered)

if __name__=='__main__':unittest.main()
