# Growth V1.2.0 — Today and What works

Paired with BookingSystem2026 V8.39. Deploy the paired update once, using scripts/deploy-v120-paired.sh after pushing both repositories.

## Today

- Prioritises incoming messages, accepted quotes needing a booking-fee check, new enquiries, recent quote-link activity and quotes waiting three days since recorded outgoing contact.
- Excludes confirmed, cancelled, test, archived, past-event and automation-suppressed records from sales prompts.
- Shows the recorded dates behind each card, including mailbox coverage and stale sync evidence.
- Editable suggested replies for appropriate stages use names, venue and stage. These are templates, not AI interpretations of message bodies. Copy and review them in Booking before sending. Reply-review cards deliberately do not guess a response without the conversation body.
- Snooze for 24 hours; restore snoozed cards any time.
- Direct links to Booking Journey, Activity or Payments.

## What works

- Original-enquiry-date filters; source, venue, package and selected add-on comparisons.
- Enquiries, confirmed bookings, conversion, booked value and average booking value.
- Excludes test and archived records. Cancelled records remain in the conversion denominator but contribute no booked value.
- Groups below 10 enquiries are marked as small samples. Package association does not prove causation. Missing sources remain visible.
- Add-on value uses selected line totals on confirmed bookings, counts each booking once per named add-on and excludes discounts.
- All reports cover only the configured Booking sync range, not the entire historical business. Booked value is agreed work, not collected payments or profit.

## Mail evidence and safety

The connector makes one read-only scan of the latest 200 WBM inbox headers per sync. Only main-address matches and timestamps are used; message bodies and attachments are not transferred and messages are not marked read. Archived mail, secondary addresses, externally sent mail, WhatsApp and phone calls may be missing. Mail failure is shown as unavailable; it is never proof that a couple has not replied. Quote-link access can include automated scanners.

Booking continues to own all packages, add-ons, quotes, contracts, invoices and emails. No credentials or send switches are changed. New evidence tables are created automatically; existing quote records are preserved. The paired deployment script validates database dump headers and preserves old image tags before replacing app containers.
