# Website performance — setup guide

This release adds the reporting section to Growth. No Booking update, extra Docker service or new dataset is needed. It uses the existing Growth database and storage dataset. It does not change your website until you install and enable the WordPress plugin.

## 1. Deploy Growth

Copy the contents of the wbm-growth-engine folder into your existing Growth GitHub Desktop repository. Commit and push main. Keep your private live .env and Dockge compose.yaml.

On TrueNAS:

```bash
cd /mnt/apps/dockge/data/wbm-growth-engine
sudo git pull --ff-only origin main &&
sudo bash scripts/deploy-v150-growth.sh
```

The script builds first, tags the old Growth image, creates a readable PostgreSQL backup, updates only the Growth app, and checks its exact build. Readable backup verification is not a complete restore rehearsal. The two analytics tables are added at startup. Booking V8.43.1 remains deployed.

## 2. Connect website visits

1. Open Growth → Website performance → Connect & manage.
2. Review the selected public page paths. Home, /packages/ and /contact/ are prefilled from the site's public links. Add other public marketing pages as `path | friendly name`. Paths must match exactly, including trailing slashes.
3. Tick “Enable collection” and save. Leave the form-hooks checkbox unticked for now.
4. In WordPress → Plugins → Add New → Upload Plugin, upload `wbm-website-insights.zip`, then activate it.
5. In WordPress → Settings → WBM Website Insights, enter `https://growth.weddingsbymark.uk` and the public Website code from Growth. This is NOT the Booking integration key.
6. Choose how visitors give their analytics choice. The plugin includes an Allow / No thanks prompt and a persistent withdrawal button. If an existing cookie banner is used, connect its analytics-consent and withdrawal callbacks before disabling the plugin's prompt. Do not run two competing prompts. Collection remains off without an explicit consent signal.
7. Add accurate analytics information to the website's privacy notice, then enable the plugin's collection setting. This implementation deliberately opts in; it does not assume a legal analytics exemption.
8. Clear the WordPress/Hostinger page cache, so pages include the new plugin script.
9. Test in a private browser window while signed OUT of WordPress. Visit a measured page, choose Allow, and check “Last activity received” in Growth. The main report uses complete days, so today's visits appear in tomorrow's report. Decline or withdraw and verify that no further event requests are made.

The website code is intentionally public. Origin/path checks, size limits, rate limits and duplicate-event IDs reduce accidental/abusive events; this is not cryptographic proof that a visitor is human. Do not use the figures for billing or exact financial reconciliation.

## 3. Connect Google Search Console

This uses a separate read-only service account so it does not interfere with Booking's Google Calendar connection.

1. In Google Cloud Console, choose/create a project for Growth and enable **Google Search Console API**.
2. Create a dedicated service account. It does not need project-owner or broad project roles for this integration. Create/download a JSON key for that account. Keep the file private.
3. In Search Console, open the existing perfectweddingsbymark.uk property → Settings → Users and permissions. Add the service-account email from that JSON file with access to the property. You need permission to manage property users. The app requests only the `webmasters.readonly` scope, even if the property permission grants fuller viewing access.
4. In Growth's Google Search connection form, choose the exact existing property: Domain (`sc-domain:perfectweddingsbymark.uk`) or the matching HTTPS URL-prefix property. These are different properties; choose the one that is actually verified.
5. Upload the JSON file directly in Growth while signed in over HTTPS. Do not upload it to GitHub or send it in chat.
6. Save. Growth checks access in the background; use “Refresh this screen” shortly afterward. If access fails, the screen explains what to check and preserves any previous report.

The key is kept in the existing storage dataset as `website-search-console.json`, mode 600. Include that private storage dataset in your existing protected backups; a PostgreSQL dump alone does not include this key. Disconnect deletes the active local key and cached Google report, but does not revoke the key in Google Cloud or remove old backup copies.

Google refresh runs roughly every six hours while Growth is running; manual refresh is rate-limited to one attempt per minute. Reports cover 28 days ending three days ago, using Google's Pacific reporting dates and finalized data. Website reports use UK dates, so totals are intentionally not combined. Google totals are queried separately from its partial top-query/page lists. No live Google request runs on a dashboard GET.

## 4. Connect enquiry starts, confirmed submissions and date checks

**This requires checking the actual website form/date-check code.** The public site confirms those controls exist, but does not establish which submission callback is authoritative. Do not guess based on a click or a visible thank-you message.

The plugin exposes these browser hooks, and ignores them until consent is granted and Growth's verified-hooks option is enabled:

```javascript
// First interaction with the actual enquiry form (no field values).
window.wbmWebsiteEvent?.('enquiry_start');

// Only after the enquiry API has positively acknowledged successful creation.
window.wbmWebsiteEvent?.('enquiry_success');

// Only after a date-check request has completed successfully (no date is sent).
window.wbmWebsiteEvent?.('date_check');

// If using the site's existing consent banner:
window.wbmAnalyticsConsent?.(true);  // analytics granted
window.wbmAnalyticsConsent?.(false); // analytics declined or withdrawn
```

An optional form selector records first focus. A matching Contact Form 7 `wpcf7mailsent` event is supported; do not configure it unless that is the actual enquiry form. Generic form submissions, validation errors, failed API responses and button clicks must not count as success. Cross-origin embedded Booking forms need a specific consent-aware bridge; the parent plugin cannot inspect them automatically. Provide the latest website/form source for that part.

Once connected, test success, validation failure, server failure, double clicks and consent withdrawal before ticking Growth's verified-hooks checkbox.

**Automatic matching to Booking IDs and agreed booking value is not part of V1.5.0.** The screen labels this honestly and links to the existing Booking performance report. That bridge needs a separately reviewed change to the website enquiry route and Booking payload; no matching by email address is attempted here.

## 5. Use it day to day

- Look at the “Worth your attention” notes first.
- Measured visits are 30-minute-inactivity browsing sessions within a tab; they are not identified individual people. Additional tabs, consent choices, private windows and blockers affect coverage.
- Enquiry counts mean visits with a recorded success event, not unique couples or confirmed weddings. Starts and completions are joined within the same measured visit.
- Use the tracked-link generator before posting on Facebook or Instagram. Campaign names stay in Growth; the link contains a generated campaign code. Results are source-labelled observations, not proof of causal lift.
- A source is fixed when a visit begins. An existing visit clicking another campaign will keep its original source until the session expires.
- The comparison requires a full previous period since collection was enabled. No difference is invented from missing history. You still need to check the “Last activity received” indicator for outages.
- Only allowlisted public paths are collected; query strings, full referrer URLs, form content, requested dates, IPs and email addresses are not stored in these analytics tables. Ordinary proxy/server logs are separate.
- Website events are removed after 90 days by hourly maintenance. Consent preference is stored in local storage; visit IDs live in session storage. Withdrawing stops future collection and clears that browser's session ID; it does not retroactively delete already-recorded events.

References: [Search Console query API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query), [Google service-account credentials](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.service_account.html), [ICO storage/access guidance](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guidance-on-the-use-of-storage-and-access-technologies/).
