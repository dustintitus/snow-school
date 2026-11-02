/** Browser-independent Snow School availability sync. Never log identity tokens. */
const APP_AVAILABILITY_WORKBOOK_ = '1mXuoAM6OH8YxSKU0ZgSIFt3b8pUf9EB8z74WmHN5kOM';
const APP_AVAILABILITY_URL_ = 'https://snowschool.app/api/integrations/availability';
const APP_AVAILABILITY_DAYS_ = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const APP_AVAILABILITY_HEADERS_ = ['App ID','Instructor','Email','Date','Weekday','Morning','Afternoon','Evening','Active','Submitted UTC','Synced UTC'];
var APP_AVAILABILITY_SNAPSHOT_CACHE_ = null;

function appAvailabilityConnectionInfo() {
  const token = ScriptApp.getIdentityToken();
  if (!token) throw new Error('The manifest needs the openid and userinfo.email scopes.');
  const claims = JSON.parse(Utilities.newBlob(Utilities.base64DecodeWebSafe(token.split('.')[1])).getDataAsString());
  console.log(JSON.stringify({client_id: claims.aud, google_account: claims.email, workbook: APP_AVAILABILITY_WORKBOOK_}));
}

function appAvailabilityInspectMatching() {
  const ss=SpreadsheetApp.openById(APP_AVAILABILITY_WORKBOOK_);
  const response=UrlFetchApp.fetch(APP_AVAILABILITY_URL_+'?workbook='+APP_AVAILABILITY_WORKBOOK_,{headers:{Authorization:'Bearer '+ScriptApp.getIdentityToken()},muteHttpExceptions:true});
  if(response.getResponseCode()!==200)throw new Error('Feed HTTP '+response.getResponseCode());
  const feed=JSON.parse(response.getContentText());appAvailabilityValidateFeed_(feed);
  const unmatched=new Set(appAvailabilityIdentityProblems_(feed.rows,appAvailabilityMaster_(ss)));
  const names=new Map();feed.rows.forEach(r=>{if(unmatched.has(r.user_id))names.set(r.user_id,r.name);});
  console.log(JSON.stringify({reviewed_instructors:new Set(feed.rows.map(r=>r.user_id)).size,availability_rows:feed.rows.length,unmatched:Array.from(names,([id,name])=>({id,name}))}));
}

function appAvailabilityInstallHourly() {
  const ss = SpreadsheetApp.openById(APP_AVAILABILITY_WORKBOOK_);
  appAvailabilityAssertWorkbook_(ss);
  // A successful manual sync is required before installing unattended writes.
  appAvailabilitySync();
  const existing = ScriptApp.getProjectTriggers();
  if (!existing.some(t => t.getHandlerFunction() === 'appAvailabilitySync')) {
    ScriptApp.newTrigger('appAvailabilitySync').timeBased().everyHours(1).create();
  }
  if (!existing.some(t => t.getHandlerFunction() === 'appAvailabilityHighlightEdit')) {
    ScriptApp.newTrigger('appAvailabilityHighlightEdit').forSpreadsheet(ss).onEdit().create();
  }
  console.log('Hourly availability sync and yellow edit highlighting are installed. Existing school triggers were preserved.');
}

function appAvailabilitySync() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) throw new Error('Another availability sync is running; retry later.');
  const props = PropertiesService.getScriptProperties();
  try {
    const ss = SpreadsheetApp.openById(APP_AVAILABILITY_WORKBOOK_);
    appAvailabilityAssertWorkbook_(ss);
    const token = ScriptApp.getIdentityToken();
    if (!token) throw new Error('Google identity authorization is missing.');
    const response = UrlFetchApp.fetch(APP_AVAILABILITY_URL_ + '?workbook=' + APP_AVAILABILITY_WORKBOOK_, {
      headers: {Authorization: 'Bearer ' + token}, muteHttpExceptions: true, followRedirects: false
    });
    if (response.getResponseCode() !== 200) {
      throw new Error('Availability feed returned HTTP ' + response.getResponseCode() + '. Check the app connection settings.');
    }
    const feed = JSON.parse(response.getContentText());
    appAvailabilityValidateFeed_(feed);
    // Preflight permissions and schema before touching any cells.
    APP_AVAILABILITY_DAYS_.forEach(name => {
      const s = ss.getSheetByName(name);
      if (!s || !s.getRange(1,1,Math.max(2,s.getLastRow()),5).canEdit()) throw new Error('Cannot edit weekday sheet: ' + name);
      appAvailabilityAssertWeekday_(s);
    });
    const master = appAvailabilityMaster_(ss);
    const identityProblems = appAvailabilityIdentityProblems_(feed.rows, master);
    if (identityProblems.length) throw new Error('Resolve MASTER identity matches for App IDs: ' + identityProblems.join(', '));
    const sheet = appAvailabilityWriteSnapshot_(ss, feed);
    APP_AVAILABILITY_SNAPSHOT_CACHE_ = null;
    let changed = 0;
    APP_AVAILABILITY_DAYS_.forEach(name => { changed += appAvailabilityApplyDay_(ss, ss.getSheetByName(name), name); });
    SpreadsheetApp.flush();
    props.setProperty('APP_AVAILABILITY_LAST_RUN', JSON.stringify({status:'ok', at:new Date().toISOString(), rows:feed.rows.length, weekday_changes:changed}));
    console.log(JSON.stringify({status:'ok', availability_rows:sheet.getLastRow()-1, weekday_changes:changed}));
  } catch (error) {
    props.setProperty('APP_AVAILABILITY_LAST_RUN', JSON.stringify({status:'failed', at:new Date().toISOString(), message:String(error.message).slice(0,500)}));
    throw error;
  } finally { lock.releaseLock(); }
}

