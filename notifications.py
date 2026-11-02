"""School staff inbox, explicit admin sending, and retryable Expo push delivery."""
import hashlib
import json
import os
import re
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, update
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from models import AppSetting, Team, User, db
from notification_models import Notification, NotificationRecipient, NotificationPreference, PushDevice, PushDelivery, NotificationWorkerLease, NotificationDraft

bp = Blueprint('notifications', __name__)
@bp.app_template_filter('school_datetime')
def school_datetime(value, fmt='%b %d, %Y'):
    return value.replace(tzinfo=UTC).astimezone(ZoneInfo('America/Toronto')).strftime(fmt)

CATEGORIES = {'school': 'Snow School', 'schedule': 'Schedule Notifications', 'evaluation': 'Evaluation notifications'}
SCHOOL = 'HORSESHOE'

def staff():
    if current_user.user_type not in {'admin', 'instructor'}:
        abort(403)

def preferences(user_id):
    row = db.session.get(NotificationPreference, user_id)
    if row is None:
        row = NotificationPreference(user_id=user_id)
        db.session.add(row)
        db.session.flush()
    return row

def eligible(user_id, category):
    pref = db.session.get(NotificationPreference, user_id)
    return bool(pref and pref.push_enabled and getattr(pref, category + '_enabled'))

def create_message(category, title, body, user_ids, event_key, author=None):
    from staff_portal import active_staff
    existing = Notification.query.filter_by(event_key=event_key).first()
    if existing:
        return existing
    message = Notification(school=SCHOOL, category=category, title=title, body=body, event_key=event_key, created_by=author)
    db.session.add(message)
    db.session.flush()
    for user_id in sorted(set(user_ids)):
        user = db.session.get(User, user_id)
        if not user or user.user_type not in {'instructor', 'admin'} or not active_staff(user_id):
            continue
        row = NotificationRecipient(notification_id=message.id, user_id=user_id)
        db.session.add(row)
        db.session.flush()
        if eligible(user_id, category):
            for device in PushDevice.query.filter_by(user_id=user_id, active=True).all():
                db.session.add(PushDelivery(recipient_id=row.id, device_id=device.id))
    return message

@bp.route('/notifications')
@login_required
def inbox():
    staff()
    rows = NotificationRecipient.query.filter_by(user_id=current_user.id).order_by(NotificationRecipient.id.desc()).limit(100).all()
    return render_template('notifications/inbox.html', rows=rows, categories=CATEGORIES)

@bp.route('/notifications/<int:recipient_id>/read', methods=['POST'])
@login_required
def mark_read(recipient_id):
    staff()
    row = db.get_or_404(NotificationRecipient, recipient_id)
    if row.user_id != current_user.id:
        abort(404)
    row.read_at = datetime.now(UTC).replace(tzinfo=None)
    db.session.commit()
    return redirect(url_for('notifications.inbox'))

@bp.route('/notifications/settings', methods=['GET', 'POST'])
@login_required
def settings():
    staff()
    pref = preferences(current_user.id)
    if request.method == 'POST':
        for key in ('push', 'school', 'schedule', 'evaluation'):
            setattr(pref, key + '_enabled', request.form.get(key) == 'on')
        db.session.commit()
        flash('Notification settings saved.', 'success')
        return redirect(url_for('notifications.settings'))
    db.session.commit()
    return render_template('notifications/settings.html', pref=pref, categories=CATEGORIES)

@bp.route('/api/notifications/context')
@login_required
def context():
    staff()
    session.setdefault('_csrf_token', secrets.token_urlsafe(32))
    key = session.setdefault('push_session', secrets.token_urlsafe(32))
    pref = preferences(current_user.id)
    db.session.commit()
    return jsonify(user_id=current_user.id, session_key=key, csrf=session.get('_csrf_token'),
                   push_enabled=pref.push_enabled, unread=NotificationRecipient.query.filter_by(user_id=current_user.id, read_at=None).count())

