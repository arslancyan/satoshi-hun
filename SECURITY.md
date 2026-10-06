# Security Policy — Satoshi Hunt

## Public frontend rule

The GitHub Pages site is intentionally treated as **public**. Never put secrets, private keys, API keys, authentication tokens, database credentials, signing material, or proprietary server-side algorithms in the published frontend.

## Data boundary

The `site/` directory is the only directory deployed to GitHub Pages.

Production reward data, account data, worker telemetry, payout addresses, reward settlement records, and private challenge material must remain on a backend service and must never be bundled into `site/`.

## Repository protection

Before committing, inspect changes for:
- API keys and access tokens
- private keys / seed phrases
- database URLs containing credentials
- webhook secrets
- production credentials
- private challenge material

Use environment variables or a server-side secret manager for runtime secrets.

## Asset protection

Browser-delivered assets cannot be made impossible to copy. Protection is therefore based on:
1. keeping proprietary logic server-side;
2. publishing only the minimum frontend assets;
3. avoiding production datasets in static files;
4. retaining copyright/provenance notices for original artwork and UI;
5. using authenticated APIs for protected data when the backend is introduced.

UI copy/selection blocking is not considered a security control.

## Reporting

Do not publish credentials or sensitive data in an issue. Rotate any exposed credential immediately and report the incident privately to the project owner.