function appAvailabilityAssertWorkbook_(ss) {
  if (!ss || ss.getId() !== APP_AVAILABILITY_WORKBOOK_) throw new Error('This script must remain bound to the Horseshoe master schedule.');
}

function appAvailabilityValidateFeed_(feed) {
  if (feed.schema_version !== 1 || feed.workbook_id !== APP_AVAILABILITY_WORKBOOK_ ||
      feed.season_start !== '2026-12-01' || feed.season_end !== '2027-03-30' || !Array.isArray(feed.rows) || feed.rows.length > 60000) {
    throw new Error('Availability feed schema or season changed. No cells were changed.');
  }
  const users = new Map();
  const keys = new Set();
  feed.rows.forEach(r => {
    const d = new Date(r.date + 'T12:00:00Z');
    const weekday = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][d.getUTCDay()];
    if (!Number.isInteger(r.user_id) || r.user_id <= 0 || typeof r.name !== 'string' || !r.name.trim() ||
        typeof r.email !== 'string' || !r.email.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(r.date) ||
        isNaN(d.getTime()) || r.date < feed.season_start || r.date > feed.season_end || weekday !== r.weekday ||
        ['morning','afternoon','evening','active'].some(k => typeof r[k] !== 'boolean')) throw new Error('Invalid availability record.');
    const k = r.user_id + '|' + r.date;
    if (keys.has(k)) throw new Error('Duplicate availability record.');
    keys.add(k);
    const u = users.get(r.user_id) || {name:r.name,email:r.email,active:r.active,count:0};
    if (u.name !== r.name || u.email !== r.email || u.active !== r.active) throw new Error('Conflicting instructor identity.');
    u.count++; users.set(r.user_id,u);
  });
  users.forEach(u => { if (u.count !== 120) throw new Error('An instructor has an incomplete 120-day season.'); });
}

function appAvailabilityNorm_(s) { return String(s || '').normalize('NFKC').toLowerCase().replace(/[’‘]/g,"'").replace(/\s+/g,' ').trim(); }
function appAvailabilityIdentity_(name,email) { return appAvailabilityNorm_(email) + '|' + appAvailabilityNorm_(name); }
function appAvailabilityLiteral_(s) { s=String(s == null ? '' : s); return /^[=+@-]/.test(s) ? "'" + s : s; }

function appAvailabilityMaster_(ss) {
  const s=ss.getSheetByName('MASTER');
  if (!s || s.getLastRow()<3) throw new Error('MASTER identity data is missing.');
  const result=new Map();
  s.getRange(3,11,s.getLastRow()-2,6).getDisplayValues().forEach(r=>{
    const k=appAvailabilityIdentity_(r[1],r[0]);
    if (!appAvailabilityNorm_(r[0]) || !appAvailabilityNorm_(r[1])) return;
    const values=result.get(k)||[];
    values.push({name:r[1],email:r[0],phone:r[2],qualifications:r.slice(3,6).filter(Boolean).join(', ')});
    result.set(k,values);
  });
  return result;
}

function appAvailabilityIdentityProblems_(rows,master) {
  const problems=new Set();
  rows.forEach(r=>{if((master.get(appAvailabilityIdentity_(r.name,r.email))||[]).length!==1) problems.add(r.user_id);});
  return Array.from(problems).sort((a,b)=>a-b);
}

