import os
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, AppSetting, User, Evaluation, Program, Team, Attendance, ClassSession
from datetime import datetime, date
from config import config
import logging
from urllib.parse import urlparse

app = Flask(__name__)

# Load configuration from environment
env = os.environ.get('FLASK_ENV', 'production' if os.environ.get('VERCEL') else 'development')
app.config.from_object(config.get(env, config['development']))
if env == 'production':
    if not os.environ.get('DATABASE_URL'):
        raise RuntimeError('DATABASE_URL is required in production')
    if not os.environ.get('SECRET_KEY'):
        raise RuntimeError('SECRET_KEY is required in production')

# Configure logging
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@app.context_processor
def inject_csrf_token():
    """Expose a per-session CSRF token to every form."""
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return {'csrf_token': token}

@app.before_request
def protect_state_changes():
    """Reject forged state-changing requests before route handlers run."""
    if request.method == 'POST' and app.config.get('CSRF_ENABLED', True):
        submitted = request.form.get('_csrf_token', '')
        expected = session.get('_csrf_token', '')
        if not submitted or not expected or not secrets.compare_digest(submitted, expected):
            abort(400, description='Invalid or missing security token')

@app.after_request
def prevent_search_indexing(response):
    """Keep the private preview out of search indexes until launch."""
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet'
    return response

def is_admin():
    return current_user.is_authenticated and current_user.user_type == 'admin'

def safe_next_url(target):
    """Allow redirects only to local application paths."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith('/') or target.startswith('//'):
        return None
    return target

def instructor_owns_team(team):
    return current_user.is_authenticated and current_user.user_type == 'instructor' and team.instructor_id == current_user.id

def instructor_can_access_student(student):
    """Team ownership is authoritative; instructor_id remains a legacy fallback."""
    if current_user.user_type != 'instructor' or student.user_type != 'student':
        return False
    return bool(
        (student.team and student.team.instructor_id == current_user.id)
        or student.instructor_id == current_user.id
    )

SESSION_STATUSES = ('not_started', 'checked_in', 'on_hill', 'break', 'completed')

def parse_session_date(raw_value, fallback=None):
    """Parse an ISO date used by coach tools."""
    if not raw_value:
        return fallback or date.today()
    return datetime.strptime(raw_value, '%Y-%m-%d').date()

def score_from_form(field):
    """Parse and validate a 0-10 score without trusting browser constraints."""
    try:
        value = float(request.form.get(field, ''))
    except (TypeError, ValueError):
        raise ValueError(f'{field.replace("_", " ").title()} must be a number')
    if not 0 <= value <= 10:
        raise ValueError(f'{field.replace("_", " ").title()} must be between 0 and 10')
    return value

def program_schedule_from_form():
    """Validate scheduling fields and normalize selected weekdays."""
    frequency_type = request.form.get('frequency_type', 'consecutive')
    if frequency_type not in {'consecutive', 'weekly', 'custom'}:
        raise ValueError('Invalid schedule type')
    try:
        frequency_value = int(request.form.get('frequency_value', ''))
    except (TypeError, ValueError):
        raise ValueError('Number of sessions must be a whole number')
    if not 1 <= frequency_value <= 365:
        raise ValueError('Number of sessions must be between 1 and 365')
    try:
        start_raw = request.form.get('start_date', '')
        end_raw = request.form.get('end_date', '')
        start_date = datetime.strptime(start_raw, '%Y-%m-%d').date() if start_raw else None
        end_date = datetime.strptime(end_raw, '%Y-%m-%d').date() if end_raw else None
    except ValueError:
        raise ValueError('Program dates are invalid')
    if not start_date:
        raise ValueError('Program start date is required')
    if end_date and end_date < start_date:
        raise ValueError('Program end date cannot be before its start date')
    if frequency_type == 'weekly':
        frequency_days = request.form.get('frequency_days')
    elif frequency_type == 'custom':
        frequency_days = ','.join(request.form.getlist('custom_days'))
        if not frequency_days:
            raise ValueError('Choose at least one custom schedule day')
    else:
        frequency_days = None
    return frequency_type, frequency_value, frequency_days, start_date, end_date

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def update_student_participation_from_team(student):
    """Update student participation flags based on their team's program"""
    if student.user_type != 'student' or not student.team_id:
        return
    
    team = Team.query.get(student.team_id)
    if not team or not team.program:
        return
    
    program_name = team.program.name
    
    # Map program names to participation flags (add flags without clearing existing ones)
    # Horseshoe Valley Skiing - exact match
    if program_name == 'Horseshoe Valley Skiing':
        student.participates_hv_skier = True
    # Horseshoe Valley Snowboarding - exact match
    elif program_name == 'Horseshoe Valley Snowboarding':
        student.participates_hv_snowboarder = True
    # Snow Stars / Racing programs (ACA) - team type
    elif team.team_type == 'team' or 'Snow Stars' in program_name or 'Racing' in program_name or 'Terrain Park' in program_name or 'LIT' in program_name:
        student.participates_snow_stars = True
    # Class type programs - check program name patterns
    elif team.team_type == 'class':
        # Programs likely for STEP (Skiing - CSIA)
        if 'Skiing' in program_name or 'Snowflakes' in program_name or 'High Flyers' in program_name:
            student.participates_skier = True
        # Programs likely for RIP (Snowboarding - CASI)
        elif 'Snowboarding' in program_name or 'Trail Blazers' in program_name:
            student.participates_snowboarder = True

