"""Auditable, repeatable school imports. Source workbooks are never modified."""
import hashlib
import json
import re
import secrets
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import text
from werkzeug.security import generate_password_hash
from models import db, User, Program, ProgramProfile, Enrollment, Team
from staff_portal import StaffProfile, StaffAvailability, ParticipantDetails, SEASON_START, SEASON_END, utcnow

bp = Blueprint('roster_imports', __name__, url_prefix='/admin/imports')
STAFF_SOURCE = '1mXuoAM6OH8YxSKU0ZgSIFt3b8pUf9EB8z74WmHN5kOM'
ALPINE_SOURCE = '1L4k6Qik-xXYIEkSQ8xOGB48BQXukSyaOJB_7NXZkuuU'
SEASON = '2026-2027'
DAYS = ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')

class SchoolImport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(80), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    workbook = db.Column(db.LargeBinary, nullable=False)
    summary = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='preview')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    applied_at = db.Column(db.DateTime)

class ImportPerson(db.Model):
    __table_args__ = (db.UniqueConstraint('role','identity_key'),)
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)
    identity_key = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    source = db.Column(db.String(80), nullable=False)
    source_facts = db.Column(db.JSON, nullable=False)
    last_values = db.Column(db.JSON, nullable=False, default=dict)
    last_batch_id = db.Column(db.Integer, db.ForeignKey('school_import.id'), nullable=False)
    user = db.relationship('User')

class ImportedOffering(db.Model):
    __table_args__ = (db.UniqueConstraint('source','source_key'),)
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(80), nullable=False)
    source_key = db.Column(db.String(64), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=False, unique=True)
    source_facts = db.Column(db.JSON, nullable=False)
    last_values = db.Column(db.JSON, nullable=False, default=dict)
    last_batch_id = db.Column(db.Integer, db.ForeignKey('school_import.id'), nullable=False)
    program = db.relationship('Program')

class ImportRegistration(db.Model):
    __table_args__ = (db.UniqueConstraint('person_id','offering_id'),)
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('import_person.id'), nullable=False)
    offering_id = db.Column(db.Integer, db.ForeignKey('imported_offering.id'), nullable=False)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('enrollment.id'), nullable=False)
    source_facts = db.Column(db.JSON, nullable=False)
    last_batch_id = db.Column(db.Integer, db.ForeignKey('school_import.id'), nullable=False)
    person = db.relationship('ImportPerson')
    offering = db.relationship('ImportedOffering')
    enrollment = db.relationship('Enrollment')

