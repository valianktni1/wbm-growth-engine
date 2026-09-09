(() => {
  'use strict';
  const config=window.wbmInsightsConfig;
  if(!config||!['perfectweddingsbymark.uk','www.perfectweddingsbymark.uk'].includes(location.hostname)||location.protocol!=='https:')return;
  let consenting=false, remote=null, generation=0, controller=null, started=false, pageSent=false;
  const blocked=()=>navigator.globalPrivacyControl===true||navigator.doNotTrack==='1';
  const read=(store,key)=>{try{return store.getItem(key)}catch{return null}};
  const write=(store,key,value)=>{try{store.setItem(key,value)}catch{}};
  const clear=()=>{try{sessionStorage.removeItem('wbm-visit')}catch{}};
  function source(){
    const tag=new URL(location.href).searchParams.get('utm_source')?.toLowerCase();
    if(tag)return ({facebook:'Facebook',instagram:'Instagram',google:'Google',bing:'Bing'})[tag]||'Other website';
    let host='';try{host=new URL(document.referrer).hostname.toLowerCase()}catch{}
    const is=domain=>host===domain||host.endsWith('.'+domain);
    if(!host||is('perfectweddingsbymark.uk'))return 'Direct / unknown';
    if(is('google.com')||is('google.co.uk'))return 'Google';
    if(is('facebook.com')||is('fb.com'))return 'Facebook';
    if(is('instagram.com'))return 'Instagram';
    if(is('bing.com'))return 'Bing';
    return 'Other website';
  }
  function visit(){
    let v;try{v=JSON.parse(read(sessionStorage,'wbm-visit'))}catch{}
    if(!v||typeof v.id!=='string'||!Number.isFinite(v.last)||Date.now()-v.last>1800000){
      const campaign=new URL(location.href).searchParams.get('utm_campaign')||'';
      v={id:crypto.randomUUID(),source:source(),campaign:remote.campaigns.includes(campaign)?campaign:'',last:Date.now()};
    }
    v.last=Date.now();write(sessionStorage,'wbm-visit',JSON.stringify(v));return v;
  }
  function track(kind){
    if(!consenting||blocked()||!remote||!remote.pages.includes(location.pathname))return;
    if(!['page_view','enquiry_start','enquiry_success','date_check'].includes(kind))return;
    if(kind!=='page_view'&&!remote.goals_ready)return;
    try{
      const v=visit();
      fetch(config.endpoint+'/api/website/events',{method:'POST',mode:'cors',credentials:'omit',referrerPolicy:'no-referrer',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token,event_id:crypto.randomUUID(),visit_id:v.id,kind,path:location.pathname,source:v.source,campaign:v.campaign,device:innerWidth<768?'Small screen':'Large screen'}),signal:controller?.signal}).catch(()=>{});
      return true;
    }catch{}
  }
  async function consent(allow){
    const current=++generation;
    consenting=allow===true&&!blocked();remote=null;started=false;pageSent=false;
    controller?.abort();controller=new AbortController();
    if(config.ownPrompt)write(localStorage,'wbm-analytics-choice',consenting?'allow':'deny');
    document.querySelector('#wbm-insights-prompt')?.remove();
    if(!consenting){clear();return}
    try{
      const res=await fetch(config.endpoint+'/api/website/config?token='+encodeURIComponent(config.token),{mode:'cors',credentials:'omit',referrerPolicy:'no-referrer',signal:controller.signal});
      if(!res.ok)return;
      const data=await res.json();
      if(current!==generation||!consenting||!Array.isArray(data.pages)||!Array.isArray(data.campaigns))return;
      remote=data;
      if(!pageSent){track('page_view');pageSent=true;}
    }catch{}
  }
  window.wbmAnalyticsConsent=consent;
  window.wbmWebsiteEvent=kind=>{if(kind==='enquiry_start'&&started)return;const sent=track(kind);if(kind==='enquiry_start'&&sent)started=true;};
  if(config.formSelector){
    document.addEventListener('focusin',e=>{try{if(e.target.closest(config.formSelector))window.wbmWebsiteEvent('enquiry_start')}catch{}},{passive:true});
    document.addEventListener('wpcf7mailsent',e=>{try{if(e.target.matches(config.formSelector)||e.target.querySelector(config.formSelector))track('enquiry_success')}catch{}});
  }
  function prompt(){
    if(blocked())return;
    document.querySelector('#wbm-insights-prompt')?.remove();
    const panel=document.createElement('section');panel.id='wbm-insights-prompt';panel.setAttribute('aria-label','Optional website analytics');
    const text=document.createElement('p');text.textContent='May we measure your visit to improve our website? We count public pages and enquiry steps, without collecting your form answers. You can change your choice at any time.';
    panel.append(text);
    for(const [label,value] of [['Allow',true],['No thanks',false]]){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=()=>consent(value);panel.append(b);}
    document.body.append(panel);
  }
  if(config.ownPrompt){
    const button=document.createElement('button');button.type='button';button.id='wbm-insights-choice';button.textContent='Analytics choice';button.onclick=()=>{consent(false);prompt()};document.body.append(button);
    const saved=read(localStorage,'wbm-analytics-choice');
    if(saved==='allow')consent(true);else if(saved!=='deny')prompt();
  }
})();
