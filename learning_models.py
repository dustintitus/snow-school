"""Additive operational records; existing evaluation history is preserved."""
from models import db

class SkillObservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    season = db.Column(db.String(20), nullable=False)
    card_key = db.Column(db.String(40), nullable=False)
    skill_id = db.Column(db.String(60), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    week = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False)
    evidence = db.Column(db.Text, nullable=False)
    achieved = db.Column(db.Integer)
    attempted = db.Column(db.Integer)
    instructor = db.relationship('User', foreign_keys=[instructor_id])
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())

class ParticipantReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    season = db.Column(db.String(20), nullable=False)
    card_key = db.Column(db.String(40), nullable=False)
    snapshot = db.Column(db.JSON, nullable=False)
    comments = db.Column(db.Text, nullable=False)
    next_steps = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    issued_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    issued_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    author = db.relationship('User', foreign_keys=[author_id])
    student = db.relationship('User', foreign_keys=[student_id])

class TrainingWeek(db.Model):
    __table_args__ = (db.UniqueConstraint('season','week'),)
    id = db.Column(db.Integer, primary_key=True)
    season = db.Column(db.String(20), nullable=False)
    week = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    content = db.Column(db.Text, nullable=False)
    announcement = db.Column(db.Text, nullable=False, default='')
    release_date = db.Column(db.Date)
    published = db.Column(db.Boolean, nullable=False, default=False)
    revision = db.Column(db.Integer, nullable=False, default=1)

class TrainingReview(db.Model):
    __table_args__ = (db.UniqueConstraint('week_id','instructor_id','revision'),)
    id = db.Column(db.Integer, primary_key=True)
    week_id = db.Column(db.Integer, db.ForeignKey('training_week.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())

class TrainingAttendance(db.Model):
    __table_args__ = (db.UniqueConstraint('week_id','instructor_id'),)
    id = db.Column(db.Integer, primary_key=True)
    week_id = db.Column(db.Integer, db.ForeignKey('training_week.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

class SchoolGroup(db.Model):
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), primary_key=True)
    school_name = db.Column(db.String(160), nullable=False)
    season = db.Column(db.String(20), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    team = db.relationship('Team')

class GroupAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())

class PrivateLesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    participant = db.Column(db.String(160), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    meeting_point = db.Column(db.String(160), nullable=False)
    notes = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    instructor = db.relationship('User', foreign_keys=[instructor_id])

class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    reported_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    occurred_at = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(160), nullable=False)
    details = db.Column(db.Text, nullable=False)
    actions = db.Column(db.Text, nullable=False)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_at = db.Column(db.DateTime)
    team = db.relationship('Team')
