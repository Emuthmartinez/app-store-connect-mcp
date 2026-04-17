# Change Impact Analysis

This is the feature that makes StorePilot different from every other
ASO tool. Here's how it works, how to use it, and its limits.

## The problem

You change your keywords. Did it move anything? Most ASO tools will
show you ranking movements or impression share. Neither of those is
the metric you care about: revenue.

Every listing mutation StorePilot executes is logged to
`data/changes.jsonl` with:

- Timestamp
- Operation (e.g. `update_keywords`)
- Locale
- Before / after diff of the changed fields
- A snapshot of your RevenueCat metrics **at the moment of the change**

Separately, the RevenueCat webhook listener and the `asc_refresh_subscriber_overview`
tool append to `data/revenuecat-overview-history.jsonl` — a time series
of your active subscriptions, active trials, and MRR.

## The tool

`asc_get_change_impact_analysis` takes:

- `before_days` (default 7): how many days of RevenueCat history to average before each change
- `after_days` (default 7): same, after the change
- `operation` (optional): filter to one operation type
- `locale` (optional): filter to one locale
- `limit` (default 20): how many recent mutations to analyze

For each matching mutation, it returns:

```json
{
  "operation": "update_keywords",
  "locale": "en-US",
  "timestamp": "2026-03-15T14:22:00+00:00",
  "change_summary": {
    "keywords": {
      "before": "outfit planner,closet",
      "after": "ai stylist,outfit planner,closet"
    }
  },
  "metrics_before": {
    "sample_size": 7,
    "active_subscriptions_avg": 820.0,
    "active_trials_avg": 45.0,
    "mrr_avg": 4100.0
  },
  "metrics_after": {
    "sample_size": 7,
    "active_subscriptions_avg": 970.0,
    "active_trials_avg": 54.0,
    "mrr_avg": 5005.0
  },
  "delta_pct": {
    "active_subscriptions": 18.3,
    "active_trials": 20.0,
    "mrr": 22.1
  }
}
```

## Caveats

> These deltas are correlational, not causal.

A lot of things move RevenueCat metrics: seasonality, marketing campaigns,
app store ranking shifts, competitors' launches, featured placements.
A keyword change followed by an 18% subscription lift is a **signal**,
not a proof.

Good uses:

- Comparing multiple keyword changes over time — which ones showed up
  as lifts vs. noise?
- Confirming that a description rewrite didn't *hurt* revenue
- Surfacing the top 3 changes that correlated with lifts, to study
  for patterns

Bad uses:

- Claiming causation in a marketing email
- Running a one-shot experiment where N=1
- Replacing proper A/B testing (use Product Page Optimization experiments
  for that — StorePilot has tools for those too)

## Recommended workflow

1. Make one listing change at a time. Batching changes makes the signal
   impossible to isolate.
2. Wait at least 7 days before analyzing (RevenueCat needs the window
   to be meaningful).
3. Run `asc_get_change_impact_analysis` with default parameters.
4. Look for *consistent* patterns across multiple similar changes, not
   single-shot outliers.

## Sample prompts

> "Run change impact analysis for my last 10 mutations, then summarize
> the 3 changes with the strongest positive MRR delta and explain what
> they have in common."

> "Compare the MRR delta for update_keywords operations vs.
> update_description operations over the last 90 days."

> "Was there any listing change in the last 6 weeks that correlated
> with a drop in active_subscriptions? If so, show me the diff and
> suggest a revert."

## Related

- [RevenueCat integration](./revenuecat-integration.md)
- [Tool reference: asc_get_change_impact_analysis](./tool-reference/change-impact-tool.md)
- [Weekly health reports](./cloud-setup.md#weekly-health-reports-team-tier)
  surface these deltas automatically.