def init_db():
    """Initialize database with sample data"""
    with app.app_context():
        # Only create tables if they don't exist (production-safe)
        db.create_all()
        
        # Create admin
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@example.com',
                password_hash=generate_password_hash('admin123', method='pbkdf2:sha256'),
                user_type='admin',
                full_name='System Administrator'
            )
            db.session.add(admin)
        
        # Create Horseshoe Valley Programs with frequency settings
        programs_data = [
            ('Snowflakes', 'Early learning program for young beginners', 'weekly', 8, 'saturday'),
            ('High Flyers', 'Advanced program for developing competitive skiers', 'daily', 8, None),
            ('Trail Blazers', 'Multi-level program for progressive skill development', 'weekly', 6, 'sunday'),
            ('LIT', 'Leader in Training program for aspiring instructors', 'daily', 10, None),
            ('Adult', 'Program designed for adult skiers and snowboarders', 'weekly', 4, 'saturday'),
            ('Terrain Park', 'Specialized program for terrain park and freestyle development', 'daily', 6, None),
            ('Horseshoe Valley Skiing', 'Proprietary skiing evaluation framework program', 'weekly', 8, 'saturday'),
            ('Horseshoe Valley Snowboarding', 'Proprietary snowboarding evaluation framework program', 'weekly', 8, 'saturday')
        ]
        
        for program_name, description, freq_type, freq_value, freq_days in programs_data:
            if not Program.query.filter_by(name=program_name).first():
                program = Program(
                    name=program_name,
                    description=description,
                    frequency_type=freq_type,
                    frequency_value=freq_value,
                    frequency_days=freq_days
                )
                db.session.add(program)
        
        db.session.flush()  # Get the program IDs
        
        # Create instructor
        if not User.query.filter_by(username='instructor1').first():
            instructor = User(
                username='instructor1',
                email='instructor@example.com',
                password_hash=generate_password_hash('instructor123', method='pbkdf2:sha256'),
                user_type='instructor',
                full_name='Coach Johnson'
            )
            db.session.add(instructor)
            db.session.flush()  # Get the instructor ID
        
        # Create team for Snowflakes program
        snowflakes_program = Program.query.filter_by(name='Snowflakes').first()
        if snowflakes_program and not Team.query.filter_by(name='Snowflakes Demo Team').first():
            team = Team(
                name='Snowflakes Demo Team',
                program_id=snowflakes_program.id,
                instructor_id=2,
                team_type='class'
            )
            db.session.add(team)
            db.session.flush()  # Get the team ID
        
        # Create student
        demo_team = Team.query.filter_by(name='Snowflakes Demo Team').first()
        if not User.query.filter_by(username='student1').first() and demo_team:
            student = User(
                username='student1',
                email='student@example.com',
                password_hash=generate_password_hash('student123', method='pbkdf2:sha256'),
                user_type='student',
                full_name='John Doe',
                participates_skier=True,
                participates_snowboarder=True,  # Can participate in both
                instructor_id=2,
                team_id=demo_team.id
            )
            db.session.add(student)
        
        db.session.commit()

