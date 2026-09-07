# Weddings By Mark Growth Engine V1.2.0

Build: 2026.09.07-today-and-performance-v1.2.0
Paired with BookingSystem2026 V8.39.

Start with Today for attention cards and What works for enquiry-source, venue,
package and add-on performance. Enquiries opens the synced booking records.
Booking owns all quotes, packages, add-ons, contracts, invoices and client emails.
Growth does not send emails or create competing proposals.

Read RELEASE-NOTES-V1.2.0.md for features and mailbox/reporting coverage.
After pushing both source repositories, update Growth with git pull --ff-only
and run sudo bash scripts/deploy-v120-paired.sh from its Dockge stack directory.
The script preserves the existing Compose configuration and credentials, builds
both images, backs up both databases, verifies versioned health and synchronises.

No new datasets or manually configured credentials are needed.
