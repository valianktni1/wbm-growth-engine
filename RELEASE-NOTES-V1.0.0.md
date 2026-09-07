# Growth Engine V1.0.0

## Outcome

This is the first deployable foundation of the Weddings By Mark Growth Engine. It adds a separate enquiry-conversion workspace without changing the live booking application.

## Included

- Responsive administrator dashboard and enquiry workspace.
- Secure signed sessions, CSRF protection and sign-in throttling.
- Independent PostgreSQL data store.
- Privacy-safe availability lookup through the existing booking application.
- Manual and public enquiry endpoints.
- Authenticated, duplicate-safe booking-system webhook endpoint.
- Optional safe forwarding to the booking application's existing enquiry endpoint.
- Automatic private proposal draft for each enquiry.
- Proposal editing, publishing and direct email action.
- Responsive personalised couple proposal page.
- First-party proposal open, package, film, consultation and booking-click events.
- Prepared 24-hour, three-day and expiry follow-ups.
- Approval-required automation by default.
- Venue enquiry, conversion and booked-value summary.
- Daily custom-format PostgreSQL backups and SHA-256 checksums.
- Read-only application container, dropped Linux capabilities and security headers.

## Verification

- Five automated journey/security tests passed.
- Python files passed bytecode compilation.
- Administrator, login and proposal JavaScript passed syntax validation.
- Backup shell script passed syntax validation.
- Compose YAML passed structural parsing.

## Not switched on automatically

No real couple emails are sent and no live booking enquiries are forwarded until Mark completes the documented test journey and deliberately enables those settings.