def seed_demo_accounts(seed_version, passwords):
    """Apply an explicitly versioned demo-account reset exactly once."""
    if not seed_version or set(passwords) != {'admin', 'instructor1', 'student1'} or not all(passwords.values()):
        return False

    setting_key = f'demo-account-seed:{seed_version}'
    if db.session.get(AppSetting, setting_key):
        return False

    account_specs = (
        ('admin', 'admin@snowschool.com', 'Administrator', 'admin'),
        ('instructor1', 'instructor@snowschool.com', 'Demo Instructor', 'instructor'),
        ('student1', 'student@snowschool.com', 'Demo Student', 'student'),
    )
    for username, email, full_name, user_type in account_specs:
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username, email=email, full_name=full_name, user_type=user_type)
            db.session.add(user)
        user.password_hash = generate_password_hash(passwords[username], method='pbkdf2:sha256')
        user.user_type = user_type

    db.session.add(AppSetting(key=setting_key, value='applied'))
    db.session.commit()
    return True

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/robots.txt')
def robots_txt():
    return 'User-agent: *\nDisallow: /\n', 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/health')
def health():
    """Health check endpoint for debugging"""
    try:
        # Test database connection
        db.session.execute(db.text('SELECT 1'))
        
        return {
            'status': 'healthy',
            'database': 'connected'
        }
    except Exception as e:
        app.logger.error(f"Health check error: {e}")
        return {
            'status': 'error',
            'database': 'unavailable'
        }, 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = safe_next_url(request.values.get('next'))
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            
            app.logger.info(f"Login attempt for username: '{username}'")
            
            if not username or not password:
                flash('Please enter both username and password', 'error')
                return render_template('login.html', next_url=next_url)
            
            user = User.query.filter_by(username=username).first()
            
            if user:
                password_valid = check_password_hash(user.password_hash, password)
                if password_valid:
                    login_user(user)
                    flash('Login successful!', 'success')
                    return redirect(next_url or url_for('dashboard'))
                else:
                    flash('Invalid username or password', 'error')
            else:
                app.logger.warning(f"Login attempt failed: User '{username}' not found")
                flash('Invalid username or password', 'error')
        except Exception as e:
            app.logger.error(f"Login error: {e}", exc_info=True)
            flash('An error occurred during login. Please try again.', 'error')
    
    return render_template('login.html', next_url=next_url)

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_type = current_user.user_type
    
    if user_type == 'admin':
        users = User.query.all()
        return render_template('dashboard_admin.html', users=users)
    elif user_type == 'instructor':
        # Get students from instructor's teams
        instructor_teams = Team.query.filter_by(instructor_id=current_user.id).all()
        team_ids = [team.id for team in instructor_teams]
        
        students = []
        if team_ids:
            students = User.query.filter(
                User.user_type == 'student',
                User.team_id.in_(team_ids)
            ).all()
        
        recent_evaluations = Evaluation.query.filter_by(
            instructor_id=current_user.id
        ).order_by(Evaluation.created_at.desc()).limit(5).all()
        today = date.today()
        team_activity = {}
        for team in instructor_teams:
            team_activity[team.id] = {
                'attendance_count': Attendance.query.filter_by(team_id=team.id, session_date=today).count(),
                'latest_evaluation': Evaluation.query.join(User, Evaluation.student_id == User.id).filter(
                    User.team_id == team.id
                ).order_by(Evaluation.created_at.desc()).first()
            }
        return render_template('dashboard_instructor.html', students=students, evaluations=recent_evaluations, teams=instructor_teams or [], today=today, team_activity=team_activity)
    else:
        evaluations = Evaluation.query.filter_by(student_id=current_user.id).order_by(Evaluation.level).all()
        return render_template('dashboard_student.html', evaluations=evaluations)

