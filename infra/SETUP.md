# Infra Stack Setup: Caddy + Cloudflare Tunnel

This guide sets up a shared reverse-proxy stack that gives any service on your server a public HTTPS URL — without exposing the host IP address. The stack consists of two Docker containers: **Caddy** (reverse proxy, subdomain routing) and **cloudflared** (Cloudflare Tunnel daemon). Cloudflare handles external TLS at the edge; all internal traffic is plain HTTP on a private Docker network.

Once this stack is running, any service you want to expose (the MCP server, Jellyfin, etc.) joins the shared `proxy` Docker network and gets a public subdomain by adding a single block to the Caddyfile.

---

## Prerequisites

- **Docker Engine** and **Docker Compose v2** installed on the server  
  Verify: `docker compose version` should print `v2.x.x` or higher
- **A payment method** for domain registration (Cloudflare Registrar charges at-cost: typically $10–15/year for a `.com`)

---

## Step 1: Create a Cloudflare Account

1. Go to <https://dash.cloudflare.com/sign-up>
2. Create an account with an email address and password
3. Verify your email

---

## Step 2: Register a Domain

1. In the Cloudflare dashboard, go to **Domain Registration > Register Domains**
2. Search for and register a domain (Cloudflare Registrar is recommended — at-cost pricing and DNS is integrated automatically)
3. Wait for registration to complete (usually instant for new registrations)

> **Already have a domain elsewhere?** You can either transfer it to Cloudflare Registrar, or add it to Cloudflare as a zone and update the nameservers at your current registrar. Both work; the key requirement is that DNS is managed in Cloudflare.

---

## Step 3: Create a Named Tunnel

> **Important:** This step creates a *named* tunnel (not a quick tunnel). Named tunnels have a stable, persistent public URL that survives restarts. Quick tunnels use ephemeral `trycloudflare.com` URLs — do not use them here.

1. Go to the Cloudflare Zero Trust dashboard: <https://one.dash.cloudflare.com/>
2. In the left sidebar, navigate to **Networks > Tunnels**
3. Click **Create a tunnel**
4. Select connector type: **Cloudflared**
5. Give the tunnel a name (e.g. `home-server`)
6. On the "Install and run a connector" page, **skip the installation step** — you will run the connector in Docker, not on the host directly
7. Click through to the tunnel's configuration page
8. Copy the **tunnel token** (a long `eyJ...` string) — this is your `TUNNEL_TOKEN` value

Keep this page open for Step 4.

---

## Step 4: Configure a Public Hostname in the Cloudflare Dashboard

While still on your tunnel's configuration page:

1. Click the **Public Hostnames** tab
2. Click **Add a public hostname**
3. Fill in the fields:
   - **Subdomain:** `mcp`
   - **Domain:** select your registered domain (e.g. `example.com`)
   - **Service type:** `HTTP` ← **MUST be HTTP, not HTTPS**
   - **Service URL:** `caddy:80`
4. Click **Save hostname**

> **Why HTTP and not HTTPS?**  
> Cloudflare terminates external TLS at the edge. Traffic between cloudflared and Caddy travels on the internal Docker network — plain HTTP is correct here. If you set the service type to HTTPS, cloudflared will attempt a TLS handshake with Caddy, which is not configured for TLS in this deployment, and requests will fail.
>
> The correct routing chain is: `Internet → Cloudflare edge (TLS) → cloudflared → caddy:80 (HTTP) → mcp-server:7363`

---

## Step 5: Copy the infra/ Directory to the Server and Configure

```bash
# On the server, copy the infra/ directory from this repository
cp -r /path/to/repo/infra ~/infra

# Create .env from the example file
cd ~/infra
cp .env.example .env

# Edit .env and fill in both values:
#   TUNNEL_TOKEN=eyJ...    (the token you copied in Step 3)
#   DOMAIN=example.com     (your root domain — NOT mcp.example.com)
nano .env
```

Your completed `~/infra/.env` should look like:

```dotenv
TUNNEL_TOKEN=eyJhbGciOiJIUzI1NiJ9...   # your actual token
DOMAIN=example.com                       # your actual root domain
```

> **Note:** `.env` is listed in `.gitignore` and is never committed. `.env.example` (without values) is committed as documentation.

---

## Step 6: Start the Infra Stack

```bash
cd ~/infra
docker compose up -d
```

Verify both containers are running:

```bash
docker compose ps
```

Expected output: both `caddy` and `cloudflared` show status `Up`.

Check that cloudflared connected to the Cloudflare edge:

