# 90-Day SaaS Profitability Plan: App Store Connect MCP

**Goal**: Go from open-source side project to $5k+ MRR in 90 days.
**Model**: Open-core (Postiz style) — free self-hosted, paid cloud + premium features.

---

## Phase 1: Foundation (Days 1–30)

### Week 1: Cloud Architecture & Pricing

**Day 1–2: Define your tiers**

| Tier | Price | What they get |
|------|-------|---------------|
| **Free (Self-hosted)** | $0 | All 54 current tools, MIT license, community support |
| **Pro (Cloud)** | $29/mo | Hosted MCP endpoint, managed JWT auth, webhook hosting, 3 apps, email support |
| **Team** | $79/mo | 10 apps, team sharing, scheduled health reports, Slack alerts, priority support |
| **Enterprise** | $199/mo | Unlimited apps, SSO, audit logs, SLA, dedicated onboarding |

**Day 3–5: Build the hosted MCP proxy**

Your current server is stdio-based. Wrap it in an HTTP/SSE transport for cloud delivery:

```
┌─────────────────────────────────────────────┐
│  Cloud Infrastructure                       │
│                                             │
│  ┌──────────┐    ┌──────────────────────┐   │
│  │ Auth     │───▶│ MCP-over-SSE Gateway │   │
│  │ (API Key)│    │ (per-tenant routing)  │   │
│  └──────────┘    └──────────────────────┘   │
│                         │                   │
│              ┌──────────┴──────────┐        │
│              │ Tenant Runtime Pool │        │
│              │ (isolated Settings  │        │
│              │  per customer)      │        │
│              └─────────────────────┘        │
└─────────────────────────────────────────────┘
```

Key implementation steps:
- Add an SSE/HTTP transport layer alongside the existing stdio transport in `src/index.py`
- Build a tenant isolation layer — each customer gets their own `Runtime` instance with their own ASC credentials stored encrypted
- Add API key authentication middleware
- Use your existing `profiles/` pattern as the model — each tenant is effectively a profile
- Deploy on Railway or Fly.io (cheap, scales to zero, easy to start)

**Day 6–7: Build billing integration**

- Stripe Checkout for sign-up flow
- Stripe webhooks for subscription lifecycle (activate, cancel, upgrade)
- Simple usage tracking: count API calls per tenant per month
- Store tenant config in PostgreSQL (Supabase free tier to start)

Deliverable: A working cloud endpoint where someone can sign up, paste their ASC credentials, and immediately use the MCP server from Claude Desktop without running anything locally.

---

### Week 2: Landing Page & Waitlist

**Day 8–10: Landing page**

Do NOT use an AI-generated template. Following Nevo's advice — hire a designer on Fiverr ($100–200) or use a polished template from Framer.

Page structure:
1. **Hero**: "Automate Your App Store Listings with AI" — show a 15-second screen recording of Claude Desktop updating keywords via your MCP
2. **Pain points**: Manual ASO is tedious, error-prone, and disconnected from revenue data
3. **Solution**: Your MCP server lets AI agents manage listings, track revenue impact, run experiments
4. **Feature grid**: Listing management, RevenueCat integration, Custom Product Pages, A/B experiments, health scoring
5. **Pricing table**: Free / Pro / Team / Enterprise
6. **Social proof**: GitHub stars count, "MIT licensed", "54 tools"
7. **CTA**: "Start free" (self-hosted docs) + "Try Pro free for 14 days" (cloud)

Domain: `ascmcp.com` or `appstoreconnect.tools` (check availability)

**Day 11–12: Documentation site**

- Use Mintlify or Docusaurus (free tier)
- Migrate README content into proper docs
- Add: Quick Start, Tool Reference (all 54 tools), Cloud Setup, Self-Hosted Setup, RevenueCat Integration Guide
- Each tool page should have: description, parameters, example request/response, related tools

**Day 13–14: Set up analytics & feedback loops**

- PostHog (free tier) for product analytics
- Add anonymous usage telemetry to the MCP server (opt-in, with clear disclosure)
- Track: which tools are used most, error rates, session duration
- Crisp or Intercom (free tier) for live chat on landing page
- Set up a Discord server for community