@app.route('/coach')
@login_required
def coach_today():
    """Glove-friendly daily operations view for instructors."""
    if current_user.user_type != 'instructor':
        return redirect(url_for('dashboard'))
    try:
        selected_date = parse_session_date(request.args.get('date'))
    except ValueError:
        flash('Invalid session date', 'error')
        return redirect(url_for('coach_today'))

    teams = Team.query.filter_by(instructor_id=current_user.id).order_by(Team.name).all()
    cards = []
    for team in teams:
        records = Attendance.query.filter_by(team_id=team.id, session_date=selected_date).all()
        session_record = ClassSession.query.filter_by(team_id=team.id, session_date=selected_date).first()
        cards.append({
            'team': team,
            'session': session_record,
            'recorded': len(records),
            'present': sum(1 for record in records if record.attended),
        })
    return render_template('coach_today.html', cards=cards, selected_date=selected_date)

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if current_user.user_type != 'admin':
        flash('Only admins can create new users', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        user_type = request.form.get('user_type')
        instructor_id = request.form.get('instructor_id')
        team_id = request.form.get('team_id')
        participates_skier = request.form.get('participates_skier') == 'on'
        participates_snowboarder = request.form.get('participates_snowboarder') == 'on'
        participates_snow_stars = request.form.get('participates_snow_stars') == 'on'
        participates_hv_skier = request.form.get('participates_hv_skier') == 'on'
        participates_hv_snowboarder = request.form.get('participates_hv_snowboarder') == 'on'
        
        if not all([username, email, password, full_name]) or user_type not in {'admin', 'instructor', 'student'}:
            flash('Please complete all required account fields', 'error')
            return redirect(url_for('register'))
        if len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return redirect(url_for('register'))
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or email already exists', 'error')
            return redirect(url_for('register'))
        
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            full_name=full_name,
            user_type=user_type,
            participates_skier=participates_skier if user_type == 'student' else False,
            participates_snowboarder=participates_snowboarder if user_type == 'student' else False,
            participates_snow_stars=participates_snow_stars if user_type == 'student' else False,
            participates_hv_skier=participates_hv_skier if user_type == 'student' else False,
            participates_hv_snowboarder=participates_hv_snowboarder if user_type == 'student' else False,
            instructor_id=int(instructor_id) if instructor_id and user_type == 'student' else None,
            team_id=int(team_id) if team_id and user_type == 'student' else None
        )
        
        db.session.add(new_user)
        db.session.flush()  # Flush to get the user ID
        
        # Auto-update participation flags based on team program if team is assigned
        if user_type == 'student' and team_id:
            team = Team.query.get_or_404(int(team_id))
            new_user.instructor_id = team.instructor_id
            update_student_participation_from_team(new_user)
        
        db.session.commit()
        flash('User created successfully', 'success')
        return redirect(url_for('dashboard'))
    
    instructors = User.query.filter_by(user_type='instructor').all()
    teams = Team.query.all()
    programs = Program.query.all()
    return render_template('register.html', instructors=instructors, teams=teams, programs=programs)

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.user_type != 'admin':
        flash('Only admins can edit users', 'error')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Check if username is being changed and if new username already exists
        new_username = request.form.get('username', '').strip()
        if new_username != user.username:
            if User.query.filter_by(username=new_username).first():
                flash('Username already exists', 'error')
                instructors = User.query.filter_by(user_type='instructor').all()
                teams = Team.query.all()
                programs = Program.query.all()
                return render_template('edit_user.html', user=user, instructors=instructors, teams=teams, programs=programs)
        
        # Update user fields
        user.username = new_username
        new_email = request.form.get('email', '').strip().lower()
        duplicate_email = User.query.filter(User.email == new_email, User.id != user.id).first()
        if duplicate_email:
            flash('Email already exists', 'error')
            return redirect(url_for('edit_user', user_id=user.id))
        user.email = new_email
        user.full_name = request.form.get('full_name', '').strip()
        user_type = request.form.get('user_type')
        user.user_type = user_type
        
        # Update password if provided
        new_password = request.form.get('password', '').strip()
        if new_password:
            user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        
        # Update student-specific fields
        if user_type == 'student':
            instructor_id = request.form.get('instructor_id')
            team_id = request.form.get('team_id')
            
            user.team_id = int(team_id) if team_id else None
            if user.team_id:
                user.instructor_id = Team.query.get_or_404(user.team_id).instructor_id
            else:
                user.instructor_id = int(instructor_id) if instructor_id else None
            
            # Update participation flags
            user.participates_skier = request.form.get('participates_skier') == 'on'
            user.participates_snowboarder = request.form.get('participates_snowboarder') == 'on'
            user.participates_snow_stars = request.form.get('participates_snow_stars') == 'on'
            user.participates_hv_skier = request.form.get('participates_hv_skier') == 'on'
            user.participates_hv_snowboarder = request.form.get('participates_hv_snowboarder') == 'on'
            
            # Auto-update participation flags based on team program if team is assigned
            if team_id:
                update_student_participation_from_team(user)
        else:
            # Clear student-specific fields for non-students
            user.instructor_id = None
            user.team_id = None
            user.participates_skier = False
            user.participates_snowboarder = False
            user.participates_snow_stars = False
            user.participates_hv_skier = False
            user.participates_hv_snowboarder = False
        
        db.session.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('dashboard'))
    
    instructors = User.query.filter_by(user_type='instructor').all()
    teams = Team.query.all()
    programs = Program.query.all()
    
    return render_template('edit_user.html', user=user, instructors=instructors, teams=teams, programs=programs)

