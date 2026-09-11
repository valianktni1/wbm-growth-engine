# Website performance — setup guide

V1.6 connects the website report to Booking V8.47. No extra Docker service or new dataset is needed. It uses the existing Growth database and storage dataset. It does not change WordPress until you install the updated plugin and replace the two supplied website code blocks.

## 1. Deploy Growth

Copy the contents of the wbm-growth-engine folder into your existing Growth GitHub Desktop repository. Commit and push main. Keep your private live .env and Dockge compose.yaml.

On TrueNAS:

```bash
cd /mnt/apps/dockge/data/wbm-growth-engine
sudo git pull --ff-only origin main &&
sudo bash scripts/deploy-v160-growth.sh
```

The script builds first, tags the old Growth image, creates a readable PostgreSQL backup, updates only the Growth app, and checks its exact build. Readable backup verification is not a complete restore rehearsal. New nullable attribution fields are added at startup. Deploy Booking V8.47 after Growth is healthy.

## 2. Connect website visits

1. Open Growth → Website performance → Connect & manage.
2. Review the friendly names for important page paths. All safe public WordPress marketing paths are collected automatically after consent; this list controls the friendly labels and tracked-link destinations. Private, login, admin and client paths remain blocked.
3. Tick “Enable collection” and save. Leave the form-hooks checkbox unticked for now.
4. In WordPress → Plugins → Add New → Upload Plugin, upload `wbm-website-insights-v1.1.0.zip`, choose **Replace current with uploaded**, then activate it.
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

Booking V8.47 and plugin V1.1.0 now provide the checked cross-origin bridge for the actual enquiry iframe. Replace the Contact-page HTML widget with `wordpress/CONTACT-ENQUIRY-EMBED-V1.6.html`. An enquiry start is counted on first form interaction and success only after Booking confirms creation.

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

Replace the homepage date-checker widget with `wordpress/HOMEPAGE-DATE-CHECKER-V1.6.html`. It records one date-check event only after the diary request completes successfully and never sends the selected date.

Once both blocks are installed, test one date check and one test-mode enquiry after choosing Allow, then tick Growth's verified-hooks checkbox.

The visit is matched through a random consented ID, never by the couple's email address. Growth verifies the visit against its own hashed record, source, campaign and landing-page event before linking it. Invalid/stale details are ignored without blocking the Booking sync. Test-mode Booking records are excluded.

## 5. Use it day to day

- Look at the “Worth your attention” notes first.
- Measured visits are 30-minute-inactivity browsing sessions within a tab; they are not identified individual people. Additional tabs, consent choices, private windows and blockers affect coverage.
- Enquiry counts mean visits with a recorded success event, not unique couples or confirmed weddings. Starts and completions are joined within the same measured visit.
- Use the tracked-link generator before posting on Facebook or Instagram. Campaign names stay in Growth; the link contains a generated campaign code. Results are source-labelled observations, not proof of causal lift.
- A source is fixed when a visit begins. An existing visit clicking another campaign will keep its original source until the session expires.
- The comparison requires a full previous period since collection was enabled. No difference is invented from missing history. You still need to check the “Last activity received” indicator for outages.
- Safe public WordPress paths are collected after consent; private/admin/client paths, query strings, full referrer URLs, form content, requested dates, IPs and email addresses are not stored in these analytics tables. Ordinary proxy/server logs are separate.
- Website events are removed after 90 days by hourly maintenance. Consent preference is stored in local storage; visit IDs live in session storage. Withdrawing stops future collection and clears that browser's session ID; it does not retroactively delete already-recorded events.

References: [Search Console query API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query), [Google service-account credentials](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.service_account.html), [ICO storage/access guidance](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guidance-on-the-use-of-storage-and-access-technologies/).
