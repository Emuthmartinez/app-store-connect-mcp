# Product Hunt launch kit

## Tagline (≤60 chars)

**Let AI agents manage your App Store listings**

Alternates (test them):
- AI-native App Store management, open source
- Your App Store Connect, via Claude / Cursor
- The MCP server for App Store Connect

## Short description (≤260 chars)

App Store Connect MCP is an open-source server that lets AI agents (Claude, Cursor, Codex, n8n) read and update your App Store Connect listings — keywords, screenshots, descriptions, experiments — and correlate every change with your RevenueCat MRR.

## Topics

- Developer Tools
- Artificial Intelligence
- iOS
- Open Source
- Productivity

## Gallery order

1. **Hero image** — dark terminal screenshot showing a natural-language ASO command and Claude's response using `asc_update_keywords`. (Designer-made; do NOT use an AI-gen template.)
2. **Change impact analysis screenshot** — the JSON output of `asc_get_change_impact_analysis` highlighting a keyword change that correlated with an 18% MRR lift.
3. **Tool catalog** — styled list of the 60+ MCP tools, grouped by category (Reads, Writes, Versioning, CPP, Analysis, Change Impact, Diagnostics, Play scaffold, Generic, Subscriber).
4. **Weekly health report** — a rendered markdown weekly digest with a health score, revenue snapshot, listing gaps, and recent change correlations.
5. **Architecture** — a simple diagram showing stdio self-hosted mode vs. hosted cloud mode with API keys.

## Demo video script (60–90s)

*Open cold, no logo intro.*

**0:00** "I ship iOS apps. Here's my usual App Store Connect workflow." [fast cut of mouse clicking around ASC dashboard]

**0:06** "Now I just tell Claude." [cut to Claude Desktop]

**0:08** User types: "Add 'ai stylist' to my keywords and update the first line of the description to lead with the new onboarding flow."

**0:12** Claude calls `asc_get_app_listing`. Show the tool call. [1s]

**0:14** Claude calls `asc_update_keywords`. Show the tool call with the new keyword string. [1s]

**0:16** Claude calls `asc_update_description`. [1s]

**0:18** "Done. But here's the part I like." [cut]

**0:22** User types: "Did my last keyword change actually move MRR?"

**0:25** Claude calls `asc_get_change_impact_analysis`. Show the result — MRR up 22.1%, subscriptions up 18.3%, with the caveat displayed.

**0:35** "Every listing change is logged with your RevenueCat metrics. The MCP server correlates them automatically."

**0:42** "Open source. MIT. Self-host it, or get the hosted version for $29 a month."

**0:52** Call-to-action card: *github.com/Emuthmartinez/app-store-connect-mcp*

## Maker comment (for the launch post)

---

Hi Product Hunt 👋

I'm Eduardo, and I build iOS apps. Every version release, I'd spend an hour in App Store Connect — tweaking keywords, rewriting descriptions, swapping screenshots. The worst part wasn't the time, it was never knowing whether any of it moved the needle.

So I built App Store Connect MCP, an open-source server that lets AI agents do the work for me. But the real unlock is `asc_get_change_impact_analysis`: every listing mutation is logged with a snapshot of my RevenueCat metrics at the time of change. I can ask Claude "did my keyword update last week correlate with a revenue lift?" and get a real answer.

The core is open source under MIT. Self-host it forever, or use the hosted cloud tier ($29/mo) if you don't want to run anything. Weekly health reports, Slack alerts, Google Play Console parity in Phase 3.

Would love your feedback — especially if you've been frustrated with ASO tools that don't connect to revenue.

Links:
- GitHub: https://github.com/Emuthmartinez/app-store-connect-mcp
- Docs: https://github.com/Emuthmartinez/app-store-connect-mcp/tree/main/docs

## Hunter outreach DM template

Hey [name] —

I'm launching App Store Connect MCP on Product Hunt on [day]. It's an open-source MCP server that lets Claude manage App Store Connect listings, with a RevenueCat-correlated change impact tool that's the real unlock.

Built it after spending way too many hours in ASC every release. Open source, MIT, already have [N] GitHub stars.

Would you be willing to hunt it? Happy to prep all the assets, just need your green light.

Here's a preview: [github.com/Emuthmartinez/app-store-connect-mcp]

No worries either way — thanks for what you do.

## Launch day checklist

- [ ] Schedule the launch for Tuesday or Wednesday, 00:01 PST
- [ ] Hunter confirmed 1 week ahead
- [ ] Hero image, gallery images, and demo video uploaded
- [ ] Landing page loads in <1s, mobile-responsive
- [ ] Cloud signup flow tested end-to-end
- [ ] Discord server has a #launch channel pinned
- [ ] 5 friends / team members ready to comment substantively (NOT "congrats", actual questions/feedback)
- [ ] Cross-post ready for X, LinkedIn, IndieHackers, Reddit r/iOSProgramming
- [ ] Reply template ready for common questions (ASC setup, RevenueCat setup, pricing, security)
- [ ] Monitor support inbox aggressively for first 24h
