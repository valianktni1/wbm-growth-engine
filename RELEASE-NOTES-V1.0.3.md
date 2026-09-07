# Growth Engine V1.0.3 - two-way booking connector

- Receives authenticated booking snapshots and updates an existing lead rather
  than creating duplicates.
- Maps enquiry, quote, accepted quote, confirmed booking and cancellation state
  into the Growth Engine journey.
- Cancels scheduled sales follow-ups immediately when a booking is confirmed or
  lost/cancelled.
- Sends manually entered telephone, WhatsApp or social enquiries to the new
  private booking-system integration route when forwarding is enabled.
- Removes the confusing per-enquiry forwarding checkbox; the integration has
  one deliberate environment switch.
- Labels administrator-created leads as `Manual enquiry added`.
- Fixes the dashboard loading overlay and refreshes static asset versions.
- Writes portable relative filenames into database dump checksum files.
- Sending, automatic sync and manual-enquiry forwarding remain off until the
  connection tests have passed.
