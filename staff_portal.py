"""Instructor self-service, auditable onboarding, and controlled family access.

All schema changes are additive tables, compatible with production create_all.
"""
import hashlib
import os
import secrets
import smtplib
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from io import BytesIO
from urllib.parse import urlparse
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for, send_file
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash
from vercel.blob import BlobClient
from models import db, User, Team, Evaluation, ParticipantMedia
from learning_models import PrivateLesson, SchoolGroup, ParticipantReport
from learning import today, field, parse_date, number

bp = Blueprint('staff_portal', __name__)
SEASON_START = date(2026, 12, 1)
SEASON_END = date(2027, 3, 30)
PERIODS = ('morning', 'afternoon', 'evening')
DOCUMENT_TYPES = ('CSIA', 'CASI', 'PSIC', 'Vulnerable sector check', 'Criminal background check', 'First aid', 'Annual dues', 'Contract', 'Other')


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)

class StaffProfile(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    phone = db.Column(db.String(50), default='')
    address = db.Column(db.String(500), default='')
    emergency_contact = db.Column(db.String(200), default='')
    discipline = db.Column(db.String(20), default='ski')
    active = db.Column(db.Boolean, nullable=False, default=True)
    availability_submitted_at = db.Column(db.DateTime)
    onboarding_seen_at = db.Column(db.DateTime)
    user = db.relationship('User')

class StaffDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    kind = db.Column(db.String(60), nullable=False)
    label = db.Column(db.String(160), nullable=False)
    expires_on = db.Column(db.Date)
    blob_url = db.Column(db.String(700), nullable=False)
    content_type = db.Column(db.String(80), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=lambda: utcnow(), nullable=False)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_at = db.Column(db.DateTime)

class StaffAvailability(db.Model):
    __table_args__ = (db.UniqueConstraint('user_id', 'day'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False, index=True)
    morning = db.Column(db.Boolean, nullable=False, default=False)
    afternoon = db.Column(db.Boolean, nullable=False, default=False)
    evening = db.Column(db.Boolean, nullable=False, default=False)
    user = db.relationship('User')

class OnboardingRequirement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    content = db.Column(db.Text, nullable=False)
    resource_url = db.Column(db.String(700), default='')
    revision = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, nullable=False, default=True)
    requires_training = db.Column(db.Boolean, nullable=False, default=False)

class OnboardingAcknowledgment(db.Model):
    __table_args__ = (db.UniqueConstraint('user_id', 'requirement_id', 'revision'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    requirement_id = db.Column(db.Integer, db.ForeignKey('onboarding_requirement.id'), nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    signed_name = db.Column(db.String(100), nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    note = db.Column(db.String(500), default='')
    acknowledged_at = db.Column(db.DateTime, nullable=False, default=lambda: utcnow())

class TrainingClearance(db.Model):
    __table_args__ = (db.UniqueConstraint('user_id', 'requirement_id', 'revision'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    requirement_id = db.Column(db.Integer, db.ForeignKey('onboarding_requirement.id'), nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=lambda: utcnow())

class ParticipantDetails(db.Model):
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    birthdate = db.Column(db.Date)
    special_needs = db.Column(db.Boolean, nullable=False, default=False)
    instructor_notes = db.Column(db.Text, default='')
    contact_name = db.Column(db.String(120), default='')
    phone = db.Column(db.String(50), default='')
    share_contact = db.Column(db.Boolean, nullable=False, default=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    student = db.relationship('User', foreign_keys=[student_id])

class PrivateParticipant(db.Model):
    __table_args__ = (db.UniqueConstraint('lesson_id', 'student_id'),)
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('private_lesson.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    student = db.relationship('User')

class StaffInvitation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    status = db.Column(db.String(30), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: utcnow())


def staff_only(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.user_type not in ('admin', 'instructor'): abort(403)
        return fn(*args, **kwargs)
    return wrapped


def admin_only():
    if current_user.user_type != 'admin': abort(403)


def profile_for(user_id):
    profile = db.session.get(StaffProfile, user_id)
    if profile is None:
        profile = StaffProfile(user_id=user_id)
        db.session.add(profile)
        db.session.flush()
    return profile


def active_staff(user_id):
    row = db.session.get(StaffProfile, user_id)
    return row is None or row.active


def private_access(student_id, user_id):
    return db.session.query(PrivateParticipant.id).join(PrivateLesson, PrivateParticipant.lesson_id == PrivateLesson.id).filter(
        PrivateParticipant.student_id == student_id, PrivateLesson.instructor_id == user_id,
        PrivateLesson.starts_at >= datetime.combine(today(), datetime.min.time()),
        PrivateLesson.starts_at < datetime.combine(today() + timedelta(days=1), datetime.min.time())).first() is not None


def onboarding(user_id, bundle=None):
    profile = bundle['profiles'][user_id] if bundle else profile_for(user_id)
    docs = bundle['documents'].get(user_id, []) if bundle else StaffDocument.query.filter_by(user_id=user_id).all()
    valid = [d for d in docs if d.reviewed_at and (not d.expires_on or d.expires_on >= today())]
    required_qualifications = {'CASI'} if profile.discipline == 'snowboard' else {'CSIA', 'PSIC'}
    if profile.discipline == 'both':
        qualification_done = any(d.kind in {'CSIA', 'PSIC'} for d in valid) and any(d.kind == 'CASI' for d in valid)
    else:
        qualification_done = any(d.kind in required_qualifications for d in valid)
    items = [dict(title='Contact information', done=bool(profile.phone and profile.address and profile.emergency_contact), href=url_for('staff_portal.profile', user_id=user_id)),
             dict(title='120-day winter availability', done=bool(profile.availability_submitted_at), href=url_for('staff_portal.availability', user_id=user_id)),
             dict(title='Certification reviewed', done=qualification_done, href=url_for('staff_portal.profile', user_id=user_id)),
             dict(title='Background check reviewed', done=any(d.kind in {'Vulnerable sector check', 'Criminal background check'} for d in valid), href=url_for('staff_portal.profile', user_id=user_id))]
    requirements = bundle['requirements'] if bundle else OnboardingRequirement.query.filter_by(active=True).order_by(OnboardingRequirement.id).all()
    for requirement in requirements:
        key = (user_id, requirement.id, requirement.revision)
        signed = bundle['acknowledgments'].get(key) if bundle else OnboardingAcknowledgment.query.filter_by(user_id=user_id, requirement_id=requirement.id, revision=requirement.revision).first()
        cleared = bundle['clearances'].get(key) if bundle else TrainingClearance.query.filter_by(user_id=user_id, requirement_id=requirement.id, revision=requirement.revision).first()
        items.append(dict(title=requirement.title, done=bool(signed), href=url_for('staff_portal.onboarding_page', user_id=user_id), requirement=requirement, signed=signed, cleared=cleared))
    return dict(items=items, done=sum(bool(item['done']) for item in items), total=len(items))


def onboarding_many(users):
    ids = [user.id for user in users]
    profiles = {row.user_id: row for row in StaffProfile.query.filter(StaffProfile.user_id.in_(ids)).all()}
    for user_id in ids:
        if user_id not in profiles:
            profiles[user_id] = StaffProfile(user_id=user_id)
            db.session.add(profiles[user_id])
    db.session.flush()
    documents = {}
    for row in StaffDocument.query.filter(StaffDocument.user_id.in_(ids)).all(): documents.setdefault(row.user_id, []).append(row)
    requirements = OnboardingRequirement.query.filter_by(active=True).order_by(OnboardingRequirement.id).all()
    acknowledgments = {(row.user_id, row.requirement_id, row.revision): row for row in OnboardingAcknowledgment.query.filter(OnboardingAcknowledgment.user_id.in_(ids)).all()}
    clearances = {(row.user_id, row.requirement_id, row.revision): row for row in TrainingClearance.query.filter(TrainingClearance.user_id.in_(ids)).all()}
    bundle = dict(profiles=profiles, documents=documents, requirements=requirements, acknowledgments=acknowledgments, clearances=clearances)
    return {user_id: onboarding(user_id, bundle) for user_id in ids}


@bp.app_context_processor
def helpers():
    return dict(participant_support=participant_support, staff_onboarding=onboarding)


def participant_support(student_id):
    details = db.session.get(ParticipantDetails, student_id)
    if not details: return None
    if current_user.user_type == 'admin': return details
    from app import instructor_can_access_student
    student = db.session.get(User, student_id)
    if current_user.user_type != 'instructor' or not instructor_can_access_student(student): return None
    if not details.special_needs: return None
    # Never hand the template the unshared phone or DOB.
    return dict(special_needs=True, instructor_notes=details.instructor_notes,
                phone=details.phone if details.share_contact else '',
                contact_name=details.contact_name if details.share_contact else '')


@bp.before_app_request
def inactive_account():
    if current_user.is_authenticated and current_user.user_type == 'instructor' and not active_staff(current_user.id):
        if request.endpoint not in ('logout', 'static', 'privacy', 'support'):
            abort(403, description='This instructor account is inactive. Contact school administration.')


@bp.route('/coach/classes')
@staff_only
def classes():
    from operations import ClassCoverage
    if current_user.user_type != 'instructor': return redirect(url_for('dashboard'))
    coverage = ClassCoverage.query.filter_by(instructor_id=current_user.id).all()
    teams = Team.query.filter(db.or_(Team.instructor_id == current_user.id, Team.id.in_([c.team_id for c in coverage]))).order_by(Team.name).all()
    school_ids = {g.team_id for g in SchoolGroup.query.all()}
    lessons = PrivateLesson.query.filter_by(instructor_id=current_user.id).order_by(PrivateLesson.starts_at.desc()).all()
    from app import supervised_teams_for_current_user
    return render_template('staff/classes.html', supervised_teams=supervised_teams_for_current_user(), selected_date=today(), teams=teams, school_ids=school_ids, lessons=lessons, coverage=coverage)


@bp.route('/coach/profile', methods=['GET', 'POST'])
@bp.route('/staff/<int:user_id>/profile', methods=['GET', 'POST'])
@staff_only
def profile(user_id=None):
    user_id = user_id or current_user.id
    if user_id != current_user.id: admin_only()
    user = db.get_or_404(User, user_id)
    if user.user_type != 'instructor': abort(404)
    profile = profile_for(user_id)
    if request.method == 'POST':
        if request.form.get('action') == 'review':
            admin_only()
            document = db.get_or_404(StaffDocument, number('document_id', 1, 2**31-1))
            if document.user_id != user_id: abort(400)
            document.reviewed_by = current_user.id
            document.reviewed_at = utcnow()
        elif request.form.get('action') == 'upload':
            kind = field('kind', 60)
            if kind not in DOCUMENT_TYPES: abort(400)
            capture = request.files.get('document')
            if not capture: abort(400, description='Choose a document.')
            data = capture.read(3 * 1024 * 1024 + 1)
            mime = capture.mimetype
            valid = {'application/pdf': data.startswith(b'%PDF-'), 'image/jpeg': data.startswith(b'\xff\xd8\xff'), 'image/png': data.startswith(b'\x89PNG\r\n\x1a\n')}
            if len(data) > 3 * 1024 * 1024 or not valid.get(mime): abort(400, description='Upload a PDF, JPEG, or PNG up to 3 MB.')
            expiry = parse_date('expires_on') if request.form.get('expires_on') else None
            label = field('label', 160)
            try:
                blob = BlobClient().put(f'staff/{user_id}/{secrets.token_hex(16)}', data, access='private', content_type=mime)
            except Exception:
                abort(503, description='Document storage is unavailable. Please try again.')
            db.session.add(StaffDocument(user_id=user_id, kind=kind, label=label, expires_on=expiry, blob_url=blob.url, content_type=mime))
        else:
            name, email = field('full_name', 100), field('email', 120).lower()
            if '@' not in email or User.query.filter(User.email == email, User.id != user_id).first(): abort(400, description='Enter an available email address.')
            discipline = field('discipline', 20)
            if discipline not in ('ski', 'snowboard', 'both'): abort(400)
            user.full_name, user.email = name, email
            profile.phone, profile.address = field('phone', 50), field('address', 500)
            profile.emergency_contact, profile.discipline = field('emergency_contact', 200), discipline
            if current_user.user_type == 'admin': profile.active = request.form.get('active') == 'on'
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('staff_portal.profile', user_id=user_id))
    return render_template('staff/profile.html', user=user, profile=profile, documents=StaffDocument.query.filter_by(user_id=user_id).order_by(StaffDocument.id.desc()).all(), kinds=DOCUMENT_TYPES, progress=onboarding(user_id), today=today())


@bp.route('/staff/documents/<int:document_id>')
@staff_only
def document(document_id):
    row = db.get_or_404(StaffDocument, document_id)
    if current_user.id != row.user_id: admin_only()
    try: blob = BlobClient().get(row.blob_url, access='private', use_cache=False)
    except Exception: abort(503)
    if not blob or blob.status_code != 200: abort(404)
    response = current_app.response_class(blob.content, mimetype=row.content_type)
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Content-Disposition'] = 'inline; filename="staff-document' + {'application/pdf':'.pdf', 'image/jpeg':'.jpg', 'image/png':'.png'}[row.content_type] + '"'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@bp.route('/coach/availability', methods=['GET', 'POST'])
@bp.route('/staff/<int:user_id>/availability', methods=['GET', 'POST'])
@staff_only
def availability(user_id=None):
    user_id = user_id or current_user.id
    if user_id != current_user.id: admin_only()
    user = db.get_or_404(User, user_id)
    if user.user_type != 'instructor': abort(404)
    days = [SEASON_START + timedelta(days=n) for n in range((SEASON_END - SEASON_START).days + 1)]
    rows = {r.day: r for r in StaffAvailability.query.filter_by(user_id=user_id).all()}
    if request.method == 'POST':
        if request.form.get('reviewed') != 'on': abort(400, description='Confirm you reviewed the entire winter schedule.')
        allowed = {f'{day.isoformat()}_{period}' for day in days for period in PERIODS}
        values = set(request.form.getlist('slots'))
        if values - allowed: abort(400, description='Availability must be within the winter season.')
        for day in days:
            row = rows.get(day)
            if row is None:
                row = StaffAvailability(user_id=user_id, day=day); db.session.add(row)
            for period in PERIODS: setattr(row, period, f'{day.isoformat()}_{period}' in values)
        profile_for(user_id).availability_submitted_at = utcnow()
        db.session.commit()
        flash('Winter availability saved. Unselected periods are unavailable.', 'success')
        return redirect(url_for('staff_portal.availability', user_id=user_id))
    months = {}
    for day in days:
        months.setdefault((day.year, day.month), []).append(day)
    return render_template('staff/availability.html', user=user, days=days, months=list(months.values()), rows=rows, periods=PERIODS)


@bp.route('/coach/onboarding', methods=['GET', 'POST'])
@bp.route('/staff/<int:user_id>/onboarding', methods=['GET', 'POST'])
@staff_only
def onboarding_page(user_id=None):
    user_id = user_id or current_user.id
    if user_id != current_user.id: admin_only()
    user = db.get_or_404(User, user_id)
    if user.user_type != 'instructor': abort(404)
    if request.method == 'POST':
        requirement = db.get_or_404(OnboardingRequirement, number('requirement_id', 1, 2**31-1))
        if not requirement.active or request.form.get('revision') != str(requirement.revision): abort(409, description='This document changed. Read the latest revision.')
        action = request.form.get('action')
        if action == 'clear_training':
            admin_only()
            if not TrainingClearance.query.filter_by(user_id=user_id, requirement_id=requirement.id, revision=requirement.revision).first():
                db.session.add(TrainingClearance(user_id=user_id, requirement_id=requirement.id, revision=requirement.revision, recorded_by=current_user.id))
        else:
            if requirement.requires_training and not TrainingClearance.query.filter_by(user_id=user_id, requirement_id=requirement.id, revision=requirement.revision).first(): abort(400, description='An administrator must confirm training before this SOP can be acknowledged.')
            if request.form.get('acknowledge') != 'on': abort(400)
            name = field('signed_name', 100)
            note = field('note', 500) if current_user.user_type == 'admin' else ''
            if not OnboardingAcknowledgment.query.filter_by(user_id=user_id, requirement_id=requirement.id, revision=requirement.revision).first():
                db.session.add(OnboardingAcknowledgment(user_id=user_id, requirement_id=requirement.id, revision=requirement.revision, signed_name=name, recorded_by=current_user.id, note=note))
        db.session.commit()
        return redirect(url_for('staff_portal.onboarding_page', user_id=user_id))
    profile_for(user_id).onboarding_seen_at = utcnow()
    progress = onboarding(user_id)
    db.session.commit()
    return render_template('staff/onboarding.html', user=user, progress=progress)


@bp.route('/admin/staff', methods=['GET', 'POST'])
@staff_only
def staff_admin():
    admin_only()
    if request.method == 'POST':
        requirement_id = request.form.get('requirement_id')
        row = db.get_or_404(OnboardingRequirement, number('requirement_id', 1, 2**31-1)) if requirement_id else OnboardingRequirement()
        title, content = field('title', 160), field('content', 12000)
        resource = request.form.get('resource_url', '').strip()
        if resource and (urlparse(resource).scheme != 'https' or not urlparse(resource).netloc or len(resource) > 700): abort(400, description='Use a complete HTTPS resource link.')
        training = request.form.get('requires_training') == 'on'
        active = request.form.get('active') == 'on'
        if row.id and (row.title, row.content, row.resource_url, row.requires_training, row.active) != (title, content, resource, training, active): row.revision += 1
        row.title, row.content, row.resource_url, row.requires_training, row.active = title, content, resource, training, active
        db.session.add(row); db.session.flush()
        if not RequirementRevision.query.filter_by(requirement_id=row.id, revision=row.revision).first():
            db.session.add(RequirementRevision(requirement_id=row.id, revision=row.revision, title=row.title, content=row.content, resource_url=row.resource_url, requires_training=row.requires_training, recorded_by=current_user.id))
        db.session.commit()
        return redirect(url_for('.staff_admin'))
    status = request.args.get('status', 'active')
    inactive_ids = {row.user_id for row in StaffProfile.query.filter_by(active=False).all()}
    users = [u for u in User.query.filter_by(user_type='instructor').order_by(User.full_name).all() if status == 'all' or (u.id not in inactive_ids) == (status != 'inactive')]
    progress = onboarding_many(users)
    invitations = {}
    for row in StaffInvitation.query.order_by(StaffInvitation.id.desc()).all(): invitations.setdefault(row.user_id, row)
    db.session.commit()
    return render_template('staff/admin.html', users=users, progress=progress, requirements=OnboardingRequirement.query.order_by(OnboardingRequirement.id).all(), status=status, invitations=invitations)


@bp.route('/admin/availability')
@staff_only
def admin_availability():
    admin_only()
    try: day = date.fromisoformat(request.args.get('date', SEASON_START.isoformat()))
    except ValueError: abort(400)
    users = [u for u in User.query.filter_by(user_type='instructor').order_by(User.full_name).all() if active_staff(u.id)]
    rows = {r.user_id: r for r in StaffAvailability.query.filter_by(day=day).all()}
    profiles = {u.id: profile_for(u.id) for u in users}
    totals = {discipline: {period: sum(bool(rows.get(u.id) and getattr(rows[u.id], period)) for u in users if profiles[u.id].discipline in (discipline, 'both')) for period in PERIODS} for discipline in ('ski', 'snowboard')}
    db.session.commit()
    return render_template('staff/admin_availability.html', users=users, rows=rows, profiles=profiles, totals=totals, day=day, periods=PERIODS, start=SEASON_START, end=SEASON_END)


@bp.route('/admin/participants/<int:student_id>/support', methods=['GET', 'POST'])
@staff_only
def support(student_id):
    admin_only()
    student = db.get_or_404(User, student_id)
    if student.user_type != 'student': abort(404)
    details = db.session.get(ParticipantDetails, student_id)
    if request.method == 'POST':
        birthdate = parse_date('birthdate') if request.form.get('birthdate') else None
        if birthdate and birthdate > today(): abort(400)
        if details is None:
            details = ParticipantDetails(student_id=student_id); db.session.add(details)
        details.birthdate = birthdate
        details.special_needs = request.form.get('special_needs') == 'on'
        details.share_contact = details.special_needs and request.form.get('share_contact') == 'on'
        details.instructor_notes = request.form.get('instructor_notes', '').strip()[:2000]
        details.contact_name = request.form.get('contact_name', '').strip()[:120]
        details.phone = request.form.get('phone', '').strip()[:50]
        details.updated_by = current_user.id
        db.session.commit()
        return redirect(url_for('.support', student_id=student_id))
    return render_template('staff/support.html', student=student, details=details)


def send_invitation(user):
    """Single-use setup link, never email a reusable password or persist a raw token."""
    token = secrets.token_urlsafe(32)
    StaffInvitation.query.filter_by(user_id=user.id, used_at=None).update({'used_at': utcnow()})
    row = StaffInvitation(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=utcnow() + timedelta(days=7))
    db.session.add(row); db.session.commit()
    host, sender = os.environ.get('SMTP_HOST'), os.environ.get('SMTP_FROM')
    origin = os.environ.get('PUBLIC_APP_URL', 'https://snowschool.app').rstrip('/')
    if not host or not sender:
        row.status = 'not_configured'; db.session.commit(); return row.status
    message = EmailMessage()
    delivery_email=user.email
    if user.email.endswith('@staff.snowschool.invalid'):
        from roster_imports import ImportPerson
        imported=ImportPerson.query.filter_by(user_id=user.id,role='instructor').first()
        delivery_email=imported.source_facts.get('email','') if imported else ''
        if not delivery_email:
            row.status='failed';db.session.commit();return row.status
    message['From'], message['To'], message['Subject'] = sender, delivery_email, 'Welcome to Snow School - set up your instructor account'
    message.set_content(f'Hi {user.full_name},\n\nYour username is {user.username}. Set your password using this link within seven days:\n{origin}/welcome/{token}\n\nThen complete your profile, winter availability and onboarding checklist.\n')
    try:
        with smtplib.SMTP(host, int(os.environ.get('SMTP_PORT', '587')), timeout=10) as smtp:
            smtp.starttls()
            if os.environ.get('SMTP_USERNAME'): smtp.login(os.environ['SMTP_USERNAME'], os.environ.get('SMTP_PASSWORD', ''))
            smtp.send_message(message)
        row.status = 'accepted'
    except Exception:
        row.status = 'failed'
    db.session.commit()
    return row.status


@bp.route('/staff/<int:user_id>/invite', methods=['POST'])
@staff_only
def invite(user_id):
    admin_only()
    user = db.get_or_404(User, user_id)
    if user.user_type != 'instructor' or not active_staff(user_id): abort(400)
    status = send_invitation(user)
    flash('Welcome email accepted by the mail server.' if status == 'accepted' else 'Welcome email not sent. Check mail configuration and retry.', 'success' if status == 'accepted' else 'error')
    return redirect(url_for('.staff_admin'))


@bp.route('/welcome/<token>', methods=['GET', 'POST'])
def welcome(token):
    row = StaffInvitation.query.filter_by(token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if not row or row.used_at or row.expires_at < utcnow() or not active_staff(row.user_id): abort(404)
    user = db.session.get(User, row.user_id)
    if user.user_type != 'instructor': abort(404)
    if request.method == 'POST':
        password = request.form.get('password', '')
        if len(password) < 12 or password != request.form.get('confirm_password'): abort(400, description='Enter matching passwords of at least 12 characters.')
        # Atomic consumption prevents concurrent reuse of an invitation.
        consumed = StaffInvitation.query.filter_by(id=row.id, used_at=None).update({'used_at': utcnow()})
        if not consumed: abort(409)
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash('Password set. Sign in to complete your onboarding.', 'success')
        return redirect(url_for('login'))
    return render_template('staff/welcome.html', user=user)


@bp.route('/parent/lookup', methods=['GET', 'POST'])
@login_required
def parent_lookup():
    if current_user.user_type != 'parent': abort(403)
    if request.method == 'POST':
        birthday = parse_date('birthdate')
        name = field('participant_name', 100).casefold()
        matches = [child for child in current_user.children if child.full_name.strip().casefold() == name and (details := db.session.get(ParticipantDetails, child.id)) and details.birthdate == birthday]
        if len(matches) == 1: return redirect(url_for('parent_child_evaluations', student_id=matches[0].id))
        flash('We could not match a participant linked to your account. Contact the school for help.', 'error')
    return render_template('staff/parent_lookup.html')


@bp.route('/participants/<int:student_id>/certificate/<int:report_id>')
@login_required
def certificate(student_id, report_id):
    from app import can_access_participant
    student = db.get_or_404(User, student_id)
    row = db.get_or_404(ParticipantReport, report_id)
    if not can_access_participant(student): abort(403)
    if row.student_id != student.id or not row.issued_at: abort(404)
    # Certificates attest to program completion only after explicit admin approval.
    completion = db.session.get(CompletionApproval, row.id)
    if not completion: abort(404)
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from xml.sax.saxutils import escape
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Certificate', fontSize=32, leading=40, alignment=1, textColor=colors.HexColor('#174862')))
    styles.add(ParagraphStyle(name='Centered', fontSize=17, leading=26, alignment=1))
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=65, bottomMargin=45)
    story = [Paragraph('SNOW SCHOOL', styles['Centered']), Spacer(1, 24), Paragraph('Certificate of Completion', styles['Certificate']), Spacer(1, 28), Paragraph(escape(student.full_name), styles['Certificate']), Spacer(1, 18), Paragraph(escape(row.snapshot['name']), styles['Centered']), Paragraph(escape(row.snapshot.get('class', '')) + ' | ' + escape(row.season), styles['Centered']), Spacer(1, 26), Paragraph('Completed ' + completion.completed_on.strftime('%B %d, %Y'), styles['Centered']), Paragraph('Evaluation and next steps are available in your family portal.', styles['Centered'])]
    doc.build(story); buffer.seek(0)
    response = send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=f'snow-school-certificate-{row.id}.pdf')
    response.headers['Cache-Control'] = 'private, no-store'
    return response

class CompletionApproval(db.Model):
    report_id = db.Column(db.Integer, db.ForeignKey('participant_report.id'), primary_key=True)
    completed_on = db.Column(db.Date, nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    approved_at = db.Column(db.DateTime, nullable=False, default=lambda: utcnow())


@bp.route('/reports/<int:report_id>/completion', methods=['POST'])
@staff_only
def approve_completion(report_id):
    admin_only()
    row = db.get_or_404(ParticipantReport, report_id)
    if not row.issued_at: abort(400, description='Issue the evaluation report before approving completion.')
    day = parse_date('completed_on')
    if day > today(): abort(400)
    if not db.session.get(CompletionApproval, row.id): db.session.add(CompletionApproval(report_id=row.id, completed_on=day, approved_by=current_user.id))
    db.session.commit()
    return redirect(url_for('learning.report', report_id=row.id))

@bp.app_template_global('completion_approval')
def completion_approval(report_id):
    return db.session.get(CompletionApproval, report_id)

@bp.app_template_global('private_participants')
def private_participants(lesson_id):
    lesson = db.session.get(PrivateLesson, lesson_id)
    if current_user.user_type != 'admin' and (not lesson or lesson.instructor_id != current_user.id): return []
    return PrivateParticipant.query.filter_by(lesson_id=lesson_id).all()

class RequirementRevision(db.Model):
    __table_args__ = (db.UniqueConstraint('requirement_id', 'revision'),)
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('onboarding_requirement.id'), nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    content = db.Column(db.Text, nullable=False)
    resource_url = db.Column(db.String(700), default='')
    requires_training = db.Column(db.Boolean, nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=lambda: utcnow())

@bp.route('/admin/requirements/<int:requirement_id>/history')
@staff_only
def requirement_history(requirement_id):
    admin_only()
    requirement = db.get_or_404(OnboardingRequirement, requirement_id)
    revisions = RequirementRevision.query.filter_by(requirement_id=requirement_id).order_by(RequirementRevision.revision.desc()).all()
    acknowledgments = OnboardingAcknowledgment.query.filter_by(requirement_id=requirement_id).order_by(OnboardingAcknowledgment.acknowledged_at.desc()).all()
    return render_template('staff/requirement_history.html', requirement=requirement, revisions=revisions, acknowledgments=acknowledgments)

@bp.route('/coach/privates/<int:lesson_id>')
@staff_only
def private_workspace(lesson_id):
    lesson = db.get_or_404(PrivateLesson, lesson_id)
    if current_user.user_type != 'admin' and lesson.instructor_id != current_user.id: abort(403)
    from app import student_has_media_consent
    links = PrivateParticipant.query.filter_by(lesson_id=lesson.id).all()
    students = [link.student for link in links]
    # Capture is restricted to the instructor on the scheduled lesson day.
    can_capture = current_user.user_type == 'instructor' and lesson.starts_at.date() == today()
    consent = {student.id: can_capture and student_has_media_consent(student) for student in students}
    return render_template('staff/private_workspace.html', lesson=lesson, students=students, media_consent=consent)