@bp.route('/api/notifications/device', methods=['POST'])
@login_required
def register_device():
    staff()
    token = request.form.get('token', '')
    if not re.fullmatch(r'(?:ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]{10,160}\]', token):
        abort(400)
    # The native bridge must prove it is still on the same authenticated session.
    key = session.get('push_session')
    if not key or not secrets.compare_digest(key, request.form.get('session_key', '')):
        abort(409)
    row = PushDevice.query.filter_by(token=token).first()
    if not row:
        row = PushDevice(token=token)
        db.session.add(row)
    row.user_id = current_user.id
    row.session_key = key
    row.active = request.form.get('enabled') == 'true'
    row.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.session.commit()
    return jsonify(ok=True)

@bp.route('/api/notifications/device-disable', methods=['POST'])
@login_required
def disable_device():
    staff()
    key = session.get('push_session')
    if key:
        PushDevice.query.filter_by(user_id=current_user.id, session_key=key).update({'active': False})
        db.session.commit()
    return jsonify(ok=True)

@bp.route('/notifications/test', methods=['POST'])
@login_required
def test_notification():
    staff()
    bucket = int(time.time() // 60)
    try:
        create_message('school', 'Notification check', 'Your Snow School notification check is saved. If push is enabled and this device is registered, an alert will also be queued.', [current_user.id], f'test:{current_user.id}:{bucket}', current_user.id)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    flash('Check saved to your inbox. A phone banner requires permission, registration and successful delivery.', 'success')
    return redirect(url_for('notifications.inbox'))

def selected_recipients(scope, values):
    from staff_portal import active_staff
    if scope == 'all':
        return [u.id for u in User.query.filter(User.user_type.in_(['instructor', 'admin'])).all() if active_staff(u.id)]
    if scope == 'team':
        try:
            team = db.get_or_404(Team, int(values.get('team_id', '')))
        except ValueError:
            abort(400)
        return [team.instructor_id]
    if scope == 'selected':
        try:
            ids = [int(v) for v in values.getlist('staff_ids')]
        except ValueError:
            abort(400)
        valid = [u.id for u in User.query.filter(User.id.in_(ids), User.user_type.in_(['instructor', 'admin'])).all()]
        if set(ids) != set(valid):
            abort(400)
        return valid
    abort(400)

@bp.route('/admin/notifications', methods=['GET', 'POST'])
@login_required
def compose():
    if current_user.user_type != 'admin':
        abort(403)
    preview = None
    if request.method == 'POST':
        if request.form.get('action') == 'send':
            key = session.get('notification_draft_key', '')
            if not key or not secrets.compare_digest(key, request.form.get('key', '')):
                abort(400)
            draft_row = db.session.get(NotificationDraft, key)
            if not draft_row or draft_row.author_id != current_user.id or draft_row.expires_at < datetime.now(UTC).replace(tzinfo=None):
                abort(400, description='This preview expired. Preview the message again.')
            valid_ids = {u.id for u in User.query.filter(User.id.in_(draft_row.recipient_ids), User.user_type.in_(['admin', 'instructor'])).all()}
            if valid_ids != set(draft_row.recipient_ids):
                abort(409, description='The recipient list changed. Preview the message again.')
            draft = {'key': key, 'category': draft_row.category, 'title': draft_row.title, 'body': draft_row.body, 'ids': draft_row.recipient_ids}
            try:
                message = create_message(draft['category'], draft['title'], draft['body'], draft['ids'], 'manual:' + draft['key'], current_user.id)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                message = Notification.query.filter_by(event_key='manual:' + draft['key']).first()
                if not message:
                    abort(409)
            process_outbox()
            session.pop('notification_draft_key', None)
            flash('Message saved to the selected staff inboxes. Eligible push alerts are queued.', 'success')
            return redirect(url_for('notifications.compose'))
        category = request.form.get('category')
        title, body = request.form.get('title', '').strip(), request.form.get('body', '').strip()
        ids = selected_recipients(request.form.get('scope'), request.form)
        if category not in CATEGORIES or not 1 <= len(title) <= 160 or not 1 <= len(body) <= 4000 or not ids:
            abort(400, description='Choose a category, title, message and at least one staff recipient.')
        preview = {'category': category, 'title': title, 'body': body, 'ids': sorted(set(ids)), 'key': str(uuid.uuid4())}
        db.session.add(NotificationDraft(key=preview['key'], author_id=current_user.id, category=category,
            title=title, body=body, recipient_ids=preview['ids'], expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)))
        db.session.commit()
        session['notification_draft_key'] = preview['key']
    history = Notification.query.filter(Notification.created_by.isnot(None)).order_by(Notification.id.desc()).limit(30).all()
    return render_template('notifications/compose.html', preview=preview, categories=CATEGORIES,
        users=User.query.filter(User.user_type.in_(['instructor', 'admin'])).order_by(User.full_name).all(),
        teams=Team.query.order_by(Team.name).all(), history=history, Recipient=NotificationRecipient, Delivery=PushDelivery)

