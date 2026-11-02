"""Source-backed progression, training and school-group workflows."""
import json
import re
import secrets
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash
from models import db, User, Team, Program, ProgramProfile, Enrollment
from learning_models import (SkillObservation, ParticipantReport, TrainingWeek, TrainingReview,
    TrainingAttendance, SchoolGroup, GroupAssignment, PrivateLesson, Incident)

bp = Blueprint('learning', __name__, url_prefix='/learning')
DATA = Path(__file__).parent / 'curriculum'
CARDS = json.loads((DATA / 'cards.json').read_text())
MANUAL = json.loads((DATA / 'manual.json').read_text())
TRAINING = json.loads((DATA / 'training.json').read_text())
STATUSES = ('attempted', 'learning', 'mastered')

@bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'private, no-store'
    return response

def today():
    return datetime.now(ZoneInfo('America/Toronto')).date()

def season():
    from app import CURRENT_SEASON
    return CURRENT_SEASON

def staff(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.user_type not in ('admin', 'instructor'):
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def admin():
    if current_user.user_type != 'admin': abort(403)

def student_access(student_id, writing=False):
    from app import can_access_participant
    student = db.get_or_404(User, student_id)
    if student.user_type != 'student' or not can_access_participant(student): abort(403)
    if writing and current_user.user_type not in ('admin', 'instructor'): abort(403)
    return student

def team_access(team_id):
    team = db.get_or_404(Team, team_id)
    from app import instructor_owns_team
    if current_user.user_type != 'admin' and not instructor_owns_team(team): abort(403)
    return team

def field(name, limit=4000):
    value = request.form.get(name, '').strip()
    if not value or len(value) > limit: abort(400, description=f'{name.replace("_", " ")} is required (maximum {limit} characters).')
    return value

def number(name, low, high):
    try: value = int(request.form.get(name, ''))
    except (TypeError, ValueError): abort(400, description=f'{name} must be a whole number.')
    if not low <= value <= high: abort(400, description=f'{name} must be between {low} and {high}.')
    return value

def parse_date(name, future=True):
    try: value = date.fromisoformat(request.form.get(name, ''))
    except ValueError: abort(400, description='Enter a valid date.')
    if not future and value > today(): abort(400, description='Observations cannot be dated in the future.')
    return value

def instructor_field():
    user = db.get_or_404(User, number('instructor_id', 1, 2**31-1))
    if user.user_type != 'instructor': abort(400, description='Select an instructor.')
    return user

def seed_training():
    for item in TRAINING:
        if not TrainingWeek.query.filter_by(season=season(), week=item['week']).first():
            db.session.add(TrainingWeek(season=season(), week=item['week'], title=item['title'], content=item['content']))
    db.session.commit()

def unlocked(week):
    return week.published and week.release_date is not None and week.release_date <= today()

def observations(student_id, card_key):
    return SkillObservation.query.filter_by(student_id=student_id, season=season(), card_key=card_key).order_by(SkillObservation.session_date.desc(), SkillObservation.id.desc()).all()

def latest_rows(student_id, card_key):
    latest = {}
    for row in observations(student_id, card_key): latest.setdefault(row.skill_id, row)
    return latest

@bp.route('/')
@staff
def hub():
    weeks = TrainingWeek.query.filter_by(season=season()).order_by(TrainingWeek.week).all()
    from operations import assigned_teams
    teams = Team.query.all() if current_user.user_type == 'admin' else assigned_teams(current_user.id, today())
    groups = SchoolGroup.query.filter_by(season=season()).all()
    groups = [g for g in groups if current_user.user_type == 'admin' or g.team in teams]
    private = PrivateLesson.query if current_user.user_type == 'admin' else PrivateLesson.query.filter_by(instructor_id=current_user.id)
    private = private.filter(PrivateLesson.starts_at >= datetime.combine(today(), datetime.min.time())).order_by(PrivateLesson.starts_at).all()
    return render_template('learning/hub.html', weeks=weeks, unlocked=unlocked, groups=groups, teams=teams, lessons=private, season=season())

@bp.route('/manual')
@staff
def manual():
    pages = []
    for source in MANUAL:
        # PDF folios and detached contents numbers are not manual content.
        text = '\n'.join(line for line in source['text'].splitlines()
                         if not re.fullmatch(r'\s*\d+\s*', line))
        pages.append(dict(source, text=text))
    return render_template('learning/manual.html', pages=pages, query=request.args.get('q','').strip())

@bp.route('/app-guide')
@staff
def app_guide():
    return render_template('learning/app_guide.html')

@bp.route('/training', methods=['GET', 'POST'])
@staff
def training():
    if request.method == 'POST':
        admin()
        seed_training()
        return redirect(url_for('.training'))
    weeks = TrainingWeek.query.filter_by(season=season()).order_by(TrainingWeek.week).all()
    instructors = User.query.filter_by(user_type='instructor').order_by(User.full_name).all() if current_user.user_type == 'admin' else [current_user]
    reviews = {(r.week_id,r.instructor_id,r.revision):r for r in TrainingReview.query.join(TrainingWeek, TrainingReview.week_id==TrainingWeek.id).filter(TrainingWeek.season==season()).all()}
    attendance = {(r.week_id,r.instructor_id):r for r in TrainingAttendance.query.join(TrainingWeek, TrainingAttendance.week_id==TrainingWeek.id).filter(TrainingWeek.season==season()).all()}
    return render_template('learning/training.html', weeks=weeks, instructors=instructors, reviews=reviews, attendance=attendance, unlocked=unlocked, season=season())

@bp.route('/training/<int:week_id>', methods=['GET', 'POST'])
@staff
def week(week_id):
    week = db.get_or_404(TrainingWeek, week_id)
    if week.season != season(): abort(404)
    if current_user.user_type != 'admin' and not unlocked(week): abort(403)
    if request.method == 'POST':
        admin()
        # Revision increases on any edit: prior acknowledgments remain auditable.
        expected = number('revision',1,2**31-1)
        if expected != week.revision: abort(409, description='This week was edited. Reload before saving.')
        week.title = field('title',160)
        week.content = field('content',20000)
        week.announcement = request.form.get('announcement','').strip()[:4000]
        week.release_date = parse_date('release_date')
        week.published = request.form.get('published') == 'on'
        week.revision += 1
        db.session.commit()
        flash('Week saved. Instructors must acknowledge this revision when it is released.', 'success')
        return redirect(url_for('.week',week_id=week.id))
    source = TRAINING[week.week-1]
    reviewed = TrainingReview.query.filter_by(week_id=week.id,instructor_id=current_user.id,revision=week.revision).first()
    return render_template('learning/week.html', week=week, source=source, reviewed=reviewed, unlocked=unlocked)

@bp.route('/training/<int:week_id>/review', methods=['POST'])
@staff
def review(week_id):
    week = db.get_or_404(TrainingWeek, week_id)
    if current_user.user_type != 'instructor' or week.season != season() or not unlocked(week): abort(403)
    if number('revision',1,2**31-1) != week.revision: abort(409,description='Content changed; read the current revision first.')
    if not TrainingReview.query.filter_by(week_id=week.id,instructor_id=current_user.id,revision=week.revision).first():
        db.session.add(TrainingReview(week_id=week.id,instructor_id=current_user.id,revision=week.revision))
        db.session.commit()
    return redirect(url_for('.week',week_id=week.id))

@bp.route('/training/<int:week_id>/attendance', methods=['POST'])
@staff
def training_attendance(week_id):
    admin()
    week = db.get_or_404(TrainingWeek, week_id)
    if week.season != season(): abort(404)
    instructor = instructor_field()
    status = field('status',20)
    if status not in ('present','absent','excused'): abort(400)
    row = TrainingAttendance.query.filter_by(week_id=week.id,instructor_id=instructor.id).first()
    if row is None:
        row = TrainingAttendance(week_id=week.id,instructor_id=instructor.id)
        db.session.add(row)
    row.status, row.recorded_by = status, current_user.id
    db.session.commit()
    return redirect(url_for('.training'))

@bp.route('/participants/<int:student_id>', methods=['GET','POST'])
@staff
def progression(student_id):
    student = student_access(student_id, writing=True)
    key = request.values.get('card','ski-1')
    if key not in CARDS: abort(400)
    card = CARDS[key]
    if request.method == 'POST':
        skill_id = field('skill_id',60)
        if skill_id not in {r['id'] for r in card['rows']}: abort(400)
        status = field('status',30)
        if status not in STATUSES: abort(400)
        achieved=attempted=None
        if request.form.get('achieved') or request.form.get('attempted'):
            attempted = number('attempted',1,10000)
            achieved = number('achieved',0,attempted)
        db.session.add(SkillObservation(student_id=student.id,instructor_id=current_user.id,season=season(),card_key=key,skill_id=skill_id,
            session_date=parse_date('session_date',future=False), week=number('week',1,8),status=status,evidence=field('evidence',2000),achieved=achieved,attempted=attempted))
        db.session.commit()
        flash('Observation saved for the next instructor and report review.', 'success')
        return redirect(url_for('.progression',student_id=student.id,card=key))
    return render_template('learning/progression.html', student=student, card=card, card_key=key,cards=CARDS,latest=latest_rows(student.id,key),history=observations(student.id,key),today=today(),statuses=STATUSES,season=season())

@bp.route('/participants/<int:student_id>/reports', methods=['GET','POST'])
@login_required
def reports(student_id):
    student = student_access(student_id, writing=request.method=='POST')
    if request.method == 'POST':
        key = field('card',40)
        if key not in CARDS: abort(400)
        latest = latest_rows(student.id,key)
        if not latest: abort(400,description='Record at least one observation before drafting a report.')
        snapshot = {'name':CARDS[key]['name'],'participant':student.full_name,'class':student.team.name if student.team else 'Individual',
            'rows':[{'label':r['label'],'status':latest[r['id']].status if r['id'] in latest else 'not_observed','observation_id':latest[r['id']].id if r['id'] in latest else None} for r in CARDS[key]['rows']]}
        row = ParticipantReport(student_id=student.id,season=season(),card_key=key,snapshot=snapshot,comments=field('comments',2000),next_steps=field('next_steps',1000),author_id=current_user.id)
        db.session.add(row); db.session.commit()
        return redirect(url_for('.report',report_id=row.id))
    rows = ParticipantReport.query.filter_by(student_id=student.id).order_by(ParticipantReport.id.desc())
    if current_user.user_type not in ('admin','instructor'): rows = rows.filter(ParticipantReport.issued_at.isnot(None))
    return render_template('learning/reports.html',student=student,reports=rows.all())

@bp.route('/reports/<int:report_id>',methods=['GET','POST'])
@login_required
def report(report_id):
    row=db.get_or_404(ParticipantReport,report_id)
    student_access(row.student_id,writing=request.method=='POST')
    if not row.issued_at and current_user.user_type not in ('admin','instructor'): abort(404)
    if request.method=='POST':
        admin()
        if not row.issued_at:
            row.issued_at=datetime.now(); row.issued_by=current_user.id; db.session.commit()
        flash('Report issued. It is now visible to the linked family.', 'success')
        return redirect(url_for('.report',report_id=row.id))
    return render_template('learning/report.html',report=row)

@bp.route('/groups/new',methods=['GET','POST'])
@staff
def new_group():
    if request.method=='POST':
        names=[n.strip() for n in field('names',16000).splitlines() if n.strip()]
        if len(names)>100 or any(len(n)>100 for n in names): abort(400,description='Use up to 100 names, one per line, maximum 100 characters each.')
        school=field('school_name',160); name=field('name',100)
        sport=field('sport',20)
        if sport not in ('ski','snowboard'): abort(400)
        start=parse_date('start_date'); count=number('sessions',1,8)
        instructor=instructor_field() if current_user.user_type=='admin' else current_user
        program=Program(name=name,description=f'{school} progressive school group',frequency_type='weekly',frequency_value=count,start_date=start,end_date=start+timedelta(weeks=count-1),frequency_days=start.strftime('%A').lower())
        db.session.add(program); db.session.flush()
        db.session.add(ProgramProfile(program_id=program.id,category='School group',sport=sport,season=season()))
        team=Team(name=name,program_id=program.id,instructor_id=instructor.id,team_type='class')
        db.session.add(team); db.session.flush()
        db.session.add(SchoolGroup(team_id=team.id,school_name=school,season=season(),created_by=current_user.id))
        db.session.add(GroupAssignment(team_id=team.id,instructor_id=instructor.id,assigned_by=current_user.id))
        for name in names:
            token=secrets.token_hex(12)
            student=User(username=f'roster-{token}',email=f'{token}@roster.invalid',password_hash=generate_password_hash(secrets.token_urlsafe(40)),full_name=name,user_type='student',team_id=team.id,instructor_id=instructor.id,participates_skier=sport=='ski',participates_snowboarder=sport=='snowboard')
            db.session.add(student); db.session.flush()
            db.session.add(Enrollment(student_id=student.id,program_id=program.id,team_id=team.id,season=season()))
        db.session.commit()
        return redirect(url_for('team_session',team_id=team.id))
    return render_template('learning/new_group.html',instructors=User.query.filter_by(user_type='instructor').all())

@bp.route('/groups/<int:team_id>/assign',methods=['GET','POST'])
@staff
def assign(team_id):
    admin(); team=team_access(team_id)
    if not db.session.get(SchoolGroup,team.id): abort(404)
    if request.method=='POST':
        instructor=instructor_field()
        from operations import qualification_check
        qualification_check(team, instructor, request.form.get('override_reason', '').strip())
        team.instructor_id=instructor.id
        for student in team.students: student.instructor_id=instructor.id
        db.session.add(GroupAssignment(team_id=team.id,instructor_id=instructor.id,assigned_by=current_user.id))
        db.session.commit()
        return redirect(url_for('.hub'))
    return render_template('learning/assign.html',team=team,instructors=User.query.filter_by(user_type='instructor').all(),history=GroupAssignment.query.filter_by(team_id=team.id).order_by(GroupAssignment.id.desc()).all())

@bp.route('/privates/new',methods=['GET','POST'])
@staff
def new_private():
    admin()
    if request.method=='POST':
        instructor=instructor_field()
        try: starts=datetime.fromisoformat(field('starts_at',30))
        except ValueError: abort(400)
        if starts.tzinfo: abort(400)
        lesson_type = request.form.get('lesson_type', 'private')
        if lesson_type not in ('private', 'semi-private'): abort(400)
        lesson = PrivateLesson(instructor_id=instructor.id,participant=field('participant',160),starts_at=starts,duration_minutes=number('duration_minutes',15,240),meeting_point=field('meeting_point',160),notes=field('notes',2000),created_by=current_user.id)
        db.session.add(lesson); db.session.flush()
        from operations import save_setting, notify
        save_setting(f'private-type:{lesson.id}', lesson_type)
        from staff_portal import PrivateParticipant
        for raw_id in set(request.form.getlist('student_ids')):
            if not raw_id.isdigit(): abort(400)
            student = db.get_or_404(User, int(raw_id))
            if student.user_type != 'student': abort(400)
            db.session.add(PrivateParticipant(lesson_id=lesson.id, student_id=student.id))
        notify('Lesson assigned', f'A {lesson_type} lesson is assigned for {starts.strftime("%b %d at %H:%M")} Toronto time. Open Today for customer details.', [instructor.id])
        db.session.commit(); return redirect(url_for('.hub'))
    return render_template('learning/private.html',instructors=User.query.filter_by(user_type='instructor').all(),students=User.query.filter_by(user_type='student').order_by(User.full_name).all())

@bp.route('/incidents',methods=['GET','POST'])
@staff
def incidents():
    if request.method=='POST':
        team=team_access(number('team_id',1,2**31-1))
        try: occurred=datetime.fromisoformat(field('occurred_at',30))
        except ValueError: abort(400)
        if occurred.tzinfo or occurred.date()>today(): abort(400)
        db.session.add(Incident(team_id=team.id,reported_by=current_user.id,occurred_at=occurred,location=field('location',160),details=field('details',4000),actions=field('actions',4000)))
        db.session.commit(); flash('Incident saved for admin review. Contact the supervisor directly for urgent help.','success')
        return redirect(url_for('.incidents'))
    teams=Team.query if current_user.user_type=='admin' else Team.query.filter_by(instructor_id=current_user.id)
    rows=Incident.query if current_user.user_type=='admin' else Incident.query.filter_by(reported_by=current_user.id)
    return render_template('learning/incidents.html',teams=teams.all(),incidents=rows.order_by(Incident.id.desc()).all())

@bp.route('/incidents/<int:incident_id>/review',methods=['POST'])
@staff
def review_incident(incident_id):
    admin(); row=db.get_or_404(Incident,incident_id)
    row.reviewed_by=current_user.id; row.reviewed_at=datetime.now(); db.session.commit()
    return redirect(url_for('.incidents'))
