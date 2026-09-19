const sensors = [
  {id:'M1', current:2.1, temp:42, vibration:0.21, rpm:1480, state:'RUNNING'},
  {id:'M2', current:2.3, temp:45, vibration:0.25, rpm:1510, state:'RUNNING'},
  {id:'M3', current:1.9, temp:39, vibration:0.18, rpm:1490, state:'IDLE'},
  {id:'M4', current:3.2, temp:68, vibration:0.72, rpm:1100, state:'FAULT'},
  {id:'M5', current:2.0, temp:41, vibration:0.20, rpm:1500, state:'RUNNING'}
];
const production = [
  {id:'M1',status:'RUNNING',cycle:12.4,output:290.3,good:281,reject:4,down:18.2},
  {id:'M2',status:'RUNNING',cycle:15.1,output:238.4,good:229,reject:5,down:25.4},
  {id:'M3',status:'IDLE',cycle:18.2,output:0,good:188,reject:3,down:122.1},
  {id:'M4',status:'FAULT',cycle:null,output:0,good:173,reject:8,down:316.7},
  {id:'M5',status:'RUNNING',cycle:14.0,output:257.1,good:245,reject:4,down:31.6}
];
function cls(state){return state.toLowerCase()}
function render(){
  document.getElementById('sensorTable').innerHTML=sensors.map(s=>`<tr><td><strong>${s.id}</strong></td><td>${s.current.toFixed(1)} A</td><td>${s.temp} °C</td><td>${s.vibration.toFixed(2)}</td><td>${s.rpm}</td><td><span class="state ${cls(s.state)}">${s.state}</span></td></tr>`).join('');
  document.getElementById('productionTable').innerHTML=production.map(p=>`<tr><td><strong>${p.id}</strong></td><td><span class="state ${cls(p.status)}">${p.status}</span></td><td>${p.cycle===null?'—':p.cycle+' s'}</td><td>${p.output.toFixed(1)}</td><td>${p.good}</td><td>${p.reject}</td><td>${p.down.toFixed(1)} s</td></tr>`).join('');
  const now=new Date().toLocaleTimeString();document.getElementById('sensorTime').textContent='Updated '+now;document.getElementById('productionTime').textContent='Updated '+now;
}
render();
setInterval(()=>{
  sensors.forEach(s=>{if(s.state==='RUNNING'){s.current=Math.max(1.7,Math.min(2.8,s.current+(Math.random()-.5)*.12));s.temp=Math.round(Math.max(38,Math.min(50,s.temp+(Math.random()-.5)*1.5)));s.rpm=Math.round(Math.max(1420,Math.min(1550,s.rpm+(Math.random()-.5)*18)));}});render();
},3000);
