# StorePilot / App Store Connect MCP — Documentation

This directory is the source for the docs site. It's structured to be
published with Mintlify or Docusaurus with minimal adaptation.

## Structure

```
docs/
├── README.md                 ← you are here
├── quick-start.md            ← 10-minute self-host walkthrough
├── self-host.md              ← detailed self-host setup + troubleshooting
├── cloud-setup.md            ← hosted cloud tier signup and API key flow
├── architecture.md           ← stdio vs cloud, tenancy, data flow
├── revenuecat-integration.md ← why and how to wire RevenueCat
├── change-impact.md          ← the revenue correlation moat, in depth
├── tool-reference/           ← one page per tool category
│   ├── reads.md
│   ├── writes.md
│   ├── versioning.md
│   ├── custom-product-pages.md
│   ├── analysis.md
│   ├── change-impact-tool.md
│   ├── diagnostics.md
│   ├── generic-api.md
│   └── subscriber.md
├── launch/                   ← internal launch artifacts
│   ├── article-1-automated-aso.md
│   ├── article-2-complete-guide.md
│   ├── article-3-broken-aso.md
│   └── product-hunt.md
└── 90-DAY-SAAS-PROFITABILITY-PLAN.md
```

## Publishing

For Mintlify:

```bash
npx mintlify init
# Point baseDirectory at this docs/ folder
npx mintlify dev
```

Mintlify's config maps directly onto this structure. If you'd rather
use Docusaurus, the filenames are all compatible; just add
`docusaurus.config.js` at the repo root.

## Contributing to docs

Docs follow the same MIT license as the code. If you spot an error,
open a PR — no CLA required.
