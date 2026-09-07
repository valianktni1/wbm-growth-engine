# Weddings By Mark Growth Engine

CURRENT RELEASE: V1.0.2, setup testing only. Read SETUP-STATUS-V1.0.2.md first; it corrects the scope and supersedes earlier deployment/feature claims. Leave sending and forwarding disabled.

Version 1.0.1 is a standalone, self-hosted enquiry conversion application for TrueNAS SCALE and Dockge.

The intended source workflow is GitHub Desktop → `valianktni1/wbm-growth-engine` main branch → TrueNAS/Dockge. The repository can be made private after TrueNAS has pulled the required revision.

## What this first release includes

- Secure administrator sign-in and responsive desktop/mobile workspace.
- Website and manual enquiry capture.
- Privacy-safe availability checks through the existing booking system.
- Optional forwarding into the existing booking system without database access.
- Automatic private proposal drafts for every enquiry.
- Personal proposal publishing and email delivery.
- First-party proposal activity: opens, package interest, film plays and booking clicks.
- New, qualified, proposal, engaged, booked and lost enquiry stages.
- Prepared 24-hour, three-day and expiry follow-ups.
- Approval-required follow-up mode by default.
- Venue enquiry, booking and revenue summaries.
- Daily PostgreSQL backups with checksums and retention.

## Important safety defaults

The initial deployment does not automatically send follow-ups and does not forward website enquiries to the booking system. Both switches remain off until the full test journey is verified.

Do not reuse database, session or administrator passwords from another application.

See `DEPLOY-TRUENAS.md` for the deployment steps.
