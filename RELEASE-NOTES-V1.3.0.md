# V1.3.0 — Fill my empty dates

New Fill my dates tab:
- Live three- or six-month availability from Booking, with weekend, weekday and all-day filters.
- Confirmed, in-progress and completed WBM weddings protect their dates, including archived/imported records and confirmed records awaiting payment entry. Non-deleted holiday blocks protect inclusive date ranges. Testing records and cancelled weddings do not block dates.
- Up to 12 dates per campaign; matching eligible synced enquiries link to Booking's conversation history.
- Editable Facebook and Google Business Profile draft wording, with an optional current Booking package price and the Booking enquiry link. No price discounts or duplicate catalogue.
- Save/edit private campaigns, check dates and package price before copying, and manually mark a post as published.
- Explicitly attribute enquiries to campaigns and see synced confirmed booking counts and agreed value. Remove a mistaken attribution. One enquiry belongs to at most one campaign.

Nothing is posted or emailed by this feature. Mark reviews and posts drafts in the chosen platform. Campaign attribution is manual; this release does not claim automatic UTM, clicks, reach or advertising-spend tracking. Existing Booking emails and automations are unchanged.

Availability is unknown if Booking is unreachable, returns incomplete dates or returns evidence older than five minutes. Current availability is checked when loading dates, generating/saving a draft, and copying a saved campaign. Previously copied posts can become outdated after a later booking. Calendar events absent from Booking are outside this check. Enquiry matching and conversion totals cover the configured Booking sync range; direct availability covers all Booking dates in the requested period.

Requires Booking V8.41 with the existing shared integration key. Uses the current Booking package catalogue: any price changes must be saved in Booking to appear here. No environment, password or deployment configuration changes.

Adds campaigns and campaign_attributions tables automatically; existing tables and historical proposals remain intact. Includes all V1.2.0 Today and What works features.

Validation: 15 Growth tests and 22 focused Booking tests passed in their supported isolated test runs. Python compilation, JavaScript and deployment-shell syntax checks passed. Browser layout and Docker builds could not be executed in this workspace; the deployment script validates image versions, health and the live integration on TrueNAS.
