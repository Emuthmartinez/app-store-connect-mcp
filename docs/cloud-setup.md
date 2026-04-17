# Cloud Setup

The hosted cloud tier lets you skip running your own MCP process. You
sign up, paste your ASC key, and get an API key that any MCP client can
use to connect.

## Sign up

1. Go to [storepilot.app/signup](https://storepilot.app/signup).
2. Choose a plan (Pro / Team / Enterprise). 14-day free trial, no card.
3. You land on the dashboard.

## Add your app

1. Dashboard → **Apps** → **Add app**.
2. Paste:
   - Bundle ID
   - ASC Key ID, Issuer ID
   - ASC `.p8` private key contents (we encrypt at rest; see [security](#security))
3. Click **Test connection**. This runs `asc_test_connection` server-side and shows you any issues.

## (Optional) Connect RevenueCat

1. Dashboard → **App settings** → **Revenue tracking**.
2. Paste your RevenueCat project ID and V2 secret API key.
3. Click **Verify**. The server calls `asc_refresh_subscriber_overview` and confirms the metrics load.

This unlocks the change impact analysis and scheduled health reports.

## Get an API key

1. Dashboard → **API keys** → **Create key**.
2. Name it (e.g. "laptop", "ci", "claude-desktop").
3. Copy the key starting with `ascmcp_`. **Shown once.**

## Connect Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "storepilot-cloud": {
      "url": "https://api.storepilot.app/v1/sse",
      "headers": {
        "Authorization": "Bearer ascmcp_your_key_here"
      }
    }
  }
}
```

Restart Claude Desktop. Tools should appear with the `asc_` prefix.

## Or call directly via HTTP

For custom integrations:

```bash
curl -X POST https://api.storepilot.app/v1/tools/call \
  -H "Authorization: Bearer ascmcp_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "asc_get_listing_health",
    "arguments": {"locale": "en-US"}
  }'
```

## Slack / Discord alerts (Team tier)

1. Dashboard → **Alerts** → **Add webhook**.
2. Paste your Slack incoming webhook URL (or Discord webhook URL).
3. Choose events:
   - Listing health score drops below threshold
   - MRR shifts more than X% in 7 days
   - Review state changes (submitted, approved, rejected)

## Weekly health reports (Team tier)

Enabled by default. Delivered Mondays 9am local time to:
- Email (the owner of the workspace)
- Slack, if a webhook is configured

## Security

- **Encryption at rest**: ASC private keys and RevenueCat secrets are encrypted with per-tenant data keys, which are wrapped by a master key stored in AWS KMS.
- **Key rotation**: Rotate your ASC API key on Apple's side, then update it in the dashboard. Old cached JWTs expire within 20 minutes.
- **Scoped permissions**: Each API key is scoped to one tenant. Revoke any time from the dashboard.
- **Audit log**: Every tool call (reads and writes) is logged with tenant ID, timestamp, and tool name. Available on Enterprise.

## Billing

- Stripe-managed. Change plan anytime from dashboard.
- Annual plans save 20%.
- Usage above your plan's included API call quota is $0.01/call.
- Cancel anytime; your data export is available for 30 days after cancellation.
