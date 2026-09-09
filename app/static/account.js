function connectionStatus(connected) {
  return `<span class="connection-state ${connected ? 'connected' : ''}">${connected ? 'Connected' : 'Not connected'}</span>`;
}

async function renderAdmin() {
  const data = await api('/api/admin/account');
  workspace.className = 'workspace';
  workspace.innerHTML = `<div class="page-heading"><div><small class="eyebrow">ADMINISTRATION</small><h1>Admin settings</h1><p>Manage your Growth login and see the important connection safeguards.</p></div></div>
    <div class="admin-grid"><div>
      <section class="detail-card"><h2>Change Growth password</h2><p class="help-text">This changes only the password used to sign in to Growth. It does not change Booking, WordPress, Google, TrueNAS or email passwords.</p>
        <form id="password-form" class="form-grid" autocomplete="off">
          <label class="full">Current password<input name="current_password" type="password" autocomplete="current-password" required minlength="8" maxlength="200"></label>
          <label>New password<input name="new_password" type="password" autocomplete="new-password" required minlength="12" maxlength="200"></label>
          <label>Confirm new password<input name="confirm_password" type="password" autocomplete="new-password" required minlength="12" maxlength="200"></label>
          <p class="full muted">Use at least 12 characters. Other signed-in Growth sessions will be closed.</p>
          <div class="full actions"><button class="primary" type="submit">Change Growth password</button></div>
        </form></section>
      <section class="detail-card"><h2>Login email</h2><p class="help-text">Your current Growth login is <strong>${esc(data.email)}</strong>.</p>
        <form id="email-form" class="form-grid" autocomplete="off">
          <label>New login email<input name="new_email" type="email" autocomplete="email" required value="${esc(data.email)}"></label>
          <label>Current password<input name="current_password" type="password" autocomplete="current-password" required minlength="8" maxlength="200"></label>
          <div class="full actions"><button class="secondary" type="submit">Change login email</button></div>
        </form></section>
    </div><aside>
      <section class="detail-card"><h2>Connections</h2><div class="safety-list">
        <p><strong>Booking System</strong>${connectionStatus(data.connections.booking)}</p>
        <p><strong>Website insights</strong>${connectionStatus(data.connections.website)}</p>
        <p><strong>Google Search</strong>${connectionStatus(data.connections.google)}</p>
      </div></section>
      <section class="detail-card"><h2>Safety controls</h2><div class="safety-list">
        <p><strong>Client emails</strong><span>${esc(data.safety.client_communications_owner)}</span></p>
        <p><strong>Automatic sending</strong><span>${data.safety.automatic_email ? 'On' : 'Off'}</span></p>
        <p><strong>Follow-up approval</strong><span>${data.safety.followup_approval ? 'Required' : 'Not required'}</span></p>
        <p><strong>Sign-in duration</strong><span>${data.session_hours} hours</span></p>
      </div><div class="notice">Changing your Growth login cannot alter any Booking System or email credentials.</div></section>
      <section class="detail-card"><h2>Application</h2><p class="muted admin-build">${esc(data.build)}</p><button class="danger wide" id="admin-logout" type="button">Sign out of Growth</button></section>
    </aside></div>`;

  document.querySelector('#password-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    if (values.new_password !== values.confirm_password) { toast('The two new passwords do not match'); return; }
    const button = form.querySelector('button'); button.disabled = true;
    try {
      const result = await api('/api/admin/account/password', {method:'PUT', body:JSON.stringify(values)});
      state.csrf = result.csrf_token; form.reset(); toast(result.message);
    } catch (error) { toast(error.message); } finally { button.disabled = false; }
  });
  document.querySelector('#email-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget, button = form.querySelector('button'); button.disabled = true;
    try {
      const result = await api('/api/admin/account/email', {method:'PUT', body:JSON.stringify(Object.fromEntries(new FormData(form)))});
      state.csrf = result.csrf_token;
      document.querySelector('#admin-name').textContent = result.email.split('@')[0];
      toast(result.message); await renderAdmin();
    } catch (error) { toast(error.message); } finally { button.disabled = false; }
  });
  document.querySelector('#admin-logout').addEventListener('click', async () => {
    await api('/api/auth/logout', {method:'POST'}); window.location.replace('/login');
  });
}
