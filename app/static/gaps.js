let gapCalendar;
let gapSelected = new Set();
let gapRequest = 0;
let gapCreative = null;
let gapPreset = null;

async function renderGaps() {
  const requestId=++gapRequest;
  gapCalendar=null;gapSelected.clear();
  workspace.className='workspace';
  workspace.innerHTML=`<div class="page-heading"><div><small class="eyebrow">MAKE ROOM FOR MORE BOOKINGS</small><h1>Fill my empty dates</h1><p>Choose dates you want to promote, review matching enquiries, and prepare a post.</p></div></div>
    <div class="gap-tabs"><button class="primary" id="gap-plan-tab">Plan a campaign</button><button class="secondary" id="gap-results-tab">Campaigns & results</button></div>
    <section class="panel gap-controls"><label>Look ahead<select id="gap-horizon"><option value="12">Next 12 months</option><option value="18">Next 18 months</option><option value="24">Next 24 months</option><option value="custom">Custom dates / season</option></select></label><label id="gap-custom-start-label" hidden>From<input type="date" id="gap-custom-start"></label><label id="gap-custom-end-label" hidden>To<input type="date" id="gap-custom-end"></label><label>Show dates<select id="gap-weekdays"><option value="weekend">Saturdays & Sundays</option><option value="all">Every day</option><option value="weekday">Monday to Friday</option></select></label><button class="primary" id="gap-refresh">Check Booking live</button></section>
    <p class="muted">Confirmed weddings and your Booking holiday blocks protect dates, including archived and imported weddings. Calendar events that have not been recorded in Booking are outside this check. Open quotes do not reserve a date.</p>
    ${gapCreative?`<div class="notice">Venue campaign: <strong>${esc(gapCreative.venue)}</strong>. Your chosen testimonial and photo links will be kept with the draft. <button class="secondary" id="gap-clear-venue">Use a general campaign instead</button></div>`:""}<div id="gap-calendar" aria-live="polite">Checking availability…</div><div id="gap-compose"></div>`;
  document.querySelector('#gap-results-tab').onclick=()=>renderGapCampaigns().catch(e=>toast(e.message));
  document.querySelector('#gap-plan-tab').onclick=()=>renderGaps().catch(e=>toast(e.message));
  document.querySelector('#gap-refresh').onclick=()=>loadGapCalendar().catch(e=>toast(e.message));
  const toggleCustom=()=>{const custom=document.querySelector('#gap-horizon').value==='custom';document.querySelector('#gap-custom-start-label').hidden=!custom;document.querySelector('#gap-custom-end-label').hidden=!custom;};
  const clearCustom=()=>{gapCalendar=null;gapSelected.clear();document.querySelector('#gap-compose').innerHTML='';document.querySelector('#gap-calendar').textContent='Choose your range, then press Check Booking live.';};
  document.querySelector('#gap-horizon').onchange=()=>{toggleCustom();if(document.querySelector('#gap-horizon').value!=='custom')loadGapCalendar().catch(e=>toast(e.message));else clearCustom()};
  document.querySelector('#gap-custom-start').onchange=clearCustom;document.querySelector('#gap-custom-end').onchange=clearCustom;
  document.querySelector('#gap-custom-start').value=londonDate();
  document.querySelector('#gap-custom-end').value=londonDate();
  document.querySelector('#gap-clear-venue')?.addEventListener('click',()=>{gapCreative=null;renderGaps().catch(e=>toast(e.message))});
  if(gapPreset){document.querySelector('#gap-horizon').value='custom';document.querySelector('#gap-custom-start').value=gapPreset.start;document.querySelector('#gap-custom-end').value=gapPreset.end;toggleCustom();gapPreset=null;}

  document.querySelector('#gap-weekdays').onchange=()=>{if(gapCalendar)drawGapCalendar()};
  if(requestId===gapRequest)await loadGapCalendar();
}

