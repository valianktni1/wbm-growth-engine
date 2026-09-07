const state = {csrf: "", view: "dashboard", leads: [], selected: null};
const app = document.querySelector("#app");
const workspace = document.querySelector("#workspace");
const toastNode = document.querySelector("#toast");

const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const money = value => new Intl.NumberFormat("en-GB", {style:"currency",currency:"GBP",maximumFractionDigits:0}).format(Number(value || 0));
const niceDate = value => value ? new Intl.DateTimeFormat("en-GB", {day:"numeric",month:"short",year:"numeric"}).format(new Date(`${value}T12:00:00`)) : "—";
const niceTime = value => value ? new Intl.DateTimeFormat("en-GB", {dateStyle:"medium",timeStyle:"short"}).format(new Date(value)) : "—";
const localDateTime = value => value ? new Date(new Date(value).getTime() - new Date(value).getTimezoneOffset() * 60000).toISOString().slice(0,16) : "";

function toast(message) { toastNode.textContent = message; toastNode.classList.add("show"); setTimeout(() => toastNode.classList.remove("show"), 2600); }

async function api(url, options={}) {
  const headers = {...(options.headers || {})};
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = state.csrf;
  const response = await fetch(url, {...options, headers});
  if (response.status === 401) { window.location.replace("/login"); throw new Error("Please sign in"); }
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Something went wrong");
  return data;
}

function setView(view) {
  state.view = view;
  document.querySelectorAll("nav button").forEach(button => button.classList.toggle("active", button.dataset.view === view));
  document.querySelector("#navigation").classList.remove("open");
  if (view === "dashboard") renderDashboard();
  if (view === "enquiries") renderEnquiries();
  if (view === "followups") renderFollowups();
  if (view === "venues") renderVenues();
  if (view === "settings") renderSettings();
  window.location.hash = view;
  workspace.focus();
}

async function renderDashboard() {
  workspace.innerHTML = `<div class="loading-screen"><div class="spinner"></div></div>`;
  const data = await api("/api/admin/dashboard");
  workspace.className = "workspace";
  workspace.innerHTML = `
    <div class="page-heading"><div><h1>Good morning, Mark</h1><p>The enquiries most likely to need your attention today.</p></div><div class="actions"><button class="primary" id="new-enquiry">+ Add enquiry</button></div></div>
    <section class="metrics">
      <article class="metric"><label>New enquiries</label><strong>${data.metrics.new_enquiries}</strong><small>This month</small></article>
      <article class="metric"><label>Proposal opened</label><strong>${data.metrics.proposal_opened}</strong><small>Interested couples</small></article>
      <article class="metric"><label>Bookings</label><strong>${data.metrics.bookings}</strong><small>This month</small></article>
      <article class="metric"><label>Booked value</label><strong>${money(data.metrics.booked_value)}</strong><small>This month</small></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel"><header><h2>Enquiries to watch</h2><span>Most active first</span></header><div class="lead-list">${data.hot_leads.length ? data.hot_leads.map(leadRow).join("") : `<div class="empty">New enquiries will appear here automatically.</div>`}</div></article>
      <aside class="panel"><header><h2>Suggested actions</h2></header><div class="action-list">${data.actions.map(x => `<div class="action-item"><strong>${x.count} ${esc(x.label)}</strong><p>Review and approve only the messages you are happy with.</p></div>`).join("")}<div class="action-item"><strong>Website connection</strong><p>New forms can feed this dashboard and your existing booking system together.</p></div></div></aside>
    </section>`;
  bindLeadRows();
  document.querySelector("#new-enquiry").addEventListener("click", renderNewEnquiry);
}

function leadRow(lead) {
  return `<button class="lead-row" data-lead="${lead.id}"><div><strong>${esc(lead.couple_name)}</strong><small>${niceDate(lead.event_date)}</small></div><div><strong>${esc(lead.venue)}</strong><small>${esc(lead.referral_source || "Source not recorded")}</small></div><div><strong>${esc(lead.package_interest || "Not chosen")}</strong><small>${money(lead.estimated_value)}</small></div><span class="status ${esc(lead.stage)}">${esc(lead.stage)}</span></button>`;
}

