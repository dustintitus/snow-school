"""Read-only availability feed for the school's Google Apps Script job.

Google verifies the job's identity on every request. No browser sessions,
passwords, Google access tokens, or permanent export keys are stored here.
"""
import json
import os
import re
from datetime import UTC, datetime

from flask import Blueprint, abort, jsonify, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from models import AppSetting, User, db
from staff_portal import StaffProfile, StaffAvailability, SEASON_START, SEASON_END

bp = Blueprint('availability_sync', __name__)
SETTING_KEY = 'google-availability-connection-v1'
WORKBOOK_ID = '1mXuoAM6OH8YxSKU0ZgSIFt3b8pUf9EB8z74WmHN5kOM'


def connection_settings():
    setting = db.session.get(AppSetting, SETTING_KEY)
    if setting is None:
        # Hosting config bootstraps the connection without depending on a
        # browser login. An explicit admin setting always takes precedence.
        return dict(audience=os.environ.get('GOOGLE_AVAILABILITY_AUDIENCE', '').strip(),
                    email=os.environ.get('GOOGLE_AVAILABILITY_EMAIL', '').strip().casefold(),
                    enabled=os.environ.get('GOOGLE_AVAILABILITY_ENABLED', '').casefold() == 'true',
                    workbook_id=WORKBOOK_ID)
    try:
        return json.loads(setting.value)
    except (TypeError, ValueError):
        return {}


def verify_google_identity(token, audience):
    # Import lazily so a disabled integration has no Google dependency at startup.
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import verify_oauth2_token

    transport = Request()

    def bounded_request(*args, **kwargs):
        kwargs['timeout'] = 10
        return transport(*args, **kwargs)

    return verify_oauth2_token(token, bounded_request, audience=audience)


@bp.route('/admin/integrations/availability', methods=['GET', 'POST'])
@login_required
def settings():
    if current_user.user_type != 'admin':
        abort(403)
    values = connection_settings()
    if request.method == 'POST':
        audience = request.form.get('audience', '').strip()
        email = request.form.get('email', '').strip().casefold()
        if not re.fullmatch(r'[A-Za-z0-9.-]{8,240}\.apps\.googleusercontent\.com', audience):
            abort(400, description='Enter the Google client ID reported by the availability script.')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 120:
            abort(400, description='Enter the Google account that owns the hourly trigger.')
        values = dict(audience=audience, email=email, enabled=request.form.get('enabled') == 'on',
                      workbook_id=WORKBOOK_ID, updated_by=current_user.id,
                      updated_at=datetime.now(UTC).isoformat())
        setting = db.session.get(AppSetting, SETTING_KEY)
        if setting is None:
            setting = AppSetting(key=SETTING_KEY)
            db.session.add(setting)
        setting.value = json.dumps(values)
        db.session.commit()
        flash('Google availability connection saved.', 'success')
        return redirect(url_for('availability_sync.settings'))
    return render_template('staff/availability_connection.html', values=values, workbook_id=WORKBOOK_ID)


@bp.route('/api/integrations/availability')
def export_availability():
    values = connection_settings()
    if not values.get('enabled') or not values.get('audience') or not values.get('email'):
        abort(503, description='Google availability connection is not enabled.')
    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer ') or len(authorization) > 12000:
        abort(401)
    token = authorization[7:]
    if not token or len(token.split('.')) != 3:
        abort(401)
    try:
        identity = verify_google_identity(token, values['audience'])
    except Exception:
        # Never log the bearer token or Google exception bodies containing it.
        abort(401)
    if identity.get('email_verified') is not True or identity.get('email', '').casefold() != values['email']:
        abort(403)
    if request.args.get('workbook') != WORKBOOK_ID:
        abort(403)
    records = (db.session.query(StaffAvailability, StaffProfile, User)
               .join(StaffProfile, StaffProfile.user_id == StaffAvailability.user_id)
               .join(User, User.id == StaffAvailability.user_id)
               .filter(User.user_type == 'instructor',
                       User.username.notin_(['instructor1', 'apple_review_coach'] +
                                            [f'demo_coach_{n}' for n in range(1, 6)]),
                       StaffProfile.availability_submitted_at.isnot(None),
                       StaffAvailability.day >= SEASON_START, StaffAvailability.day <= SEASON_END)
               .order_by(User.id, StaffAvailability.day).all())
    rows = [dict(user_id=user.id, name=user.full_name, email=user.email, date=slot.day.isoformat(),
                 weekday=slot.day.strftime('%A'), active=bool(profile.active), morning=bool(slot.morning),
                 afternoon=bool(slot.afternoon), evening=bool(slot.evening),
                 submitted_at=profile.availability_submitted_at.isoformat(timespec='seconds') + 'Z')
            for slot, profile, user in records]
    response = jsonify(schema_version=1, workbook_id=WORKBOOK_ID,
                       season_start=SEASON_START.isoformat(), season_end=SEASON_END.isoformat(),
                       exported_at=datetime.now(UTC).isoformat(), rows=rows)
    response.headers['Cache-Control'] = 'private, no-store'
    return response
