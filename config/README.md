# Configuration contract

`corpus.example.json` is a Phase 1 design example, not a runnable configuration. It records five source roles, proposed source-specific historical and incremental methods, corpus boundaries, free-only deployment rules, and the fact that Phase 2/3 have not started.

Before Phase 2: profile each source and topic, confirm API semantics and rate limits, estimate local storage, then freeze a versioned configuration. Do not interpret the 30,000–60,000 target as a hard cap or verified count. Each source must have its own watermark and independent run state.
