# Growth Engine V1.0.1

This release retains the tested V1.0.0 application and adds the agreed GitHub-first deployment workflow.

- Repository: `valianktni1/wbm-growth-engine`
- Deployment branch: `main`
- TrueNAS clones directly into the Dockge stacks directory.
- The repository may be made private after cloning/building.
- Updates use a database backup followed by `git pull --ff-only origin main` and a clean application rebuild.
- Live secrets remain in TrueNAS `.env` and are excluded from Git.