function bindLeadRows() { document.querySelectorAll("[data-lead]").forEach(row => row.addEventListener("click", () => renderLead(row.dataset.lead))); }

async function renderEnquiries() {
  state.leads = await api("/api/admin/leads");
  workspace.className = "workspace";
  workspace.innerHTML = `<div class="page-heading"><div><h1>Enquiries</h1><p>Every couple from first enquiry to confirmed booking.</p></div><div class="actions"><button class="primary" id="new-enquiry">+ Add enquiry</button></div></div>
    <div class="toolbar"><input id="lead-search" type="search" placeholder="Search couple or venue"><select id="stage-filter"><option value="">All stages</option>${["new","qualified","proposal","engaged","booked","lost"].map(x=>`<option>${x}</option>`).join("")}</select></div><div id="lead-table"></div>`;
  const draw = () => {
    const query = document.querySelector("#lead-search").value.toLowerCase(); const stage = document.querySelector("#stage-filter").value;
    const rows = state.leads.filter(x => (!stage || x.stage === stage) && (!query || `${x.couple_name} ${x.venue} ${x.email}`.toLowerCase().includes(query)));
    document.querySelector("#lead-table").innerHTML = rows.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Couple</th><th>Wedding</th><th>Venue</th><th>Interest</th><th>Stage</th></tr></thead><tbody>${rows.map(x=>`<tr data-lead="${x.id}"><td><strong>${esc(x.couple_name)}</strong><br><small>${esc(x.email)}</small></td><td>${niceDate(x.event_date)}</td><td>${esc(x.venue)}</td><td>${esc(x.package_interest || "Not selected")}</td><td><span class="status ${esc(x.stage)}">${esc(x.stage)}</span></td></tr>`).join("")}</tbody></table></div>` : `<div class="panel empty">No enquiries match this view.</div>`;
    bindLeadRows();
  };
  draw(); document.querySelector("#lead-search").addEventListener("input", draw); document.querySelector("#stage-filter").addEventListener("change", draw);
  document.querySelector("#new-enquiry").addEventListener("click", renderNewEnquiry);
}

function renderNewEnquiry() {
  workspace.className="workspace";
  workspace.innerHTML=`<button class="back" id="back">← Back</button><div class="page-heading"><div><h1>Add an enquiry</h1><p>Use this for telephone, WhatsApp or manually received enquiries.</p></div></div><form class="detail-card form-grid" id="lead-form">
    <label>First name<input name="primary_first_name" required></label><label>Partner’s first name<input name="partner_first_name" required></label><label>Email<input type="email" name="email" required></label><label>Telephone<input name="phone"></label><label>Wedding date<input type="date" name="event_date" required></label><label>Venue<input name="location" required></label><label>Package interest<input name="package_interest"></label><label>How they found you<input name="heard_about_us" value="Direct enquiry"></label><label class="full">Message<textarea name="message" rows="5"></textarea></label><input type="hidden" name="privacy_agreed" value="true"><div class="full notice">Manual enquiries are copied safely into the booking system when the integration switch is enabled.</div><div class="full actions"><button class="primary" type="submit">Save enquiry</button></div></form>`;
  document.querySelector("#back").addEventListener("click",()=>setView("enquiries"));
  document.querySelector("#lead-form").addEventListener("submit",async event=>{event.preventDefault();const raw=Object.fromEntries(new FormData(event.currentTarget));raw.privacy_agreed=true;raw.forward_to_booking=false;raw.website="";try{const lead=await api("/api/admin/leads",{method:"POST",body:JSON.stringify(raw)});toast("Enquiry saved safely");renderLead(lead.id)}catch(err){toast(err.message)}});
}

async function renderLead(id) {
  const lead = await api(`/api/admin/leads/${id}`); state.selected = lead; workspace.className="workspace";
  workspace.innerHTML=`<button class="back" id="back">← All enquiries</button><div class="page-heading"><div><h1>${esc(lead.couple_name)}</h1><p>${niceDate(lead.event_date)} · ${esc(lead.venue)}</p></div><div class="actions"><select id="lead-stage">${["new","qualified","proposal","engaged","booked","lost"].map(x=>`<option value="${x}" ${lead.stage===x?"selected":""}>${x[0].toUpperCase()+x.slice(1)}</option>`).join("")}</select></div></div>
  ${lead.booking_sync_error?`<div class="notice">The enquiry is safe here, but forwarding to the booking system needs retrying: ${esc(lead.booking_sync_error)}</div>`:""}
  <section class="detail-grid"><div><article class="detail-card"><h2>Enquiry details</h2><div class="facts"><div class="fact"><label>Email</label><span>${esc(lead.email)}</span></div><div class="fact"><label>Telephone</label><span>${esc(lead.phone||"—")}</span></div><div class="fact"><label>Availability</label><span>${esc(lead.availability)}</span></div><div class="fact"><label>Package interest</label><span>${esc(lead.package_interest||"Not selected")}</span></div><div class="fact"><label>Found you through</label><span>${esc(lead.referral_source||"Not recorded")}</span></div><div class="fact"><label>Booking sync</label><span>${esc(lead.booking_sync_status)}</span></div></div>${lead.message?`<hr><p>${esc(lead.message)}</p>`:""}</article>
  <article class="detail-card"><h2>Personal proposal</h2><div class="proposal-preview"><strong>${lead.proposal.published?"Published and ready":"Private draft"}</strong><a href="${esc(lead.proposal.url)}" target="_blank" rel="noopener">${esc(lead.proposal.url)}</a></div><form id="proposal-form" class="form-grid"><label class="full">Heading<input name="headline" value="${esc(lead.proposal.headline)}" required></label><label class="full">Introduction<textarea name="introduction" rows="4" required>${esc(lead.proposal.introduction)}</textarea></label><label class="full">Personal message<textarea name="personal_message" rows="5">${esc(lead.proposal.personal_message)}</textarea></label><div class="full actions"><button class="secondary" type="submit">Save changes</button>${lead.proposal.published?`<button class="primary" id="send-proposal" type="button">Email to couple</button>`:`<button class="primary" id="publish-proposal" type="button">Publish proposal</button>`}</div></form></article></div>
  <aside><article class="detail-card"><h2>Activity</h2><ol class="timeline">${lead.activities.length?lead.activities.map(x=>`<li><strong>${esc(x.label)}</strong><time>${niceTime(x.occurred_at)}</time></li>`).join(""):`<li><strong>No activity yet</strong></li>`}</ol></article><article class="detail-card"><h2>Prepared follow-ups</h2>${lead.automations.length?lead.automations.map(automationCard).join(""):`<p class="empty">Follow-ups are created when the proposal is published.</p>`}</article></aside></section>`;
  document.querySelector("#back").addEventListener("click",()=>setView("enquiries"));
  document.querySelector("#lead-stage").addEventListener("change",async event=>{await api(`/api/admin/leads/${id}`,{method:"PATCH",body:JSON.stringify({stage:event.target.value})});toast("Enquiry stage updated");renderLead(id)});
  document.querySelector("#proposal-form").addEventListener("submit",async event=>{event.preventDefault();await api(`/api/admin/leads/${id}/proposal`,{method:"PATCH",body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))});toast("Proposal saved")});
  document.querySelector("#publish-proposal")?.addEventListener("click",async()=>{await api(`/api/admin/leads/${id}/proposal/publish`,{method:"POST"});toast("Proposal published");renderLead(id)});
  document.querySelector("#send-proposal")?.addEventListener("click",async()=>{try{await api(`/api/admin/leads/${id}/proposal/send`,{method:"POST"});toast("Proposal emailed successfully");renderLead(id)}catch(err){toast(err.message)}});
  document.querySelectorAll("[data-approve]").forEach(button=>button.addEventListener("click",async()=>{await api(`/api/admin/automations/${button.dataset.approve}/approve`,{method:"POST"});toast("Follow-up approved");renderLead(id)}));
  document.querySelectorAll("[data-cancel]").forEach(button=>button.addEventListener("click",async()=>{if(!confirm("Cancel this follow-up? It will not be sent."))return;await api(`/api/admin/automations/${button.dataset.cancel}/cancel`,{method:"POST"});toast("Follow-up cancelled");renderLead(id)}));
  document.querySelectorAll("[data-automation-form]").forEach(form=>form.addEventListener("submit",async event=>{event.preventDefault();const raw=Object.fromEntries(new FormData(form));raw.scheduled_for=new Date(raw.scheduled_for).toISOString();await api(`/api/admin/automations/${form.dataset.automationForm}`,{method:"PATCH",body:JSON.stringify(raw)});toast("Follow-up changes saved");renderLead(id)}));
}

function automationCard(x){const editable=x.status==="scheduled";return `<section class="automation"><header><strong>${esc(x.kind.replaceAll("_"," "))}</strong><span class="status ${esc(x.status)}">${x.approved_at?"approved":x.approval_required&&editable?"needs approval":x.status}</span></header><small>${niceTime(x.scheduled_for)}</small><p>${esc(x.body)}</p>${editable?`<details><summary>Edit message or timing</summary><form class="automation-form" data-automation-form="${x.id}"><label>Subject<input name="subject" value="${esc(x.subject)}" required></label><label>Send after<input type="datetime-local" name="scheduled_for" value="${localDateTime(x.scheduled_for)}" required></label><label>Message<textarea name="body" rows="8" required>${esc(x.body)}</textarea></label><button class="secondary" type="submit">Save changes</button></form></details><footer>${x.approval_required&&!x.approved_at?`<button class="primary" data-approve="${x.id}">Approve</button>`:""}<button class="danger" data-cancel="${x.id}">Cancel</button></footer>`:""}</section>`}

async function renderFollowups(){const leads=await api("/api/admin/leads");const items=[];for(const lead of leads){if(!lead.proposal?.published)continue;const detail=await api(`/api/admin/leads/${lead.id}`);detail.automations.forEach(x=>items.push({...x,couple_name:lead.couple_name,lead_id:lead.id}))}items.sort((a,b)=>a.scheduled_for.localeCompare(b.scheduled_for));workspace.className="workspace";workspace.innerHTML=`<div class="page-heading"><div><h1>Follow-ups</h1><p>Prepared messages stay under your control.</p></div></div><article class="panel"><div class="lead-list">${items.length?items.map(x=>`<button class="lead-row" data-lead="${x.lead_id}"><div><strong>${esc(x.couple_name)}</strong><small>${esc(x.kind.replaceAll("_"," "))}</small></div><div><strong>${niceTime(x.scheduled_for)}</strong><small>${esc(x.subject)}</small></div><div></div><span class="status">${x.approved_at?"approved":x.status}</span></button>`).join(""):`<div class="empty">No follow-ups are waiting.</div>`}</div></article>`;bindLeadRows()}

async function renderVenues(){const leads=await api("/api/admin/leads");const map={};leads.forEach(x=>{const key=x.venue||"Unknown";map[key]??={venue:key,enquiries:0,bookings:0,value:0};map[key].enquiries++;if(x.stage==="booked"){map[key].bookings++;map[key].value+=x.estimated_value}});const rows=Object.values(map).sort((a,b)=>b.bookings-a.bookings||b.enquiries-a.enquiries);workspace.className="workspace";workspace.innerHTML=`<div class="page-heading"><div><h1>Venue performance</h1><p>See which venues produce enquiries and confirmed work.</p></div></div>${rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Venue</th><th>Enquiries</th><th>Bookings</th><th>Booked value</th><th>Conversion</th></tr></thead><tbody>${rows.map(x=>`<tr><td><strong>${esc(x.venue)}</strong></td><td>${x.enquiries}</td><td>${x.bookings}</td><td>${money(x.value)}</td><td>${Math.round(x.bookings/x.enquiries*100)}%</td></tr>`).join("")}</tbody></table></div>`:`<div class="panel empty">Venue results will build automatically as enquiries arrive.</div>`}`}

function packageEditor(item={code:"",name:"",price:0,description:""}){return `<article class="package-editor"><div class="package-editor-grid"><label>Short code<input name="code" value="${esc(item.code)}" pattern="[a-z0-9-]+" required></label><label>Package name<input name="name" value="${esc(item.name)}" required></label><label>Price (£)<input type="number" name="price" min="0" step="1" value="${Number(item.price||0)}" required></label><button class="danger remove-package" type="button">Remove</button><label class="full">Description<textarea name="description" rows="3" required>${esc(item.description)}</textarea></label></div></article>`}

async function renderSettings(){const data=await api("/api/admin/settings/package-catalogue");workspace.className="workspace";workspace.innerHTML=`<div class="page-heading"><div><h1>Growth Engine settings</h1><p>Manage what appears in new personal proposals.</p></div></div><div class="settings-grid"><section class="detail-card"><h2>Package catalogue</h2><p class="help-text">Published proposals are left untouched. You can safely update every unpublished draft when saving.</p><form id="catalogue-form"><div id="package-editors">${data.packages.map(packageEditor).join("")}</div><div class="catalogue-actions"><button class="secondary" id="add-package" type="button">+ Add package</button><label class="check"><input type="checkbox" id="apply-drafts" checked> Apply these packages to all unpublished drafts</label><button class="primary" type="submit">Save package catalogue</button></div></form></section><aside class="detail-card"><h2>Safety status</h2><div class="safety-list"><p><strong>Email connection</strong><span>${data.smtp_configured?"Configured":"Not configured"}</span></p><p><strong>Automatic sending</strong><span>${data.sending_enabled?"Enabled":"Off"}</span></p><p><strong>Follow-up approval</strong><span>${data.approval_required?"Required":"Not required"}</span></p></div><div class="notice">Saving packages cannot send an email. Follow-up messages remain under your approval.</div></aside></div>`;
  const editors=document.querySelector("#package-editors");
  const bindRemove=()=>document.querySelectorAll(".remove-package").forEach(button=>button.onclick=()=>{if(document.querySelectorAll(".package-editor").length===1){toast("Keep at least one package");return}button.closest(".package-editor").remove()});
  bindRemove();
  document.querySelector("#add-package").addEventListener("click",()=>{editors.insertAdjacentHTML("beforeend",packageEditor());bindRemove()});
  document.querySelector("#catalogue-form").addEventListener("submit",async event=>{event.preventDefault();const packages=[...document.querySelectorAll(".package-editor")].map(card=>({code:card.querySelector('[name="code"]').value.trim().toLowerCase(),name:card.querySelector('[name="name"]').value.trim(),price:Number(card.querySelector('[name="price"]').value),description:card.querySelector('[name="description"]').value.trim()}));try{const result=await api("/api/admin/settings/package-catalogue",{method:"PUT",body:JSON.stringify({packages,apply_to_drafts:document.querySelector("#apply-drafts").checked})});toast(`Packages saved · ${result.drafts_updated} drafts updated`);renderSettings()}catch(err){toast(err.message)}});
}

async function start(){try{const me=await api("/api/auth/me");state.csrf=me.csrf_token;document.querySelector("#admin-name").textContent=me.email.split("@")[0];document.querySelector("#loading").hidden=true;app.hidden=false;document.querySelectorAll("nav button").forEach(x=>x.addEventListener("click",()=>setView(x.dataset.view)));document.querySelector("#mobile-menu").addEventListener("click",()=>document.querySelector("#navigation").classList.toggle("open"));document.querySelector("#logout").addEventListener("click",async()=>{await api("/api/auth/logout",{method:"POST"});window.location.replace("/login")});setView(location.hash.slice(1)||"dashboard")}catch(err){if(!location.pathname.startsWith("/login"))window.location.replace("/login")}}
start();
