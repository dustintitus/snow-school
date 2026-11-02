"""Shared admin task organization. Tasks record work; they do not execute it."""
from datetime import date
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from models import db, User, AdminTask

bp = Blueprint('admin_tasks', __name__)
STATUSES = {'todo': 'To do', 'in_progress': 'In progress', 'done': 'Done'}
PRIORITIES = {'normal': 'Normal', 'high': 'High', 'low': 'Low'}


@bp.before_request
@login_required
def require_admin():
    if current_user.user_type != 'admin':
        abort(403)


def fields():
    title = request.form.get('title', '').strip()
    notes = request.form.get('notes', '').strip()
    status = request.form.get('status', 'todo')
    priority = request.form.get('priority', 'normal')
    if not title or len(title) > 160 or len(notes) > 6000 or status not in STATUSES or priority not in PRIORITIES:
        abort(400, description='Check the task title, notes, status and priority.')
    try:
        due = date.fromisoformat(request.form['due_date']) if request.form.get('due_date') else None
        owner = int(request.form['owner_id']) if request.form.get('owner_id') else None
    except ValueError:
        abort(400, description='Invalid due date or owner.')
    if owner is not None:
        user = db.session.get(User, owner)
        if not user or user.user_type != 'admin':
            abort(400, description='Choose an admin owner.')
    return dict(title=title, notes=notes, status=status, priority=priority, due_date=due, owner_id=owner)


@bp.route('/admin/tasks', methods=['GET', 'POST'])
def index():
    if request.method == 'POST' and request.form.get('action') != 'draft':
        task = AdminTask(**fields(), created_by=current_user.id)
        db.session.add(task)
        db.session.commit()
        flash('Task created.', 'success')
        return redirect(url_for('.index'))
    status = request.args.get('status', 'open')
    owner = request.args.get('owner', 'all')
    if status not in {'all', 'open', *STATUSES} or owner not in {'all', 'mine', 'unassigned'}:
        abort(400)
    query = AdminTask.query
    if status == 'open':
        query = query.filter(AdminTask.status != 'done')
    elif status != 'all':
        query = query.filter_by(status=status)
    if owner == 'mine':
        query = query.filter_by(owner_id=current_user.id)
    elif owner == 'unassigned':
        query = query.filter_by(owner_id=None)
    tasks = query.order_by(AdminTask.due_date.is_(None), AdminTask.due_date, AdminTask.created_at.desc()).all()
    draft = {'title': request.form.get('title', '')[:160], 'notes': request.form.get('notes', '')[:6000]} if request.method == 'POST' else {'title': '', 'notes': ''}
    return render_template('admin/tasks.html', tasks=tasks, statuses=STATUSES, priorities=PRIORITIES,
                           admins=User.query.filter_by(user_type='admin').order_by(User.full_name).all(),
                           status=status, owner=owner, draft=draft, today=date.today())


@bp.post('/admin/tasks/<int:task_id>')
def update(task_id):
    task = db.get_or_404(AdminTask, task_id)
    for key, value in fields().items():
        setattr(task, key, value)
    db.session.commit()
    flash('Task updated.', 'success')
    return redirect(url_for('.index'))