class ImportedAvailability(db.Model):
    __table_args__ = (db.UniqueConstraint('user_id','day'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    day = db.Column(db.Date, nullable=False)
    last_values = db.Column(db.JSON, nullable=False)

class ImportIssue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('school_import.id'), nullable=False, index=True)
    location = db.Column(db.String(240), nullable=False)
    reason = db.Column(db.String(1000), nullable=False)


def norm(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return re.sub(r'\s+', ' ', value).strip()


def key(value): return hashlib.sha256(norm(value).encode()).hexdigest()


def clean(value):
    if value is None: return ''
    if isinstance(value, (datetime, date)): return value.isoformat()
    if isinstance(value, float) and value.is_integer(): return str(int(value))
    return str(value).strip()


def serial(value):
    if isinstance(value, (datetime, date)): return value.isoformat()
    return value


def valid_email(value):
    value = clean(value).casefold()
    return value if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value) and len(value) <= 120 else ''


def phone(value): return clean(value)


def open_workbook(data):
    if not data or len(data) > 3 * 1024 * 1024: raise ValueError('Choose an XLSX file up to 3 MB.')
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 32 * 1024 * 1024: raise ValueError('Workbook expands beyond the import limit.')
        from openpyxl import load_workbook
        return load_workbook(BytesIO(data), data_only=True)
    except (BadZipFile, KeyError, OSError) as error:
        raise ValueError('This is not a readable XLSX workbook.') from error


def weekly_periods(value):
    value = norm(value)
    if not value or value in ('none','n/a','no','unavailable'): return []
    result = [p for p in ('morning','afternoon','evening') if p in value]
    if 'all day' in value: result = ['morning','afternoon'] + (['evening'] if '8pm' in value or 'evening' in value else [])
    return result


def parse_staff(workbook):
    sheet = next((s for s in workbook if norm(s.title) == 'form responses 1'), None)
    if not sheet: raise ValueError('The staff workbook needs its current Form Responses 1 tab.')
    headers = [clean(c.value) for c in sheet[1]]
    if not headers or norm(headers[0]) != 'first and last name': raise ValueError('Staff source headers changed. Review the mapping before importing.')
    records, issues, duplicate_count = {}, [], 0
    for row_num, cells in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
        row = list(cells) + [None] * max(0,15-len(cells))
        name, email = clean(row[0]), valid_email(row[2])
        if not name: continue
        if not email or len(name) > 100:
            issues.append(dict(location=f'{sheet.title}!{row_num}',reason='Staff name or email is missing/invalid.')); continue
        item = dict(kind='instructor',name=name,email=email,phone=phone(row[3]),qualifications=clean(row[4]),
                    document_links=[u for c in (row[5],row[14]) for u in re.findall(r'https://[^\s,]+',clean(c))],
                    weekly={day:weekly_periods(row[6+n]) for n,day in enumerate(DAYS)},casual_holidays=clean(row[13]),
                    timestamp=clean(row[1]),locations=[f'{sheet.title}!{row_num}'])
        record_key=(email,norm(name))
        if record_key in records:
            duplicate_count += 1
            previous = records[record_key]
            # Source timestamps, not worksheet order, decide the latest resubmission.
            if item['timestamp'] >= previous['timestamp']:
                item['locations'] += previous['locations']; records[record_key] = item
            else: previous['locations'] += item['locations']
        else: records[record_key] = item
    by_email=defaultdict(list)
    for item in records.values():by_email[item['email']].append(item)
    for email,items in by_email.items():
        for item in items:
            item['shared_email']=len(items)>1
            item['identity_text']=email+'|'+norm(item['name']) if len(items)>1 else email
        if len(items)>1:issues.append(dict(location=items[0]['locations'][0],reason='Multiple staff names share an email. Separate staff profiles retained; verify each contact before invitations.'))
    master = next((s for s in workbook if norm(s.title) == 'master'), None)
    if master:
        for row_num, row in enumerate(master.iter_rows(min_row=3, values_only=True), 3):
            # Staff master contains a shifted formula block; email is the join key.
            email = valid_email(row[10] if len(row) > 10 else '')
            if email not in by_email: continue
            candidates=by_email[email]
            if len(candidates)>1:
                candidates=[item for item in candidates if norm(item['name'])==norm(row[11] if len(row)>11 else '')]
            if len(candidates)!=1:
                issues.append(dict(location=f'{master.title}!{row_num}',reason='Shared-email staff status could not be matched uniquely by name; archived for review.'));continue
            item = candidates[0]
            facts = {clean(master.cell(2,i+1).value):serial(row[i]) for i in range(min(9,len(row))) if master.cell(2,i+1).value}
            item.setdefault('master_status',{}).update({k:v for k,v in facts.items() if v is not None})
            item.setdefault('master_locations',[]).append(f'{master.title}!{row_num}')
    not_returning = next((s for s in workbook if norm(s.title) == 'not returning'), None)
    if not_returning:
        names={norm(cell.value) for row in not_returning for cell in row if cell.value}
        for item in records.values(): item['not_returning_source'] = norm(item['name']) in names
    return dict(people=list(records.values()),offerings=[],registrations=[],issues=issues,duplicate_rows=duplicate_count,
                tabs=[s.title for s in workbook],source_rows=sheet.max_row-1)


def schedule_token(value):
    value = norm(value).replace('a.m.','').replace('p.m.','')
    value = re.sub(r'\b(am|pm)\b','',value)
    value = re.sub(r'(?<=\d)(am|pm)', '', value)
    day = next((d for d in DAYS if d in value), '')
    times = re.findall(r'\d{1,2}:\d{2}',value)
    return day,tuple(t.lstrip('0') for t in times)


def family_of(title):
    value=norm(title)
    for family, needles in [('SF',['snowflakes','sf ']),('HF',['highflyers','high flyers','hf ']),('TB',['trailblazers','tb ']),('LIT',['leaders in training','lit ']),('ADULT',['adults','adult ']),('LABS',['droppers','bunsens','labs '])]:
        if any(n in value for n in needles): return family
    return ''


def parse_alpine(workbook):
    summary = next((s for s in workbook if all(norm(s.cell(1,c).value) == label for c,label in [(2,'reg.'),(3,'capacity'),(4,'unit price')])),None)
    if not summary: raise ValueError('Program summary columns REG., CAPACITY and UNIT PRICE were not found.')
    offerings, people, registrations, issues = {}, {}, [], []
    for row_num,row in enumerate(summary.iter_rows(min_row=2,values_only=True),2):
        title=clean(row[0])
        if '|' not in title: continue
        if len(title)>100: raise ValueError('Program title exceeds 100 characters; review the mapping.')
        facts=dict(title=title,registered_count=serial(row[1]),capacity=serial(row[2]),unit_price=serial(row[3]),gross_revenue=serial(row[4]),location=f'{summary.title}!{row_num}',sport='snowboard' if 'snowboard' in norm(title) else 'ski')
        offerings[key(title)]=facts
    # Keep commercial reference records with the offering instead of duplicating programs.
    for sheet in workbook:
        if norm(sheet.title) not in ('aspenware build','rtp build'):continue
        for rn,row in enumerate(sheet.iter_rows(min_row=3,values_only=True),3):
            token=key(clean(row[0]))
            if token in offerings:offerings[token].setdefault('commercial',{})[sheet.title]={'row':rn,'values':[serial(v) for v in row]}
    roster_sheets=[]
    for sheet in workbook:
        starts=[c.column for c in sheet[3] if norm(c.value)=='first name'] if sheet.max_row>=3 else []
        if not starts:continue
        roster_sheets.append(sheet.title)
        for col in starts:
            sport='snowboard' if 'board' in norm(sheet.title) or (family_of(sheet.title) in ('LIT','ADULT') and col>1) else 'ski'
            section=clean(sheet.cell(2,col).value)
            current=None
            for rn in range(4,sheet.max_row+1):
                schedule=clean(sheet.cell(rn,col).value)
                if any(day in norm(schedule) for day in DAYS):
                    candidates=[(k,v) for k,v in offerings.items() if v['sport']==sport and family_of(v['title'])==family_of(sheet.title) and schedule_token(v['title'])==schedule_token(schedule)]
                    if len(candidates)>1:
                        advanced='advanced' in norm(section)
                        candidates=[(k,v) for k,v in candidates if ('advanced' in norm(v['title']))==advanced]
                    if len(candidates)==1:current=candidates[0][0]
                    else:
                        # Preserve mismatched roster schedules as separate offerings for admin review.
                        # Example: LIT Sunday 1-3 differs from the catalogue's Sunday evening.
                        title=f'{sheet.title} {section} | {schedule}'.replace('2627','2026/27').strip()
                        current=key(title)
                        offerings.setdefault(current,dict(title=title[:100],sport=sport,location=f'{sheet.title}!{rn}',schedule_review=True,capacity=None,unit_price=None,registered_count=None))
                        issues.append(dict(location=f'{sheet.title}!{rn}',reason='Roster schedule has no unique matching catalogue offering; preserved separately for review.'))
                    continue
                first,last=clean(sheet.cell(rn,col+1).value),clean(sheet.cell(rn,col+2).value)
                # Empty numbered slots and headings are not participant registrations.
                if not first and not last:continue
                if not current or not re.fullmatch(r'\d+(?:\.0)?',schedule):
                    if first or last:issues.append(dict(location=f'{sheet.title}!{rn}',reason='Unrecognised non-roster content retained in the archived workbook.'))
                    continue
                if not first or not last:
                    issues.append(dict(location=f'{sheet.title}!{rn}',reason='Incomplete participant name.'));continue
                name=' '.join((first,last));age=clean(sheet.cell(rn,col+3).value)
                email=valid_email(sheet.cell(rn,col+5).value);number=phone(sheet.cell(rn,col+6).value)
                identity=key(name)
                item=dict(kind='student',name=name,age=age,contact_email=email,phone=number,
                          locations=[f'{sheet.title}!{sheet.cell(rn,col+1).column_letter}{rn}'],sport=sport)
                if identity in people:
                    previous=people[identity]
                    age_conflict=previous['age'] and age and previous['age']!=age
                    email_conflict=previous['contact_email'] and email and previous['contact_email']!=email
                    digits=lambda v:re.sub(r'\D','',v).removeprefix('1') if len(re.sub(r'\D','',v))==11 else re.sub(r'\D','',v)
                    phone_conflict=previous['phone'] and number and digits(previous['phone'])!=digits(number)
                    if age_conflict or email_conflict or phone_conflict:
                        previous['identity_conflict']=True
                        issues.append(dict(location=item['locations'][0],reason='The same participant name has conflicting age or contact information; held for identity review.'))
                    for f in ('contact_email','phone'):
                        if not previous[f] and item[f]:previous[f]=item[f]
                    previous['locations']+=item['locations']
                else:people[identity]=item
                start_text=clean(sheet.cell(rn,col+7).value) if norm(sheet.cell(3,col+7).value)=='start date' else ''
                registrations.append(dict(identity_key=identity,offering_key=current,level=clean(sheet.cell(rn,col+4).value),location=item['locations'][0],age=age,contact_email=email,phone=number,start_date_text=start_text))
    grouped=defaultdict(list)
    for item in registrations:grouped[(item['identity_key'],item['offering_key'])].append(item)
    for occurrences in grouped.values():
        dates=sorted({row.get('start_date_text','') for row in occurrences if row.get('start_date_text')})
        levels={row.get('level') for row in occurrences if row.get('level')}
        if len(dates)>1 or len(levels)>1:
            issues.append(dict(location=occurrences[0]['location'],reason='Repeated registration has different start dates or levels; all source occurrences retained for review.'))
    return dict(people=list(people.values()),offerings=[dict(source_key=k,**v) for k,v in offerings.items()],registrations=registrations,issues=issues,duplicate_rows=len(registrations)-len(people),tabs=[s.title for s in workbook],source_rows=len(registrations),roster_tabs=roster_sheets)


def parse_workbook(data,source):
    workbook=open_workbook(data)
    try:
        if source==STAFF_SOURCE:return parse_staff(workbook)
        if source==ALPINE_SOURCE:return parse_alpine(workbook)
        raise ValueError('Select a configured source workbook.')
    finally:workbook.close()


def create_preview(data,source,filename,author):
    parsed=parse_workbook(data,source)
    summary={k:v for k,v in parsed.items() if k not in ('people','offerings','registrations','issues')}
    summary.update(people=len(parsed['people']),offerings=len(parsed['offerings']),registrations=len(parsed['registrations']),source_issues=parsed['issues'])
    row=SchoolImport(source=source,filename=Path(filename).name[:200],sha256=hashlib.sha256(data).hexdigest(),workbook=data,summary=summary,created_by=author)
    db.session.add(row);db.session.flush()
    return row


def merge_field(obj,attribute,value,previous,token,issues,location,creating=False):
    if value is None or value=='':return
    value=serial(value)
    current=getattr(obj,attribute)
    old=previous.get(token)
    if creating or current in (None,'') or current==value or (token in previous and current==old):
        setattr(obj,attribute,value)
    elif token in previous and old!=value:
        issues.append(dict(location=location,reason=f'App change to {token} preserved; source change needs review.'))
    previous[token]=value


def lock_import():
    if db.engine.dialect.name=='postgresql':db.session.execute(text('SELECT pg_advisory_xact_lock(83102701)'))


def apply_import(batch):
    lock_import()
    # Reload inside the lock so two confirmations of the same batch cannot race.
    db.session.refresh(batch)
    if batch.status=='applied':return batch.summary
    parsed=parse_workbook(batch.workbook,batch.source)
    issues=list(parsed['issues']);counts=Counter()
    known={p.identity_key:p for p in ImportPerson.query.filter_by(role='instructor' if batch.source==STAFF_SOURCE else 'student').all()}
    current_student_keys={key(item['name']) for item in parsed['people'] if item['kind']=='student'}
    prior_locations=defaultdict(list)
    for prior in known.values():
        if prior.source==batch.source and prior.identity_key not in current_student_keys:
            for location in prior.source_facts.get('locations',[]):prior_locations[location].append(prior)
    all_users=User.query.all()
    by_email={norm(u.email):u for u in all_users}
    by_name=defaultdict(list)
    for u in all_users:by_name[(u.user_type,norm(u.full_name))].append(u)
    offerings={}
    for item in parsed['offerings']:
        row=ImportedOffering.query.filter_by(source=batch.source,source_key=item['source_key']).first()
        creating=row is None
        if creating:
            existing=Program.query.filter(db.func.lower(Program.name)==item['title'].lower()).all()
            if len(existing)>1:
                issues.append(dict(location=item['location'],reason='Multiple existing programs match this offering.'));continue
            program=existing[0] if existing else Program(name=item['title'],frequency_type='weekly',frequency_value=8)
            if not existing:db.session.add(program);db.session.flush()
            row=ImportedOffering(source=batch.source,source_key=item['source_key'],program_id=program.id,source_facts=item,last_values={},last_batch_id=batch.id)
            db.session.add(row);counts['programs_created' if not existing else 'programs_matched']+=1
        else:counts['programs_updated']+=1
        program=row.program or db.session.get(Program,row.program_id)
        profile=program.profile
        if not profile:
            profile=ProgramProfile(program_id=program.id);db.session.add(profile)
        previous=dict(row.last_values or {})
        for attr,value in [('capacity',int(float(item['capacity'])) if item.get('capacity') is not None else None),('price_cents',round(float(item['unit_price'])*100) if item.get('unit_price') is not None else None),('sport',item['sport'])]:
            merge_field(profile,attr,value,previous,'profile.'+attr,issues,item['location'],creating)
        commercial=item.get('commercial',{})
        reference=next(iter(commercial.values()),{})
        description=clean(reference.get('values',['',''])[1]) if reference.get('values') else ''
        if description:
            merge_field(program,'description',description,previous,'description',issues,item['location'],creating)
            match=re.search(r'Ages (\d+)\s*-\s*(\d+)',description,re.I)
            if match:
                for attr,v in [('age_min',int(match[1])),('age_max',int(match[2]))]:merge_field(profile,attr,v,previous,'profile.'+attr,issues,item['location'],creating)
            merge_field(profile,'ability_levels',description.split(';',1)[-1].strip()[:100],previous,'profile.ability_levels',issues,item['location'],creating)
        if creating:profile.category='8 Week Programs';profile.duration_label='8 weeks'
        profile.season=SEASON;profile.source_url='https://docs.google.com/spreadsheets/d/'+batch.source
        day=schedule_token(item['title'])[0]
        if creating:
            program.frequency_days=day
            # Jan 4 is the first program week explicitly listed in the build reference.
            first=date(2027,1,4)
            if day:
                while first.weekday()!=DAYS.index(day):first+=timedelta(days=1)
                program.start_date=first;program.end_date=first+timedelta(weeks=7)
        row.source_facts=item;row.last_values=previous;row.last_batch_id=batch.id
        offerings[item['source_key']]=row
    db.session.flush()
    matched_people={}
    for item in parsed['people']:
        role=item['kind'];identity=key(item.get('identity_text',item['email'])) if role=='instructor' else key(item['name'])
        location=item['locations'][0]
        if item.get('identity_conflict'):
            counts['people_held']+=1;continue
        person=known.get(identity)
        if person is None and role=='instructor' and item.get('shared_email'):
            legacy=known.get(key(item['email']))
            if legacy and norm(legacy.user.full_name)==norm(item['name']):
                person=legacy;person.identity_key=identity;known[identity]=person
        creating=person is None
        if person:user=person.user
        else:
            if role=='student' and any(prior_locations.get(loc) for loc in item['locations']):
                issues.append(dict(location=location,reason='A previously imported participant name changed at this source location. Held for identity review to prevent a duplicate account.'));counts['people_held']+=1;continue
            names=by_name[(role,norm(item['name']))]
            candidate=by_email.get(item.get('email','')) if role=='instructor' else None
            if candidate and item.get('shared_email') and norm(candidate.full_name)!=norm(item['name']):candidate=None
            if candidate and candidate.user_type!=role:
                issues.append(dict(location=location,reason='Email already belongs to a different account role.'));counts['people_held']+=1;continue
            if not candidate and len(names)==1:
                # Never silently merge a changed staff email, or two distinct people with the same name.
                if role=='instructor' and names[0].email and names[0].email.lower()!=item['email']:
                    issues.append(dict(location=location,reason='Staff name matches an account with a different email. Identity review required.'));counts['people_held']+=1;continue
                if role=='student':
                    contact=valid_email(item.get('contact_email',''))
                    details=db.session.get(ParticipantDetails,names[0].id)
                    same_email=contact and norm(names[0].email)==contact
                    same_phone=bool(details and details.phone and re.sub(r'\D','',details.phone)==re.sub(r'\D','',item.get('phone','')))
                    if not same_email and not same_phone:
                        issues.append(dict(location=location,reason='Existing participant has this name but no matching contact evidence. Identity review required.'));counts['people_held']+=1;continue
                candidate=names[0]
            elif not candidate and len(names)>1:
                issues.append(dict(location=location,reason='Multiple accounts have this name; identity review required.'));counts['people_held']+=1;continue
            user=candidate
            if user is None:
                username=('staff-' if role=='instructor' else 'participant-')+identity[:20]
                email=item['email'] if role=='instructor' and not item.get('shared_email') else identity[:30]+('@staff.snowschool.invalid' if role=='instructor' else '@participants.snowschool.invalid')
                user=User(username=username,email=email,password_hash='!imported-account-'+secrets.token_hex(32),full_name=item['name'],user_type=role)
                db.session.add(user);db.session.flush();by_email[norm(email)]=user;by_name[(role,norm(user.full_name))].append(user);counts['people_created']+=1
            else:counts['people_matched']+=1
            person=ImportPerson(role=role,identity_key=identity,user_id=user.id,source=batch.source,source_facts={},last_values={},last_batch_id=batch.id)
            db.session.add(person);known[identity]=person
        if not creating:counts['people_updated']+=1
        previous=dict(person.last_values or {})
        merge_field(user,'full_name',item['name'],previous,'name',issues,location,creating)
        if role=='instructor':
            profile=db.session.get(StaffProfile,user.id)
            new_profile=profile is None
            if new_profile:profile=StaffProfile(user_id=user.id);db.session.add(profile)
            merge_field(profile,'phone',item.get('phone'),previous,'phone',issues,location,new_profile)
            quals=norm(item.get('qualifications',''))
            ski=any(x in quals for x in ('csia','psic','ski'))
            board=any(x in quals for x in ('casi','snowboard'))
            if ski or board:merge_field(profile,'discipline','both' if ski and board else 'snowboard' if board else 'ski',previous,'discipline',issues,location,new_profile)
            db.session.flush()
            existing_days={r.day:r for r in StaffAvailability.query.filter_by(user_id=user.id).all()}
            snapshots={r.day:r for r in ImportedAvailability.query.filter_by(user_id=user.id).all()}
            for n in range((SEASON_END-SEASON_START).days+1):
                day=SEASON_START+timedelta(days=n);periods=item['weekly'][DAYS[day.weekday()]]
                values={p:p in periods for p in ('morning','afternoon','evening')}
                slot=existing_days.get(day);snapshot=snapshots.get(day)
                if slot is None:
                    slot=StaffAvailability(user_id=user.id,day=day,**values);db.session.add(slot);counts['availability_created']+=1
                elif snapshot and not profile.availability_submitted_at and all(getattr(slot,p)==snapshot.last_values.get(p) for p in values):
                    for p,v in values.items():setattr(slot,p,v)
                    counts['availability_updated']+=1
                elif any(getattr(slot,p)!=values[p] for p in values):counts['availability_preserved']+=1
                if not snapshot:snapshot=ImportedAvailability(user_id=user.id,day=day);db.session.add(snapshot)
                snapshot.last_values=values
        person.source_facts=item;person.last_values=previous;person.last_batch_id=batch.id
        matched_people[identity]=person
    db.session.flush()
    seen_registrations=set()
    source_occurrences=defaultdict(list)
    for item in parsed['registrations']:source_occurrences[(item['identity_key'],item['offering_key'])].append(item)
    for item in parsed['registrations']:
        person=matched_people.get(item['identity_key']);offering=offerings.get(item['offering_key'])
        if not person or not offering:counts['registrations_held']+=1;continue
        pair=(person.id,offering.id)
        if pair in seen_registrations:counts['duplicate_registrations_skipped']+=1;continue
        seen_registrations.add(pair)
        registration=ImportRegistration.query.filter_by(person_id=person.id,offering_id=offering.id).first()
        if not registration:
            enrollment=Enrollment.query.filter_by(student_id=person.user_id,program_id=offering.program_id,season=SEASON).first()
            if not enrollment:
                enrollment=Enrollment(student_id=person.user_id,program_id=offering.program_id,season=SEASON,status='registered');db.session.add(enrollment);db.session.flush()
            registration=ImportRegistration(person_id=person.id,offering_id=offering.id,enrollment_id=enrollment.id,source_facts=item,last_batch_id=batch.id)
            db.session.add(registration);counts['registrations_created']+=1
        else:counts['registrations_updated']+=1
        occurrences=source_occurrences[(item['identity_key'],item['offering_key'])]
        dates=sorted({r.get('start_date_text','') for r in occurrences if r.get('start_date_text')})
        registration.source_facts={**item,'occurrences':occurrences,'source_start_dates':dates,'source_review':len(dates)>1 or len({r['level'] for r in occurrences if r['level']})>1}
        registration.last_batch_id=batch.id
        # Enrollment/team assignments, evaluations and consent are never reset by a source refresh.
        user=person.user
        if offering.source_facts['sport']=='ski':user.participates_skier=True
        else:user.participates_snowboarder=True
    for issue in issues:db.session.add(ImportIssue(batch_id=batch.id,location=issue['location'][:240],reason=issue['reason'][:1000]))
    batch.summary={**batch.summary,'applied_counts':dict(counts),'issue_count':len(issues)}
    batch.status='applied';batch.applied_at=utcnow()
    db.session.flush()
    return batch.summary


def admin():
    if current_user.user_type!='admin':abort(403)

@bp.route('/',methods=['GET','POST'])
@login_required
def index():
    admin()
    if request.method=='POST':
        upload=request.files.get('workbook')
        if not upload:abort(400,description='Choose a workbook export.')
        try:batch=create_preview(upload.read(3*1024*1024+1),request.form.get('source'),upload.filename,current_user.id)
        except ValueError as error:abort(400,description=str(error))
        db.session.commit()
        return redirect(url_for('.review',batch_id=batch.id))
    return render_template('imports/index.html',batches=SchoolImport.query.order_by(SchoolImport.id.desc()).limit(40).all(),staff_source=STAFF_SOURCE,alpine_source=ALPINE_SOURCE)

@bp.route('/<int:batch_id>',methods=['GET','POST'])
@login_required
def review(batch_id):
    admin();batch=db.get_or_404(SchoolImport,batch_id)
    if request.method=='POST':
        try:apply_import(batch);db.session.commit()
        except Exception:
            db.session.rollback();raise
        flash('Import applied. Review any held records and assign registrations to classes. No welcome emails were sent.','success')
        return redirect(url_for('.review',batch_id=batch.id))
    return render_template('imports/review.html',batch=batch,issues=ImportIssue.query.filter_by(batch_id=batch.id).all())

@bp.route('/<int:batch_id>/source')
@login_required
def source_download(batch_id):
    admin();batch=db.get_or_404(SchoolImport,batch_id)
    response=send_file(BytesIO(batch.workbook),download_name=batch.filename,as_attachment=True,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response.headers['Cache-Control']='private, no-store';return response

@bp.route('/placement',methods=['GET','POST'])
@login_required
def placement():
    admin()
    from learning import number, field
    if request.method=='POST':
        ids=request.form.getlist('registration_ids')
        if not ids or len(ids)>200 or any(not i.isdigit() for i in ids):abort(400,description='Select up to 200 registrations.')
        registrations=ImportRegistration.query.filter(ImportRegistration.id.in_([int(i) for i in ids])).all()
        if len(registrations)!=len(set(ids)):abort(400)
        program_ids={r.offering.program_id for r in registrations}
        if len(program_ids)!=1:abort(400,description='Assign one program offering at a time.')
        action=request.form.get('action')
        if action=='create_class':
            instructor=db.get_or_404(User,number('instructor_id',1,2**31-1))
            if instructor.user_type!='instructor':abort(400)
            from staff_portal import active_staff
            if not active_staff(instructor.id):abort(400,description='Select an active instructor.')
            name=field('class_name',100)
            if Team.query.filter_by(name=name,program_id=next(iter(program_ids))).first():abort(400,description='A class with this name already exists in this offering.')
            team=Team(name=name,program_id=next(iter(program_ids)),instructor_id=instructor.id,team_type=request.form.get('team_type','class'))
            if team.team_type not in ('class','team'):abort(400)
            db.session.add(team);db.session.flush()
        else:team=db.get_or_404(Team,number('team_id',1,2**31-1))
        if team.program_id not in program_ids:abort(400,description='Choose a class belonging to the selected offering.')
        from operations import qualification_check
        qualification_check(team,team.instructor,request.form.get('override_reason','').strip())
        for row in registrations:
            old_team_id=row.enrollment.team_id
            row.enrollment.team_id=team.id;row.enrollment.status='registered'
            # Keep the legacy primary assignment for existing tools, with additional enrolments supported.
            if not row.person.user.team_id or row.person.user.team_id == old_team_id:
                row.person.user.team_id=team.id;row.person.user.instructor_id=team.instructor_id
        db.session.commit();flash(f'{len(registrations)} registrations assigned to {team.name}.','success')
        return redirect(url_for('.placement',offering_id=registrations[0].offering_id))
    offerings=ImportedOffering.query.order_by(ImportedOffering.id).all()
    requested=request.args.get('offering_id','')
    offering=db.get_or_404(ImportedOffering,int(requested)) if requested.isdigit() else (offerings[0] if offerings else None)
    registrations=ImportRegistration.query.filter_by(offering_id=offering.id).all() if offering else []
    from staff_portal import active_staff
    staff=[u for u in User.query.filter_by(user_type='instructor').order_by(User.full_name).all() if active_staff(u.id)]
    return render_template('imports/placement.html',offerings=offerings,offering=offering,registrations=registrations,teams=Team.query.filter_by(program_id=offering.program_id).all() if offering else [],instructors=staff)

@bp.app_template_global('imported_staff_facts')
def imported_staff_facts(user_id):
    if not current_user.is_authenticated or (current_user.user_type!='admin' and current_user.id!=user_id):return []
    return ImportPerson.query.filter_by(role='instructor',user_id=user_id).all()