---

### Week 3: Launch Prep & Content

**Day 15–17: Product Hunt prep**

Product Hunt is your single biggest Day 1 lever. Prepare:

- **Tagline**: "Let AI agents manage your App Store listings" (under 60 chars)
- **Description**: Focus on the MCP angle — this is novel, not "another ASO tool"
- **Media**:
  - 1 hero image (designer-made, not AI-generated)
  - 1 demo video (60–90 seconds): show Claude Desktop running `asc_get_listing_health`, identifying issues, then fixing keywords and description in one conversation
  - 3–4 gallery images showing tool categories
- **Maker comment**: Write your launch story — why you built this, the open-source angle, RevenueCat integration story
- **Hunter**: Reach out to a top hunter 1 week before launch (DM on X, be genuine)

**Day 18–20: Write 3 launch articles**

Article 1: **"How I Automated My App Store Listings with Claude and Made $X More"**
- Personal story format
- Show real before/after of listing optimization
- Include revenue impact (even projected)
- Target: Dev.to, Hashnode, X

Article 2: **"The Complete Guide to App Store Connect MCP Tools"**
- Technical deep-dive
- Every tool category with examples
- Target: Dev.to, Reddit r/iOSProgramming

Article 3: **"Why Your ASO Workflow is Broken (And How AI Agents Fix It)"**
- Pain-point focused
- Compare manual vs. MCP-automated workflow
- Target: IndieHackers, X

**Day 21: Prepare cover images**

Following Nevo's "make people click" advice:
- Bold, unusual cover images (not generic SaaS gradient)
- Consider: terminal screenshot aesthetic, App Store icon mashup, "money printer" meme format
- Use Figma or hire the same Fiverr designer

---

### Week 4: Launch

**Day 22: Product Hunt launch**

- Launch Tuesday or Wednesday (best days)
- Post at 12:01 AM PST
- Share on X, LinkedIn, Discord communities, Slack groups
- Respond to EVERY comment within 30 minutes
- Cross-post launch announcement to Reddit (r/SideProject, r/iOSProgramming, r/OpenSource)

**Day 23–24: Reddit blitz**

Post your Article 2 (technical guide) to:
- r/iOSProgramming ("I built an MCP server that lets Claude manage your App Store listings")
- r/AppBusiness
- r/SideProject
- r/selfhosted (open-source angle)
- r/MachineLearning or r/LocalLLaMA (MCP/agent angle)

**Day 25–26: X content push**

- Thread 1: "I built 54 MCP tools for App Store Connect. Here's what each one does." (list thread)
- Thread 2: Share Article 1 with eye-catching cover
- Reply to every iOS dev, indie hacker, ASO-related post you see
- Follow and engage with: ASO community, indie iOS devs, MCP/AI agent builders

**Day 27–28: Integrations push**

- Submit to MCP server directories (there are several curated lists)
- Submit to awesome-mcp-servers GitHub repos
- Create an n8n community node (or at minimum, document how to use with n8n)
- Post in Claude Discord, OpenAI community (generic MCP works with any client)

**Day 29–30: Retro & metrics check**

Target end-of-month metrics:
- 200+ GitHub stars
- 50+ cloud sign-ups
- 5–10 paying customers ($145–$290 MRR)
- 3+ articles published
- Product Hunt top 10 of the day

---

## Phase 2: Growth Engine (Days 31–60)

### Week 5–6: Feature Expansion for Paid Tiers

**Day 31–35: Scheduled Health Reports (Team tier)**

Build a cron system that:
1. Runs `asc_get_listing_health` daily for each tenant's apps
2. Compares against previous day's snapshot
3. Emails a weekly digest: "Your App Store Health Report"
   - Listing completeness score (0–100)
   - Revenue trend (from RevenueCat)
   - Keyword opportunities detected
   - Screenshot coverage gaps
   - Action items with one-click fixes (deep links to Claude Desktop with pre-filled prompts)

This is your **retention hook** — even if they stop actively using the MCP tools, the weekly email keeps them engaged and reminds them of value.

**Day 36–38: Slack/Discord Alerts (Team tier)**

