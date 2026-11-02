// Spreadsheet-only compatibility layer. Adds no OAuth scopes or triggers.

const APP_AVAILABILITY_WORKBOOK_ = '1mXuoAM6OH8YxSKU0ZgSIFt3b8pUf9EB8z74WmHN5kOM';

const APP_AVAILABILITY_HEADERS_ = ['App ID','Instructor','Email','Date','Weekday','Morning','Afternoon','Evening','Active','Submitted UTC','Synced UTC'];

var APP_AVAILABILITY_SNAPSHOT_CACHE_ = null;

function appAvailabilityAssertWorkbook_(ss) {
  if (!ss || ss.getId() !== APP_AVAILABILITY_WORKBOOK_) throw new Error('This script must remain bound to the Horseshoe master schedule.');
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


function appAvailabilityAssertWeekday_(s) {
  const expected=['Availability','Qualifications','Name','Email','Phone'];
  const actual=s.getRange(1,1,1,5).getDisplayValues()[0];
  if(actual.some((v,i)=>v!==expected[i])) throw new Error('Weekday columns changed: ' + s.getName());
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

