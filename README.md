# Snow School

A comprehensive platform for Horseshoe Valley Resort instructors and coaches to evaluate and work with students and athletes.

## Features

- **Three User Types**: Admin, Instructor, Student
- **Role-Based Access**: Each user type has specific permissions
- **Dual Sport Support**: Separate evaluation programs for Skiers (STEP) and Snowboarders (RIP)
- **Sport-Specific Criteria**: 
  - **Skiers**: Evaluated using STEP program from CSIA (Technical, Edging, Pressure Control, Turn Shape)
  - **Snowboarders**: Evaluated using RIP program from CASI (Board Control, Edge Awareness, Body Positioning, Turn Control)
- **Evaluation System**: Instructors can evaluate students on skills, attitude, and performance with sport-specific criteria
- **Level Progression**: One evaluation per level per student to track progression through STEP (1-8) or RIP (1-6) levels
- **Dashboard Views**: Personalized dashboards for each user role
- **User Management**: Admins can create and manage all user accounts
- **Modern UI**: Beautiful, responsive web interface

## User Roles

### Admin
- Manage all users (create, view)
- View system statistics
- Access to all functionalities

### Instructor/Coach
- View assigned students
- Create and submit evaluations for students
- Track evaluation history
- View student progress

### Student/Athlete
- View personal evaluations
- See scores and feedback for their sport-specific program
- Track progress over time
- Access instructor comments
- See both overall scores and sport-specific program scores

## Getting Started

### Prerequisites
- Python 3.7+
- pip (Python package manager)

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Access the application at `http://localhost:5000`

## Sample Accounts

The application comes with three pre-configured accounts:

- **Admin**
  - Username: `admin`
  - Password: `admin123`

- **Instructor**
  - Username: `instructor1`
  - Password: `instructor123`

- **Student** (Skiing - STEP Program)
  - Username: `student1`
  - Password: `student123`

## Database Schema

The application uses SQLite for data storage. The database automatically creates these tables:

- **Users**: Stores user information and roles
- **Evaluations**: Stores evaluation scores and comments

## Features Overview

### Evaluation System

**General Evaluation (All Students):**
- Skills Score (0-10)
- Attitude Score (0-10)
- Performance Score (0-10)
- Text comments and feedback
- Timestamp for each evaluation

**STEP Program (Skiers - CSIA):**
- Levels: 1-8
- Technical Skills Score (0-10)
- Edging Score (0-10)
- Pressure Control Score (0-10)
- Turn Shape Score (0-10)
- STEP Program Average

**RIP Program (Snowboarders - CASI):**
- Levels: 1-6
- Board Control Score (0-10)
- Edge Awareness Score (0-10)
- Body Positioning Score (0-10)
- Turn Control Score (0-10)
- RIP Program Average

### Security
- Password hashing using Werkzeug
- Session management with Flask-Login
- Role-based access control
- Protected routes

## Project Structure

```
athlete_evaluation_app/
├── app.py              # Main application
├── models.py           # Database models
├── requirements.txt    # Python dependencies
├── README.md          # This file
├── templates/         # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── dashboard_admin.html
│   ├── dashboard_instructor.html
│   ├── dashboard_student.html
│   ├── evaluate.html
│   ├── register.html
│   └── view_evaluation.html
├── static/
│   └── css/
│       └── style.css  # Stylesheet
└── athlete_evaluation.db  # SQLite database (auto-created)
```

## License

MIT License - Feel free to use and modify as needed.
