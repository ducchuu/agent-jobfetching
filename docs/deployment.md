# Deployment, Access Control, and Maintenance

[Back to README](../README.md)

## Local deployment

```bash
cp .env.example .env
# Edit credentials and settings.
docker compose up -d --build
```

Use `127.0.0.1:8000:8000` for the host port. Run one application process and one scheduler. Do not add workers/replicas without shared coordination.

Never commit `.env`. Verify `.dockerignore` excludes credentials, virtual environments, profiles, databases, and CVs before building; `COPY . .` otherwise includes eligible build-context files.

## Access-control boundary

A tunnel, a home-server location, and a localhost-only host port are not visitor authentication. A public tunnel route can expose the service through the tunnel even when direct host access is restricted.

Before remote access, choose and verify an enforced boundary:

- Cloudflare Access with restrictive policies and appropriate Access-token validation;
- application API-key authentication, with a deliberate policy for public status routes; or
- genuinely private network connectivity without an unrestricted public route.

Cloudflare Access plus application authentication can provide additional protection. See [Cloudflare's self-hosted application guide](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/).

### Application authentication

Set `API_SECRET_KEY` to enable checks on `/profile`, `/upload-cv`, and `/trigger-pipeline`. These require `X-API-Key` and reject missing/incorrect keys with 403. An empty secret disables that application check. `/` and `/pipeline-status` remain public at application level; protect them externally if needed.

```bash
curl --fail-with-body --silent --show-error \
  -X POST http://127.0.0.1:8000/trigger-pipeline \
  -H 'X-API-Key: YOUR_API_SECRET_KEY'
```

Do not send secrets over unprotected remote HTTP. Internal requests still require the header when application authentication is enabled.

## Optional Cloudflare Tunnel

Configure `CLOUDFLARE_TUNNEL_TOKEN`, the published route, and access controls before starting:

```bash
docker compose --profile tunnel up -d --build
```

A tunnel container on the Compose network should reach the API using an origin such as `http://api:8000`, not its own localhost.

Verify unauthorized requests are denied at the published hostname, then verify authorized upload, profile access, and triggering. Do not infer protection from tunnel connectivity alone.

## Automation

Inspect the actual files in [`.github/workflows/`](../.github/workflows/). The intended deployment design runs tests on a GitHub-hosted runner and gates the dependent home-server deployment job with `needs: test`.

- Deploy the exact tested revision.
- Preserve the intended authentication settings in generated `.env` files.
- Build before replacing the running service.
- Start the tunnel profile only when configured and intended.
- Retry a post-start HTTP check with a bounded timeout.
- Treat `/` as a basic liveness response, not a provider or end-to-end readiness check.
- Keep untrusted pull-request code off the home-server runner.

A manual pipeline workflow requests background execution, not completion. Use HTTP failure-aware curl options. If `API_SECRET_KEY` is enabled, automation must send the header; a conditional-header script supports both local configurations. A busy response means no additional run should be assumed.

## Maintenance

Prevent pipeline activity before changing data. Host `data/` and a Docker named volume are different locations. While the service is running, its scheduler remains active: coordinate maintenance rather than assuming a command is atomic with pipeline execution.

### Local Python deployment

Remove the cached profile:

```bash
rm -f data/candidate_profile.json
```

Clear processing history:

```bash
python clear_db.py
```

### Docker deployment

When the API container is running and pipeline activity has been prevented:

```bash
docker compose exec api rm -f /app/data/candidate_profile.json
docker compose exec api python clear_db.py
```

For a complete clean slate:

```bash
docker compose down -v
```

This stops the deployment and removes its declared named volumes, including cached profile and processing history. It is destructive. Do not use it as an ordinary restart command.

These operations do not delete external provider records, Langfuse traces, or Discord history.

## Release checklist

- Successful CI for the intended release commit.
- Clean image build; verify secrets/personal files are excluded.
- Local API startup and authenticated endpoint checks.
- Correct public access policy, if a hostname is published.
- Profile and history persist across container recreation.
- One bounded, cost-aware live smoke run where practical.
- Rendered Markdown, relative links, screenshot, and license checked.
- Tag the tested commit and write concise release notes.
