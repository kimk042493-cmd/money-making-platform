# money-making-platform
Legitimate online monetization platform with multiple revenue streams.

## Performance improvement opportunities

The current app is a small arithmetic starter with no database, API, or UI layer. Items 2–10 are roadmap candidates for when those parts of the platform exist, not measured bottlenecks in the current code.

1. Preserve hot memoized results under cache pressure with least-recently-used (LRU) eviction instead of flushing the entire cache. Implemented in `performance/cache.py`.
2. Batch database queries and API calls instead of issuing one request per user action.
3. Add targeted indexes on high-cardinality filters and join columns to reduce query latency.
4. Replace N+1 database patterns with eager loading or aggregated queries.
5. Move non-critical work to background jobs and queues so the request path stays fast.
6. Use CDN caching and edge compression for static assets, media, and API responses.
7. Compress and prune large payloads before sending them over the network.
8. Implement lazy loading for large lists, galleries, and dashboards to defer unnecessary rendering.
9. Simplify hot loops by reusing objects, avoiding repeated serialization, and reducing allocations.
10. Add read-through caching and TTL policies for high-traffic metadata and configuration endpoints.

## Recommended first action

Use the bounded LRU memoization helper for repeated, expensive, deterministic operations; avoid caching cheap arithmetic where cache overhead may exceed the work saved.

## Google Sheets export

Every calculation is recorded to a Google Sheet so there is a permanent history
of the math performed. `src/calculator.calculate()` runs the operation and then
appends a row (timestamp, operation, operands, result) through
`src/sheets.record_result()`.

Configure it with two environment variables:

| Variable | Meaning |
| --- | --- |
| `GOOGLE_SHEET_ID` | The id of the target spreadsheet (from its URL). |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | The service-account key, as raw JSON. A key file path via `GOOGLE_SERVICE_ACCOUNT_FILE` also works. |

Setup:

1. Create a Google Cloud service account and enable the Google Sheets API, then
   download a JSON key.
2. Create (or pick) a spreadsheet and share it with the service account's
   `client_email` as an **Editor**.
3. Provide the two variables above. `src/sheets.py` writes a header row on the
   first record.

When the variables are absent the recorder is a no-op, so calculations keep
working without credentials. A failed export is logged and never breaks a
calculation.
