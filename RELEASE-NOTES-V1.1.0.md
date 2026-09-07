# Growth Engine V1.1.0 – package and follow-up controls

- Adds a Growth Engine Settings screen for managing the proposal package catalogue.
- Includes the current Weddings By Mark catalogue:
  - Half Day Photography – £475
  - Silver – £699
  - Gold – £899
  - Platinum – £1,350
  - Ultimate – £1,799
- Lets Mark apply catalogue changes to every unpublished proposal draft in one safe action.
- Never changes a proposal that has already been published to a couple.
- Lets scheduled follow-ups be edited, approved or cancelled from the enquiry screen.
- Automatically removes approval when an approved message or its timing is edited, requiring it to be checked again.
- Shows SMTP, automatic-send and approval safety status on the Settings screen.
- Automatic email sending remains off and this release does not alter any credentials.

No database migration command is required. The existing `settings` table stores the catalogue and is created automatically on first startup.
