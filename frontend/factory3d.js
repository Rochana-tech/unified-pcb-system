import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';

let current=null;
const palette={steel:0xb4c6c6,dark:0x182829,trim:0x237e70,rail:0x577574,pcb:0x168555,yellow:0xe4b04f};
class FactoryScene{
 constructor(root,data,selected,handlers){
  this.root=root;this.handlers=handlers;this.data=data;this.selected=selected;
  this.models=new Map();this.transfers=[];this.resources=new Set();this.lastTime=performance.now();this.disposed=false;
  this.scene=new THREE.Scene();this.scene.background=new THREE.Color(0x091414);
  this.camera=new THREE.PerspectiveCamera(42,1,.1,150);
  this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,powerPreference:'high-performance'});
  this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
  this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  this.renderer.outputColorSpace=THREE.SRGBColorSpace;
  this.renderer.domElement.setAttribute('aria-label','Live 3D PCB assembly line. Drag to orbit, scroll to zoom, or use machine buttons to select.');
  root.replaceChildren(this.renderer.domElement);
  this.labels=document.createElement('div');this.labels.className='machine-labels';root.append(this.labels);
  this.controls=new OrbitControls(this.camera,this.renderer.domElement);
  this.controls.enableDamping=true;this.controls.dampingFactor=.08;
  this.controls.maxPolarAngle=Math.PI*.47;this.controls.minDistance=7;this.controls.maxDistance=42;
  this.controls.target.set(0,.7,1);this.reset();
  this.scene.add(new THREE.HemisphereLight(0xd5ffef,0x3a4744,2));
  const key=new THREE.DirectionalLight(0xffffff,3);key.position.set(-4,14,8);key.castShadow=true;
  key.shadow.mapSize.set(1024,1024);Object.assign(key.shadow.camera,{left:-15,right:15,top:12,bottom:-12,near:1,far:45});
  this.scene.add(key);
  const rim=new THREE.DirectionalLight(0x54ccb6,1.2);rim.position.set(7,5,-8);this.scene.add(rim);
  this.boxGeo=this.keep(new THREE.BoxGeometry(1,1,1));
  this.cylinderGeo=this.keep(new THREE.CylinderGeometry(1,1,1,12));
  this.materials=new Map();
  const floor=this.box(this.scene,0,-.12,1,32,.18,20,0x182321);floor.receiveShadow=true;
  const grid=new THREE.GridHelper(32,32,0x36584c,0x233e35);grid.position.y=-.015;this.scene.add(grid);
  this.keep(grid.geometry);this.keep(grid.material);
  // Painted travel lane and a visible conveyor, including a separate testing spur.
  this.box(this.scene,0,.025,-1.4,24,.015,.025,0xb69747);
  this.box(this.scene,0,.025,1.35,24,.015,.025,0xb69747);
  this.conveyor(this.scene,0,0,24);
  this.conveyor(this.scene,4.2,4.2,3.4);
  const names={M1:'PLACEMENT',M2:'REFLOW OVEN',M3:'AOI INSPECTION',M4:'TEST FIXTURE',M5:'PACKAGING','M4-BACKUP':'STANDBY TEST'};
  data.machines.forEach(m=>{
   const index=data.topology.indexOf(m.machine_id);
   const x=index>=0?(index-2)*4.2:4.2,z=index>=0?0:4.2;
   const group=new THREE.Group();group.position.set(x,0,z);group.userData.machineId=m.machine_id;this.scene.add(group);
   const model={id:m.machine_id,group,time:0,row:m,counter:m.telemetry?.units_processed_total??0,kind:index,parts:{},queue:[]};
   this.models.set(m.machine_id,model);
   this.base(model);
   if(index===0)this.placement(model);
   else if(index===1)this.oven(model);
   else if(index===2)this.inspection(model);
   else if(index===4)this.packaging(model);
   else this.testing(model);
   model.work=this.board(group,0,.99,0,true);
   model.ring=this.box(group,0,.04,0,3.15,.04,2.1,0x225d50);
   for(let i=0;i<12;i++){
    const board=this.board(group,-1.65+(i%2)*.24,.9+Math.floor(i/4)*.085,-.32+Math.floor(i%4/2)*.35,false);
    model.queue.push(board);
   }
   const label=document.createElement('button');label.className='machine-tag';label.dataset.machine=m.machine_id;
   label.innerHTML='<b></b><span></span>';label.firstChild.textContent=m.machine_id+' · '+names[m.machine_id];
   label.addEventListener('click',()=>handlers.select(m.machine_id));this.labels.append(label);model.label=label;
  });
  this.routeMaterial=this.keep(new THREE.LineDashedMaterial({color:0x54d6b8,dashSize:.22,gapSize:.14}));
  const points=[new THREE.Vector3(0,.12,.8),new THREE.Vector3(0,.12,4.2),new THREE.Vector3(8.4,.12,4.2),new THREE.Vector3(8.4,.12,.8)];
  const geom=this.keep(new THREE.BufferGeometry().setFromPoints(points));
  this.route=new THREE.Line(geom,this.routeMaterial);this.route.computeLineDistances();this.scene.add(this.route);
  this.pointerDown=null;
  this.onDown=e=>{this.pointerDown={x:e.clientX,y:e.clientY};};
  this.onUp=e=>{
   if(!this.pointerDown||Math.hypot(e.clientX-this.pointerDown.x,e.clientY-this.pointerDown.y)>5)return;
   const rect=this.renderer.domElement.getBoundingClientRect();
   const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),this.camera);
   for(const hit of ray.intersectObjects([...this.models.values()].map(m=>m.group),true)){
    let node=hit.object;while(node&&!node.userData.machineId)node=node.parent;
    if(node){handlers.select(node.userData.machineId);break;}
   }
  };
  this.renderer.domElement.addEventListener('pointerdown',this.onDown);
  this.renderer.domElement.addEventListener('pointerup',this.onUp);
  this.renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();this.contextLost=true;root.dataset.error='WebGL context lost. Reload to restore 3D.';});
  this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(root);
  this.resize();this.update(data,selected);
  this.renderer.setAnimationLoop(t=>this.frame(t));
 }
 keep(resource){this.resources.add(resource);return resource;}
 mat(color,options={}){
  const key=color+JSON.stringify(options);
  if(!this.materials.has(key))this.materials.set(key,this.keep(new THREE.MeshStandardMaterial({color,roughness:.58,metalness:.25,...options})));
  return this.materials.get(key);
 }
 box(parent,x,y,z,w,h,d,color,opts={}){
  const mesh=new THREE.Mesh(this.boxGeo,this.mat(color,opts));mesh.position.set(x,y,z);mesh.scale.set(w,h,d);
  mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;
 }
 cyl(parent,x,y,z,r,h,color,rotation=0){
  const mesh=new THREE.Mesh(this.cylinderGeo,this.mat(color));mesh.position.set(x,y,z);mesh.scale.set(r,h,r);mesh.rotation.z=rotation;
  mesh.castShadow=true;parent.add(mesh);return mesh;
 }
 conveyor(parent,x,z,length){
  this.box(parent,x,.77,z,length,.1,.86,0x213331);
  for(const dz of [-.52,.52])this.box(parent,x,.88,z+dz,length,.15,.09,palette.rail);
  for(let i=-length/2+.2;i<length/2;i+=.34){
   const roller=this.cyl(parent,x+i,.85,z,.052,.88,0x778c86);roller.rotation.x=Math.PI/2;
  }
  for(const dx of [-length/2+.45,length/2-.45])for(const dz of [-.42,.42])this.box(parent,x+dx,.4,z+dz,.09,.8,.09,palette.dark);
 }
 board(parent,x,y,z,components){
  const group=new THREE.Group();group.position.set(x,y,z);parent.add(group);
  this.box(group,0,0,0,.56,.04,.4,palette.pcb);
  if(components){
   for(const dx of [-.14,.1])this.box(group,dx,.065,0,.12,.09,.12,0x172425);
   for(const dz of [-.12,.12])this.box(group,0,.029,dz,.38,.009,.014,0xdbbd58);
  }
  return group;
 }
 base(m){
  const g=m.group;
  this.box(g,0,.37,0,2.65,.62,1.52,palette.steel);
  this.box(g,0,.12,0,2.85,.15,1.7,palette.dark);
  for(const x of [-1.12,1.12])for(const z of [-.6,.6])this.cyl(g,x,.11,z,.11,.2,0x151e1b);
  this.box(g,0,.56,.78,2.2,.06,.025,palette.trim);
  // HMI and physical emergency stop.
  this.box(g,1.16,1.08,.82,.38,.38,.12,0x344c49);
  this.box(g,1.16,1.09,.889,.28,.21,.015,0x4db4a7,{emissive:0x276b60,emissiveIntensity:.5});
  this.cyl(g,1.15,.84,.92,.055,.04,0xd84d40,Math.PI/2);
  this.cyl(g,-1.08,2.22,-.53,.035,.5,0x4b6760);
  m.light=this.cyl(g,-1.08,2.46,-.53,.078,.16,0x51d5a5);
  // Unique material so status changes never recolor unrelated geometry.
  m.light.material=this.keep(new THREE.MeshStandardMaterial({color:0x51d5a5,emissive:0x27a377,emissiveIntensity:1}));
 }
 framePosts(g){
  for(const x of [-1.1,1.1])for(const z of [-.62,.62])this.box(g,x,1.45,z,.085,1.35,.085,0x56716b);
  this.box(g,0,2.11,-.62,2.3,.1,.09,palette.steel);
  this.box(g,0,2.11,.62,2.3,.1,.09,palette.steel);
 }
 placement(m){
  const g=m.group;this.framePosts(g);
  // Transparent side guarding leaves the XY placement carriage visible.
  for(const x of [-1.13,1.13])this.box(g,x,1.5,0,.025,1.02,1.13,0x5baca4,{transparent:true,opacity:.16,depthWrite:false});
  for(const z of [-.48,.48])this.box(g,0,1.88,z,2.05,.075,.07,0xdce8df);
  const carriage=new THREE.Group();g.add(carriage);m.parts.head=carriage;
  this.box(carriage,0,1.84,0,.16,.16,1.05,palette.trim);
  this.box(carriage,0,1.62,0,.3,.31,.3,0xd2dbd4);
  m.parts.nozzle=this.cyl(carriage,0,1.36,0,.025,.22,0xd8b962);
  for(let i=0;i<8;i++){
   const reel=this.cyl(g,-.93+i*.26,1.01,.93,.12,.08,0x304b47,Math.PI/2);reel.rotation.x=Math.PI/2;
   this.box(g,-.93+i*.26,.93,.72,.1,.025,.3,0xd7b14f);
  }
 }
 oven(m){
  const g=m.group;
  // Three reflow zones, tunnel openings at both conveyor ends and exhaust ducts.
  for(let i=0;i<3;i++){
   this.box(g,(i-1)*.84,1.54,0,.79,.9,1.45,0xbfc9bf);
   this.box(g,(i-1)*.84,1.43,.739,.62,.29,.025,0x543d26,{emissive:0xcc6124,emissiveIntensity:.45});
   for(let k=0;k<4;k++)this.box(g,(i-1)*.84-.24+k*.15,2.005,0,.07,.014,.68,0x40564e);
  }
  for(const x of [-.8,.8]){this.cyl(g,x,2.17,-.28,.13,.37,0x718880);this.cyl(g,x,2.36,-.28,.22,.06,0x52665e);}
  m.parts.heat=this.box(g,0,1.12,0,2.52,.035,.68,0xeb8b36,{emissive:0xec5922,emissiveIntensity:.5});
 }
 inspection(m){
  const g=m.group;this.framePosts(g);
  this.box(g,0,2.07,0,2.35,.15,1.4,palette.steel);
  this.box(g,0,1.9,0,.48,.35,.46,0x223739);
  this.cyl(g,0,1.66,0,.14,.19,0x101b20);
  this.cyl(g,0,1.53,0,.2,.055,0x65bade);
  m.parts.scan=this.box(g,0,1.06,0,.025,.016,.58,0x62d5ff,{emissive:0x42baff,emissiveIntensity:2});
  for(const x of [-.85,.85])this.box(g,x,1.35,-.56,.05,.65,.04,0xe4f0ec);
 }
 testing(m){
  const g=m.group;
  this.box(g,0,.95,0,1.35,.09,.68,0x263638);
  for(let i=0;i<7;i++)for(const z of [-.18,.18])this.cyl(g,-.45+i*.15,1.08,z,.018,.17,0xd9b54e);
  for(const x of [-.69,.69])this.cyl(g,x,1.52,-.46,.045,1.1,0xaec6be);
  const platen=new THREE.Group();g.add(platen);m.parts.platen=platen;
  this.box(platen,0,1.65,0,1.48,.13,.79,0x789a8b);
  this.cyl(platen,0,1.88,-.28,.12,.36,palette.trim);
  this.box(g,0,2.11,-.51,1.75,.15,.18,palette.steel);
 }
 packaging(m){
  const g=m.group;
  this.box(g,0,1.99,0,2.38,.15,1.3,palette.yellow);
  for(const x of [-1.02,1.02])this.box(g,x,1.46,-.5,.12,1.1,.12,0xc59a48);
  const head=new THREE.Group();g.add(head);m.parts.pack=head;
  this.box(head,0,1.7,0,.28,.45,.26,palette.yellow);
  for(const x of [-.22,.22])this.box(head,x,1.38,0,.04,.24,.39,0x56716b);
  // Open corrugated carton, rather than another generic machine block.
  const carton=new THREE.Group();carton.position.set(.35,.98,0);g.add(carton);m.parts.carton=carton;
  this.box(carton,0,0,0,.76,.05,.59,0xb28a52);
  for(const x of [-.37,.37])this.box(carton,x,.15,0,.035,.3,.6,0xc79b5e);
  for(const z of [-.29,.29])this.box(carton,0,.15,z,.76,.3,.025,0xb58c50);
  for(const z of [-.39,.39]){const flap=this.box(carton,0,.28,z,.76,.02,.19,0xd0aa70);flap.rotation.x=z>0?-.5:.5;}
 }
 reset(){const fit=Math.max(1,1.45/this.camera.aspect);this.camera.position.set(7*fit,10*fit,18*fit);this.controls.target.set(0,.65,1.0);this.controls.update();}
 focus(){const m=this.models.get(this.selected);if(!m)return;this.controls.target.copy(m.group.position).add(new THREE.Vector3(0,1,0));this.camera.position.copy(m.group.position).add(new THREE.Vector3(4,4,5));this.controls.update();}
 resize(){
  const w=this.root.clientWidth,h=this.root.clientHeight;if(!w||!h)return;
  this.camera.aspect=w/h;this.camera.updateProjectionMatrix();this.renderer.setSize(w,h,false);if(!this.sized){this.sized=true;this.reset();}
 }
 transfer(source,dest){
  if(!dest||this.transfers.length>=30)return;
  const board=this.board(this.scene,0,.96,0,true);
  const a=source.group.position.clone().add(new THREE.Vector3(.6,.96,0));
  const b=dest.group.position.clone().add(new THREE.Vector3(-1.5,.96,0));
  this.transfers.push({board,a,b,age:0});
 }
 update(data,selected){
  this.data=data;this.selected=selected;
  for(const row of data.machines){
   const m=this.models.get(row.machine_id);if(!m)continue;m.row=row;
   const count=row.telemetry?.units_processed_total;
   if(Number.isFinite(count)){
    const delta=count-m.counter;
    if(delta>0&&delta<=10){
     const logical=Object.keys(data.routes).find(k=>data.routes[k]===m.id);
     const i=data.topology.indexOf(logical);
     const dest=i>=0&&i<data.topology.length-1?this.models.get(data.routes[data.topology[i+1]]):null;
     for(let j=0;j<Math.min(3,delta);j++)this.transfer(m,dest);
     m.time=0;
    }
    m.counter=count;
   }
   m.queue.forEach((b,i)=>b.visible=!row.stale&&i<row.queue_length);
   const status=row.stale?'STALE':row.machine_status;
   const fault=status==='DOWN'||row.fault_status==='FAULT';
   const color=row.stale?0x71827d:fault?0xf26b63:status==='BLOCKED'?0xe6b559:0x51d5a5;
   m.light.material.color.setHex(color);m.light.material.emissive.setHex(color);
   m.ring.material=this.mat(m.id===selected?0x80cdb8:0x225d50);
   m.label.classList.toggle('selected',m.id===selected);
   m.label.style.setProperty('--status','#'+new THREE.Color(color).getHexString());
   m.label.lastChild.textContent=status+' · '+row.queue_length+' waiting';
   m.label.setAttribute('aria-label',row.machine_id+' '+row.name+' '+status);
   m.work.visible=!row.stale&&['RUNNING','BLOCKED'].includes(status);
  }
  this.route.visible=data.routes.M4==='M4-BACKUP';
 }
 frame(now){
  if(this.disposed)return;
  if(!this.root.isConnected){this.dispose();return;}
  const dt=Math.min(.08,(now-this.lastTime)/1000);this.lastTime=now;
  const fresh=this.handlers.isFresh()&&!this.contextLost;
  this.root.dataset.fresh=String(fresh);
  for(const m of this.models.values()){
   const running=fresh&&!m.row.stale&&m.row.machine_status==='RUNNING';
   if(running)m.time+=dt;
   const cycle=Math.max(1,m.row.telemetry?.cycle_time_sec||8);
   const phase=m.time/cycle*Math.PI*2;
   if(m.parts.head){m.parts.head.position.x=Math.sin(phase)*.65;m.parts.head.position.z=Math.cos(phase)*.25;m.parts.nozzle.position.y=1.36-Math.max(0,Math.sin(phase*3))*.16;}
   if(m.parts.scan)m.parts.scan.position.x=Math.sin(phase)*.62;
   if(m.parts.platen)m.parts.platen.position.y=-.38*(.5+.5*Math.sin(phase));
   if(m.parts.pack){m.parts.pack.position.x=Math.sin(phase)*.5;m.parts.pack.position.y=-.2*(.5+.5*Math.cos(phase));}
   if(m.parts.heat)m.parts.heat.visible=running;
   // World-space anchoring is updated after orbiting; labels remain keyboard buttons.
   const v=m.group.position.clone().add(new THREE.Vector3(0,2.8,0)).project(this.camera);
   m.label.style.left=((v.x*.5+.5)*100)+'%';m.label.style.top=((-v.y*.5+.5)*100)+'%';
   m.label.hidden=v.z>1||Math.abs(v.x)>1.1||Math.abs(v.y)>1.1;
  }
  for(let i=this.transfers.length-1;i>=0;i--){
   const t=this.transfers[i];if(fresh)t.age+=dt;
   const f=Math.min(1,t.age/1.6);
   // A visible board transfer represents an observed counter increase, not a new output prediction.
   t.board.position.lerpVectors(t.a,t.b,f);
   if(t.age>=1.6){this.scene.remove(t.board);this.transfers.splice(i,1);}
  }
  this.controls.update();this.renderer.render(this.scene,this.camera);
 }
 dispose(){
  if(this.disposed)return;this.disposed=true;
  this.renderer.setAnimationLoop(null);this.resizeObserver.disconnect();this.controls.dispose();
  for(const resource of this.resources)resource.dispose();
  this.renderer.dispose();this.renderer.forceContextLoss();
  this.root.replaceChildren();
 }
 debug(){
  return {renderer:'three-webgl',models:[...this.models.values()].map(m=>({id:m.id,status:m.row.machine_status,
   time:m.time,queueVisible:m.queue.filter(q=>q.visible).length,headX:m.parts.head?.position.x,
   kind:m.kind})),routeVisible:this.route.visible,transfers:this.transfers.length,selected:this.selected,
   camera:this.camera.position.toArray(),fresh:this.handlers.isFresh()};
 }
}
export function update(root,data,selected,handlers){
 if(!current||current.root!==root||current.disposed){current?.dispose();current=new FactoryScene(root,data,selected,handlers);}
 else current.update(data,selected);
}
export function reset(){current?.reset();}
export function focus(){current?.focus();}
export function dispose(){current?.dispose();current=null;}
export function debug(){return current?.debug()??null;}

