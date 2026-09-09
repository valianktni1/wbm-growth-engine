# V1.5.1 — Growth Admin settings

## What changed

- Added a dedicated **Admin** screen to the main navigation.
- The round profile button now opens Admin settings instead of signing out immediately.
- Added secure self-service changes for the Growth login password and login email.
- Both changes require the current Growth password.
- Changing either login detail closes other active Growth sessions and renews the current one.
- Added a plain-English view of Booking, website and Google Search connection status.
- Added a safety summary confirming that Booking owns client communications and Growth automatic sending remains off.
- Moved **Sign out of Growth** into the Admin screen.

## Safety and compatibility

Deployment does not change any existing password. Passwords are stored only as salted scrypt hashes in the Growth database. The original `ADMIN_PASSWORD` value remains the one-time account seed and is not used to overwrite an existing database account.

This is a Growth-only update and remains compatible with Booking V8.43.1. Existing Google Search, website, Booking integration and reporting data are retained.