function appAvailabilityAssertWeekday_(s) {
  const expected=['Availability','Qualifications','Name','Email','Phone'];
  const actual=s.getRange(1,1,1,5).getDisplayValues()[0];
  if(actual.some((v,i)=>v!==expected[i])) throw new Error('Weekday columns changed: ' + s.getName());
}

function appAvailabilityWriteSnapshot_(ss,feed) {
  let s=ss.getSheetByName('App Availability');
  if (!s) s=ss.insertSheet('App Availability');
  const count=s.getLastRow();
  if (count && JSON.stringify(s.getRange(1,1,1,11).getDisplayValues()[0])!==JSON.stringify(APP_AVAILABILITY_HEADERS_)) {
    throw new Error('App Availability already contains a different layout. No existing data was overwritten.');
  }
  if (!s.getRange(1,1,Math.max(count,1),11).canEdit()) throw new Error('Cannot edit App Availability.');
  const previous=count>1?s.getRange(2,1,count-1,11).getDisplayValues():[];
  const previousByKey=new Map(previous.map(r=>[r[0]+'|'+r[3],r]));
  const oldKeys=new Set(previousByKey.keys());
  const now=new Date().toISOString();
  const rows=feed.rows.map(r=>[String(r.user_id),r.name,r.email,r.date,r.weekday,r.morning?'Yes':'No',r.afternoon?'Yes':'No',r.evening?'Yes':'No',r.active?'Yes':'No',r.submitted_at,now]);
  // A missing instructor must be reviewed rather than silently removing their overrides.
  rows.forEach(r=>oldKeys.delete(r[0]+'|'+r[3]));
  if(oldKeys.size) throw new Error('Previously synced records are missing from the feed. Review before removing them.');
  const backgrounds=rows.map(r=>{
    const old=previousByKey.get(r[0]+'|'+r[3]);
    return r.map((v,i)=>i<10 && (!old||v!==old[i])?'#ffff00':null);
  });
  // Stable instructor/date ordering keeps existing yellow marks on the same records.
  if(count>1){
    const oldBackgrounds=s.getRange(2,1,count-1,11).getBackgrounds();
    const bgByKey=new Map(previous.map((r,i)=>[r[0]+'|'+r[3],oldBackgrounds[i]]));
    rows.forEach((r,i)=>{const old=bgByKey.get(r[0]+'|'+r[3]);if(old) old.forEach((v,j)=>{if(!backgrounds[i][j]) backgrounds[i][j]=v;});});
  }
  const requiredRows=rows.length+1;
  if(s.getMaxRows()<requiredRows) s.insertRowsAfter(s.getMaxRows(),requiredRows-s.getMaxRows());
  s.getRange(1,1,1,11).setValues([APP_AVAILABILITY_HEADERS_]).setBackground('#274e13').setFontColor('#ffffff').setFontWeight('bold');
  if(rows.length){
    s.getRange(2,1,rows.length,11).setNumberFormat('@').setValues(rows.map(r=>r.map(appAvailabilityLiteral_))).setBackgrounds(backgrounds);
  }
  s.setFrozenRows(1); s.setFrozenColumns(2);
  s.setColumnWidth(1,80); s.setColumnWidth(2,180); s.setColumnWidth(3,230); s.setColumnWidth(4,110);
  s.setColumnWidths(5,5,105); s.setColumnWidths(10,2,190);
  return s;
}

function appAvailabilitySummary_(rows) {
  const groups=new Map();
  rows.forEach(r=>{const mask=[r[5],r[6],r[7]].map(v=>v==='Yes'?'1':'0').join(''); const dates=groups.get(mask)||[]; dates.push(r[3]); groups.set(mask,dates);});
  const labels={'000':'Unavailable','100':'Morning','010':'Afternoon','001':'Evening','110':'All Day','101':'Morning/Evening','011':'Afternoon/PM','111':'All Day til 8PM'};
  const ordered=Array.from(groups.entries()).sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0]));
  if(!ordered.length) throw new Error('No dates for weekday summary.');
  const base=ordered[0];
  const exceptions=ordered.slice(1).map(([mask,dates])=>labels[mask]+' on '+dates.sort().join(', '));
  return labels[base[0]]+(exceptions.length?'; exceptions: '+exceptions.join('; '):'');
}