```bash
docker compose logs cloudflared
```

Expected: log lines containing `Connection ... registered` or `Registered tunnel connection`. If you see TLS errors instead, re-check that the public hostname service type is `HTTP` (not `HTTPS`) in the Cloudflare dashboard (Step 4).

---

## Step 7: Start (or Restart) the MCP Stack

```bash
cd /path/to/mcp-project
docker compose up -d
```

The MCP stack joins the `proxy` external network only when `docker-compose.proxy.yml` is enabled: set `COMPOSE_FILE=docker-compose.yml:docker-compose.proxy.yml` in the MCP project's `.env`. With that override, `mcp-server` attaches to the `proxy` network (and stays on its own default network, where Weaviate is), and Caddy can reach it by container name. Without it, `mcp-server` is published on `127.0.0.1:7363` only and is not reachable through Caddy.

> **Important: Start order matters.** The infra stack (Step 6) must be running before you start the MCP stack. If the `proxy` network does not exist yet and the proxy override is enabled, this step will fail with:
> ```
> network proxy declared as external, but could not be found
> ```
> Fix: run `docker compose up -d` in `~/infra/` first, then retry.

---

## Step 8: Verify End-to-End

From any machine **outside your local network** (e.g. your phone on cellular, or a remote machine):

```bash
curl -f https://mcp.yourdomain.com/health
```

Expected: HTTP 200 with a JSON body like `{"status": "healthy", ...}`.

If this works, the full routing chain is operational:

```
Internet → Cloudflare edge (TLS) → cloudflared → Caddy → mcp-server
```

Your server's public IP is not exposed to clients — all traffic enters through Cloudflare's network.

---

## Troubleshooting

**1. `network proxy declared as external, but could not be found`**  
The infra stack must be running before the MCP stack starts. Run `docker compose up -d` in `~/infra/` first, then retry starting the MCP stack.

**2. `curl` returns 502 or connection refused**  
Caddy cannot reach `mcp-server`. Check that both containers are on the `proxy` network:

```bash
docker network inspect proxy
```

The output should list both `caddy` and `mcp-server` under `Containers`. If `mcp-server` is missing, the MCP stack may not be running or may not have joined the `proxy` network.

**3. `curl` hangs or DNS error**  
Verify the DNS CNAME was created by Cloudflare:

```bash
dig mcp.yourdomain.com
```

Expected: a CNAME record pointing to your tunnel UUID (e.g. `<uuid>.cfargotunnel.com`). If the record is missing or resolves to your server IP instead, check the public hostname configuration in the Cloudflare dashboard (Step 4).

**4. cloudflared logs show TLS errors**  
The public hostname service type in the Cloudflare dashboard must be `HTTP` (not `HTTPS`) with URL `caddy:80`. If it is set to `HTTPS`, cloudflared will attempt a TLS handshake that Caddy is not configured to handle. Update the public hostname in the dashboard and restart cloudflared: `docker compose restart cloudflared`.

**5. Caddy logs show `environment variable not found`**  
The `DOMAIN` variable is not set in `~/infra/.env`. Open `~/infra/.env` and add:

```dotenv
DOMAIN=example.com
```

Then restart the infra stack: `docker compose up -d` in `~/infra/`.

---

## Adding More Services

To expose another service on the server (e.g. Jellyfin on port 8096):

1. Add the service's container to the `proxy` network in its own Compose stack
2. Add a site block to `~/infra/Caddyfile`:
   ```
   jellyfin.{$DOMAIN} {
       reverse_proxy jellyfin:8096
   }
   ```
3. Reload Caddy to apply the change without restarting:
   ```bash
   cd ~/infra
   docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
   ```
4. Add a new public hostname in the Cloudflare dashboard pointing to `caddy:80` with subdomain `jellyfin`

No changes to `cloudflared` configuration are needed — cloudflared always routes to `caddy:80`, and Caddy handles the subdomain routing from there.

---

## Restarting

The infra stack runs with `restart: unless-stopped` and will start automatically after a server reboot (if Docker is configured to start on boot).

After a manual server reboot or stack restart:

```bash
# Start infra stack first (creates the proxy network)
cd ~/infra && docker compose up -d

# Then start the MCP stack (joins the proxy network via docker-compose.proxy.yml in COMPOSE_FILE)
cd /path/to/mcp-project && docker compose up -d
```

The `TUNNEL_TOKEN` persists in `~/infra/.env`. The same public URL (`mcp.yourdomain.com`) is restored automatically — no reconfiguration in the Cloudflare dashboard is needed.
