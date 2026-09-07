# Growth Engine V1.1.1 – Booking-owned sales intelligence

This corrective release supersedes V1.1.0.

- Removes the duplicate package catalogue, proposal and follow-up workflow from the Growth Engine interface.
- Makes BookingSystem2026 the only place that owns packages, available add-ons, quotes, contracts, invoices and client emails.
- Displays the package, selected add-ons, required extras, discounts, booking fee and quote total received from BookingSystem2026.
- Adds clear prompts for new enquiries, sent quotes, accepted quotes awaiting payment and confirmed bookings.
- Makes enquiry stages read-only in Growth; stage changes arrive automatically from Booking.
- Disables Growth Engine client-email processing in code as an additional safety measure.
- Preserves historic proposal records in the database, but does not create new ones or expose that old workflow in the interface.
- Adds a safe automatic schema update for the new quote detail fields.

This release requires the paired BookingSystem2026 V8.38 connector so quote line-items can be sent to Growth.