function londonDate() {
  const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const part=type=>parts.find(p=>p.type===type).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

async function loadGapCalendar() {
  const id=++gapRequest;
  const horizon=document.querySelector('#gap-horizon').value;
  const months=horizon==='custom'?0:Number(horizon);
  const start=horizon==='custom'?document.querySelector('#gap-custom-start').value:londonDate();
  if(!start){toast('Choose a start date');return;}
  const endDate=new Date(start+'T12:00:00Z');
  const wantedDay=endDate.getUTCDate();
  endDate.setUTCDate(1);endDate.setUTCMonth(endDate.getUTCMonth()+months);
  const last=new Date(Date.UTC(endDate.getUTCFullYear(),endDate.getUTCMonth()+1,0)).getUTCDate();
  endDate.setUTCDate(Math.min(wantedDay,last));
  // Inclusive custom ranges support up to 732 days, including leap years.
  const cap=new Date(new Date(start+'T12:00:00Z').getTime()+731*86400000);
  const end=horizon==='custom'?document.querySelector('#gap-custom-end').value:new Date(Math.min(endDate,cap)).toISOString().slice(0,10);
  if(!end){toast('Choose an end date');return;}
  gapCalendar=null;gapSelected.clear();
  document.querySelector('#gap-compose').innerHTML='';
  document.querySelector('#gap-calendar').textContent='Checking Booking live…';
  try{
    const data=await api(`/api/admin/gaps/calendar?start=${start}&end=${end}`);
    if(id!==gapRequest||state.view!=='gaps')return;
    gapCalendar=data;drawGapCalendar();
  }catch(error){if(id===gapRequest&&document.querySelector('#gap-calendar'))document.querySelector('#gap-calendar').innerHTML=`<div class="notice"><strong>Availability unknown</strong><p>${esc(error.message)}</p></div>`;}
}

function drawGapCalendar() {
  const filter=document.querySelector('#gap-weekdays').value;
  const days=gapCalendar.days.filter(d=>{const weekend=[0,6].includes(new Date(d.date+'T12:00:00Z').getUTCDay());return filter==='all'||(filter==='weekend'?weekend:!weekend)});
  const free=days.filter(d=>d.status==='available');
  const groups={};for(const day of free)(groups[day.date.slice(0,7)]??=[]).push(day);
  document.querySelector('#gap-calendar').innerHTML=`<div class="gap-summary"><strong>${free.length} available dates</strong><span>${days.filter(d=>d.status==='booked').length} booked · ${days.filter(d=>d.status==='blocked').length} blocked in this filter</span><small>${niceDate(gapCalendar.start)} to ${niceDate(gapCalendar.end)} · Checked ${niceTime(gapCalendar.checked_at)} · checked again when you prepare or copy a campaign</small></div>
    <p>Select up to 12 dates. A matching enquiry is a prompt to review the conversation before contacting anyone.</p>
    ${Object.entries(groups).map(([month,dates],index)=>`<details class="panel gap-month" ${index===0?'open':''}><summary>${esc(new Intl.DateTimeFormat('en-GB',{month:'long',year:'numeric'}).format(new Date(month+'-01T12:00:00')))} · ${dates.length} available</summary><div class="gap-grid">${dates.map(d=>`<article class="gap-date"><label><input type="checkbox" data-gap-date="${d.date}" ${gapSelected.has(d.date)?'checked':''}><strong>${esc(new Intl.DateTimeFormat('en-GB',{weekday:'short',day:'numeric',month:'short'}).format(new Date(d.date+'T12:00:00')))}</strong></label>${d.enquiries.length?`<details><summary>${d.enquiries.length} matching enquir${d.enquiries.length===1?'y':'ies'}</summary>${d.enquiries.map(e=>`<div class="gap-enquiry"><strong>${esc(e.name)}</strong><span>${esc(e.venue)} · ${money(e.value)}</span><small>Quote: ${esc(e.quote_status||'Not recorded')}<br>Latest outgoing: ${niceTime(e.last_contact_at)}<br>Incoming seen: ${niceTime(e.last_incoming_at)}<br>Synced: ${niceTime(e.synced_at)}</small><a href="${esc(e.url)}" target="_blank" rel="noopener">Review conversation in Booking</a></div>`).join('')}</details>`:'<small>No eligible synced enquiries for this date</small>'}</article>`).join('')}</div></details>`).join('')||'<div class="panel empty">No available dates in this filter. Try every day or a longer period.</div>'}
    <div class="gap-selection"><strong id="gap-selection-count"></strong><button class="secondary" id="gap-clear">Clear selection</button><button class="primary" id="gap-prepare">Prepare a promotion</button></div>`;
  document.querySelectorAll('[data-gap-date]').forEach(input=>input.onchange=()=>{if(input.checked&&gapSelected.size>=12){input.checked=false;toast('Choose up to 12 dates per campaign');return;}if(input.checked)gapSelected.add(input.dataset.gapDate);else gapSelected.delete(input.dataset.gapDate);document.querySelector('#gap-compose').innerHTML='';updateGapSelection()});
  document.querySelector('#gap-clear').onclick=()=>{gapSelected.clear();document.querySelector('#gap-compose').innerHTML='';drawGapCalendar()};
  document.querySelector('#gap-prepare').onclick=()=>showGapComposer();
  updateGapSelection();
}
function updateGapSelection(){document.querySelector('#gap-selection-count').textContent=`${gapSelected.size} selected (including other filters)`;document.querySelector('#gap-prepare').disabled=!gapSelected.size;}

function showGapComposer(){
  const selected=[...gapSelected].sort();
  const target=document.querySelector('#gap-compose');
  target.innerHTML=`<section class="panel gap-composer"><h2>Prepare your promotion</h2><p>${selected.map(niceDate).join(' · ')}</p><form id="gap-draft-form"><label>Campaign name<input name="name" maxlength="160" required value="${esc('Wedding availability '+niceDate(selected[0]))}"></label><label>Where will you post it?<select name="channel"><option value="facebook">Facebook</option><option value="google">Google Business Profile</option></select></label><label>Include a current package price?<select name="package_id"><option value="">No price in this post</option>${gapCalendar.packages.map(p=>`<option value="${esc(p.id)}">${esc(p.name)} · ${money(p.price)}</option>`).join('')}</select></label><p class="muted">Prices come directly from your Booking catalogue. Review the wording and Booking enquiry link before posting.</p><button class="primary" type="submit">Generate draft</button></form><div id="gap-generated"></div></section>`;
  target.scrollIntoView({behavior:'smooth',block:'start'});
  const form=document.querySelector('#gap-draft-form');
  form.onchange=()=>{document.querySelector('#gap-generated').innerHTML=''};
  form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;try{
    const fields=Object.fromEntries(new FormData(form));
    const payload={dates:selected,channel:fields.channel,package_id:fields.package_id||null,creative:gapCreative};
    const data=await api('/api/admin/gaps/draft',{method:'POST',body:JSON.stringify(payload)});
    const output=document.querySelector('#gap-generated');if(!output)return;
    output.innerHTML=`<label>Review and edit your post<textarea id="gap-draft-text" rows="12">${esc(data.draft)}</textarea></label><p>Nothing is posted or sent from Growth. Save this campaign, then copy the reviewed post.</p><button class="primary" id="gap-save" type="button">Save campaign</button>`;
    document.querySelector('#gap-save').onclick=async()=>{const save=document.querySelector('#gap-save');save.disabled=true;try{await api('/api/admin/gaps/campaigns',{method:'POST',body:JSON.stringify({...payload,package_snapshot:data.package.id?data.package:null,name:form.elements.name.value,draft:document.querySelector('#gap-draft-text').value})});await renderGapCampaigns();toast('Campaign saved—ready to review and copy')}catch(e){toast(e.message);save.disabled=false}};
  }catch(e){toast(e.message)}finally{button.disabled=false}};
}

