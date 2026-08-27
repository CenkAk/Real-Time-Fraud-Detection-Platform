# Benchmarks

## Current status

The production benchmark protocol is implemented, but no result is published until all three
independent runs complete. The p95 `<100 ms` value is a target, not a measured claim.

## Reproducible protocol

- API levels: 10, 50 and 100 concurrent Locust users.
- Streaming levels: fixed 10, 50 and 100 events/second.
- Each level: 120 seconds warm-up followed by 300 seconds measured time.
- Repetitions: three independent runs per level.
- API outputs: average, p50, p95, p99, maximum latency, RPS and failure count.
- Streaming outputs: average, p50, p95, p99, maximum event latency, throughput and delivery ratio.
- Environment evidence: Docker resource snapshot, Docker/host versions, CPU and RAM.

Run the complete protocol from PowerShell:

```powershell
.\scripts\run_benchmarks.ps1
```

Raw results are written under `artifacts/benchmarks/` and must be reviewed before this document
is updated. Partial or shortened smoke runs are not production benchmark evidence.
