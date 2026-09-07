let attentionCards = [];
let performanceData;
let performanceGroup = 'sources';
const categoryNames = {reply:'Messages', accepted:'Booking fees', new:'New enquiries', interest:'Recent interest', waiting:'Waiting quotes'};

async function renderToday() {
  const data = await api('/api/admin/intelligence/today');
  attentionCards = data.cards;
  workspace.className = 'workspace';
  workspace.innerHTML = `<div class="page-heading"><div><small class="eyebrow">YOUR MORNING CHECK-IN</small><h1>Who needs me today?</h1><p>${data.cards.length} couples to review · updated ${niceTime(data.generated_at)}</p></div><button class="secondary" id="refresh-today">Refresh</button></div>
    ${data.missing_evidence ? `<div class="notice">${data.missing_evidence} records are waiting for the new Booking activity connector. Recommendations appear when their evidence arrives.</div>` : ''}
    <div class="notice">Mailbox evidence covers the latest 200 inbox headers, matched by the main email address. Archived mail, partner addresses, phone calls and WhatsApp may be missing. Review the conversation before contacting a couple.</div>
    <div class="attention-filters"><button class="secondary active" data-category="all">All · ${data.cards.length}</button>${Object.entries(categoryNames).map(([k,v])=>`<button class="secondary" data-category="${k}">${v} · ${data.cards.filter(c=>c.kind===k).length}</button>`).join('')}</div>
    ${data.snoozed ? `<p>${data.snoozed} cards snoozed <button class="secondary" id="restore-snoozes">Show again</button></p>` : ''}
    <div class="attention-grid" id="attention-cards"></div>`;
  document.querySelector('#refresh-today').onclick = () => renderToday().catch(e=>toast(e.message));
  document.querySelector('#restore-snoozes')?.addEventListener('click',async()=>{try{await api('/api/admin/intelligence/reset-snoozes',{method:'POST'});await renderToday()}catch(e){toast(e.message)}});
  document.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>{
    document.querySelectorAll('[data-category]').forEach(x=>x.classList.toggle('active',x===b));drawAttention(b.dataset.category);
  });
  drawAttention('all');
}

function drawAttention(category) {
  const rows=attentionCards.filter(c=>category==='all'||c.kind===category);
  document.querySelector('#attention-cards').innerHTML=rows.length ? rows.map(c=>`<article class="attention-card ${esc(c.kind)}" data-card="${esc(c.lead_id)}">
    <header><span class="status">${esc(categoryNames[c.kind])}</span><strong>${money(c.value)}</strong></header>
    <h2>${esc(c.couple_name)}</h2><p class="muted">${niceDate(c.event_date)} · ${esc(c.venue)}</p>
    <h3>${esc(c.title)}</h3><p>${esc(c.reason)}</p>
    ${c.stale?'<div class="notice">Booking evidence is over 30 minutes old. Check Booking for the latest position.</div>':''}
    <details><summary>Why this is here</summary><dl class="evidence">
      <dt>Quote sent</dt><dd>${niceTime(c.quote_sent_at)}</dd><dt>Last outgoing contact</dt><dd>${niceTime(c.last_contact_at)}</dd>
      <dt>Incoming email seen</dt><dd>${niceTime(c.last_incoming_at)}</dd><dt>Quote-link access</dt><dd>${niceTime(c.quote_link_at)}</dd>
      <dt>Mailbox check</dt><dd>${esc({recent_inbox:'Recent inbox headers checked',unavailable:'Mailbox unavailable',not_configured:'Mailbox not configured'}[c.mail_status])} · ${niceTime(c.mail_checked_at)}</dd>
      <dt>Booking synced</dt><dd>${niceTime(c.synced_at)}</dd></dl></details>
    ${c.draft?`<details class="reply-draft"><summary>Review a suggested reply</summary><p>Prepared from the recorded stage and wedding details. Edit it, copy it, then review and send in Booking.</p><label>Message<textarea rows="8">${esc(c.draft)}</textarea></label><button class="secondary" data-copy="${esc(c.lead_id)}">Copy message</button></details>`:''}
    <footer><a class="primary button-link" href="${esc(c.url)}" target="_blank" rel="noopener">Open in Booking</a><button class="secondary" data-snooze="${esc(c.lead_id)}">Tomorrow</button><button class="secondary" data-lead="${esc(c.lead_id)}">Details</button></footer>
  </article>`).join('') : '<div class="panel empty">Nothing to review in this group. Snoozed cards return automatically when their time is up.</div>';
  bindLeadRows();
  document.querySelectorAll('[data-copy]').forEach(b=>b.onclick=async()=>{
    const textarea=b.closest('article').querySelector('textarea');
    try{await navigator.clipboard.writeText(textarea.value);toast('Copied—review and send in Booking')}catch{textarea.select();toast('Select and copy the message from the text box')}
  });
  document.querySelectorAll('[data-snooze]').forEach(b=>b.onclick=async()=>{
    try{await api(`/api/admin/intelligence/${b.dataset.snooze}/snooze`,{method:'POST',body:JSON.stringify({hours:24})});await renderToday()}catch(e){toast(e.message)}
  });
}

