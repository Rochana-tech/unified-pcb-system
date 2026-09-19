let state=null, view='overview', selected='M4', explanation=null, explanationId=null;
let scenario=null, online=false, lastReceived=0, pending=false, lastExplanationStatus='';
let scenarioForm={machine_id:'M4',downtime_seconds:120,horizon_minutes:15,use_backup:true};
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n=(v,d=0)=>v==null?'—':Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
const label=s=>esc(String(s||'unknown').replaceAll('_',' '));
const time=s=>s?new Date(s).toLocaleTimeString():'—';
const views={overview:'Line overview',machine:'Machine details',recovery:'Recovery & what-if',alerts:'Alerts & explanations',system:'System & event log'};
function toast(message,error=false){
 const t=document.getElementById('toast');t.textContent=message;t.style.display='block';
 t.style.borderLeftColor=error?'var(--err)':'var(--ok)';clearTimeout(t.hideTimer);
 t.hideTimer=setTimeout(()=>t.style.display='none',6000);
}
async function api(path,body){
 const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json',...(operatorKey?{'Authorization':'Bearer '+operatorKey}:{})},body:JSON.stringify(body)});
 if(!response.ok){const error=await response.json().catch(()=>({detail:response.statusText}));throw new Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail));}
 return response.json();
}
async function refreshAll(){
 try{receive(await api('/api/dashboard'));}catch(e){online=false;connection();toast(e.message,true);}
}
function connection(){
 const fresh=online && Date.now()-lastReceived<6000;
 document.getElementById('sysDot').className='dot '+(fresh&&!state?.connection.error?'ok':'err');
 document.getElementById('sysLabel').textContent=fresh?(state?.connection.error?'PIPELINE ERROR':'CONNECTED'):'DISCONNECTED / STALE';
 const banner=document.getElementById('connectionBanner');
 if(banner){banner.hidden=fresh&&!state?.connection.error;banner.textContent=state?.connection.error||'Connection lost. Displayed readings may be stale; controls are disabled until data resumes.';}
 document.querySelectorAll('[data-control]').forEach(b=>b.disabled=!fresh||pending||!!state?.connection.error||!publicAccess.can_control);
}
function receive(data){
 state=data;online=true;lastReceived=Date.now();render();
 const decision=state.decisions.find(d=>d.decision_id===explanationId);
 if(decision && decision.status!==lastExplanationStatus)loadExplanation(explanationId);
}
function connect(){
 const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws/dashboard');
 ws.onmessage=e=>{try{receive(JSON.parse(e.data));}catch(error){toast('Dashboard data could not be read: '+error.message,true);}};
 ws.onclose=()=>{online=false;connection();setTimeout(connect,2000);};
 ws.onerror=()=>ws.close();
}
function go(next){
 if(typeof factory3D!=='undefined')factory3D?.dispose();
 view=next;
 document.getElementById('main').innerHTML='<div id="connectionBanner" class="notice error" hidden></div><div id="content"></div>';
 render();
}
function selectMachine(mid){selected=mid;go('machine');}
function badge(row){
 const kind=row.stale?'STALE':row.machine_status;
 return '<span class="pill"><span class="dot '+(row.stale||kind==='DOWN'?'err':kind==='BLOCKED'?'warn':'ok')+'"></span>'+esc(kind)+'</span>';
}
function row(k,v){return '<div class="row"><span>'+esc(k)+'</span><b>'+v+'</b></div>';}
function metric(title,value,unit){return '<div class="card"><div class="ctitle">'+esc(title)+'</div><div class="big">'+value+'</div><div class="muted">'+esc(unit)+'</div></div>';}
function options(value){return state.topology.map(mid=>'<option '+(mid===value?'selected':'')+' value="'+mid+'">'+mid+' · '+esc(state.machines.find(m=>m.machine_id===mid).name)+'</option>').join('');}
function render(){
 if(!state)return;
 document.getElementById('industryLabel').textContent=state.mode==='demo'?'PCB ASSEMBLY · SIMULATED':'PCB ASSEMBLY · EXTERNAL';
 document.getElementById('nav').innerHTML=Object.entries(views).map(([k,v])=>'<button class="'+(view===k?'active':'')+'" onclick="go(\''+k+'\')">'+esc(v)+'</button>').join('');
 const content=document.getElementById('content');
 if(view==='overview' && document.getElementById('factoryScene')){updateFactory();connection();return;}
 // Keep form nodes and keyboard focus stable while live readings refresh.
 if(view==='recovery' && document.getElementById('scenarioForm')){
   document.getElementById('recoveryList').innerHTML=recoveryList();
   connection();return;
 }
 content.innerHTML=({overview:overview,machine:machine,recovery:recovery,alerts:alerts,system:system})[view]();
 if(view==='overview')updateFactory();
 connection();
}
function overview(){return factoryOverview();}
function spark(history,key){
 const values=history.map(h=>key==='queue'?h.queue:h.sensors?.[key]).filter(v=>Number.isFinite(v));
 if(values.length<2)return '<p class="muted">Collecting trend history…</p>';
 const max=Math.max(...values),min=Math.min(...values),span=max-min||1;
 const points=values.map((v,i)=>(i*560/(values.length-1)).toFixed(1)+','+(90-(v-min)/span*70).toFixed(1)).join(' ');
 return '<svg viewBox="0 0 560 110" role="img" aria-label="'+esc(key)+' trend"><polyline points="'+points+'" fill="none" stroke="var(--accent)" stroke-width="2"/></svg><div class="muted">'+n(min,2)+' – '+n(max,2)+' · last '+values.length+' samples</div>';
}
function machine(){
 const m=state.machines.find(m=>m.machine_id===selected)||state.machines[0], t=m.telemetry, p=m.prediction;
 let html='<h2>Machine details</h2><div class="filters">'+state.machines.map(x=>'<button class="btn '+(m.machine_id===x.machine_id?'active':'')+'" onclick="selectMachine(\''+x.machine_id+'\')">'+esc(x.machine_id)+'</button>').join('')+'</div>';
 html+='<div class="section"><h3>'+esc(m.machine_id)+' · '+esc(m.name)+'</h3>'+badge(m)+'<p class="muted">Last controller reading: '+esc(t?.timestamp||'Not received')+'</p><div class="grid">'+metric('Queue',n(m.queue_length),'boards')+metric('Output counter',n(t?.units_processed_total),'boards')+metric('Cycle time',n(t?.cycle_time_sec,2),'seconds')+metric('Busy fraction',state.mode==='demo'?n(m.busy_fraction*100,1)+'%':'—',state.mode==='demo'?'time processing / elapsed demo time':'not inferred from output alone')+'</div></div>';
 html+='<div class="grid"><div class="section"><h3>Sensor readings</h3>'+(t?.sensors?Object.entries(t.sensors).map(([k,v])=>row(k,n(v,3)+' '+({current:'A',temperature:'°C',vibration:'mm/s RMS',rpm:'rpm'})[k])).join(''):'<p>Not supplied. Controller monitoring still works; sensor ANN is unavailable.</p>')+'</div><div class="section"><h3>ANN diagnosis</h3><p>'+(p?'<b>'+label(p.fault_type)+'</b> · model score '+n(p.confidence*100,1)+'%':'No sensor-based classification available.')+'</p><p class="muted">Trained on synthetic examples. A class score is not proof of root cause or a failure forecast.</p><p>Future failure risk: <b>unavailable</b></p></div></div>';
 html+='<div class="section"><h3>Queue trend · boards</h3>'+spark(m.history,'queue')+'</div>';
 if(t?.sensors)html+='<div class="section"><h3>Vibration trend · mm/s RMS</h3>'+spark(m.history,'vibration')+'</div>';
 if(state.mode==='demo' && state.topology.includes(m.machine_id)){
 html+='<div class="section"><h3>Demo controls</h3><p class="muted">Injects generated fault signals and stops this virtual station. The ANN receives readings, not the injected label.</p><div class="actions"><button data-control class="btn danger" onclick="action(\'/api/demo/fault/'+m.machine_id+'\',{fault_type:\'BEARING_FAULT\'})">Inject bearing-fault demo</button> <button data-control class="btn" onclick="action(\'/api/demo/fault/'+m.machine_id+'\',{fault_type:\'STOPPED\'})">Inject controller stop</button> <button data-control class="btn primary" onclick="action(\'/api/recovery/'+m.machine_id+'/correct\',{})">Simulate human correction</button></div></div>';
 }
 return html;
}
function recoveryList(){
 if(!state.decisions.length)return '<p class="muted">No incidents in this session. In demo mode, open a machine to inject a fault.</p>';
 return state.decisions.slice().reverse().map(d=>{
 const remaining=Math.max(0,Math.ceil((Date.parse(d.correction_deadline)-Date.parse(state.generated_at))/1000));
 return '<div class="incident"><div><b>'+esc(d.machine_id)+'</b> · '+label(d.status)+(d.status==='awaiting_correction'?' · '+remaining+'s left':'')+(d.alternative_machine_id?' → '+esc(d.alternative_machine_id):'')+'</div><div class="actions"><button class="btn" onclick="showExplanation(\''+esc(d.decision_id)+'\')">Explain alert</button>'+(d.status==='awaiting_correction'?'<button data-control class="btn" onclick="action(\'/api/recovery/'+d.machine_id+'/correct\',{})">'+(state.mode==='demo'?'Simulate correction':'Confirm observed correction')+'</button>':'')+'</div></div>';
 }).join('');
}
function recovery(){
 return '<h2>Recovery & what-if</h2><div class="section"><h3>Human-first recovery · '+state.correction_seconds+' second correction window</h3><p class="muted">If the window expires, the scheduler checks operation compatibility, availability, queue and load, then compares output before applying a virtual route.</p><div id="recoveryList">'+recoveryList()+'</div></div>'+
 '<div class="section"><h3>Compare an assumed stoppage</h3><form id="scenarioForm" onsubmit="runScenario(event)"><div class="form-grid"><label>Station<select id="scenarioMachine" onchange="scenarioForm.machine_id=this.value">'+options(scenarioForm.machine_id)+'</select></label><label>Assumed downtime (seconds)<input id="downtime" type="number" min="0" max="3600" value="'+scenarioForm.downtime_seconds+'" oninput="scenarioForm.downtime_seconds=Number(this.value)" required></label><label>Simulation horizon (minutes)<input id="horizon" type="number" min="1" max="60" value="'+scenarioForm.horizon_minutes+'" oninput="scenarioForm.horizon_minutes=Number(this.value)" required></label></div><p><button data-control class="btn primary" type="submit">Run what-if comparison</button></p></form><p class="muted">This comparison does not change live routing. A testing standby is available only in the configured demo.</p><div id="scenarioResult">'+scenarioHTML()+'</div></div>';
}
function scenarioHTML(){
 if(!scenario)return '';
 const b=scenario.baseline,r=scenario.recovery;
 return '<div class="notice">SIMULATION · '+scenario.horizon_minutes+' minute horizon · '+esc(scenario.starting_state_id)+'</div><div class="grid">'+metric('Wait for correction',n(b.throughput_units_per_hour,1),'predicted finished boards/hour')+metric('Use testing standby',r?n(r.throughput_units_per_hour,1):'Unavailable','predicted finished boards/hour')+'</div><p>'+esc(scenario.alternative_reason)+'</p><details><summary>Model assumptions</summary><ul>'+scenario.assumptions.map(a=>'<li>'+esc(a)+'</li>').join('')+'</ul></details>';
}
async function runScenario(event){
 event.preventDefault();pending=true;connection();
 try{scenario=await api('/api/scenarios/compare',scenarioForm);document.getElementById('scenarioResult').innerHTML=scenarioHTML();}
 catch(e){toast(e.message,true);}finally{pending=false;connection();}
}
async function action(path,body){
 pending=true;connection();
 try{const result=await api(path,body);toast(result.message||'Action completed.');await refreshAll();}
 catch(e){toast(e.message,true);}finally{pending=false;connection();}
}
function showExplanation(id){explanation=null;explanationId=id;lastExplanationStatus='';go('alerts');loadExplanation(id);}
async function loadExplanation(id){
 const decision=state.decisions.find(d=>d.decision_id===id);lastExplanationStatus=decision?.status||'';
 try{const result=await api('/api/alerts/'+encodeURIComponent(id)+'/explanation');if(explanationId===id){explanation=result;if(view==='alerts')render();}}
 catch(e){toast(e.message,true);}
}
let openQuestion=null;
function toggleQuestion(key){openQuestion=openQuestion===key?null:key;render();}
function alerts(){
 let html='<h2>Alerts & explanations</h2><div class="section">'+recoveryList()+'</div>';
 if(!explanation)return html+'<div class="section"><p>'+(explanationId?'Loading explanation…':'Select “Explain alert” to see evidence-backed answers.')+'</p><p class="muted">The explanation layer uses backend facts only. Missing causes, repair times and maintenance procedures are left unknown.</p></div>';
 html+='<div class="section"><h3>'+esc(explanation.alert.machine_id)+' · '+esc(explanation.alert.machine_name)+'</h3><p class="muted">Grounded explanation · '+esc(explanation.explanation_mode)+' · '+esc(explanation.alert.id)+'</p>';
 for(const a of explanation.answers){
 html+='<div class="question"><button class="question-button" aria-expanded="'+(openQuestion===a.key)+'" onclick="toggleQuestion(\''+esc(a.key)+'\')">'+esc(a.question)+' <span class="muted">'+esc(a.status)+'</span></button>'+(openQuestion===a.key?'<div class="answer"><p>'+esc(a.answer)+'</p>'+(a.missing_information.length?'<p class="muted">Missing: '+esc(a.missing_information.join('; '))+'</p>':'')+'<p class="muted">Evidence: '+esc(a.evidence_ids.join(', ')||'not provided')+'</p></div>':'')+'</div>';
 }
 return html+'<p class="muted">'+explanation.warnings.map(esc).join(' ')+'</p></div>';
}
function system(){
 const live=state.machines.filter(m=>!m.stale).length;
 return '<h2>Connected layers</h2><div class="grid">'+[
 ['Data acquisition',live+' fresh machines',state.mode==='demo'?'Generated feed → Layer 1 StateManager':'Controller HTTP / optional MQTT → Layer 1 StateManager'],
 ['ANN fault detection','Loaded',state.model.name+' · synthetic training · requires 4 sensor features'],
 ['Digital twin','Connected','Topology, counters, queue trends, capacity & bottleneck ranking'],
 ['Decision & recovery','Connected','Supplied Layer 4 scheduler with real adapters and virtual route application'],
 ['Failure prediction','Unavailable','Training scripts retained. No trained controller-risk model was supplied.'],
 ['Alert explanation','Connected','Separate backend module; evidence templates; no external AI key required.']
 ].map(([name,status,desc])=>'<div class="card"><div class="ctitle">'+esc(name)+'</div><div class="clabel">'+esc(status)+'</div><p class="muted">'+esc(desc)+'</p></div>').join('')+'</div><div class="section spaced"><h3>Services</h3><p>MQTT: '+esc(state.connection.mqtt)+' · API: <a href="/docs" target="_blank" rel="noopener">interactive API documentation</a></p><p class="muted">The supplied HTML workspace is connected directly to FastAPI and WebSockets. SQLite stores telemetry samples and recovery events. No factory controller commands are issued.</p>'+(state.mode==='demo'?'<button data-control class="btn" onclick="action(\'/api/demo/reset\',{})">Reset demo session</button>':'')+'</div><div class="section"><h3>Recent persisted events</h3>'+state.recent_events.map(e=>'<div class="event"><span class="muted">'+time(e.timestamp)+'</span> <b>'+label(e.kind)+'</b><pre>'+esc(JSON.stringify(e.payload,null,2))+'</pre></div>').join('')+'</div>';
}
go('overview');refreshAll();connect();setInterval(connection,1000);

