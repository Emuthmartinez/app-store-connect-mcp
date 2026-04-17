# Quick Start

Get App Store Connect MCP running with Claude Desktop in 10 minutes.

## 1. Prerequisites

- Python 3.11 or newer
- App Store Connect API key (see [ASC key setup](./self-host.md#minting-an-asc-api-key))
- (Optional) RevenueCat project ID + API key

## 2. Clone & install

```bash
git clone https://github.com/Emuthmartinez/app-store-connect-mcp
cd app-store-connect-mcp
pip install -e ".[dev]"
```

## 3. Configure

Copy `.env.example` to `.env` and fill in:

```env
APP_STORE_KEY_ID=XXXXXXXXXX
APP_STORE_ISSUER_ID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
APP_STORE_PRIVATE_KEY=/absolute/path/to/AuthKey_XXXXXXXXXX.p8
APP_STORE_BUNDLE_ID=com.example.myapp

# Optional
REVENUECAT_API_KEY_V2=sk_...
REVENUECAT_PROJECT_ID=proj...
```

## 4. Verify the connection

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from config import Settings
from auth import AppStoreJwtProvider
from client import AppStoreConnectClient
from revenuecat import RevenueCatMetricsClient
from change_log import ChangeLogger
from subscriber_state import SubscriberSnapshotStore
from index import Runtime
from tools.diagnostics import test_connection
settings = Settings.load()
asc = AppStoreConnectClient(settings, AppStoreJwtProvider(settings))
runtime = Runtime(
    settings=settings, asc=asc,
    revenuecat=RevenueCatMetricsClient(settings),
    change_logger=ChangeLogger(settings.change_log_path),
    subscriber_store=SubscriberSnapshotStore(
        event_log_path=settings.revenuecat_event_log_path,
        snapshot_path=settings.revenuecat_snapshot_path,
        overview_history_path=settings.revenuecat_overview_history_path,
    ),
)
import json
print(json.dumps(test_connection(runtime, {}), indent=2))
"
```

If all checks pass, you're good.

## 5. Register with Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) or `%APPDATA%/Claude/claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "app-store-connect-mcp": {
      "command": "python3",
      "args": ["/absolute/path/to/app-store-connect-mcp/src/index.py"]
    }
  }
}
```

Restart Claude Desktop. In a new chat, type:

> What's my current App Store listing look like?

Claude should call `asc_get_app_listing` and show you the result.

## 6. Try a mutation

> Update my keywords to include "ai stylist" and make sure we're under 100 characters.

Claude will read the current keywords, compute the new string, and call `asc_update_keywords`.

Every write is logged to `data/changes.jsonl`.

## 7. Try the revenue correlation

After a few days (or if you have change history already):

> Run change impact analysis for the last 10 mutations.

Claude calls `asc_get_change_impact_analysis` and shows you which changes correlated with revenue shifts.

## Next steps

- [Self-host details](./self-host.md) — profiles, multi-app, systemd
- [Cloud setup](./cloud-setup.md) — sign up, API keys, Slack alerts
- [Change impact](./change-impact.md) — how the revenue correlation works
