# Self-Host Guide

This is the long-form version of [Quick Start](./quick-start.md) with
detail on credential management, multi-app profiles, and running as a
long-lived process.

## Minting an ASC API key

1. Go to [App Store Connect → Users and Access → Keys](https://appstoreconnect.apple.com/access/api).
2. Click **Generate API Key**. Name it "StorePilot" (or whatever you'll remember).
3. Grant it **Admin** access (listing edits require it).
4. Download the `.p8` file. **You can only download it once.** Keep it safe.
5. Note the **Key ID** (10 characters) and the **Issuer ID** (UUID at the top of the page).

## Finding your bundle ID

You already know this — it's in your Xcode target under Bundle Identifier.

## RevenueCat setup (optional but recommended)

1. [RevenueCat → Project settings → API keys](https://app.revenuecat.com/settings/api-keys).
2. Create a **V2 secret** API key. Save it.
3. Copy the project ID from the URL (`proj...`).

## Configuration files

StorePilot loads configuration in this order (later overrides earlier):

1. `.env` in the repo root
2. Path in `APP_STORE_CONNECT_MCP_ENV` env var
3. Process environment variables

### Multi-app profiles

For multiple apps, create one file per app in `profiles/`:

```
profiles/
├── clueless.env   # Clueless Clothing iOS app
└── other-app.env  # Your other app
```

Switch apps by pointing `APP_STORE_CONNECT_MCP_ENV` at the right file:

```bash
APP_STORE_CONNECT_MCP_ENV=profiles/other-app.env python3 src/index.py
```

Or configure two MCP server entries in your client:

```json
{
  "mcpServers": {
    "asc-clueless": {
      "command": "python3",
      "args": ["/abs/path/src/index.py"],
      "env": { "APP_STORE_CONNECT_MCP_ENV": "/abs/path/profiles/clueless.env" }
    },
    "asc-other-app": {
      "command": "python3",
      "args": ["/abs/path/src/index.py"],
      "env": { "APP_STORE_CONNECT_MCP_ENV": "/abs/path/profiles/other-app.env" }
    }
  }
}
```

## Analysis heuristics

Tune the listing health checks via env vars (JSON):

```env
ASC_COPY_TERMS='{"subtitle": ["AI", "weekly"], "keywords": ["stylist"]}'
ASC_BENCHMARK_NOTES='["Trial conversion target: 8%"]'
ASC_PREFERRED_KEYWORDS='["ai stylist", "outfit planner", "wardrobe app"]'
```

These flow into `asc_get_listing_health` and `asc_suggest_keyword_updates`.

## Notifications (Slack / Discord / generic)

If you want outbound alerts, set:

```env
ASC_NOTIFICATION_WEBHOOK_URL=https://hooks.slack.com/services/...
ASC_NOTIFICATION_PROVIDER=slack           # or discord, generic
ASC_NOTIFICATION_MIN_SEVERITY=warning     # info, warning, critical
```

Without a URL, notifications no-op. See `src/notifications.py` for the API.

## Running as a service

### systemd (Linux)

```ini
# /etc/systemd/system/storepilot.service
[Unit]
Description=StorePilot MCP server
After=network.target

[Service]
Type=simple
User=storepilot
WorkingDirectory=/opt/storepilot
EnvironmentFile=/opt/storepilot/.env
ExecStart=/usr/bin/python3 /opt/storepilot/src/index.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### launchd (macOS)

```xml
<!-- ~/Library/LaunchAgents/com.storepilot.server.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.storepilot.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/python3</string>
    <string>/opt/storepilot/src/index.py</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>WorkingDirectory</key><string>/opt/storepilot</string>
  <key>StandardErrorPath</key><string>/tmp/storepilot.err</string>
</dict>
</plist>
```

Load with `launchctl load ~/Library/LaunchAgents/com.storepilot.server.plist`.

## Troubleshooting

### `ConfigurationError: Missing required App Store Connect configuration`

One of the four required env vars is blank. Check that `.env` is loading — try `python3 -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.environ.get('APP_STORE_KEY_ID'))"`.

### `AscApiError: 401 Unauthorized`

Your JWT is wrong. Common causes:
- Key ID and Issuer ID swapped
- Private key file has extra whitespace (re-download)
- Private key is expired or revoked in ASC

Run `asc_test_connection` — it isolates which step failed.

### `RevenueCat client returned None`

API key format mismatch. Double-check you're using the **V2** secret, not the V1 legacy.

### Tools not showing up in Claude

MCP client caches tool definitions. Restart Claude Desktop fully (quit from the menu, not just close the window).
