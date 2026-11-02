"""Read-only planning context for the shared mobile coach dashboard."""
from datetime import timedelta

# Suggested lesson structures, separate from school-approved training releases.
WEEK_FOCUS = (
    ('Meet your class', 'Build confidence, check equipment and observe starting skills.'),
    ('Build control', 'Revisit stopping and control on terrain suited to each learner.'),
    ('Find balance', 'Use familiar movements and games to practise balance.'),
    ('Review your progress', 'Review demonstrated skills and agree on the next learning goal.'),
    ('Build consistency', 'Return to skills that still need practice before adding complexity.'),
    ('Put skills together', 'Link familiar skills while maintaining control and confidence.'),
    ('Prepare to progress', 'Revisit individual goals and collect clear examples of progress.'),
    ('Celebrate progress', 'Reflect on progress and share each learner’s next steps.'),
)


def teaching_context(program, selected_date, evaluation_intervals=(4, 8)):
    result = dict(week=None, label='Schedule needed', focus=None, evaluation=False,
                  scheduled=False, note='Ask an administrator to set the program dates and weekly schedule.')
    if not program.start_date:
        return result
    if selected_date < program.start_date:
        result.update(label='Starts ' + program.start_date.strftime('%b %d'), note='Your program has not started yet.')
        return result
    if program.end_date and selected_date > program.end_date:
        result.update(label='Program complete', note='Choose a program date to review that week.')
        return result
    if program.frequency_type != 'weekly':
        result.update(label='Session-based program', note='Weekly planning is available for weekly programs. Open the class for session tasks.')
        return result
    days = [d.strip().lower() for d in (program.frequency_days or '').split(',') if d.strip()]
    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    if not days or any(d not in weekdays for d in days):
        return result
    first = program.start_date
    while first.strftime('%A').lower() not in days:
        first += timedelta(days=1)
    if selected_date < first:
        result.update(label='Starts ' + first.strftime('%b %d'), note='Your first class is coming up.')
        return result
    week = (selected_date - first).days // 7 + 1
    total = program.frequency_value if len(days) == 1 else None
    if total and week > total:
        result.update(label='Program complete', note='Choose a program date to review that week.')
        return result
    focus = WEEK_FOCUS[week-1] if week <= len(WEEK_FOCUS) else ('Continue individual goals', 'Review the latest progression notes and choose the next skill to practise.')
    if week in evaluation_intervals:
        focus = ('Evaluation week', 'Review demonstrated skills, complete evaluations and agree on each learner’s next steps.')
    result.update(week=week, label=f'Week {week}' + (f' of {total}' if total else ''), focus=focus,
                  evaluation=week in evaluation_intervals, scheduled=selected_date.strftime('%A').lower() in days,
                  note='Based on the program schedule; cancelled or rescheduled classes may need a date adjustment.')
    return result


def evaluation_weeks(program):
    """Per-program admin setting; existing programs retain weeks 4 and 8."""
    from models import db, AppSetting
    row = db.session.get(AppSetting, f'evaluation-weeks:{program.id}')
    return tuple(int(value) for value in row.value.split(',') if value) if row else (4, 8)


def evaluation_availability(program):
    from learning import today
    weeks = evaluation_weeks(program)
    context = teaching_context(program, today(), weeks)
    if context['evaluation']:
        message = f"Open now · Week {context['week']}"
    elif not weeks:
        message = 'Not scheduled by your administrator'
    else:
        message = 'Available in weeks ' + ', '.join(map(str, weeks))
    return {'enabled': context['evaluation'], 'message': message}


def guidance_sections(text):
    """Preserve every source line; indentation alone groups subordinate practices."""
    sections = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[0].isspace() and sections:
            sections[-1]['practices'].append(line.strip())
        else:
            sections.append({'heading': line.strip(), 'practices': []})
    return sections