- Real-time notifications when:
  - App review status changes (submitted → in review → approved/rejected)
  - RevenueCat metrics cross thresholds (MRR drops >10%, trial conversion spike)
  - Listing health score drops below threshold
- Use Slack incoming webhooks (simple, no OAuth needed initially)

**Day 39–42: Revenue-Correlated Insights (Pro+ tier)**

This is your **blue ocean differentiator** — no ASO tool connects listing changes to revenue:

Build a new tool `asc_get_change_impact_analysis`:
1. Read mutation log (`data/changes.jsonl`) — you already log before/after + RevenueCat metrics
2. For each listing change, show revenue metrics 7 days before vs. 7 days after
3. Surface: "After updating keywords on Jan 15, active subscriptions increased 12% over 7 days"
4. Caveat: correlation, not causation — but incredibly valuable signal

This leverages infrastructure you ALREADY have. The mutation log + RevenueCat polling is built. You just need the analysis layer.

---

### Week 7–8: Content Flywheel & Community

**Day 43–45: Build the content machine**

Set up a repeatable content cadence:

| Day | Channel | Content Type |
|-----|---------|-------------|
| Monday | X | Tool tip / mini-tutorial (1 tool deep-dive) |
| Wednesday | Dev.to/Hashnode | Technical article (integration guide, use case) |
| Friday | Reddit | Community post (release notes, case study) |

You have 54 tools — that's 54 weeks of "Tool of the Week" content without repeating.

**Day 46–48: Video content**

Create 3–5 short videos (60–90 seconds each):
- "Watch Claude optimize my App Store keywords in 30 seconds"
- "How I track revenue impact of listing changes with AI"
- "Setting up App Store Connect MCP in 2 minutes"

Post to: TikTok, X (video), YouTube Shorts
These are your "make people stop scrolling" assets — show the magic, not the setup.

**Day 49–52: Community building**

- Discord server with channels: #general, #showcase, #feature-requests, #self-hosted-help, #cloud-support
- Weekly "Office Hours" (30 min, just you answering questions live on Discord)
- Create a "Wall of Wins" channel where users share ASO improvements
- GitHub Discussions enabled for the repo

**Day 53–56: Partnership outreach**

Reach out to:
1. **RevenueCat** — co-marketing opportunity. You're one of the few tools deeply integrating their API. Ask for a blog post feature or newsletter mention.
2. **MCP directory maintainers** — get featured/pinned
3. **ASO tool reviewers** — blogs that review ASO tools, pitch your AI-native angle
4. **iOS dev YouTubers** — offer a free Team account for a review/tutorial
5. **AI agent builders** — people building with Claude, OpenAI, etc. who have iOS apps

**Day 57–60: Retro & metrics check**

Target end-of-month metrics:
- 500+ GitHub stars
- 150+ cloud sign-ups
- 25–40 paying customers ($725–$1,580 MRR)
- 10+ pieces of content published
- 100+ Discord members
- RevenueCat or 1 other partnership in progress

---

## Phase 3: Scale & Differentiate (Days 61–90)

### Week 9–10: Google Play Console Expansion

**Day 61–68: Build Google Play Console MCP tools**

This is your "brand consolidation" move. Same audience, same pain, one product:

- `gpc_get_app_listing` — read Play Store listing
- `gpc_update_description` — update description
- `gpc_update_screenshots` — manage screenshots
- `gpc_get_listing_health` — health scoring
- `gpc_get_reviews` — review monitoring

Consider renaming the product to something broader once you have cross-platform support:
- Keep "App Store Connect MCP" for now (strong SEO, descriptive)
- Rebrand only when Google Play support ships and a short brand name is validated as available

New pricing angle:
- Pro: 1 platform (iOS or Android), $29/mo
- Team: Both platforms, $99/mo (price bump justified)
- Enterprise: Both + white-label, $249/mo

**Day 69–70: Cross-platform health reports**

Weekly email now shows: iOS health + Android health side by side. No other tool does this with AI agents.

---

### Week 11–12: Enterprise & Self-Serve Growth

**Day 71–75: Enterprise features**

