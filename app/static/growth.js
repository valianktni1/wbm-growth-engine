const state = {csrf: "", view: "dashboard", leads: []};
const app = document.querySelector("#app");
const workspace = document.querySelector("#workspace");
const toastNode = document.querySelector("#toast");

const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const money = value => new Intl.NumberFormat("en-GB", {style:"currency", currency:"GBP", maximumFractionDigits:2}).format(Number(value || 0));
const niceDate = value => value ? new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"short", year:"numeric"}).format(new Date(`${value}T12:00:00`)) : "—";
const niceTime = value => value ? new Intl.DateTimeFormat("en-GB", {dateStyle:"medium", timeStyle:"short"}).format(new Date(value)) : "—";
const stageNames = {new:"New enquiry", qualified:"Quote sent", proposal:"Quote prepared", engaged:"Quote accepted", booked:"Booked", lost:"Lost / cancelled"};
const stageName = value => stageNames[value] || value || "Unknown";

function toast(message) {
  toastNode.textContent = message;
  toastNode.classList.add("show");
  setTimeout(() => toastNode.classList.remove("show"), 2600);
}

async function api(url, options={}) {
  const headers = {...(options.headers || {})};
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = state.csrf;
  const response = await fetch(url, {...options, headers});
  if (response.status === 401) {
    window.location.replace("/login");
    throw new Error("Please sign in");
  }
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Something went wrong");
  return data;
}

function setView(view) {
  if (view === 'dashboard') view = 'today';
  if (view === 'venues') view = 'performance';
  state.view = view;
  document.querySelectorAll("nav button").forEach(button => button.classList.toggle("active", button.dataset.view === view));
  document.querySelector("#navigation").classList.remove("open");
  if (view === "dashboard") renderDashboard();
  if (view === "enquiries") renderEnquiries();
  if (view === "venues") renderVenues();
  if (view === "today") renderToday().catch(error => toast(error.message));
  if (view === "performance") renderPerformance().catch(error => toast(error.message));
  window.location.hash = view;
  workspace.focus();
}

function leadRow(lead) {
  return `<button class="lead-row" data-lead="${lead.id}"><div><strong>${esc(lead.couple_name)}</strong><small>${niceDate(lead.event_date)}</small></div><div><strong>${esc(lead.venue)}</strong><small>${esc(lead.referral_source || "Source not recorded")}</small></div><div><strong>${esc(lead.package_interest || "Quote not prepared")}</strong><small>${money(lead.estimated_value)}</small></div><span class="status ${esc(lead.stage)}">${esc(stageName(lead.stage))}</span></button>`;
}

function bindLeadRows() {
  document.querySelectorAll("[data-lead]").forEach(row => row.addEventListener("click", () => renderLead(row.dataset.lead)));
}

async function renderDashboard() {
  workspace.innerHTML = `<div class="loading-screen"><div class="spinner"></div></div>`;
  const data = await api("/api/admin/dashboard");
  workspace.className = "workspace";
  workspace.innerHTML = `<div class="page-heading"><div><h1>Your sales overview</h1><p>Live information from the Weddings By Mark Booking System.</p></div><a class="primary button-link" href="https://booking.weddingsbymark.uk" target="_blank" rel="noopener">Open Booking System</a></div>
    <section class="metrics">
      <article class="metric"><label>Enquiries</label><strong>${data.metrics.new_enquiries}</strong><small>This month</small></article>
      <article class="metric"><label>Quotes progressing</label><strong>${data.metrics.quotes_progressing}</strong><small>Sent or accepted</small></article>
      <article class="metric"><label>Bookings</label><strong>${data.metrics.bookings}</strong><small>This month</small></article>
      <article class="metric"><label>Booked value</label><strong>${money(data.metrics.booked_value)}</strong><small>This month</small></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel"><header><h2>Enquiries needing attention</h2><span>Most important first</span></header><div class="lead-list">${data.hot_leads.length ? data.hot_leads.map(leadRow).join("") : `<div class="empty">Nothing currently needs attention.</div>`}</div></article>
      <aside class="panel"><header><h2>Suggested actions</h2></header><div class="action-list">${data.actions.map(item => `<div class="action-item"><strong>${item.count} ${esc(item.label)}</strong><p>${item.kind === "accepted" ? "Look out for their booking fee and confirm it promptly in Booking." : "Prepare and send their quote from the Booking System."}</p></div>`).join("")}<div class="action-item"><strong>One connected workflow</strong><p>Packages, add-ons, quotes and emails are controlled only in Booking.</p></div></div></aside>
    </section>`;
  bindLeadRows();
}