async function renderGapCampaigns(){
  const requestId=++gapRequest;
  const data=await api('/api/admin/gaps/campaigns');
  if(state.view!=='gaps'||requestId!==gapRequest)return;
  workspace.innerHTML=`<div class="page-heading"><div><h1>Campaigns & results</h1><p>See which promotions turn into bookings.</p></div><button class="primary" id="gap-back">Plan a campaign</button></div><div class="notice">Attribute an enquiry only when you know it came from this campaign. Each enquiry can belong to one campaign. Results use the latest Booking sync and exclude test and archived records. Booked value is agreed work, not cash received. No click or reach tracking is claimed.</div><div class="gap-campaigns">${data.campaigns.map(c=>`<article class="panel gap-campaign" data-campaign="${esc(c.id)}"><header><h2>${esc(c.name)}</h2><span class="status">${c.status==='published'?'Marked as posted':'Private draft'}</span></header><p>${c.channel==='facebook'?'Facebook':'Google Business Profile'} · ${c.dates.map(niceDate).join(' · ')}</p><div class="gap-summary"><strong>${c.enquiries} enquiries · ${c.bookings} bookings</strong><span>${money(c.booked_value)} booked value</span></div>${c.creative?.photo_urls?.length?`<details><summary>Chosen photos · ${c.creative.photo_urls.length}</summary><p>Use these photos when you publish the post. Growth does not download or publish them.</p>${c.creative.photo_urls.map((url,i)=>`<a class="button-link secondary" href="${esc(url)}" target="_blank" rel="noopener">Open photo ${i+1}</a>`).join(' ')}</details>`:''}<details><summary>Review the post</summary><label>Campaign name<input class="campaign-name" value="${esc(c.name)}" ${c.status==='published'?'readonly':''} maxlength="160"></label><label>Post text<textarea class="campaign-text" rows="12" ${c.status==='published'?'readonly':''}>${esc(c.draft)}</textarea></label><div class="gap-actions">${c.status==='draft'?'<button class="secondary" data-campaign-save>Save edits</button>':''}<button class="primary" data-campaign-copy>Check dates & copy saved post</button>${c.status==='draft'?'<button class="secondary" data-campaign-posted>I’ve posted it</button>':''}</div><p class="muted">Copy checks availability and package price again. “I’ve posted it” records your action; it does not publish anything.</p></details><details><summary>Attribute an enquiry / review results</summary><p>Check the couple’s source before assigning this campaign.</p><label>Enquiry<select class="campaign-lead"><option value="">Choose a synced enquiry…</option>${data.leads.filter(l=>!l.campaign_id).sort((a,b)=>a.name.localeCompare(b.name)).map(l=>`<option value="${esc(l.id)}">${esc(l.name)} · ${niceDate(l.date)}</option>`).join('')}</select></label><button class="secondary" data-campaign-attribute>Attribute to this campaign</button>${c.leads.map(l=>`<div class="gap-attribution"><span>${esc(l.name)} · ${l.booked?'Booked':'Not booked'}</span><button class="secondary" data-unattribute="${esc(l.id)}">Remove attribution</button></div>`).join('')}</details></article>`).join('')||'<div class="panel empty">No campaigns yet. Choose available dates to prepare your first promotion.</div>'}</div>`;
  document.querySelector('#gap-back').onclick=()=>renderGaps().catch(e=>toast(e.message));
  document.querySelectorAll('[data-campaign]').forEach(article=>{
    const id=article.dataset.campaign,c=data.campaigns.find(c=>c.id===id);
    const action=(selector,fn)=>article.querySelector(selector)?.addEventListener('click',async event=>{const button=event.currentTarget;button.disabled=true;try{await fn()}catch(e){toast(e.message)}finally{button.disabled=false}});
    action('[data-campaign-save]',async()=>{await api(`/api/admin/gaps/campaigns/${id}`,{method:'PATCH',body:JSON.stringify({name:article.querySelector('.campaign-name').value,draft:article.querySelector('.campaign-text').value})});await renderGapCampaigns();toast('Edits saved')});
    action('[data-campaign-copy]',async()=>{if(article.querySelector('.campaign-text').value!==c.draft)throw new Error('Save your edits before copying.');await api(`/api/admin/gaps/campaigns/${id}/check`,{method:'POST'});try{await navigator.clipboard.writeText(c.draft);toast('Dates checked and post copied. Review before posting.')}catch{article.querySelector('.campaign-text').select();toast('Dates checked. Select and copy the text above.')}});
    action('[data-campaign-posted]',async()=>{if(article.querySelector('.campaign-text').value!==c.draft)throw new Error('Save the wording you posted first.');await api(`/api/admin/gaps/campaigns/${id}/published`,{method:'POST'});await renderGapCampaigns()});
    action('[data-campaign-attribute]',async()=>{const lead_id=article.querySelector('.campaign-lead').value;if(!lead_id)throw new Error('Choose an enquiry first.');await api(`/api/admin/gaps/campaigns/${id}/attribution`,{method:'POST',body:JSON.stringify({lead_id})});await renderGapCampaigns()});
    article.querySelectorAll('[data-unattribute]').forEach(button=>button.onclick=async()=>{try{await api(`/api/admin/gaps/campaigns/${id}/attribution/${button.dataset.unattribute}`,{method:'DELETE'});await renderGapCampaigns()}catch(e){toast(e.message)}});
  });
}
