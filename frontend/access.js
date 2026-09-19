// Operator key stays only in this tab's memory; it is never written to browser storage.
let operatorKey='', publicAccess={public:false,can_control:false};
async function checkAccess(){
 try{
  const result=await fetch('/api/access',{headers:operatorKey?{Authorization:'Bearer '+operatorKey}:{}});
  if(!result.ok)throw Error('Access check failed');
  publicAccess=await result.json();
  const button=document.getElementById('operatorAccess');
  button.hidden=!publicAccess.public;
  button.textContent=publicAccess.can_control?'Lock operator controls':'Operator access';
  if(typeof connection==='function')connection();
  return publicAccess.can_control;
 }catch(error){
  publicAccess.can_control=false;
  if(typeof connection==='function')connection();
  return false;
 }
}
function showOperatorLogin(){
 if(publicAccess.can_control){operatorKey='';checkAccess();return;}
 let dialog=document.getElementById('operatorDialog');
 if(!dialog){
  dialog=document.createElement('dialog');dialog.id='operatorDialog';
  dialog.style.cssText='max-width:390px;width:90%;background:var(--panel);color:var(--text);border:1px solid var(--line);padding:24px;border-radius:6px';
  dialog.innerHTML='<form id="operatorForm"><h3>Operator access</h3><p class="muted">Anyone can view this demo. Enter your operator key to inject faults, reset the line, or run what-if scenarios.</p><label for="operatorKey">Operator key</label><input id="operatorKey" type="password" autocomplete="off" required style="display:block;width:100%;margin:12px 0"><p id="accessError" role="alert"></p><button class="btn primary" type="submit">Unlock controls</button> <button class="btn" type="button" id="cancelOperator">Cancel</button></form>';
  document.body.append(dialog);
  dialog.querySelector('#cancelOperator').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.querySelector('input').value='';});
  dialog.querySelector('form').onsubmit=async e=>{
   e.preventDefault();operatorKey=dialog.querySelector('input').value;
   if(await checkAccess()){dialog.close();toast('Operator controls unlocked for this tab.');}
   else{operatorKey='';dialog.querySelector('#accessError').textContent='Key not accepted. Check the key in your hosting environment settings.';}
  };
 }
 dialog.querySelector('#accessError').textContent='';dialog.showModal();
}
checkAccess();

