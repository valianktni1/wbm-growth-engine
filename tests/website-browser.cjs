// DOM-level integration tests. Run with WEB_TEST_MODULES pointing to a node_modules directory containing jsdom and php-parser.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {JSDOM}=require(path.join(process.env.WEB_TEST_MODULES,'jsdom'));
const root=path.join(__dirname,'..');
const tracker=fs.readFileSync(path.join(root,'wordpress/wbm-website-insights/tracker.js'),'utf8');
const settle=()=>new Promise(resolve=>setTimeout(resolve,20));
async function trackerTest(block=false){
  const dom=new JSDOM('<body><form id="enquiry"><input name="email"></form></body>',{url:'https://perfectweddingsbymark.uk/?utm_source=facebook&private=not-to-collect',runScripts:'outside-only'});
  const w=dom.window,calls=[];
  w.wbmInsightsConfig={endpoint:'https://growth.weddingsbymark.uk',token:'public-test-code',ownPrompt:false,formSelector:'#enquiry'};
  Object.defineProperty(w.navigator,'globalPrivacyControl',{value:block});
  w.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({pages:['/'],campaigns:[],goals_ready:true})}};
  w.eval(tracker);await settle();assert.equal(calls.length,0,'No tracking request before consent');
  w.wbmWebsiteEvent('enquiry_start');assert.equal(calls.length,0);
  await w.wbmAnalyticsConsent(true);await settle();
  if(block){assert.equal(calls.length,0);assert.equal(w.sessionStorage.length,0);dom.window.close();return;}
  assert.equal(calls.length,2);let event=JSON.parse(calls[1].options.body);
  assert.equal(event.source,'Facebook');assert.equal(event.path,'/');assert(!calls[1].options.body.includes('private'));
  w.document.querySelector('input').dispatchEvent(new w.FocusEvent('focusin',{bubbles:true}));
  w.document.querySelector('input').dispatchEvent(new w.FocusEvent('focusin',{bubbles:true}));
  assert.equal(calls.filter(c=>c.options?.body&&JSON.parse(c.options.body).kind==='enquiry_start').length,1);
  w.document.querySelector('form').dispatchEvent(new w.Event('submit',{bubbles:true}));
  assert.equal(calls.filter(c=>c.options?.body&&JSON.parse(c.options.body).kind==='enquiry_success').length,0,'A submit event is not a delivered enquiry');
  w.wbmWebsiteEvent('enquiry_success');assert.equal(calls.length,4);
  assert.equal(JSON.parse(calls[3].options.body).visit_id,event.visit_id);
  await w.wbmAnalyticsConsent(false);w.wbmWebsiteEvent('enquiry_success');await settle();assert.equal(calls.length,4);assert.equal(w.sessionStorage.length,0);
  dom.window.close();
}
async function uiTest(){
  const html=fs.readFileSync(path.join(root,'app/static/admin.html'),'utf8');
  const dom=new JSDOM(html,{url:'https://growth.weddingsbymark.uk/#website',runScripts:'outside-only'});
  const ctx=dom.getInternalVMContext();
  // Start is exercised explicitly with controlled fixtures instead of the page's automatic auth bootstrap.
  const source=fs.readFileSync(path.join(root,'app/static/growth.js'),'utf8').replace("window.addEventListener('DOMContentLoaded', start, {once: true});",'');
  vm.runInContext(source,ctx);
  vm.runInContext(fs.readFileSync(path.join(root,'app/static/website.js'),'utf8'),ctx);
  const report={start:'2026-08-01',end:'2026-08-28',days:28,enabled:false,last_event:null,goals_ready:false,comparison_ready:false,current:{visits:0,views:0,starts:0,enquiries:0,started_and_completed:0,date_checks:0,sources:[],pages:[],campaigns:[]},previous:{visits:0},tips:['Not connected yet.'],google:null,google_status:{},google_connected:false,booking_attribution:'Not connected.'};
  dom.window.fixture=report;
  vm.runInContext("api=async(url)=>url==='/api/auth/me'?{csrf_token:'test',email:'mark@example.com'}:window.fixture; state.view='website';",ctx);
  await vm.runInContext('start()',ctx);await settle();
  assert(dom.window.document.querySelector('[data-view=website]').classList.contains('active'));
  assert(dom.window.document.querySelector('#web-report').textContent.includes('Not connected'));
  assert(dom.window.document.querySelector('#web-report').textContent.includes('Worth your attention'));
  assert(!dom.window.document.querySelector('#web-report').textContent.includes('undefined'));
  dom.window.fixture={website:{pages:{'/':'Home'},token:'public-code',enabled:false,goals_ready:false},google:{},endpoint:'https://growth.weddingsbymark.uk'};
  await vm.runInContext('renderWebsiteSetup()',ctx);
  assert(dom.window.document.querySelector('#web-settings'));
  assert(dom.window.document.querySelector('#web-google-connect'));
  dom.window.close();
}
(async()=>{await trackerTest();await trackerTest(true);await uiTest();
 const Parser=require(path.join(process.env.WEB_TEST_MODULES,'php-parser'));
 new Parser({parser:{phpVersion:'7.4',suppressErrors:false}}).parseCode(fs.readFileSync(path.join(root,'wordpress/wbm-website-insights/wbm-website-insights.php'),'utf8'));
 console.log('PASS: consent/withdrawal, same-visit events, no submit-click conversion, GPC, dashboard/setup DOM, PHP syntax.');
})().catch(e=>{console.error(e);process.exitCode=1});
