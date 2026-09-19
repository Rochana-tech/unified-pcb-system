const {chromium}=require('C:/Users/dhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,args:['--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1600,height:1050}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
 await page.goto('http://127.0.0.1:8002',{waitUntil:'networkidle'});
 await page.waitForFunction(()=>typeof factory3D!=='undefined'&&factory3D?.debug()?.models.length===6,{},{timeout:30000});
 await page.screenshot({path:'data/true3d-desktop.png',fullPage:true});
 console.log(JSON.stringify({debug:await page.evaluate(()=>factory3D.debug()),errors}));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

