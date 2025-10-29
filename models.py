from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    # Attendance frequency settings
    frequency_type = db.Column(db.String(20), nullable=False, default='daily')  # 'daily', 'weekly', 'custom'
    frequency_value = db.Column(db.Integer, nullable=False, default=8)  # Number of sessions
    frequency_days = db.Column(db.String(50), nullable=True)  # For weekly: 'saturday', 'sunday', etc. For custom: comma-separated days
    start_date = db.Column(db.Date, nullable=True)  # Program start date
    end_date = db.Column(db.Date, nullable=True)  # Program end date
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    teams = db.relationship('Team', backref='program', lazy=True)
    
    def __repr__(self):
        return f'<Program {self.name}>'

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    team_type = db.Column(db.String(20), nullable=False, default='class')  # 'class' for STEP/RIP, 'team' for Snow Stars
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    instructor = db.relationship('User', foreign_keys=[instructor_id], backref='managed_teams')
    students = db.relationship('User', foreign_keys='User.team_id', backref='team')
    
    def __repr__(self):
        return f'<Team {self.name}>'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    participates_skier = db.Column(db.Boolean, default=False)  # Can participate in skiing
    participates_snowboarder = db.Column(db.Boolean, default=False)  # Can participate in snowboarding
    participates_snow_stars = db.Column(db.Boolean, default=False)  # Can participate in Snow Stars
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id', use_alter=True), nullable=True)  # For students
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    instructor = db.relationship('User', remote_side=[id], foreign_keys=[instructor_id])
    
    def __repr__(self):
        return f'<User {self.username}>'

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    attended = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, nullable=True)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Instructor who recorded
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    student = db.relationship('User', foreign_keys=[student_id], backref='attendance_records')
    team = db.relationship('Team', backref='attendance_records')
    recorder = db.relationship('User', foreign_keys=[recorded_by], backref='recorded_attendance')
    
    def __repr__(self):
        return f'<Attendance {self.student.username} - {self.session_date}>'

class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sport_type = db.Column(db.String(20), nullable=False)  # 'skier' or 'snowboarder'
    level = db.Column(db.Integer, nullable=False)  # STEP levels 1-8, RIP levels 1-6
    skills_score = db.Column(db.Float, nullable=False)
    attitude_score = db.Column(db.Float, nullable=False)
    performance_score = db.Column(db.Float, nullable=False)
    
    # STEP program criteria for skiers (CSIA)
    technical_score = db.Column(db.Float, nullable=True)
    edging_score = db.Column(db.Float, nullable=True)
    pressure_control_score = db.Column(db.Float, nullable=True)
    turn_shape_score = db.Column(db.Float, nullable=True)
    
    # RIP program criteria for snowboarders (CASI)
    board_control_score = db.Column(db.Float, nullable=True)
    edge_awareness_score = db.Column(db.Float, nullable=True)
    body_positioning_score = db.Column(db.Float, nullable=True)
    turn_control_score = db.Column(db.Float, nullable=True)
    
    # Snow Stars program criteria (ACA)
    movement_quality_score = db.Column(db.Float, nullable=True)
    balance_score = db.Column(db.Float, nullable=True)
    control_score = db.Column(db.Float, nullable=True)
    awareness_score = db.Column(db.Float, nullable=True)
    
    comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False)
    
    student = db.relationship('User', foreign_keys=[student_id], backref='evaluations_received')
    instructor = db.relationship('User', foreign_keys=[instructor_id])
    
    @property
    def average_score(self):
        return round((self.skills_score + self.attitude_score + self.performance_score) / 3, 2)
    
    @property
    def step_average_score(self):
        """Average score for STEP program (skiers)"""
        if self.technical_score and self.edging_score and self.pressure_control_score and self.turn_shape_score:
            return round((self.technical_score + self.edging_score + self.pressure_control_score + self.turn_shape_score) / 4, 2)
        return None
    
    @property
    def rip_average_score(self):
        """Average score for RIP program (snowboarders)"""
        if self.board_control_score and self.edge_awareness_score and self.body_positioning_score and self.turn_control_score:
            return round((self.board_control_score + self.edge_awareness_score + self.body_positioning_score + self.turn_control_score) / 4, 2)
        return None
    
    @property
    def snow_stars_average_score(self):
        """Average score for Snow Stars program (ACA)"""
        if self.movement_quality_score and self.balance_score and self.control_score and self.awareness_score:
            return round((self.movement_quality_score + self.balance_score + self.control_score + self.awareness_score) / 4, 2)
        return None
    
    def __repr__(self):
        return f'<Evaluation {self.id}>'
