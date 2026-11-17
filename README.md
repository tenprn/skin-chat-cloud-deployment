# Skin Chat VM Deployment

Self-contained deployment bundle for migrating the verified Skin Chat n8n
stack to a Linux VM.

## Project layout

```text
skin-chat-vm-deployment/
├── compose.yaml
├── README.md
├── config/
│   ├── caddy/Caddyfile
│   └── postgres/01-create-chat-app.sh
├── env/
│   ├── n8n.env.example
│   ├── postgres.env.example
│   ├── pgadmin.env.example
│   ├── proxy.env.example
│   └── line-gateway.env.example
├── migration/
│   ├── n8n-data.tar.gz
│   ├── postgres.dump
│   └── SHA256SUMS
├── services/
│   └── line-signature-gateway/
│       ├── app.py
│       └── Dockerfile
└── scripts/
    ├── prepare-env.sh
    ├── preflight.sh
    ├── restore-n8n-volume.sh
    ├── restore-postgres-logical.sh
    └── verify.sh
```

The cloud bundle intentionally excludes raw PostgreSQL and pgAdmin volumes,
the old Compose snapshot, development tests, macOS metadata, duplicate restore
notes, historical n8n event logs, and historical binary execution files.
PostgreSQL uses the portable logical dump, while n8n keeps only the state files
needed to restore its workflows, credentials, configuration, and custom-node
metadata.

Pinned images:

- n8n 2.47.7
- PostgreSQL 17.12
- pgAdmin 9.19.0 (optional profile)
- Caddy 2.11.9
- Python 3.13 Alpine for the LINE signature gateway

The migration data contains encrypted n8n credentials, chat history, and the
matching encryption configuration. Treat the entire archive as sensitive even
though the environment templates contain no real secrets.

## 1. Transfer and extract

From the computer holding the bundle:

```sh
scp skin-chat-vm-migration-bundle-2026-11-15.tar.gz \
  skin-chat-vm-migration-bundle-2026-11-15.sha256 \
  user@YOUR_VM:/opt/
```

On the VM:

```sh
cd /opt
sha256sum -c skin-chat-vm-migration-bundle-2026-11-15.sha256
tar -xzf skin-chat-vm-migration-bundle-2026-11-15.tar.gz
sudo chown -R "$USER":"$USER" /opt/skin-chat-vm-deployment
chmod 700 /opt/skin-chat-vm-deployment
cd /opt/skin-chat-vm-deployment
```

## 2. Create private configuration

```sh
./scripts/prepare-env.sh
```

Edit the five newly created files in `env/`:

- `env/n8n.env`
- `env/postgres.env`
- `env/pgadmin.env`
- `env/proxy.env`
- `env/line-gateway.env`

Important:

- The n8n domain must match in `n8n.env` and `proxy.env`.
- `LINE_WEBHOOK_PATH` is only the exact production path from the n8n Webhook
  node, such as `/webhook/abc123`; do not include the domain.
- `LINE_CHANNEL_SECRET` is from LINE Developers > Messaging API channel >
  Basic settings. It is not the channel access token.
- `APP_DB_PASSWORD` must match the PostgreSQL credential restored in n8n, or
  that n8n credential must be updated after restoration.
- Do not create a different `N8N_ENCRYPTION_KEY`. The restored n8n data
  contains the matching encryption configuration.
- DNS must point the configured domain to the VM before Caddy requests HTTPS.

Validate the configuration and migration checksums without printing secrets:

```sh
./scripts/preflight.sh
```

## 3. Restore the data

Restore n8n before starting the n8n container:

```sh
./scripts/restore-n8n-volume.sh
```

Initialize PostgreSQL and restore the portable chat-memory dump:

```sh
./scripts/restore-postgres-logical.sh
```

Both scripts use the bundled `migration/` directory by default.

## 4. Start and verify

Keep the LINE webhook pointed to the old environment until all checks pass.

```sh
docker compose up -d --build
docker compose ps
./scripts/verify.sh
```

Optional pgAdmin is bound only to VM localhost port 5050:

```sh
docker compose --profile admin up -d pgadmin
ssh -L 5050:127.0.0.1:5050 user@YOUR_VM
```

Open `http://localhost:5050` on your computer through that SSH tunnel.

## LINE signature routing

The accepted LINE route is:

```text
LINE -> Caddy -> line-signature-gateway:8080 -> n8n:5678
```

Caddy matches exactly `LINE_WEBHOOK_PATH` and forwards it to the Python
gateway. Caddy returns HTTP 404 for every other path beginning with `/webhook`,
including n8n test-webhook paths. The gateway checks the same path again,
calculates HMAC-SHA256 over the unchanged request body, Base64-encodes it, and
uses a constant-time comparison with `x-line-signature`. Invalid signatures
receive HTTP 401 and are never sent to n8n.

The editor, health endpoint, and other non-webhook routes go directly from
Caddy to n8n. If another public webhook is added later, define an explicit
Caddy route and an appropriate authentication policy for it.

## Production acceptance

Before changing the LINE webhook:

1. Confirm `https://YOUR_DOMAIN/healthz` succeeds.
2. Confirm workflows and credentials are visible and decrypt correctly.
3. Confirm the PostgreSQL memory credential connects.
4. Confirm an unsigned request to the LINE URL returns HTTP 401.
5. Use LINE Developers' Verify button to test a correctly signed request.
6. Test the workflow with synthetic text and a non-patient test image.
7. Confirm YOLO, validation, Gemini, memory, and LINE reply/push succeed.
8. Activate exactly one production workflow before switching the webhook.

## Network exposure

Allow publicly:

- TCP 80 for certificate issuance and HTTP redirection
- TCP 443 and optionally UDP 443 for HTTPS/HTTP3

Restrict TCP 22 to administrator access. Do not publicly expose PostgreSQL
5432, n8n 5678, the signature gateway 8080, or pgAdmin 5050.

## Normal commands

```sh
docker compose config --quiet
docker compose pull
docker compose up -d --build
docker compose ps
docker compose logs --tail=200 n8n line-signature-gateway caddy
docker compose down
```

Do not run `docker compose down -v` unless you intentionally want to delete the
Compose-managed database, pgAdmin, and Caddy volumes.