@app.route('/admin/view_student_evaluations/<int:student_id>')
@login_required
def view_student_evaluations(student_id):
    if current_user.user_type != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    student = User.query.get_or_404(student_id)
    if student.user_type != 'student':
        flash('This user is not a student', 'error')
        return redirect(url_for('dashboard'))
    
    evaluations = Evaluation.query.filter_by(student_id=student_id).order_by(Evaluation.created_at.desc()).all()
    
    return render_template('view_student_evaluations.html', student=student, evaluations=evaluations)

@app.route('/evaluate/<int:student_id>', methods=['GET', 'POST'])
@login_required
def evaluate_student(student_id):
    if current_user.user_type != 'instructor':
        flash('Only instructors can evaluate students', 'error')
        return redirect(url_for('dashboard'))
    
    student = User.query.get_or_404(student_id)
    
    if not instructor_can_access_student(student):
        flash('You can only evaluate your assigned students', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        sport_type = request.form.get('sport_type')
        
        # Check if student participates in selected sport
        if sport_type == 'skier' and not student.participates_skier:
            flash('Student does not participate in skiing. Please update student profile.', 'error')
            return redirect(url_for('dashboard'))
        elif sport_type == 'snowboarder' and not student.participates_snowboarder:
            flash('Student does not participate in snowboarding. Please update student profile.', 'error')
            return redirect(url_for('dashboard'))
        elif sport_type == 'snow_stars' and not student.participates_snow_stars:
            flash('Student does not participate in Snow Stars. Please update student profile.', 'error')
            return redirect(url_for('dashboard'))
        elif sport_type == 'hv_skier' and not student.participates_hv_skier:
            flash('Student does not participate in Horseshoe Valley Skiing. Please update student profile.', 'error')
            return redirect(url_for('dashboard'))
        elif sport_type == 'hv_snowboarder' and not student.participates_hv_snowboarder:
            flash('Student does not participate in Horseshoe Valley Snowboarding. Please update student profile.', 'error')
            return redirect(url_for('dashboard'))
        
        if not sport_type:
            flash('Please select a sport for evaluation.', 'error')
            return redirect(url_for('dashboard'))
        
        max_levels = {'skier': 8, 'snowboarder': 6, 'snow_stars': 6, 'hv_skier': 5, 'hv_snowboarder': 7}
        try:
            level = int(request.form.get('level', ''))
        except (TypeError, ValueError):
            flash('Please select a valid level', 'error')
            return redirect(url_for('evaluate_student', student_id=student_id))
        if sport_type not in max_levels or not 1 <= level <= max_levels[sport_type]:
            flash('Selected level is not valid for this program', 'error')
            return redirect(url_for('evaluate_student', student_id=student_id))
        
        # Check if student already has an evaluation for this level
        existing_evaluation = Evaluation.query.filter_by(
            student_id=student_id, 
            sport_type=sport_type,
            level=level
        ).first()
        
        if existing_evaluation:
            flash(f'Student already has an evaluation for level {level}. You can only create one evaluation per level per student.', 'error')
            return redirect(url_for('dashboard'))
        
        try:
            evaluation = Evaluation(
                student_id=student_id,
                instructor_id=current_user.id,
                sport_type=sport_type,
                level=level,
                skills_score=score_from_form('skills_score'),
                attitude_score=score_from_form('attitude_score'),
                performance_score=score_from_form('performance_score'),
                comments=request.form.get('comments', '').strip(),
                created_at=datetime.now()
            )
        
        # Add sport-specific criteria
            if sport_type == 'skier':
                evaluation.technical_score = score_from_form('technical_score')
                evaluation.edging_score = score_from_form('edging_score')
                evaluation.pressure_control_score = score_from_form('pressure_control_score')
                evaluation.turn_shape_score = score_from_form('turn_shape_score')
            elif sport_type == 'snowboarder':
                evaluation.board_control_score = score_from_form('board_control_score')
                evaluation.edge_awareness_score = score_from_form('edge_awareness_score')
                evaluation.body_positioning_score = score_from_form('body_positioning_score')
                evaluation.turn_control_score = score_from_form('turn_control_score')
            elif sport_type == 'snow_stars':
                evaluation.movement_quality_score = score_from_form('movement_quality_score')
                evaluation.balance_score = score_from_form('balance_score')
                evaluation.control_score = score_from_form('control_score')
                evaluation.awareness_score = score_from_form('awareness_score')
            elif sport_type == 'hv_skier':
                evaluation.hv_skills_balance_score = score_from_form('hv_skills_balance_score')
                evaluation.hv_edging_score = score_from_form('hv_edging_score')
                evaluation.hv_turn_shape_performance_score = score_from_form('hv_turn_shape_performance_score')
                evaluation.hv_pressure_control_score = score_from_form('hv_pressure_control_score')
                evaluation.hv_technical_score = score_from_form('hv_technical_score')
            elif sport_type == 'hv_snowboarder':
                evaluation.hv_technical_skills_score = score_from_form('hv_technical_skills_score')
                evaluation.hv_freeride_skills_score = score_from_form('hv_freeride_skills_score')
                evaluation.hv_balance_score = score_from_form('hv_balance_score')
                evaluation.hv_steering_control_score = score_from_form('hv_steering_control_score')
                evaluation.hv_edge_control_score = score_from_form('hv_edge_control_score')
        except ValueError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('evaluate_student', student_id=student_id))
        
        db.session.add(evaluation)
        db.session.commit()
        flash('Evaluation submitted successfully', 'success')
        return redirect(url_for('dashboard'))
    
    # Get available sports for this student
    available_sports = []
    if student.participates_skier:
        available_sports.append('skier')
    if student.participates_snowboarder:
        available_sports.append('snowboarder')
    if student.participates_snow_stars:
        available_sports.append('snow_stars')
    if student.participates_hv_skier:
        available_sports.append('hv_skier')
    if student.participates_hv_snowboarder:
        available_sports.append('hv_snowboarder')
    
    # Get completed levels for each sport
    completed_levels_skier = []
    completed_levels_snowboarder = []
    completed_levels_snow_stars = []
    completed_levels_hv_skier = []
    completed_levels_hv_snowboarder = []
    
    for eval in Evaluation.query.filter_by(student_id=student_id).all():
        if eval.sport_type == 'skier':
            completed_levels_skier.append(eval.level)
        elif eval.sport_type == 'snowboarder':
            completed_levels_snowboarder.append(eval.level)
        elif eval.sport_type == 'snow_stars':
            completed_levels_snow_stars.append(eval.level)
        elif eval.sport_type == 'hv_skier':
            completed_levels_hv_skier.append(eval.level)
        elif eval.sport_type == 'hv_snowboarder':
            completed_levels_hv_snowboarder.append(eval.level)
    
    return render_template('evaluate.html', student=student, 
                         available_sports=available_sports,
                         completed_levels_skier=completed_levels_skier,
                         completed_levels_snowboarder=completed_levels_snowboarder,
                         completed_levels_snow_stars=completed_levels_snow_stars,
                         completed_levels_hv_skier=completed_levels_hv_skier,
                         completed_levels_hv_snowboarder=completed_levels_hv_snowboarder)

