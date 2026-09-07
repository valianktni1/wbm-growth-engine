# GitHub, TrueNAS and Dockge deployment

V1.0.3 includes the paired BookingSystem2026 V8.37 connector. Keep sending,
automatic booking sync and manual-enquiry forwarding off until the connection
and one test record have been verified.

## Create the GitHub repository

1. Extract the complete Growth Engine ZIP on the computer running GitHub Desktop.
2. In GitHub Desktop, create/add a repository from the extracted `growth-engine` folder.
3. Use repository name `wbm-growth-engine`.
4. Confirm `.env` is not listed among the files to commit. Only `.env.example` should be present.
5. Commit the complete initial application and publish it to `valianktni1/wbm-growth-engine`.
6. Keep it public only while TrueNAS needs to clone or pull it.

## Datasets

Create these two datasets:

- `/mnt/apps/wbm-growth-engine`
- `/mnt/weddings_backups/wbm-growth-engine`

The Dockge stack itself belongs at `/mnt/apps/dockge/data/wbm-growth-engine` and is cloned directly from GitHub.

## Prepare the live-data folders

Run these commands in the TrueNAS shell:

```bash
sudo mkdir -p /mnt/apps/wbm-growth-engine/postgres
sudo mkdir -p /mnt/apps/wbm-growth-engine/storage
sudo mkdir -p /mnt/weddings_backups/wbm-growth-engine/database
sudo chown -R 70:70 /mnt/apps/wbm-growth-engine/postgres
sudo chown -R 10001:10001 /mnt/apps/wbm-growth-engine/storage
sudo chown -R 0:0 /mnt/weddings_backups/wbm-growth-engine
sudo chmod 750 /mnt/weddings_backups/wbm-growth-engine
sudo chmod 750 /mnt/weddings_backups/wbm-growth-engine/database
```

PostgreSQL Alpine uses user/group 70. The Growth Engine application uses
user/group 10001. The deliberately capability-dropped backup loop runs as
container root, so its private backup dataset is owned by root with mode 750.

## Pull the main branch into Dockge

While the GitHub repository is public, run:

```bash
cd /mnt/apps/dockge/data
git clone https://github.com/valianktni1/wbm-growth-engine.git
cd /mnt/apps/dockge/data/wbm-growth-engine
git branch --show-current
```

The final command must show `main`. After the clone and initial Docker build succeed, the repository can be made private again. This does not stop or alter the running application.

## Configure

Copy `.env.example` to `.env`, then replace every `CHANGE_ME` value. Generate independent random values for `POSTGRES_PASSWORD` and `SESSION_SECRET`.

Keep these settings off for the first test:

```text
BOOKING_ENQUIRY_FORWARDING=false
AUTOMATION_SEND_ENABLED=false
FOLLOWUP_APPROVAL_REQUIRED=true
```

## Build and start

```bash
cd /mnt/apps/dockge/data/wbm-growth-engine
sudo docker compose build --no-cache app
sudo docker compose up -d
sudo docker compose ps
curl -fsS http://127.0.0.1:30110/api/health
```

## Reverse proxy

In Nginx Proxy Manager create a proxy host:

- Domain: `growth.weddingsbymark.uk`
- Forward hostname/IP: the TrueNAS server IP
- Forward port: `30110`
- Websockets: off
- Block common exploits: on
- SSL: request a certificate, force SSL and enable HTTP/2

The application uses host port `30110` so Nginx Proxy Manager can reach it from its Docker network. Do not forward port 30110 from the public internet; only the HTTPS proxy host should be public.

## First test

1. Sign in at `https://growth.weddingsbymark.uk`.
2. Add a manual test enquiry.
3. Confirm the live date result is returned from the booking system.
4. Review and edit the automatically created proposal.
5. Publish the proposal and open its private URL.
6. Click a package and confirm the activity appears in the enquiry.
7. Configure SMTP and test sending to your own email address.
8. Confirm three prepared follow-ups exist but are not sent.
9. Deploy the paired BookingSystem2026 V8.37 connector and verify one test
   booking before enabling either automatic sync or manual-enquiry forwarding.

The existing website form remains unchanged and enters the booking system
first. BookingSystem2026 V8.37 sends authenticated idempotent snapshots to
`/api/integrations/booking/enquiry`. The same independent 64-character secret
is stored as `BOOKING_WEBHOOK_KEY` here and `GROWTH_INTEGRATION_KEY` in the
booking system. Neither application reads the other's database.

## Backups

The backup container writes one custom-format PostgreSQL dump every 24 hours to:

`/mnt/weddings_backups/wbm-growth-engine/database`

Every dump receives a SHA-256 checksum. The default retention is 60 days. TrueNAS snapshots can protect both datasets separately.

Verify a dump from the host using:

```bash
cd /mnt/weddings_backups/wbm-growth-engine/database
sudo sha256sum -c growth-engine-YYYYMMDD-HHMMSS.dump.sha256
```

## GitHub update procedure

1. Make and test the next update on the computer.
2. Push it to the `main` branch using GitHub Desktop.
3. Temporarily make `valianktni1/wbm-growth-engine` public.
4. Back up the live Growth Engine database.
5. Pull only the fast-forwarded `main` branch and rebuild.
6. Confirm the health endpoint and application screens.
7. Make the GitHub repository private again.

Use these TrueNAS commands:

```bash
cd /mnt/apps/dockge/data/wbm-growth-engine
stamp="$(date +%Y%m%d-%H%M%S)"
sudo docker compose exec -T database pg_dump -U growthengine -d growthengine -Fc > "/mnt/weddings_backups/wbm-growth-engine/database/pre-update-${stamp}.dump"
git pull --ff-only origin main
sudo docker compose build --no-cache app
sudo docker compose up -d app
sudo docker compose ps
curl -fsS http://127.0.0.1:30110/api/health
```

Never commit `.env`, mailbox passwords, integration keys, database passwords or session secrets to GitHub. They remain only in the private `.env` file on TrueNAS and are ignored by Git.
