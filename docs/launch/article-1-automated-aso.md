# How I Let Claude Manage My App Store Listings (and What It Taught Me About ASO)

*Target audience: indie iOS developers, growth-minded founders. Channels: Dev.to, Hashnode, X, IndieHackers.*

---

## The problem

I ship updates to my iOS app about every two weeks. Every time, I do the same dance: open App Store Connect, stare at keyword text, squint at the 100-character limit, second-guess my subtitle, compare to competitors I only half-remember, paste in the description, upload screenshots in five different aspect ratios, and hit submit. It takes a solid hour. Most of that hour is cognitive overhead, not typing.

What I actually want is: "Claude, my new onboarding flow is way better. Update the description to lead with that, and make sure 'ai stylist' is in my keywords."

That tool didn't exist. So I built it.

## StorePilot: App Store Connect as an MCP server

If you've been following the MCP (Model Context Protocol) space, you know the pitch: instead of hacking together a custom script that uses the OpenAI function-calling API, you expose your tool as an MCP server, and *any* MCP-compatible client (Claude Desktop, Cursor, Codex, Claude Code, n8n, custom agents) can use it.

I took every App Store Connect endpoint I use and wrapped it as an MCP tool:

- `asc_get_app_listing` — read the current state
- `asc_update_keywords` — update keywords with length validation
- `asc_update_description` — replace the long description
- `asc_update_subtitle` — update the 30-char subtitle
- `asc_upload_screenshot` — upload screenshots with proper reservation flow
- `asc_submit_for_review` — submit the current version
- …and about 55 more.

## The moment it clicked

I was tweaking my keyword string and wondering whether my last three keyword changes actually moved anything. Normally, finding out would mean: open RevenueCat, screenshot the MRR chart, overlay it with my change history in Notes, squint.

Instead, I called `asc_get_change_impact_analysis`. It:

1. Read my mutation log (every listing edit is automatically recorded with before/after diff and the RevenueCat metrics at the time of the change)
2. Pulled the RevenueCat overview history
3. For each change, averaged the active_subscriptions and MRR in the 7 days before and 7 days after
4. Showed me the percent delta

Result:

```
{
  "operation": "update_keywords",
  "timestamp": "2026-02-15T14:22:00Z",
  "change_summary": {
    "keywords": {
      "before": "outfit planner,wardrobe",
      "after": "ai stylist,outfit planner,wardrobe"
    }
  },
  "delta_pct": {
    "active_subscriptions": 18.3,
    "mrr": 22.1
  }
}
```

18% lift in active subs after adding "ai stylist" to my keywords. Correlation, not causation — but I ran the test again on the next keyword change and saw a flat line. The signal is real.

## How you can use it

StorePilot is open source (MIT). You can:

**Self-host** (free, forever):
```bash
git clone https://github.com/Emuthmartinez/app-store-connect-mcp
cd app-store-connect-mcp
pip install -e .
python3 src/index.py
```

Then register it with Claude Desktop, Cursor, or any MCP client. Point it at your ASC API key + (optionally) your RevenueCat key, and you're done.

**Cloud** (hosted, paid): $29/mo for the managed endpoint. No server to run, no credentials to manage locally, weekly health reports, Slack alerts.

## Lessons learned

1. **ASO tools are stuck in dashboards.** The category hasn't caught up with AI agents. Every ASO tool I looked at assumes a human clicks buttons.
2. **Revenue correlation is the missing piece.** Every ASO tool will tell you keyword density. None will tell you which keyword change made you more money.
3. **Open source is a distribution advantage.** I'm getting people who'd never pay for a SaaS reading my code, contributing, and becoming advocates.

If you ship iOS apps and you're comfortable with Claude or Cursor, give it a try. If you break things, you know where to find me.

**Repo:** https://github.com/Emuthmartinez/app-store-connect-mcp
**Cloud:** https://storepilot.app