@app.route('/evaluations/<int:evaluation_id>')
@login_required
def view_evaluation(evaluation_id):
    evaluation = Evaluation.query.get_or_404(evaluation_id)
    
    if current_user.user_type == 'student' and evaluation.student_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    if current_user.user_type == 'instructor' and evaluation.instructor_id != current_user.id and not instructor_can_access_student(evaluation.student):
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('view_evaluation.html', evaluation=evaluation)

# Admin routes for managing programs and teams

@app.route('/admin/programs')
@login_required
def manage_programs():
    if current_user.user_type != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    programs = Program.query.all()
    return render_template('manage_programs.html', programs=programs)

@app.route('/admin/teams')
@login_required
def manage_teams():
    if current_user.user_type != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    teams = Team.query.all()
    programs = Program.query.all()
    instructors = User.query.filter_by(user_type='instructor').all()
    return render_template('manage_teams.html', teams=teams, programs=programs, instructors=instructors)

@app.route('/admin/create_team', methods=['POST'])
@login_required
def create_team():
    if current_user.user_type != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    name = request.form.get('name')
    program_id = int(request.form.get('program_id'))
    instructor_id = int(request.form.get('instructor_id'))
    team_type = request.form.get('team_type', 'class')  # 'class' for STEP/RIP, 'team' for Snow Stars
    
    team = Team(name=name, program_id=program_id, instructor_id=instructor_id, team_type=team_type)
    db.session.add(team)
    db.session.commit()
    flash('Team created successfully', 'success')
    return redirect(url_for('manage_teams'))