async function renderEnquiries() {
  state.leads = await api("/api/admin/leads");
  workspace.className = "workspace";
  workspace.innerHTML = `<div class="page-heading"><div><h1>Enquiries and bookings</h1><p>Read-only sales progress received automatically from Booking.</p></div><a class="primary button-link" href="https://booking.weddingsbymark.uk" target="_blank" rel="noopener">Add or edit in Booking</a></div>
    <div class="toolbar"><input id="lead-search" type="search" placeholder="Search couple, venue or package"><select id="stage-filter"><option value="">All stages</option>${Object.entries(stageNames).map(([value,label]) => `<option value="${value}">${esc(label)}</option>`).join("")}</select></div><div id="lead-table"></div>`;
  const draw = () => {
    const query = document.querySelector("#lead-search").value.toLowerCase();
    const stage = document.querySelector("#stage-filter").value;
    const rows = state.leads.filter(item => (!stage || item.stage === stage) && (!query || `${item.couple_name} ${item.venue} ${item.email} ${item.package_interest || ""}`.toLowerCase().includes(query)));
    document.querySelector("#lead-table").innerHTML = rows.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Couple</th><th>Wedding</th><th>Venue</th><th>Quote</th><th>Stage</th></tr></thead><tbody>${rows.map(item => `<tr data-lead="${item.id}"><td><strong>${esc(item.couple_name)}</strong><br><small>${esc(item.email)}</small></td><td>${niceDate(item.event_date)}</td><td>${esc(item.venue)}</td><td>${esc(item.package_interest || "Not prepared")}<br><small>${money(item.estimated_value)}</small></td><td><span class="status ${esc(item.stage)}">${esc(stageName(item.stage))}</span></td></tr>`).join("")}</tbody></table></div>` : `<div class="panel empty">No records match this view.</div>`;
    bindLeadRows();
  };
  draw();
  document.querySelector("#lead-search").addEventListener("input", draw);
  document.querySelector("#stage-filter").addEventListener("change", draw);
}

function guidance(lead) {
  if (lead.stage === "new") return ["Prepare their quote", "Open this couple in Booking, choose the package and any add-ons, then send the normal quote from there."];
  if (lead.stage === "qualified" || lead.stage === "proposal") return ["Quote is with the couple", "No second proposal is needed. Growth will update automatically when they accept it."];
  if (lead.stage === "engaged") return ["Quote accepted", "Look out for the booking fee. Confirm the payment in Booking as soon as it arrives."];
  if (lead.stage === "booked") return ["Booking confirmed", "No sales follow-up is needed. Continue managing the wedding through Booking."];
  return ["Record closed", "This record is retained for conversion and venue reporting."];
}

function quoteLine(item) {
  const type = item.type === "addon" ? (item.required ? "Required add-on" : "Add-on") : item.type === "discount" ? "Discount" : "Package";
  return `<div class="quote-line"><span><strong>${esc(item.name)}</strong><small>${esc(type)}</small></span><b>${money(item.total)}</b></div>`;
}

async function renderLead(id) {
  const lead = await api(`/api/admin/leads/${id}`);
  const advice = guidance(lead);
  const lines = lead.quote_items || [];
  workspace.className = "workspace";
  workspace.innerHTML = `<button class="back" id="back">← All enquiries</button><div class="page-heading"><div><h1>${esc(lead.couple_name)}</h1><p>${niceDate(lead.event_date)} · ${esc(lead.venue)}</p></div><span class="status ${esc(lead.stage)} large-status">${esc(stageName(lead.stage))}</span></div>
    <section class="detail-grid"><div>
      <article class="detail-card"><h2>Enquiry details</h2><div class="facts"><div class="fact"><label>Email</label><span>${esc(lead.email)}</span></div><div class="fact"><label>Telephone</label><span>${esc(lead.phone || "—")}</span></div><div class="fact"><label>Wedding date</label><span>${niceDate(lead.event_date)}</span></div><div class="fact"><label>Venue</label><span>${esc(lead.venue)}</span></div><div class="fact"><label>Found you through</label><span>${esc(lead.referral_source || "Not recorded")}</span></div><div class="fact"><label>Connection</label><span>Synced from Booking</span></div></div>${lead.message ? `<hr><p>${esc(lead.message)}</p>` : ""}</article>
      <article class="detail-card"><div class="card-heading"><div><h2>Quote from Booking System</h2><p>Booking remains the master copy.</p></div><a class="secondary button-link" href="${esc(lead.booking_record_url)}" target="_blank" rel="noopener">Open Booking</a></div>${lines.length ? `<div class="quote-lines">${lines.map(quoteLine).join("")}</div>` : `<div class="empty compact">No quote line-items have synced yet. Once the Booking connector update is installed, the selected package and add-ons will appear here.</div>`}<div class="quote-summary"><span><small>Package</small><strong>${esc(lead.package_interest || "Not selected")}</strong></span><span><small>Booking fee</small><strong>${money(lead.deposit_amount)}</strong></span><span><small>Quote total</small><strong>${money(lead.estimated_value)}</strong></span></div><div class="notice">To add, remove or price an add-on, edit the quote in the Booking System. Growth will update automatically.</div></article>
    </div><aside><article class="detail-card guidance"><small>WHAT NEEDS ATTENTION</small><h2>${esc(advice[0])}</h2><p>${esc(advice[1])}</p><a class="primary button-link wide" href="${esc(lead.booking_record_url)}" target="_blank" rel="noopener">Continue in Booking</a></article><article class="detail-card"><h2>Activity</h2><ol class="timeline">${lead.activities.length ? lead.activities.map(item => `<li><strong>${esc(item.label)}</strong><time>${niceTime(item.occurred_at)}</time></li>`).join("") : `<li><strong>No activity yet</strong></li>`}</ol></article></aside></section>`;
  document.querySelector("#back").addEventListener("click", () => setView("enquiries"));
}

async function renderVenues() {
  const leads = await api("/api/admin/leads");
  const map = {};
  leads.forEach(item => {
    const key = item.venue || "Unknown";
    map[key] ??= {venue:key, enquiries:0, bookings:0, value:0};
    map[key].enquiries += 1;
    if (item.stage === "booked") {
      map[key].bookings += 1;
      map[key].value += item.estimated_value;
    }
  });
  const rows = Object.values(map).sort((a,b) => b.bookings - a.bookings || b.enquiries - a.enquiries);
  workspace.className = "workspace";
  workspace.innerHTML = `<div class="page-heading"><div><h1>Venue performance</h1><p>See which venues produce enquiries and confirmed work.</p></div></div>${rows.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Venue</th><th>Enquiries</th><th>Bookings</th><th>Booked value</th><th>Conversion</th></tr></thead><tbody>${rows.map(item => `<tr><td><strong>${esc(item.venue)}</strong></td><td>${item.enquiries}</td><td>${item.bookings}</td><td>${money(item.value)}</td><td>${Math.round(item.bookings / item.enquiries * 100)}%</td></tr>`).join("")}</tbody></table></div>` : `<div class="panel empty">Venue results will build automatically as enquiries arrive.</div>`}`;
}

async function start() {
  try {
    const me = await api("/api/auth/me");
    state.csrf = me.csrf_token;
    document.querySelector("#admin-name").textContent = me.email.split("@")[0];
    document.querySelector("#loading").hidden = true;
    app.hidden = false;
    document.querySelectorAll("nav button").forEach(button => button.addEventListener("click", () => setView(button.dataset.view)));
    document.querySelector("#mobile-menu").addEventListener("click", () => document.querySelector("#navigation").classList.toggle("open"));
    document.querySelector("#logout").addEventListener("click", async () => {await api("/api/auth/logout", {method:"POST"}); window.location.replace("/login");});
    const requested = location.hash.slice(1);
    setView(["dashboard", "enquiries", "venues", "today", "performance"].includes(requested) ? requested : "today");
  } catch (error) {
    if (!location.pathname.startsWith("/login")) window.location.replace("/login");
  }
}

window.addEventListener('DOMContentLoaded', start, {once: true});
