# V1.4.0 — Plan next year's wedding business

## Longer availability planner

Fill my dates now defaults to the next 12 months, with 18-month, 24-month and custom-range options. Custom ranges support up to 732 inclusive days, including leap years, and can target a chosen month or season. Availability still comes live from Booking and is checked again before saving/copying campaigns.

## Business plan

- Year & targets: choose a wedding year, set wedding-count and agreed-value targets, and see live total/monthly figures from Booking. These cover all real confirmed/in-progress/completed WBM records, including archived and imported weddings, regardless of the enquiry sync cutoff. Cancelled/test records are excluded. Values use Booking's current quoted_total, not collected payments or profit.
- Year comparison: saves an observed snapshot when the year is viewed, including through the weekly review. A same-calendar-day snapshot from the prior wedding year is required for comparison. No historical position is fabricated from current records. Snapshots are view-triggered, not an unattended daily job.
- Enquiry journey: filter by original enquiry date, see independent recorded milestones, currently-booked conversion, open stages, and median durations from paired timestamps. Imported or missing historical events remain unknown. Resends do not replace the first recorded successful quote email. Timing samples are shown. Timings are for valid recorded pairs, not a complete event-history reconstruction.
- Review prompts: 3 days for preparing a quote or reviewing an accepted quote without a recorded fee, 7 days after the first recorded quote email, and no recorded outgoing contact within the last 3 days. Review all channels before following up. Test, archived, suppressed and terminal bookings are excluded from chase prompts.
- Venue campaigns: rank recorded venue results, retain a venue name, exact credited testimonial, up to six chosen photograph/gallery URLs and an optional destination link. Use them in an editable campaign draft with selected live-available dates and current package prices. URLs remain links to your selected material; Growth does not fetch, upload or publish photographs.
- Weekly actions: an on-demand shortlist of recorded client attention, a future month to check, chosen target progress, a relevant venue and a saved draft. It is regenerated when opened, not emailed or scheduled externally. Low booking counts prompt an availability review rather than a claim that holiday dates should be sold.

Enquiry journeys, venue performance and client prompts cover the existing Growth sync scope. Year totals and live availability bypass that cutoff by querying Booking directly. This distinction is stated in the interface.

Uses existing settings storage for targets, snapshots, venue materials and campaign materials. No new database schema or environment settings in this release. Keeps Today, What works, invoice-related integrations and campaign attribution. No password changes, posting or client email sending.

Requires paired Booking V8.42. Deployment script builds both apps, backs up databases, retains rollback image tags, verifies image build markers/health and checks both a 732-day availability response and next-year totals.

Validation: 20 Growth tests and 24 focused Booking tests passed (44 total), plus Python, JavaScript and shell syntax checks. Docker builds and browser rendering could not run in this workspace. Verify mobile/desktop layout on the deployment; the included script verifies live builds and connections on TrueNAS.