@app.route('/admin/create_program', methods=['POST'])
@login_required
def create_program():
    if current_user.user_type != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    name = request.form.get('name')
    description = request.form.get('description')
    try:
        frequency_type, frequency_value, frequency_days, start_date_obj, end_date_obj = program_schedule_from_form()
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('manage_programs'))
    
    program = Program(
        name=name, 
        description=description,
        frequency_type=frequency_type,
        frequency_value=frequency_value,
        frequency_days=frequency_days,
        start_date=start_date_obj,
        end_date=end_date_obj
    )
    db.session.add(program)
    db.session.commit()
    flash('Program created successfully', 'success')
    return redirect(url_for('manage_programs'))

@app.route('/admin/update_program/<int:program_id>', methods=['POST'])
@login_required
def update_program(program_id):
    if current_user.user_type != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    program = Program.query.get_or_404(program_id)
    
    program.name = request.form.get('name')
    program.description = request.form.get('description')
    if 'start_date' in request.form:
        try:
            program.frequency_type, program.frequency_value, program.frequency_days, program.start_date, program.end_date = program_schedule_from_form()
        except ValueError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('manage_programs'))
    
    db.session.commit()
    flash('Program updated successfully', 'success')
    return redirect(url_for('manage_programs'))

@app.route('/admin/delete_program/<int:program_id>', methods=['POST'])
@login_required
def delete_program(program_id):
    if current_user.user_type != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    program = Program.query.get_or_404(program_id)
    
    # Check if program has teams
    if program.teams:
        flash('Cannot delete program that has teams assigned', 'error')
        return redirect(url_for('manage_programs'))
    
    db.session.delete(program)
    db.session.commit()
    flash('Program deleted successfully', 'success')
    return redirect(url_for('manage_programs'))

@app.route('/admin/update_team/<int:team_id>', methods=['POST'])
@login_required
def update_team(team_id):
    if current_user.user_type != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    team = Team.query.get_or_404(team_id)
    old_program_id = team.program_id
    team.name = request.form.get('name')
    team.program_id = int(request.form.get('program_id'))
    team.instructor_id = int(request.form.get('instructor_id'))
    team.team_type = request.form.get('team_type')
    
    # If program changed, update participation flags for all students in this team
    for student in team.students:
        # Keep legacy instructor assignment synchronized with team ownership.
        student.instructor_id = team.instructor_id
        if old_program_id != team.program_id:
            update_student_participation_from_team(student)
    
    db.session.commit()
    flash('Team updated successfully', 'success')
    return redirect(url_for('manage_teams'))

@app.route('/admin/delete_team/<int:team_id>', methods=['POST'])
@login_required
def delete_team(team_id):
    if current_user.user_type != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    team = Team.query.get_or_404(team_id)
    
    # Check if team has students
    if team.students:
        flash('Cannot delete team that has students assigned', 'error')
        return redirect(url_for('manage_teams'))
    
    db.session.delete(team)
    db.session.commit()
    flash('Team deleted successfully', 'success')
    return redirect(url_for('manage_teams'))

# Note: Database initialization is handled in api/index.py for Vercel

@app.route('/teams/<int:team_id>/session')
@login_required
def team_session(team_id):
    """Team-first workspace for a day's attendance and coaching actions."""
    team = Team.query.get_or_404(team_id)
    if not (is_admin() or instructor_owns_team(team)):
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))

    try:
        session_date = parse_session_date(request.args.get('date'))
    except ValueError:
        flash('Invalid session date', 'error')
        return redirect(url_for('team_session', team_id=team_id))

    students = User.query.filter_by(team_id=team_id, user_type='student').order_by(User.full_name).all()
    attendance = {
        record.student_id: record
        for record in Attendance.query.filter_by(team_id=team_id, session_date=session_date).all()
    }
    latest_evaluations = {}
    completed_levels = {}
    for student in students:
        latest_evaluations[student.id] = Evaluation.query.filter_by(student_id=student.id).order_by(Evaluation.created_at.desc()).first()
        completed_levels[student.id] = Evaluation.query.filter_by(student_id=student.id).count()

    class_session = ClassSession.query.filter_by(team_id=team_id, session_date=session_date).first()

    return render_template(
        'team_session.html', team=team, students=students, session_date=session_date,
        attendance=attendance, latest_evaluations=latest_evaluations, completed_levels=completed_levels,
        class_session=class_session, session_statuses=SESSION_STATUSES
    )

