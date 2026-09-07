# Safe connector activation - Growth V1.0.3 + Booking V8.37

Deploy both releases with all connector and email switches off first. Existing
private `.env` files must be preserved and must never be committed to GitHub.

## Required matching secret

Growth Engine already has a private `BOOKING_WEBHOOK_KEY`. Copy that value into
the booking system as `GROWTH_INTEGRATION_KEY`. Do not paste the value into chat
or display it in terminal output.

The booking-system settings are:

```text
GROWTH_INTEGRATION_ENABLED=false
GROWTH_INTEGRATION_AUTO_SYNC=false
GROWTH_API_URL=https://growth.weddingsbymark.uk
GROWTH_INTEGRATION_KEY=<same private value as BOOKING_WEBHOOK_KEY>
GROWTH_SYNC_MINUTES=5
GROWTH_SYNC_FROM_DATE=2026-09-07
```

Growth Engine must initially retain:

```text
BOOKING_ENQUIRY_FORWARDING=false
AUTOMATION_SEND_ENABLED=false
FOLLOWUP_APPROVAL_REQUIRED=true
```

After both updated applications report healthy, enable only
`GROWTH_INTEGRATION_ENABLED=true` in the booking system. Keep automatic sync and
Growth Engine forwarding off. Run the private connection check and transfer one
test booking. Inspect the same couple and status in both applications.

Only after that passes:

1. Set `GROWTH_INTEGRATION_AUTO_SYNC=true` in BookingSystem2026.
2. Set `BOOKING_ENQUIRY_FORWARDING=true` in Growth Engine so manually entered
   telephone, WhatsApp and social enquiries create their official booking record.
3. Keep `AUTOMATION_SEND_ENABLED=false` until proposal email content and SMTP
   have been tested separately with Mark's own address.
