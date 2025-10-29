import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Evaluation, Program, Team, Attendance
from datetime import datetime
from config import config
import logging

app = Flask(__name__)

# Load configuration from environment
env = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config.get(env, config['development']))

# Configure logging
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
            ('Terrain Park', 'Specialized program for terrain park and freestyle development', 'daily', 6, None)
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

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint for debugging"""
    try:
        # Test database connection
        user_count = User.query.count()
        program_count = Program.query.count()
        
        return {
            'status': 'healthy',
            'database': 'connected',
            'users': user_count,
            'programs': program_count,
            'environment': os.environ.get('FLASK_ENV', 'development')
        }
    except Exception as e:
        app.logger.error(f"Health check error: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'environment': os.environ.get('FLASK_ENV', 'development')
        }, 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            
            if not username or not password:
                flash('Please enter both username and password', 'error')
                return render_template('login.html')
            
            user = User.query.filter_by(username=username).first()
            
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password', 'error')
        except Exception as e:
            app.logger.error(f"Login error: {e}")
            flash('An error occurred during login. Please try again.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
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
        return render_template('dashboard_instructor.html', students=students, evaluations=recent_evaluations, teams=instructor_teams if instructor_teams else [])
    else:
        evaluations = Evaluation.query.filter_by(student_id=current_user.id).order_by(Evaluation.level).all()
        return render_template('dashboard_student.html', evaluations=evaluations)

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if current_user.user_type != 'admin':
        flash('Only admins can create new users', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        user_type = request.form.get('user_type')
        instructor_id = request.form.get('instructor_id')
        team_id = request.form.get('team_id')
        participates_skier = request.form.get('participates_skier') == 'on'
        participates_snowboarder = request.form.get('participates_snowboarder') == 'on'
        participates_snow_stars = request.form.get('participates_snow_stars') == 'on'
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('register.html', instructors=instructors, teams=teams, programs=programs)
        
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            full_name=full_name,
            user_type=user_type,
            participates_skier=participates_skier if user_type == 'student' else False,
            participates_snowboarder=participates_snowboarder if user_type == 'student' else False,
            participates_snow_stars=participates_snow_stars if user_type == 'student' else False,
            instructor_id=int(instructor_id) if instructor_id else None,
            team_id=int(team_id) if team_id and user_type == 'student' else None
        )
        
        db.session.add(new_user)
        db.session.commit()
        flash('User created successfully', 'success')
        return redirect(url_for('dashboard'))
    
    instructors = User.query.filter_by(user_type='instructor').all()
    teams = Team.query.all()
    programs = Program.query.all()
    return render_template('register.html', instructors=instructors, teams=teams, programs=programs)

@app.route('/evaluate/<int:student_id>', methods=['GET', 'POST'])
@login_required
def evaluate_student(student_id):
    if current_user.user_type != 'instructor':
        flash('Only instructors can evaluate students', 'error')
        return redirect(url_for('dashboard'))
    
    student = User.query.get_or_404(student_id)
    
    if student.user_type != 'student' or student.instructor_id != current_user.id:
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
        
        if not sport_type:
            flash('Please select a sport for evaluation.', 'error')
            return redirect(url_for('dashboard'))
        
        level = int(request.form.get('level'))
        
        # Check if student already has an evaluation for this level
        existing_evaluation = Evaluation.query.filter_by(
            student_id=student_id, 
            sport_type=sport_type,
            level=level
        ).first()
        
        if existing_evaluation:
            flash(f'Student already has an evaluation for level {level}. You can only create one evaluation per level per student.', 'error')
            return redirect(url_for('dashboard'))
        
        evaluation = Evaluation(
            student_id=student_id,
            instructor_id=current_user.id,
            sport_type=sport_type,
            level=level,
            skills_score=float(request.form.get('skills_score')),
            attitude_score=float(request.form.get('attitude_score')),
            performance_score=float(request.form.get('performance_score')),
            comments=request.form.get('comments'),
            created_at=datetime.now()
        )
        
        # Add sport-specific criteria
        if sport_type == 'skier':
            evaluation.technical_score = float(request.form.get('technical_score'))
            evaluation.edging_score = float(request.form.get('edging_score'))
            evaluation.pressure_control_score = float(request.form.get('pressure_control_score'))
            evaluation.turn_shape_score = float(request.form.get('turn_shape_score'))
        elif sport_type == 'snowboarder':
            evaluation.board_control_score = float(request.form.get('board_control_score'))
            evaluation.edge_awareness_score = float(request.form.get('edge_awareness_score'))
            evaluation.body_positioning_score = float(request.form.get('body_positioning_score'))
            evaluation.turn_control_score = float(request.form.get('turn_control_score'))
        elif sport_type == 'snow_stars':
            evaluation.movement_quality_score = float(request.form.get('movement_quality_score'))
            evaluation.balance_score = float(request.form.get('balance_score'))
            evaluation.control_score = float(request.form.get('control_score'))
            evaluation.awareness_score = float(request.form.get('awareness_score'))
        
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
    
    # Get completed levels for each sport
    completed_levels_skier = []
    completed_levels_snowboarder = []
    completed_levels_snow_stars = []
    
    for eval in Evaluation.query.filter_by(student_id=student_id).all():
        if eval.sport_type == 'skier':
            completed_levels_skier.append(eval.level)
        elif eval.sport_type == 'snowboarder':
            completed_levels_snowboarder.append(eval.level)
        elif eval.sport_type == 'snow_stars':
            completed_levels_snow_stars.append(eval.level)
    
    return render_template('evaluate.html', student=student, 
                         available_sports=available_sports,
                         completed_levels_skier=completed_levels_skier,
                         completed_levels_snowboarder=completed_levels_snowboarder,
                         completed_levels_snow_stars=completed_levels_snow_stars)

@app.route('/evaluations/<int:evaluation_id>')
@login_required
def view_evaluation(evaluation_id):
    evaluation = Evaluation.query.get_or_404(evaluation_id)
    
    if current_user.user_type == 'student' and evaluation.student_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    if current_user.user_type == 'instructor' and evaluation.instructor_id != current_user.id:
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
    frequency_type = request.form.get('frequency_type', 'consecutive')
    frequency_value = int(request.form.get('frequency_value', 8))
    frequency_days = request.form.get('frequency_days', None)
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date', None)
    
    # Convert date strings to date objects
    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
    
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
    program.frequency_type = request.form.get('frequency_type', 'consecutive')
    program.frequency_value = int(request.form.get('frequency_value', 8))
    program.frequency_days = request.form.get('frequency_days', None)
    
    # Handle date updates
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date', None)
    
    if start_date:
        program.start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if end_date:
        program.end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
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
    team.name = request.form.get('name')
    team.program_id = int(request.form.get('program_id'))
    team.instructor_id = int(request.form.get('instructor_id'))
    team.team_type = request.form.get('team_type')
    
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
    
    session_date = datetime.strptime(request.form.get('session_date'), '%Y-%m-%d').date()
    
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
    return redirect(url_for('manage_attendance', team_id=team_id))

if __name__ == '__main__':
    # Only run init_db in development
    if os.environ.get('FLASK_ENV') == 'development':
        with app.app_context():
            init_db()
    
    # Development server
    app.run(debug=True, host='0.0.0.0', port=5001)
