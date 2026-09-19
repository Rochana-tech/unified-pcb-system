// Factory overview and backend-driven triage. Three.js renders machine geometry.
let factorySelected='M4', factoryMoved=false, factory3D=null, factoryImport=null;
function factoryOverview(){
 return '<div class="factory-summary" id="factorySummary"></div><div class="factory-layout"><section class="factory-stage" aria-label="Interactive factory view"><div class="scene-toolbar"><span id="sceneMode"></span><span><button class="btn" onclick="factory3D?.focus()">Focus selected</button> <button class="btn" onclick="resetFactoryView()">Reset view</button></span></div><div id="factoryScene"><p class="muted">Loading 3D machines…</p></div><div class="scene-caption"><span>Drag to orbit · scroll to zoom · click a machine</span><span><i class="legend normal"></i>Running <i class="legend warning"></i>Blocked <i class="legend fault"></i>Fault / down</span></div></section><aside id="factoryTriage" aria-label="Machine triage and recovery"></aside></div>';
}
function selectFactory(mid){
 if(factoryMoved)return;
 factorySelected=mid;updateFactory();
}
function resetFactoryView(){factory3D?.reset();}
function fMetric(name,value,unit){return '<div class="factory-metric"><span>'+esc(name)+'</span><strong>'+value+'</strong><small>'+esc(unit)+'</small></div>';}
function updateFactory(){
 if(!state||!document.getElementById('factoryScene'))return;
 const active=state.topology.map(mid=>state.machines.find(m=>m.machine_id===state.routes[mid])).filter(Boolean);
 const output=state.machines.find(m=>m.machine_id==='M5');
 const fault=state.machines.some(m=>m.machine_status==='DOWN'||m.fault_status==='FAULT');
 const stale=active.some(m=>m.stale);
 const blocked=active.some(m=>m.machine_status==='BLOCKED');
 const usable=active.filter(m=>!m.stale);
 const utilization=state.mode==='demo'&&usable.length===active.length?usable.reduce((s,m)=>s+(m.busy_fraction||0),0)/usable.length:null;
 const queue=usable.reduce((s,m)=>s+m.queue_length,0);
 const bottleneck=state.bottlenecks[0];
 const bn=state.machines.find(m=>m.machine_id===bottleneck?.machine_id);
 document.getElementById('factorySummary').innerHTML='<div class="line-condition '+(fault?'fault':blocked?'warning':'normal')+'"><i class="legend"></i>'+ (stale?'STALE':fault?'DEGRADED':blocked?'CONSTRAINED':'RUNNING')+'</div>'+
 fMetric('Throughput',output?.stale?'—':n(output?.throughput_units_per_hour/60,2),'boards/min · measured')+
 fMetric('Utilization',utilization==null?'—':n(utilization*100,1)+'%','average busy time · demo')+
 fMetric('Efficiency','—','quality / OEE data unavailable')+
 fMetric('Queue',stale?'—':n(queue),'boards waiting · active route')+
 fMetric('Bottleneck',esc(bn?.machine_id||'—'),bn?.name||'No ranking available');
 document.getElementById('sceneMode').textContent=state.mode==='demo'?'LIVE DEMO · REPRESENTATIVE 3D MACHINES':'LIVE TELEMETRY · REPRESENTATIVE 3D MACHINES';
 drawFactory();
 renderTriage();
 connection();
}
function drawFactory(){
 const root=document.getElementById('factoryScene');if(!root)return;
 const handlers={select:selectFactory,isFresh:()=>online&&Date.now()-lastReceived<6000&&!state?.connection.error};
 if(factory3D){factory3D.update(root,state,factorySelected,handlers);return;}
 if(!factoryImport){
  factoryImport=import('/static/factory3d.js').then(mod=>{
   factory3D=mod;
   if(document.getElementById('factoryScene'))drawFactory();
  }).catch(error=>{
   const area=document.getElementById('factoryScene');
   if(area){area.textContent='3D could not start. Enable WebGL / browser graphics acceleration and reload. Machine readings remain available in the other tabs.';}
   console.error('3D initialization failed',error);
  });
 }
}
function renderTriage(){
 const m=state.machines.find(m=>m.machine_id===factorySelected)||state.machines[0];
 const decision=state.decisions.slice().reverse().find(d=>d.machine_id===m.machine_id);
 const prediction=m.prediction;
 const isFault=m.machine_status==='DOWN'||m.fault_status==='FAULT';
 const score=prediction&&prediction.fault_status==='FAULT'?prediction.severity:(isFault?'CONTROLLER ALERT':'NO ACTIVE FAULT');
 const remaining=decision?Math.max(0,Math.ceil((Date.parse(decision.correction_deadline)-Date.parse(state.generated_at))/1000)):null;
 let html='<section class="side-panel"><div class="side-heading">TRIAGE <span class="'+(isFault?'fault-text':'normal-text')+'">'+esc(m.stale?'STALE':score)+'</span></div><div class="side-body">'+row('Affected machine',esc(m.machine_id)+' · '+esc(m.name))+row('Status',badge(m))+row('Health score','Not available')+row('Queue',n(m.queue_length)+' boards')+row('Utilization',m.busy_fraction==null?'—':n(m.busy_fraction*100,1)+'%')+row('Bottleneck',state.bottlenecks[0]?.machine_id===m.machine_id?'Highest ranked':'No')+row('Human status',decision?label(decision.status):'No correction pending');
 html+='<div class="triage-reasons"><small>DETECTION EVIDENCE</small><p>'+(prediction?('ANN: <b>'+label(prediction.fault_type)+'</b> · score '+n(prediction.confidence*100,1)+'%.'): 'Sensor ANN unavailable. No readings have been invented.')+'</p><p>Controller: '+esc(m.machine_status)+'. '+n(m.queue_length)+' boards waiting.</p><p class="muted">Health and future-failure models are unavailable. An ANN class is a suspected fault, not a confirmed root cause.</p></div>';
 if(decision)html+='<button class="btn primary full" onclick="showExplanation(\''+decision.decision_id+'\')">Understand This Alert</button>';
 else html+='<p class="muted">No alert for this machine. Select a fault demo below to see detection and recovery.</p>';
 html+='<button class="btn full" onclick="selectMachine(\''+m.machine_id+'\')">Open machine readings</button></div></section>';
 html+='<section class="side-panel"><div class="side-heading">HUMAN-FIRST RECOVERY</div><div class="side-body"><ol class="recovery-steps"><li class="'+(decision?'done':'')+'">Fault detected</li><li class="'+(decision?'done':'')+'">Operator notified'+(decision?.status==='awaiting_correction'?' · '+remaining+'s left':'')+'</li><li class="'+(decision?.status==='resumed_by_human'?'done':'')+'">Human correction</li><li class="'+(decision?.whatif_scenario_id?'done':'')+'">Check standby & simulate</li><li class="'+(decision?.status==='reallocated'?'done':'')+'">Apply virtual recovery route</li></ol>';
 if(decision?.alternative_machine_id)html+='<p class="normal-text">Workload → '+esc(decision.alternative_machine_id)+'</p>';
 if(decision?.status==='no_alternative_flagged')html+='<p class="fault-text">No compatible, feasible alternate available.</p>';
 if(state.mode==='demo'&&state.topology.includes(m.machine_id)){
  html+='<div class="demo-controls"><small>SIMULATED FAULT CONTROLS</small><button data-control class="btn danger full" onclick="action(\'/api/demo/fault/'+m.machine_id+'\',{fault_type:\'BEARING_FAULT\'})">Simulate fault & detect</button><button data-control class="btn full" onclick="action(\'/api/recovery/'+m.machine_id+'/correct\',{})">Simulate human correction</button></div>';
 }
 html+='<button class="btn full" onclick="go(\'recovery\')">Compare what-if scenarios →</button></div></section>';
 document.getElementById('factoryTriage').innerHTML=html;
}