@app.route('/teams/<int:team_id>/session/status', methods=['POST'])
@login_required
def update_session_status(team_id):
    """Update the shared operational state for a coach's class."""
    team = Team.query.get_or_404(team_id)
    if not (is_admin() or instructor_owns_team(team)):
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    try:
        session_date = parse_session_date(request.form.get('session_date'))
    except ValueError:
        flash('Please choose a valid session date', 'error')
        return redirect(url_for('team_session', team_id=team_id))
    status = request.form.get('status', '')
    if status not in SESSION_STATUSES:
        abort(400, description='Invalid class status')
    class_session = ClassSession.query.filter_by(team_id=team_id, session_date=session_date).first()
    if class_session is None:
        class_session = ClassSession(team_id=team_id, session_date=session_date, updated_by=current_user.id)
        db.session.add(class_session)
    class_session.status = status
    class_session.meeting_point = request.form.get('meeting_point', '').strip()[:120] or None
    class_session.coach_note = request.form.get('coach_note', '').strip()[:2000] or None
    class_session.updated_by = current_user.id
    db.session.commit()
    flash(f'Class marked {class_session.status_label.lower()}', 'success')
    return redirect(url_for('team_session', team_id=team_id, date=session_date.isoformat()))

@app.route('/attendance/<int:team_id>')
@login_required
def manage_attendance(team_id):
    """Manage attendance for a team"""
    if current_user.user_type not in ['admin', 'instructor']:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    team = Team.query.get_or_404(team_id)
    
    # Check if instructor has access to this team
    if current_user.user_type == 'instructor' and team.instructor_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    # Get students in this team
    students = User.query.filter_by(team_id=team_id, user_type='student').all()
    
    # Get recent attendance records
    attendance_records = Attendance.query.filter_by(team_id=team_id).order_by(Attendance.session_date.desc()).limit(50).all()
    
    return render_template('attendance.html', team=team, students=students, attendance_records=attendance_records)

@app.route('/attendance/<int:team_id>/record', methods=['POST'])
@login_required
def record_attendance(team_id):
    """Record attendance for a team session"""
    if current_user.user_type not in ['admin', 'instructor']:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    team = Team.query.get_or_404(team_id)
    
    # Check if instructor has access to this team
    if current_user.user_type == 'instructor' and team.instructor_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        session_date = datetime.strptime(request.form.get('session_date', ''), '%Y-%m-%d').date()
    except ValueError:
        flash('Please choose a valid session date', 'error')
        return redirect(url_for('team_session', team_id=team_id))
    if team.program.start_date and session_date < team.program.start_date:
        flash('Session date is before the program begins', 'error')
        return redirect(url_for('team_session', team_id=team_id, date=session_date.isoformat()))
    if team.program.end_date and session_date > team.program.end_date:
        flash('Session date is after the program ends', 'error')
        return redirect(url_for('team_session', team_id=team_id, date=session_date.isoformat()))
    
    # Record attendance for each student
    for student in team.students:
        attended = request.form.get(f'attended_{student.id}') == 'on'
        notes = request.form.get(f'notes_{student.id}', '')
        
        # Check if attendance already exists for this date
        existing = Attendance.query.filter_by(
            student_id=student.id,
            team_id=team_id,
            session_date=session_date
        ).first()
        
        if existing:
            existing.attended = attended
            existing.notes = notes
            existing.recorded_by = current_user.id
        else:
            attendance = Attendance(
                student_id=student.id,
                team_id=team_id,
                session_date=session_date,
                attended=attended,
                notes=notes,
                recorded_by=current_user.id
            )
            db.session.add(attendance)
    
    db.session.commit()
    flash('Attendance recorded successfully', 'success')
    if request.form.get('return_to') == 'session':
        return redirect(url_for('team_session', team_id=team_id, date=session_date.isoformat()))
    return redirect(url_for('manage_attendance', team_id=team_id))

if __name__ == '__main__':
    # Only run init_db in development
    if os.environ.get('FLASK_ENV') == 'development':
        with app.app_context():
            init_db()
    
    # Development server
    app.run(debug=True, host='0.0.0.0', port=5001)