async function renderPerformance() {
  workspace.className='workspace';
  workspace.innerHTML=`<div class="page-heading"><div><small class="eyebrow">WHERE YOUR BOOKINGS COME FROM</small><h1>What’s working?</h1><p>Follow enquiries through to confirmed bookings.</p></div></div>
    <form class="toolbar" id="performance-filter"><label>Enquiries received from <input type="date" name="start"></label><label>To <input type="date" name="end"></label><button class="primary">Apply dates</button><button class="secondary" type="button" id="all-dates">All synced dates</button></form>
    <p class="muted">Dates refer to the original enquiry, not the wedding or import date. This covers only records included in your Booking sync range. Test and archived records are excluded. Booked value is agreed work, not cash collected.</p><div id="performance-content"></div>`;
  document.querySelector('#performance-filter').onsubmit=e=>{e.preventDefault();loadPerformance().catch(e=>toast(e.message))};
  document.querySelector('#all-dates').onclick=()=>{document.querySelector('#performance-filter').reset();loadPerformance().catch(e=>toast(e.message))};
  await loadPerformance();
}

async function loadPerformance() {
  const fields=new FormData(document.querySelector('#performance-filter'));
  const query=new URLSearchParams([...fields].filter(([,v])=>v));
  performanceData=await api(`/api/admin/intelligence/performance?${query}`);
  const d=performanceData;
  document.querySelector('#performance-content').innerHTML=`${d.missing_evidence?`<div class="notice">${d.missing_evidence} records lack source-date evidence and are excluded until the updated sync.</div>`:''}
    <section class="metrics"><article class="metric"><label>Enquiries in range</label><strong>${d.enquiries}</strong></article><article class="metric"><label>Confirmed bookings</label><strong>${d.bookings}</strong><small>${d.conversion}% of enquiries</small></article><article class="metric"><label>Booked value</label><strong>${money(d.booked_value)}</strong></article><article class="metric"><label>Average booking</label><strong>${money(d.average_booking)}</strong></article></section>
    <div class="attention-filters">${Object.entries({sources:'Enquiry sources',venues:'Venues',packages:'Packages',addons:'Add-ons'}).map(([k,v])=>`<button class="secondary" data-group="${k}">${v}</button>`).join('')}</div><div id="performance-table"></div>`;
  document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>{performanceGroup=b.dataset.group;drawPerformance()});drawPerformance();
}

function drawPerformance() {
  document.querySelectorAll('[data-group]').forEach(b=>b.classList.toggle('active',b.dataset.group===performanceGroup));
  const rows=performanceData.groups[performanceGroup], addon=performanceGroup==='addons';
  const best=rows.find(r=>r.bookings>0 && (addon || !r.small_sample));
  document.querySelector('#performance-table').innerHTML=`<p>${addon?'Selected add-ons on confirmed bookings. Counts are distinct bookings; amounts are add-on line totals. Discounts are excluded.':'Conversion is confirmed bookings divided by enquiries in the selected range. Groups below 10 enquiries are marked as a small sample.'}</p>
    ${performanceGroup==='packages'?'<p class="muted">Package groups use the selected quote package, falling back to recorded interest. They show associations, not proof that a package caused a booking.</p>':''}
    ${best?`<div class="notice"><strong>${esc(best.name)}</strong> has the highest booked value ${addon?'among selected add-ons':'among groups with at least 10 enquiries'}: ${money(best.booked_value)} from ${best.bookings} bookings.</div>`:''}
    ${rows.length?`<div class="table-wrap"><table class="insight-table"><thead><tr><th>Name</th>${addon?'':'<th>Enquiries</th>'}<th>Bookings</th>${addon?'':'<th>Conversion</th>'}<th>${addon?'Add-on value':'Booked value'}</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.name)}</strong>${r.small_sample?'<small>Small sample</small>':''}</td>${addon?'':`<td>${r.enquiries}</td>`}<td>${r.bookings}</td>${addon?'':`<td><span>${r.conversion}%</span><progress max="100" value="${r.conversion}" aria-label="Conversion ${r.conversion} percent"></progress></td>`}<td>${money(r.booked_value)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="panel empty">No results in this group for the selected dates.</div>'}`;
}