- **SSO**: SAML/OAuth integration (use WorkOS — free up to 1M MAUs)
- **Audit log UI**: Expose your existing `changes.jsonl` as a searchable web dashboard
- **Role-based access**: Admin (full access) vs. Editor (no release/submit) vs. Viewer (read-only)
- **API rate limiting**: Per-tenant limits enforced at the gateway

**Day 76–78: Self-serve onboarding optimization**

By now you have data on where people drop off. Fix the top 3 friction points. Common ones:
- ASC API key generation is confusing → build a step-by-step wizard with screenshots
- RevenueCat setup is optional but valuable → add an "Enable Revenue Tracking" upsell prompt
- First tool call fails → add a `asc_test_connection` diagnostic tool

**Day 79–82: Referral & expansion revenue**

- **Referral program**: "Give $10, get $10" — Stripe coupon codes
- **Annual plans**: 20% discount for annual billing (improves cash flow, reduces churn)
- **Usage-based add-on**: $0.01 per API call beyond 10k/month (for heavy users)
- **OAuth for third parties**: Let other SaaS products connect to your hosted MCP (Postiz model — become infrastructure)

**Day 83–86: Second launch wave**

Now that you have Google Play support + paying customers + case studies:

- **Product Hunt re-launch**: "App Store Connect MCP 2.0 — AI-Native App Store Management for iOS & Android"
- **Hacker News**: "Show HN: I built an MCP server that manages App Store and Play Store listings"
- **New articles** with real customer metrics: "How [Customer] increased conversions 23% using AI-powered ASO"
- **TikTok/X push**: New demo videos showing cross-platform management

**Day 87–90: Retro & scaling plan**

Target end-of-90-days metrics:
- 1,000+ GitHub stars
- 300+ cloud sign-ups
- 60–100 paying customers ($2,500–$5,000+ MRR)
- 200+ Discord members
- Google Play support shipped
- 1–2 enterprise pilots in progress
- RevenueCat co-marketing live
- Clear path to $10k MRR by month 6

---

## Key Principles (Stolen from Nevo, Applied to You)

### 1. Be Different
You're not "another ASO tool." You're the **first AI-agent-native app store management platform**. Every competitor requires a human clicking buttons in a dashboard. You let Claude/GPT/any MCP client do it programmatically. That's your wedge.

### 2. Blue Ocean
Your market isn't "ASO tools" (crowded, dominated by Sensor Tower, AppTweak, etc.). Your market is **"AI agent infrastructure for mobile developers."** You're serving people who are already using Claude Code, Cursor, Codex — and happen to have iOS/Android apps. Nobody else is here.

### 3. Open Source = Trust
Keep the core open source forever. It's your distribution channel, your credibility, and your moat against copycats (they can clone the code but not the community, brand, or hosted infrastructure).

### 4. Revenue Correlation = Moat
The RevenueCat integration is your technical moat. No ASO tool shows "you changed keywords on Tuesday and subscriptions went up 15% by Friday." Build this story relentlessly.

### 5. One Product, Go Deep
Don't build a second product. Expand THIS product to cover more platforms (Google Play, then maybe Amazon Appstore, Huawei AppGallery). Same brand, same customers, more value, higher prices.

---

## Budget Estimate (90 Days)

| Item | Cost |
|------|------|
| Landing page design (Fiverr) | $150–300 |
| Domain name | $12–50 |
| Hosting (Railway/Fly.io) | $0–50/mo |
| Database (Supabase free tier) | $0 |
| Stripe fees | 2.9% + $0.30/txn |
| Mintlify docs (free tier) | $0 |
| PostHog analytics (free tier) | $0 |
| Cover image designs (Fiverr, 5x) | $50–100 |
| Video editing (if outsourced) | $100–200 |
| Discord (free) | $0 |
| **Total 90-day budget** | **$300–750** |

Revenue target at Day 90: $2,500–$5,000 MRR → profitable from Month 2.

---

## What to Do TODAY

1. Register your domain
2. Set up Stripe account with the 4 tiers
3. Start building the SSE transport layer in `src/index.py`
4. Post on X: "Building an AI-powered App Store management tool in public. Day 1."
5. Message 3 Fiverr designers for landing page quotes

The code is built. The hard part starts now.
