# V1.0.2 — setup testing only

Replace the files in your local GitHub Desktop repository with this archive's contents, commit and push main. Do not delete .git or overwrite a local .env. Then pull the revision onto TrueNAS before initial configuration.

Corrected: fabricated testimonial defaults removed; admin-login link removed from couples' pages; availability checked when viewing a proposal; unavailable dates no longer announced as brilliant news; expiry and follow-ups start after email delivery, not publishing; setup sending switch now blocks manual proposal email as well; repeated sends rejected; enquiries committed before external forwarding.

This is an initial testing build, not the complete automated product described in the brainstorm. The existing booking application has not been modified to send webhooks. Website submissions and payment/status changes therefore do not automatically arrive here yet. Do not replace the website form or enable sending/forwarding until that integration is implemented and tested against the deployed booking version. A package button currently opens an email enquiry; it does not accept a quote or create an invoice. Booked status is manual, so automatic follow-ups must remain off for live couples.

Media upload/editor, review management, TOTP, complete file backups, recovery verification, reliable delivery retries and comprehensive browser/Docker testing remain outstanding. Daily database dumps are implemented; complete uploaded-file backups are not. Five tests and syntax checks are limited verification, not proof of production readiness.

For initial deployment keep BOOKING_ENQUIRY_FORWARDING=false and AUTOMATION_SEND_ENABLED=false. No real client details should be used during setup testing.
