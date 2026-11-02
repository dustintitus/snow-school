"""Daily staffing and roster operations shared by web and the native portal."""
import json
import uuid
from flask import Blueprint, abort, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from models import db, AppSetting, Team, User, Program, Enrollment

bp = Blueprint('operations', __name__, url_prefix='/operations')

class ClassCoverage(db.Model):
    __table_args__ = (db.UniqueConstraint('team_id', 'session_date', name='uq_coverage_team_date'),)
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.String(500), nullable=False)

class RosterMove(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    from_team_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    to_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    moved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())

@bp.app_template_global('operation_setting')
def setting(key, default=None):
    row = db.session.get(AppSetting, key)
    return json.loads(row.value) if row else default

def save_setting(key, value):
    row = db.session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key); db.session.add(row)
    row.value = json.dumps(value)

def daily_instructor(team, day):
    row = ClassCoverage.query.filter_by(team_id=team.id, session_date=day).first()
    return row.instructor_id if row else team.instructor_id

def assigned_teams(user_id, day):
    return [team for team in Team.query.order_by(Team.name).all() if daily_instructor(team, day) == user_id]

def notify(title, body, ids):
    from notifications import create_message
    create_message('schedule', title, body, ids, 'operations:' + str(uuid.uuid4()), author=current_user.id)

def qualification_check(team, instructor, override):
    minimum = setting(f'program-operations:{team.program_id}', {}).get('minimum_level', 0)
    level = setting(f'instructor-level:{instructor.id}', 0)
    if level < minimum:
        if not override:
            abort(400, description='Instructor is below the program minimum. Enter a supervisor override reason to continue.')
        if len(override) > 250: abort(400, description='Override reason must be at most 250 characters.')
        save_setting('qualification-override:' + str(uuid.uuid4()), dict(team_id=team.id, program_id=team.program_id, instructor_id=instructor.id, minimum_level=minimum, level=level, reason=override, approved_by=current_user.id))

@bp.route('/', methods=['GET', 'POST'])
@login_required
def manage():
    from learning import number, field, parse_date, instructor_field, season, today
    if current_user.user_type != 'admin': abort(403)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'coverage':
            team = db.get_or_404(Team, number('team_id', 1, 2**31-1))
            day = parse_date('session_date')
            instructor = instructor_field()
            reason = field('reason', 500)
            qualification_check(team, instructor, request.form.get('override_reason', '').strip())
            old = daily_instructor(team, day)
            row = ClassCoverage.query.filter_by(team_id=team.id, session_date=day).first()
            if not row:
                row = ClassCoverage(team_id=team.id, session_date=day); db.session.add(row)
            row.instructor_id = instructor.id; row.assigned_by = current_user.id
            row.reason = reason + (' | Override: ' + request.form['override_reason'].strip() if request.form.get('override_reason', '').strip() else '')
            if len(row.reason) > 500: abort(400, description='Combined reasons must be at most 500 characters.')
            notify('Class coverage assigned', f'{team.name}: coverage on {day.isoformat()}. Open Today for the roster.', [old, instructor.id])
        elif action == 'cancel_coverage':
            row = db.get_or_404(ClassCoverage, number('coverage_id', 1, 2**31-1))
            team = db.session.get(Team, row.team_id)
            notify('Class coverage cancelled', f'{team.name}: regular instructor restored for {row.session_date.isoformat()}.', [row.instructor_id, team.instructor_id])
            db.session.delete(row)
        elif action == 'move':
            student = db.get_or_404(User, number('student_id', 1, 2**31-1))
            if student.user_type != 'student': abort(400)
            team = db.get_or_404(Team, number('team_id', 1, 2**31-1))
            if student.team_id == team.id: abort(400, description='Participant is already in this class.')
            reason = field('reason', 500)
            old_team = student.team
            db.session.add(RosterMove(student_id=student.id, from_team_id=student.team_id, to_team_id=team.id, moved_by=current_user.id, reason=reason))
            old_enrollments = Enrollment.query.filter_by(student_id=student.id, season=season()).all()
            for enrollment in old_enrollments:
                if old_team and enrollment.team_id == old_team.id and enrollment.program_id != team.program_id:
                    enrollment.status = 'transferred'
            enrollment = Enrollment.query.filter_by(student_id=student.id, program_id=team.program_id, season=season()).first()
            if not enrollment:
                enrollment = Enrollment(student_id=student.id, program_id=team.program_id, season=season()); db.session.add(enrollment)
            enrollment.team_id = team.id; enrollment.status = 'registered'; enrollment.completed_at = None
            student.team = team; student.instructor_id = team.instructor_id
            db.session.flush()
            from app import update_student_participation_from_team
            update_student_participation_from_team(student)
            notify('Class roster updated', 'A participant changed classes. Open your roster to review the change.', [team.instructor_id, daily_instructor(team, today())] + ([old_team.instructor_id, daily_instructor(old_team, today())] if old_team else []))
        elif action == 'qualification':
            instructor = instructor_field()
            save_setting(f'instructor-level:{instructor.id}', number('level', 0, 4))
        elif action == 'program':
            program = db.get_or_404(Program, number('program_id', 1, 2**31-1))
            mode = request.form.get('placement')
            if mode not in ('manual', 'automatic'): abort(400)
            team_id = request.form.get('default_team_id', '')
            team = db.get_or_404(Team, int(team_id)) if team_id.isdigit() else None
            if mode == 'automatic' and (not team or team.program_id != program.id):
                abort(400, description='Automatic placement needs a default class belonging to this program.')
            save_setting(f'program-operations:{program.id}', dict(minimum_level=number('minimum_level', 0, 4), placement=mode, default_team_id=team.id if mode == 'automatic' else None))
        else: abort(400)
        db.session.commit()
        return redirect(url_for('.manage'))
    return render_template('admin/operations.html', teams=Team.query.order_by(Team.name).all(), instructors=User.query.filter_by(user_type='instructor').order_by(User.full_name).all(), students=User.query.filter_by(user_type='student').order_by(User.full_name).all(), programs=Program.query.order_by(Program.name).all(), setting=setting, today=today(), coverage=ClassCoverage.query.order_by(ClassCoverage.session_date.desc()).limit(30).all(), moves=RosterMove.query.order_by(RosterMove.id.desc()).limit(30).all())
