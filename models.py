from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class AppSetting(db.Model):
    key = db.Column(db.String(120), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

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
    profile = db.relationship('ProgramProfile', backref='program', uselist=False, cascade='all, delete-orphan')
    enrollments = db.relationship('Enrollment', backref='program', lazy=True)
    
    def __repr__(self):
        return f'<Program {self.name}>'

class ProgramProfile(db.Model):
    """Catalogue and planning details that extend the legacy program record."""
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=False, unique=True)
    category = db.Column(db.String(50), nullable=False, default='Seasonal program')
    sport = db.Column(db.String(30), nullable=False, default='ski_snowboard')
    age_min = db.Column(db.Integer, nullable=True)
    age_max = db.Column(db.Integer, nullable=True)
    ability_levels = db.Column(db.String(100), nullable=True)
    duration_label = db.Column(db.String(60), nullable=True)
    price_cents = db.Column(db.Integer, nullable=True)
    capacity = db.Column(db.Integer, nullable=True)
    season = db.Column(db.String(20), nullable=False, default='2026-2027')
    source_url = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

class Enrollment(db.Model):
    """Seasonal registration history used for retention and tenure reporting."""
    __table_args__ = (db.UniqueConstraint('student_id', 'program_id', 'season', name='uq_enrollment_student_program_season'),)
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    season = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='registered')
    registered_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    completed_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship('User', backref='enrollments')
    team = db.relationship('Team', backref='enrollments')

class CurriculumLevel(db.Model):
    """A resort curriculum level and its progression outcome."""
    __table_args__ = (db.UniqueConstraint('discipline', 'level_number', name='uq_curriculum_discipline_level'),)
    id = db.Column(db.Integer, primary_key=True)
    discipline = db.Column(db.String(20), nullable=False)  # step or rip
    level_number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    terrain = db.Column(db.String(120), nullable=True)
    readiness_outcome = db.Column(db.Text, nullable=False)
    framework = db.Column(db.String(120), nullable=False)
    source_url = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    skills = db.relationship('CurriculumSkill', backref='curriculum_level', cascade='all, delete-orphan', order_by='CurriculumSkill.sort_order')

class CurriculumSkill(db.Model):
    """An observable skill outcome attached to one curriculum level."""
    __table_args__ = (db.UniqueConstraint('curriculum_level_id', 'code', name='uq_curriculum_level_skill_code'),)
    id = db.Column(db.Integer, primary_key=True)
    curriculum_level_id = db.Column(db.Integer, db.ForeignKey('curriculum_level.id'), nullable=False)
    code = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    skill_family = db.Column(db.String(40), nullable=False)
    description = db.Column(db.Text, nullable=False)
    assessment_prompt = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_required = db.Column(db.Boolean, nullable=False, default=True)

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
    participates_hv_skier = db.Column(db.Boolean, default=False)  # Can participate in Horseshoe Valley Skiing
    participates_hv_snowboarder = db.Column(db.Boolean, default=False)  # Can participate in Horseshoe Valley Snowboarding
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id', use_alter=True), nullable=True)  # For students
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    instructor = db.relationship('User', remote_side=[id], foreign_keys=[instructor_id])
    
    def __repr__(self):
        return f'<User {self.username}>'

class Attendance(db.Model):
    __table_args__ = (db.UniqueConstraint('student_id', 'team_id', 'session_date', name='uq_attendance_student_team_date'),)
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

class ClassSession(db.Model):
    """Operational state for one team's on-hill session."""
    __table_args__ = (db.UniqueConstraint('team_id', 'session_date', name='uq_class_session_team_date'),)
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='not_started')
    meeting_point = db.Column(db.String(120), nullable=True)
    coach_note = db.Column(db.Text, nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    team = db.relationship('Team', backref='class_sessions')
    updater = db.relationship('User', foreign_keys=[updated_by])

    @property
    def status_label(self):
        return self.status.replace('_', ' ').title()

class Evaluation(db.Model):
    __table_args__ = (db.UniqueConstraint('student_id', 'sport_type', 'level', name='uq_evaluation_student_sport_level'),)
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
    
    # Horseshoe Valley Skiing program criteria
    hv_skills_balance_score = db.Column(db.Float, nullable=True)  # S&B
    hv_edging_score = db.Column(db.Float, nullable=True)  # E
    hv_turn_shape_performance_score = db.Column(db.Float, nullable=True)  # T&P
    hv_pressure_control_score = db.Column(db.Float, nullable=True)  # P.C
    hv_technical_score = db.Column(db.Float, nullable=True)  # T
    
    # Horseshoe Valley Snowboarding program criteria
    hv_technical_skills_score = db.Column(db.Float, nullable=True)
    hv_freeride_skills_score = db.Column(db.Float, nullable=True)
    hv_balance_score = db.Column(db.Float, nullable=True)
    hv_steering_control_score = db.Column(db.Float, nullable=True)
    hv_edge_control_score = db.Column(db.Float, nullable=True)
    
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
    
    @property
    def hv_skier_average_score(self):
        """Average score for Horseshoe Valley Skiing program"""
        scores = [self.hv_skills_balance_score, self.hv_edging_score, self.hv_turn_shape_performance_score, 
                 self.hv_pressure_control_score, self.hv_technical_score]
        if all(s is not None for s in scores):
            return round(sum(scores) / len(scores), 2)
        return None
    
    @property
    def hv_snowboarder_average_score(self):
        """Average score for Horseshoe Valley Snowboarding program"""
        scores = [self.hv_technical_skills_score, self.hv_freeride_skills_score, self.hv_balance_score,
                 self.hv_steering_control_score, self.hv_edge_control_score]
        if all(s is not None for s in scores):
            return round(sum(scores) / len(scores), 2)
        return None
    
    def __repr__(self):
        return f'<Evaluation {self.id}>'
