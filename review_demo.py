"""Explicitly enabled, one-time fictional App Review data; never replaces accounts."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from datetime import datetime
from werkzeug.security import generate_password_hash
from models import db, AppSetting, User, Program, ProgramProfile, Team, Enrollment, ClassSession


def seed_review_demo(password):
    marker = 'app-review-demo:v1'
    if not password or len(password) < 24 or db.session.get(AppSetting, marker):
        return False
    # Refuse collisions instead of overwriting a person's access or records.
    if User.query.filter_by(username='apple_review_coach').first():
        raise ValueError('App Review username already exists; inspect before changing access')
    start = datetime.now(ZoneInfo('America/Toronto')).date() - timedelta(days=21)
    coach = User(username='apple_review_coach', email='apple-review@demo.snowschool.app',
                 full_name='Demo Coach', user_type='instructor',
                 password_hash=generate_password_hash(password, method='pbkdf2:sha256'))
    db.session.add(coach); db.session.flush()
    program = Program(name='[App Review] High Flyers', description='Fictional demonstration program for Apple review.',
                      frequency_type='weekly', frequency_value=52,
                      frequency_days='saturday,sunday',
                      start_date=start, end_date=start + timedelta(days=364))
    db.session.add(program); db.session.flush()
    db.session.add(ProgramProfile(program_id=program.id, category='App Review demo', sport='ski', season='2026-2027', is_active=False))
    team = Team(name='[App Review] Demo Class', program_id=program.id, instructor_id=coach.id, team_type='class')
    db.session.add(team); db.session.flush()
    for index, name in enumerate(['Demo Avery', 'Demo Sam', 'Demo Mia', 'Demo Noah'],1):
        username=f'apple_review_learner_{index}'
        if User.query.filter_by(username=username).first():
            raise ValueError('App Review learner collision; no records changed')
        learner=User(username=username,email=f'{username}@demo.snowschool.app',full_name=name,
                     user_type='student',password_hash='!fictional-no-login',instructor_id=coach.id,
                     team_id=team.id, participates_skier=True)
        db.session.add(learner); db.session.flush()
        db.session.add(Enrollment(student_id=learner.id,program_id=program.id,team_id=team.id,season='2026-2027'))
    today=start+timedelta(days=21)
    db.session.add(ClassSession(team_id=team.id,session_date=today,status='not_started',meeting_point='Demo meeting area',
                               coach_note='Fictional class: practise balance and controlled turns.',updated_by=coach.id))
    # Only this demo program keeps evaluations open for every review week.
    db.session.add(AppSetting(key=f'evaluation-weeks:{program.id}',value=','.join(map(str,range(1,53)))))
    from notifications import create_message
    create_message('school','Welcome to your school inbox','This fictional message demonstrates school announcements. Optional phone alerts can be tested in Notification settings.',[coach.id], 'app-review-welcome:v1')
    db.session.add(AppSetting(key=marker,value=f'coach:{coach.id};team:{team.id};fictional-only'))
    db.session.commit()
    return True