/** Called by each existing weekday rebuild, after its original formatting. */
function appAvailabilitySnapshot_(ss) {
  if(APP_AVAILABILITY_SNAPSHOT_CACHE_) return APP_AVAILABILITY_SNAPSHOT_CACHE_;
  const s=ss.getSheetByName('App Availability');
  if(!s || s.getLastRow()<2) return {rows:[],colors:[]};
  if(JSON.stringify(s.getRange(1,1,1,11).getDisplayValues()[0])!==JSON.stringify(APP_AVAILABILITY_HEADERS_)) throw new Error('App Availability columns changed.');
  APP_AVAILABILITY_SNAPSHOT_CACHE_={rows:s.getRange(2,1,s.getLastRow()-1,11).getDisplayValues(),colors:s.getRange(2,6,s.getLastRow()-1,4).getBackgrounds()};
  return APP_AVAILABILITY_SNAPSHOT_CACHE_;
}

function appAvailabilityApplyDay_(ss,s,day) {
  appAvailabilityAssertWorkbook_(ss);
  const snapshot=appAvailabilitySnapshot_(ss);
  if(!snapshot.rows.length) return 0;
  appAvailabilityAssertWeekday_(s);
  const data=snapshot.rows;
  const grouped=new Map();
  data.forEach(r=>{if(r[4]===day){const a=grouped.get(r[0])||[];a.push(r);grouped.set(r[0],a);}});
  const master=appAvailabilityMaster_(ss);
  const props=PropertiesService.getScriptProperties();
  const pending=new Set(JSON.parse(props.getProperty('APP_AVAILABILITY_YELLOW_'+day)||'[]'));
  const snapshotColors=snapshot.colors;
  data.forEach((r,i)=>{if(r[4]===day && snapshotColors[i].some(c=>c.toLowerCase()==='#ffff00'))pending.add(r[0]);});
  const current=s.getLastRow()>1?s.getRange(2,1,s.getLastRow()-1,5).getDisplayValues():[];
  const originalCount=current.length;
  const colors=originalCount?s.getRange(2,1,originalCount,1).getBackgrounds():[];
  if(originalCount && s.getRange(2,1,originalCount,1).getFormulas().some(r=>r[0])) throw new Error('Availability formulas require review in '+day);
  let changes=0;
  grouped.forEach((records,id)=>{
    const row=records[0]; const identity=appAvailabilityIdentity_(row[1],row[2]);
    const source=master.get(identity)||[];
    if(source.length!==1) throw new Error('MASTER identity needs review for App ID '+id);
    const matches=[]; current.forEach((r,i)=>{if(appAvailabilityIdentity_(r[2],r[3])===identity)matches.push(i);});
    if(matches.length>1) throw new Error('Duplicate weekday identity for App ID '+id+' in '+day);
    const summary=row[8]==='Yes'?appAvailabilitySummary_(records):'Unavailable (inactive in app)';
    let index=matches.length?matches[0]:current.length;
    if(!matches.length){
      const m=source[0]; const value=[summary,m.qualifications,m.name,m.email,m.phone];
      current.push(value); colors.push(['#ffff00']); pending.add(id); changes++;
    }else if(current[index][0]!==summary){
      current[index][0]=summary; pending.add(id); changes++;
    }
    if(pending.has(id)) colors[index]=['#ffff00'];
  });
  if(s.getMaxRows()<current.length+1)s.insertRowsAfter(s.getMaxRows(),current.length+1-s.getMaxRows());
  if(current.length>originalCount)s.getRange(originalCount+2,1,current.length-originalCount,5).setValues(current.slice(originalCount).map(r=>r.map(appAvailabilityLiteral_))).setBackground('#ffff00');
  if(changes && current.length)s.getRange(2,1,current.length,1).setValues(current.map(r=>[appAvailabilityLiteral_(r[0])]));
  if(current.length)s.getRange(2,1,current.length,1).setBackgrounds(colors);
  props.setProperty('APP_AVAILABILITY_YELLOW_'+day,JSON.stringify(Array.from(pending)));
  if(changes){s.getRange(2,1,Math.max(current.length,1),5).setWrap(true);}
  return changes;
}

function appAvailabilityHighlightEdit(e) {
  if(!e || !e.range || !e.source || e.source.getId()!==APP_AVAILABILITY_WORKBOOK_) return;
  const range=e.range; const name=range.getSheet().getName();
  if(name!=='App Availability' && APP_AVAILABILITY_DAYS_.indexOf(name)<0) return;
  const firstRow=Math.max(2,range.getRow());
  const lastRow=range.getLastRow(); const maxCol=name==='App Availability'?10:5;
  const firstCol=range.getColumn(); const lastCol=Math.min(range.getLastColumn(),maxCol);
  if(lastRow>=firstRow && lastCol>=firstCol) range.getSheet().getRange(firstRow,firstCol,lastRow-firstRow+1,lastCol-firstCol+1).setBackground('#ffff00');
}
