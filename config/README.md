# Corpus configuration example

[corpus.example.json](corpus.example.json) makes the proposed source boundary visible. It is an illustrative configuration contract; no loader or ETL pipeline exists yet.

Before implementing extraction:

1. Inspect the candidate topic definitions and source work-type vocabulary.
2. Measure complete topic and year partition counts.
3. Finalize the inclusion rules and replace the draft corpus version.
4. Set the partial-year cutoff to the intended extraction window.
5. Recheck API access policies and enforce a free-budget stop in the client.

The work-count target is not permission to truncate a query. The byte thresholds trigger review. They are proposed operating limits, not measured resource requirements.

Keep credentials in a local ignored environment file. Never put an API key in this JSON.
