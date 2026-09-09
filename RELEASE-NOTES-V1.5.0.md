# V1.5.0 — Website performance in plain English

Growth-only release on the deployed V1.4.1 / Booking V8.43.1 base. Booking source, dashboards, passwords, quotes, invoices and email sending are unchanged.

## Built

- Website performance navigation, 7/28 complete-day reports and clear connection/freshness labels.
- Measured visits, page views, first-visit sources, screen sizes, registered campaign links and same-visit enquiry counts.
- Evidence-based “Worth your attention” notes with small-sample warnings. No invented historical comparisons or booked revenue.
- A WordPress plugin for consent-controlled collection from selected public paths. No tracking requests before consent; honours GPC/DNT, excludes logged-in WordPress visitors and supports withdrawal.
- Duplicate event protection, bounded public payloads, exact origin/path checks and process-local rate limits. A public collector cannot prove human activity and must not be used as a financial ledger.
- Google Search Console service-account connection with read-only scope; key kept privately in persistent storage, never in repository/administrative JSON output.
- Separate Google totals/top lists, finalized data and explicit Pacific reporting dates. Background six-hour refresh, bounded requests and retained cached figures after upstream errors. No live Google request during dashboard rendering.
- Two new analytics tables; hourly cleanup removes website events older than 90 days. Existing business data is untouched.
- Growth-only deployment script with old-image tag, PostgreSQL backup/readability check and exact build health check.

## Still needs connection to Mark's services

Install/configure the WordPress plugin and connect the verified Search Console property. The initial screen deliberately shows “Not connected” where appropriate.

Enquiry-start, confirmed-success and date-check hooks are implemented, but must be attached to and tested against the actual website enquiry/date-check code. Generic submit clicks are never treated as success. Automatic matching to Booking IDs and booked value is not included in this release; that requires a reviewed website/Booking bridge. The screen says so explicitly.

Website visits are consenting, tab-scoped browsing sessions, not individual people. Traffic before installation cannot be reconstructed. Missing referrers, blocked scripts and consent choices leave gaps. The 28-day Google report is separate from the 7/28-day website selector.

## Validation

27 Python/API checks passed (the prior 20 plus 7 website-specific checks). The new checks cover authentication/CSRF, public origin and payload rejection, duplicate handling, first-source retention, same-visit enquiry counting, unconnected states, saved campaigns, cached Google failures, Google key sanitisation/storage permissions, separate Google totals, bounded requests and rate limits.

DOM-level JavaScript checks exercise tracker consent, withdrawal, GPC, stable visit IDs, first form interaction, rejection of submit-click-as-success, website hash navigation, disconnected report rendering and setup forms. PHP was parsed for PHP 7.4 syntax; shell and JavaScript syntax checks passed.

Real WordPress runtime, Google authorisation, Nginx/Docker deployment and mobile layout still need live checks. A Chromium download was unavailable in this workspace; DOM checks are not a full rendered-browser test. No real Google credentials, visitor data or client emails were used in testing.

See WEBSITE-SETUP.md for the complete setup and measurement definitions.
