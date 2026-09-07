# Weddings By Mark Growth Engine

CURRENT RELEASE: V1.1.1. BookingSystem2026 is the single source of truth for packages, add-ons, quotes, contracts, invoices and client emails. Growth Engine is the read-only sales intelligence layer.

Version 1.0.1 is a standalone, self-hosted enquiry conversion application for TrueNAS SCALE and Dockge.

The intended source workflow is GitHub Desktop → `valianktni1/wbm-growth-engine` main branch → TrueNAS/Dockge. The repository can be made private after TrueNAS has pulled the required revision.

## What this first release includes

- Secure administrator sign-in and responsive desktop/mobile workspace.
- Website and manual enquiry capture.
- Privacy-safe availability checks through the existing booking system.
- Optional forwarding into the existing booking system without database access.
- Automatic booking, quote, add-on, value and stage updates from BookingSystem2026.
- Clear new enquiry, quote sent, quote accepted, booked and lost stages.
- Suggested next actions without duplicating the Booking System workflow.
- Read-only display of the package, selected add-ons, discounts, booking fee and total from the real quote.
- Venue enquiry, booking and revenue summaries.
- Daily PostgreSQL backups with checksums and retention.

## Important safety defaults

Growth Engine does not send quotes or client emails. Those remain in BookingSystem2026, preventing duplicate messages or two conflicting versions of a quote.

Do not reuse database, session or administrator passwords from another application.

See `DEPLOY-TRUENAS.md` for the deployment steps.
