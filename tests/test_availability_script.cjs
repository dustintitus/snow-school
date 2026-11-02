const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const context=vm.createContext({console});
vm.runInContext(fs.readFileSync('integrations/google-apps-script/AppAvailability.gs','utf8'),context);
const call=(name,...args)=>context[name](...args);
const id='1mXuoAM6OH8YxSKU0ZgSIFt3b8pUf9EB8z74WmHN5kOM';
const rows=Array.from({length:120},(_,i)=>{
 const date=new Date(Date.UTC(2026,11,1+i));
 return {user_id:1,name:'Coach One',email:'coach@test.invalid',date:date.toISOString().slice(0,10),weekday:['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][date.getUTCDay()],active:true,morning:true,afternoon:false,evening:false,submitted_at:'2026-10-26T12:00:00Z'};
});
const feed={schema_version:1,workbook_id:id,season_start:'2026-12-01',season_end:'2027-03-30',rows};
call('appAvailabilityValidateFeed_',feed);
assert.throws(()=>call('appAvailabilityValidateFeed_',{...feed,rows:rows.slice(1)}),/incomplete/);
assert.throws(()=>call('appAvailabilityValidateFeed_',{...feed,rows:[...rows,rows[0]]}),/Duplicate/);
assert.throws(()=>call('appAvailabilityValidateFeed_',{...feed,rows:[{...rows[0],weekday:'Monday'},...rows.slice(1)]}),/Invalid/);
assert.throws(()=>call('appAvailabilityValidateFeed_',{...feed,rows:[{...rows[0],email:'different@test.invalid'},...rows.slice(1)]}),/Conflicting/);
assert.throws(()=>call('appAvailabilityValidateFeed_',{...feed,workbook_id:'wrong'}),/schema/);
const sheetRow=(date,m,a,e)=>['1','Coach','coach@test.invalid',date,'Monday',m?'Yes':'No',a?'Yes':'No',e?'Yes':'No','Yes'];
assert.equal(call('appAvailabilitySummary_',[sheetRow('2026-12-07',1,1,0),sheetRow('2026-12-14',1,1,0)]),'All Day');
assert.equal(call('appAvailabilitySummary_',[sheetRow('2026-12-07',1,1,0),sheetRow('2026-12-14',0,0,0),sheetRow('2026-12-21',1,1,0)]),'All Day; exceptions: Unavailable on 2026-12-14');
assert.equal(call('appAvailabilitySummary_',[sheetRow('2026-12-07',0,0,0)]),'Unavailable');
assert.equal(call('appAvailabilityIdentity_',"Coach O’Neil",' COACH@test.invalid '),call('appAvailabilityIdentity_',"coach o'neil",'coach@test.invalid'));
assert.equal(call('appAvailabilityLiteral_','=IMPORTXML("https://bad.invalid")'),"'=IMPORTXML(\"https://bad.invalid\")");
const master=new Map([[call('appAvailabilityIdentity_',rows[0].name,rows[0].email),[{}]]]);
assert.equal(call('appAvailabilityIdentityProblems_',rows,master).length,0);
master.set(call('appAvailabilityIdentity_',rows[0].name,rows[0].email),[{},{}]);
assert.deepEqual(Array.from(call('appAvailabilityIdentityProblems_',rows,master)),[1]);
class Sheet {
 constructor(name,values){this.name=name;this.values=values;this.backgrounds=values.map(r=>r.map(()=>'#ffffff'));this.maxRows=1000;}
 getName(){return this.name;}
 getLastRow(){return this.values.length;}
 getMaxRows(){return this.maxRows;}
 insertRowsAfter(start,count){this.maxRows+=count;}
 getRange(row,col,n=1,m=1){
  const s=this;
  const read=(a,fallback)=>Array.from({length:n},(_,i)=>Array.from({length:m},(_,j)=>a[row+i-1]?.[col+j-1]??fallback));
  const range={getDisplayValues:()=>read(s.values,''),getBackgrounds:()=>read(s.backgrounds,'#ffffff'),getFormulas:()=>Array.from({length:n},()=>Array(m).fill('')),
   setValues:(data)=>{for(let i=0;i<n;i++){s.values[row+i-1]??=[];for(let j=0;j<m;j++)s.values[row+i-1][col+j-1]=data[i][j];}return range;},
   setBackgrounds:(data)=>{for(let i=0;i<n;i++){s.backgrounds[row+i-1]??=[];for(let j=0;j<m;j++)s.backgrounds[row+i-1][col+j-1]=data[i][j];}return range;},
   setBackground:(color)=>range.setBackgrounds(Array.from({length:n},()=>Array(m).fill(color))),setWrap:()=>range};return range;
 }
}
const headers=['App ID','Instructor','Email','Date','Weekday','Morning','Afternoon','Evening','Active','Submitted UTC','Synced UTC'];
const snapshots=['2026-12-07','2026-12-14','2026-12-21'].map(d=>[...sheetRow(d,d!=='2026-12-14',d!=='2026-12-14',false),'2026-10-26','2026-10-26']);
const snapshot=new Sheet('App Availability',[headers,...snapshots]);
const weekday=new Sheet('Monday',[['Availability','Qualifications','Name','Email','Phone'],['Evening','B1','Different Coach','different@test.invalid','111'],['Morning','S1','Coach','coach@test.invalid','222']]);
const masterSheet=new Sheet('MASTER',[[],[],Array(10).fill('').concat(['coach@test.invalid','Coach','222','S1','',''])]);
const sheets=new Map([['App Availability',snapshot],['Monday',weekday],['MASTER',masterSheet]]);
const ss={getId:()=>id,getSheetByName:name=>sheets.get(name)};
const properties=new Map();context.PropertiesService={getScriptProperties:()=>({getProperty:key=>properties.get(key),setProperty:(key,value)=>properties.set(key,value)})};
assert.equal(call('appAvailabilityApplyDay_',ss,weekday,'Monday'),1);
assert.equal(weekday.values[1][0],'Evening');
assert.equal(weekday.values[2][0],'All Day; exceptions: Unavailable on 2026-12-14');
assert.equal(weekday.values[2][1],'S1');
assert.equal(weekday.backgrounds[2][0],'#ffff00');
assert.equal(call('appAvailabilityApplyDay_',ss,weekday,'Monday'),0);
// A later school rebuild must reapply the app summary and retain its yellow mark.
weekday.values[2][0]='Morning';weekday.backgrounds[2][0]='#ffffff';
assert.equal(call('appAvailabilityApplyDay_',ss,weekday,'Monday'),1);
assert.equal(weekday.backgrounds[2][0],'#ffff00');
console.log('21 availability-script checks passed');