def expo_request(endpoint, payload):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    token = os.environ.get('EXPO_ACCESS_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = Request('https://exp.host/--/api/v2/push/' + endpoint, data=json.dumps(payload).encode(), headers=headers)
    with urlopen(req, timeout=6) as response:
        return json.load(response)

def generate_events():
    """Daily evaluation availability; changed schedules use a durable snapshot baseline."""
    from coaching import evaluation_availability, teaching_context, evaluation_weeks
    from learning import today
    day = today()
    for team in Team.query.all():
        program = team.program
        availability = evaluation_availability(program)
        if availability['enabled']:
            create_message('evaluation', 'Evaluations are available', f'Open Today to review the evaluation tasks for {team.name}.', [team.instructor_id], f"evaluation:{team.id}:{program.start_date}:{teaching_context(program, day, evaluation_weeks(program))['week']}")
        snapshot = json.dumps([team.instructor_id, program.start_date.isoformat() if program.start_date else None,
                              program.end_date.isoformat() if program.end_date else None, program.frequency_type,
                              program.frequency_value, program.frequency_days], sort_keys=True)
        key = f'notification-schedule:{team.id}'
        baseline = db.session.get(AppSetting, key)
        if baseline is None:
            db.session.add(AppSetting(key=key, value=snapshot))
        elif baseline.value != snapshot:
            old = json.loads(baseline.value)
            create_message('schedule', 'Class schedule updated', f'The assignment or schedule for {team.name} has changed. Check Today or contact your school administrator.', [team.instructor_id, old[0]], f'schedule:{team.id}:{uuid.uuid4()}')
            baseline.value = snapshot
    db.session.commit()

def process_outbox():
    from staff_portal import active_staff
    now = datetime.now(UTC).replace(tzinfo=None)
    # A leased send with no persisted ticket has unknown outcome. Do not blindly resend it.
    PushDelivery.query.filter(PushDelivery.status == 'sending', PushDelivery.retry_at < now).update({'status': 'unknown', 'error': 'Send outcome unknown'}, synchronize_session=False)
    db.session.commit()
    rows = PushDelivery.query.options(joinedload(PushDelivery.device), joinedload(PushDelivery.recipient).joinedload(NotificationRecipient.notification)).filter(PushDelivery.status.in_(['pending', 'retry']), or_(PushDelivery.retry_at == None, PushDelivery.retry_at <= now)).order_by(PushDelivery.id).limit(100).all()
    batch = []
    claimed = []
    user_ids = {r.recipient.user_id for r in rows}
    prefs = {p.user_id: p for p in NotificationPreference.query.filter(NotificationPreference.user_id.in_(user_ids)).all()}
    valid_users = {u.id for u in User.query.filter(User.id.in_(user_ids), User.user_type.in_(['admin', 'instructor'])).all()}
    for row in rows:
        recipient, device = row.recipient, row.device
        pref = prefs.get(recipient.user_id)
        allowed = pref and pref.push_enabled and getattr(pref, recipient.notification.category + '_enabled')
        if not active_staff(recipient.user_id) or not device.active or device.user_id != recipient.user_id or recipient.user_id not in valid_users or not allowed:
            row.status = 'skipped'
            continue
        result = db.session.execute(update(PushDelivery).where(PushDelivery.id == row.id, PushDelivery.status.in_(['pending', 'retry'])).values(status='sending', attempts=PushDelivery.attempts + 1, retry_at=now + timedelta(minutes=2)))
        if result.rowcount:
            claimed.append(row)
            batch.append({'to': device.token, 'title': 'Snow School Coach', 'body': 'You have a new school notification. Open your inbox to read it.', 'sound': 'default', 'data': {'path': '/notifications'}})
    db.session.commit()
    if claimed:
        try:
            tickets_reply = expo_request('send', batch).get('data', [])
            if not isinstance(tickets_reply, list) or len(tickets_reply) != len(claimed):
                raise ValueError('Incomplete provider response')
            for row, ticket in zip(claimed, tickets_reply):
                if ticket.get('status') == 'ok' and ticket.get('id'):
                    row.status, row.ticket_id, row.error = 'ticket', ticket['id'], None
                    row.retry_at = now + timedelta(minutes=15)
                else:
                    error = ticket.get('details', {}).get('error', 'ProviderRejected')
                    row.error = error
                    if error == 'DeviceNotRegistered':
                        row.device.active = False
                    row.status = 'retry' if error == 'MessageRateExceeded' and row.attempts < 5 else 'failed'
                    row.retry_at = now + timedelta(minutes=2 ** row.attempts)
        except Exception:
            # A timeout may follow provider acceptance; never blindly duplicate banners.
            for row in claimed:
                row.status, row.error = 'unknown', 'Send outcome unknown'
        db.session.commit()
    tickets = PushDelivery.query.filter(PushDelivery.status == 'ticket', PushDelivery.retry_at <= now).limit(100).all()
    if tickets:
        try:
            receipts = expo_request('getReceipts', {'ids': [r.ticket_id for r in tickets]}).get('data', {})
            for row in tickets:
                receipt = receipts.get(row.ticket_id)
                if not receipt:
                    row.retry_at = now + timedelta(minutes=15)
                    continue
                row.status = 'accepted' if receipt.get('status') == 'ok' else 'failed'
                row.error = receipt.get('details', {}).get('error')
                if row.error == 'DeviceNotRegistered':
                    row.device.active = False
            db.session.commit()
        except Exception:
            db.session.rollback()
    return len(rows)

@bp.route('/api/cron/notifications')
def worker():
    secret = os.environ.get('CRON_SECRET')
    if not secret or not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + secret):
        abort(401)
    now = datetime.now(UTC).replace(tzinfo=None)
    if not db.session.get(NotificationWorkerLease, 'notifications'):
        try:
            db.session.add(NotificationWorkerLease(name='notifications', until=now - timedelta(seconds=1)))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    holder = str(uuid.uuid4())
    claim = db.session.execute(update(NotificationWorkerLease).where(NotificationWorkerLease.name == 'notifications', NotificationWorkerLease.until < now).values(holder=holder, until=now + timedelta(minutes=1)))
    db.session.commit()
    if not claim.rowcount:
        return jsonify(ok=True, busy=True)
    try:
        generate_events()
        processed = process_outbox()
        return jsonify(ok=True, processed=processed)
    finally:
        db.session.rollback()
        db.session.execute(update(NotificationWorkerLease).where(NotificationWorkerLease.name == 'notifications', NotificationWorkerLease.holder == holder).values(until=now))
        db.session.commit()
