import unittest
from datetime import datetime,date
from io import BytesIO
from openpyxl import Workbook
from unittest.mock import patch
import test_workflows
from app import app
from models import db,User,Program,Team,Enrollment,Attendance
from staff_portal import StaffProfile,StaffAvailability,profile_for
from roster_imports import (STAFF_SOURCE,ALPINE_SOURCE,SchoolImport,ImportPerson,ImportedOffering,ImportRegistration,
    ImportIssue,create_preview,apply_import,parse_workbook,key)


def staff_file(phone='111-222-3333',name='New Staff',email='staff@fixture.invalid',reverse=False):
 w=Workbook();s=w.active;s.title='Form Responses 1'
 s.append(['First and Last name ','Timestamp','Email Address','Phone Number','Qualifications','Upload']+[f'Availability [{d}]' for d in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']]+['Holidays','Upload'])
 rows=[[name,datetime(2026,10,1),email,'old-phone','CSIA 1','',*(['Morning']*7),'',''],[name,datetime(2026,10,2),email,phone,'CSIA 2, CASI 1','https://drive.google.com/file/d/evidence',*(['Morning, Afternoon']*7),'Holidays only','']]
 for row in reversed(rows) if reverse else rows:s.append(row)
 m=w.create_sheet('MASTER');m.append(['PRE SEASON']);m.append(['NOTES','Registered for Training?','Indoor Training','Outdoor Training','Training sent','Cert received','Dues received','Hired/MRS','Returning Staff','Time Stamp','Email']);m.append(['','Yes','attended','','Yes','Yes','Yes','','',datetime(2026,10,2),email])
 out=BytesIO();w.save(out);return out.getvalue()


def participant_file(name='Child One',email='parent@fixture.invalid',age=7):
 w=Workbook();s=w.active;s.title='20262027 Last Updated Oct 11';s.append(['UPDATED','REG.','CAPACITY','UNIT PRICE','GROSS REVENUE']);s.append(['HIGHFLYERS SKI | Mondays 6:00PM - 7:30PM',2,20,499,998])
 s=w.create_sheet('HF SKI 2627');s.append(['UPDATED']);s.append([]);s.append(['First Name','','Last Name','Age','Level','Email','Phone']);s.append(['Mondays 6:00 - 7:30'])
 first,last=name.split(' ',1);s.append([1,first,last,age,'L2',email,'555-111-2222']);s.append([2,'Sibling','One',8,'L1',email,'555-111-2222'])
 out=BytesIO();w.save(out);return out.getvalue()

class RosterImportTests(unittest.TestCase):
 login_as=test_workflows.WorkflowTestCase.login_as
 def setUp(self):
  test_workflows.WorkflowTestCase.setUp(self)
  with app.app_context():
   user=User(username='admin',email='admin@fixture.invalid',password_hash='unused',full_name='School Admin',user_type='admin');db.session.add(user);db.session.commit();self.admin_id=user.id
  self.login_as(self.admin_id)
 def apply(self,data,source):
  row=create_preview(data,source,'source.xlsx',self.admin_id);db.session.commit();result=apply_import(row);db.session.commit();return row,result
 def test_staff_repeat_is_idempotent_latest_response_wins_after_reordering(self):
  with app.app_context():
   self.apply(staff_file(),STAFF_SOURCE)
   user=User.query.filter_by(email='staff@fixture.invalid').one();profile=profile_for(user.id)
   self.assertEqual(profile.phone,'111-222-3333');self.assertEqual(profile.discipline,'both');self.assertIsNone(profile.availability_submitted_at)
   self.assertFalse(__import__('werkzeug.security',fromlist=['check_password_hash']).check_password_hash(user.password_hash,'anything'))
   total=User.query.count();self.apply(staff_file(reverse=True),STAFF_SOURCE)
   self.assertEqual(User.query.count(),total);self.assertEqual(ImportPerson.query.count(),1);self.assertEqual(StaffAvailability.query.count(),120)
   self.assertEqual(ImportPerson.query.one().source_facts['master_status']['Indoor Training'],'attended')
 def test_staff_source_updates_and_manual_edits_are_preserved(self):
  with app.app_context():
   self.apply(staff_file(),STAFF_SOURCE);user=User.query.filter_by(email='staff@fixture.invalid').one()
   self.apply(staff_file(phone='222-333-4444'),STAFF_SOURCE);self.assertEqual(profile_for(user.id).phone,'222-333-4444')
   profile_for(user.id).phone='manually-updated';db.session.commit()
   batch,result=self.apply(staff_file(phone='333-444-5555'),STAFF_SOURCE)
   self.assertEqual(profile_for(user.id).phone,'manually-updated');self.assertGreater(result['issue_count'],0)
 def test_instructor_reviewed_availability_survives_repeat(self):
  with app.app_context():
   self.apply(staff_file(),STAFF_SOURCE);user=User.query.filter_by(email='staff@fixture.invalid').one();profile_for(user.id).availability_submitted_at=datetime.now()
   row=StaffAvailability.query.filter_by(user_id=user.id).first();row.morning=False;db.session.commit();self.apply(staff_file(),STAFF_SOURCE)
   self.assertFalse(db.session.get(StaffAvailability,row.id).morning)
 def test_shared_parent_email_creates_distinct_participants_and_blank_dob(self):
  with app.app_context():
   self.apply(participant_file(),ALPINE_SOURCE)
   people=ImportPerson.query.filter_by(role='student').all();self.assertEqual(len(people),2);self.assertNotEqual(people[0].user.email,people[1].user.email)
   self.assertEqual({p.source_facts['contact_email'] for p in people},{'parent@fixture.invalid'})
   count=User.query.count();self.apply(participant_file(email='updated-parent@fixture.invalid'),ALPINE_SOURCE)
   self.assertEqual(User.query.count(),count);self.assertEqual(ImportRegistration.query.count(),2)
 def test_apply_same_batch_twice_does_not_duplicate_or_repeat_mutations(self):
  with app.app_context():
   batch,result=self.apply(staff_file(),STAFF_SOURCE);again=apply_import(batch);db.session.commit()
   self.assertEqual(result,again);self.assertEqual(ImportPerson.query.count(),1)
 def test_wrong_workbook_fails_without_mutation(self):
  with app.app_context():
   self.assertRaises(ValueError,parse_workbook,participant_file(),STAFF_SOURCE)
   self.assertEqual(ImportPerson.query.count(),0)
 def test_admin_upload_preview_apply_and_archive_access(self):
  response=self.client.post('/admin/imports/',data={'source':ALPINE_SOURCE,'workbook':(BytesIO(participant_file()),'source.xlsx')})
  self.assertEqual(response.status_code,302)
  with app.app_context():self.assertEqual(ImportPerson.query.count(),0)
  self.assertEqual(self.client.get(response.location).status_code,200)
  self.assertEqual(self.client.post(response.location).status_code,302)
  with app.app_context():batch_id=SchoolImport.query.one().id
  self.assertEqual(self.client.get(f'/admin/imports/{batch_id}/source').headers['Cache-Control'],'private, no-store')
  self.login_as(self.instructor_id)
  for path in ['/admin/imports/','/admin/imports/placement',f'/admin/imports/{batch_id}',f'/admin/imports/{batch_id}/source']:self.assertEqual(self.client.get(path).status_code,403)
 def test_placement_and_repeat_preserve_assignment(self):
  with app.app_context():
   self.apply(participant_file(),ALPINE_SOURCE);offering=ImportedOffering.query.one();registration=ImportRegistration.query.first();rid=registration.id
   team=Team(name='New class',program_id=offering.program_id,instructor_id=self.other_id);db.session.add(team);db.session.commit();tid=team.id;uid=registration.person.user_id;oid=offering.id
  self.assertEqual(self.client.get('/admin/imports/placement').status_code,200)
  response=self.client.post('/admin/imports/placement',data={'registration_ids':[str(rid)],'team_id':tid,'action':'assign'})
  self.assertEqual(response.status_code,302)
  with app.app_context():
   self.apply(participant_file(),ALPINE_SOURCE);self.assertEqual(db.session.get(ImportRegistration,rid).enrollment.team_id,tid)
  self.login_as(self.other_id)
  self.assertIn(b'Child One',self.client.get(f'/teams/{tid}/session').data)
  self.assertEqual(self.client.get(f'/learning/participants/{uid}').status_code,200)
 def test_multiple_class_memberships_are_visible_and_authorized(self):
  with app.app_context():
   self.apply(participant_file(),ALPINE_SOURCE);registration=ImportRegistration.query.first();user=registration.person.user
   user.team_id=self.team_id
   team=Team(name='Secondary class',program_id=registration.offering.program_id,instructor_id=self.other_id);db.session.add(team);db.session.flush();registration.enrollment.team_id=team.id;db.session.commit();tid=team.id;uid=user.id
   self.assertIn(uid,[u.id for u in team.participants]);self.assertIn(uid,[u.id for u in db.session.get(Team,self.team_id).participants])
  self.login_as(self.other_id);self.assertEqual(self.client.get(f'/learning/participants/{uid}').status_code,200)
  self.assertIn(b'Child One',self.client.get('/dashboard').data)
 def test_ambiguous_existing_participant_is_held_instead_of_duplicated(self):
  with app.app_context():
   user=User(username='existing-child',email='unrelated@fixture.invalid',password_hash='unused',full_name='Child One',user_type='student');db.session.add(user);db.session.commit()
   batch,result=self.apply(participant_file(),ALPINE_SOURCE)
   self.assertEqual(User.query.filter_by(full_name='Child One').count(),1)
   self.assertEqual(result['applied_counts']['people_held'],1)
   self.assertTrue(any('contact evidence' in i.reason for i in ImportIssue.query.filter_by(batch_id=batch.id)))
 def test_same_name_conflicting_contact_is_held(self):
  from openpyxl import load_workbook
  data=participant_file();workbook=load_workbook(BytesIO(data));sheet=workbook['HF SKI 2627'];sheet.append([3,'Child','One',7,'L2','different@fixture.invalid','777-888-9999'])
  output=BytesIO();workbook.save(output)
  parsed=parse_workbook(output.getvalue(),ALPINE_SOURCE)
  self.assertTrue(next(p for p in parsed['people'] if p['name']=='Child One')['identity_conflict'])
  with app.app_context():
   batch,result=self.apply(output.getvalue(),ALPINE_SOURCE)
   self.assertEqual(result['applied_counts']['people_held'],1)

 def test_duplicate_registration_retains_different_source_start_dates(self):
  from openpyxl import load_workbook
  workbook=load_workbook(BytesIO(participant_file()));sheet=workbook['HF SKI 2627'];sheet.cell(3,8,'Start Date');sheet.cell(5,8,'January 4th');sheet.append([3,'Child','One',7,'L2','parent@fixture.invalid','555-111-2222','January 11th'])
  output=BytesIO();workbook.save(output)
  with app.app_context():
   batch,result=self.apply(output.getvalue(),ALPINE_SOURCE)
   person=ImportPerson.query.filter_by(identity_key=key('Child One')).one();row=ImportRegistration.query.filter_by(person_id=person.id).one()
   self.assertEqual(len(row.source_facts['occurrences']),2)
   self.assertEqual(set(row.source_facts['source_start_dates']),{'January 4th','January 11th'})
   self.assertTrue(row.source_facts['source_review']);self.assertGreater(result['issue_count'],0)

 def test_participant_name_correction_is_held_instead_of_creating_duplicate(self):
  with app.app_context():
   self.apply(participant_file(),ALPINE_SOURCE);before=User.query.count()
   batch,result=self.apply(participant_file(name='Corrected Name'),ALPINE_SOURCE)
   self.assertEqual(User.query.count(),before)
   self.assertEqual(result['applied_counts']['people_held'],1)
   self.assertTrue(any('name changed' in row.reason for row in ImportIssue.query.filter_by(batch_id=batch.id)))

 def test_shared_staff_email_does_not_merge_distinct_people(self):
  from openpyxl import load_workbook
  workbook=load_workbook(BytesIO(staff_file()));sheet=workbook['Form Responses 1'];sheet.append(['Different Staff',datetime(2026,10,3),'staff@fixture.invalid','777-888-9999','CASI 2','',*(['Evening']*7),'',''])
  output=BytesIO();workbook.save(output)
  with app.app_context():
   # Start with the earlier single-person interpretation, then safely migrate it.
   self.apply(staff_file(),STAFF_SOURCE);existing=User.query.filter_by(email='staff@fixture.invalid').one();existing_id=existing.id
   self.apply(output.getvalue(),STAFF_SOURCE)
   self.assertEqual(ImportPerson.query.filter_by(role='instructor').count(),2)
   self.assertEqual(User.query.filter_by(full_name='New Staff').one().id,existing_id)
   self.assertEqual(StaffAvailability.query.count(),240)
   before=User.query.count();self.apply(output.getvalue(),STAFF_SOURCE);self.assertEqual(User.query.count(),before)
   self.assertEqual(User.query.filter_by(full_name='Different Staff').count(),1)

 def test_csrf_on_import_and_placement(self):
  app.config['CSRF_ENABLED']=True
  try:
   self.assertEqual(self.client.post('/admin/imports/',data={}).status_code,400)
   self.assertEqual(self.client.post('/admin/imports/placement',data={}).status_code,400)
  finally:app.config['CSRF_ENABLED']=False

if __name__=='__main__':unittest.main()
