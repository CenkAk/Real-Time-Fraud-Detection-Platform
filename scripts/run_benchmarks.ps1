param(
    [int]$WarmupSeconds = 120,
    [int]$MeasureSeconds = 300,
    [int]$Repeats = 3
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$resultRoot = Join-Path $repositoryRoot "artifacts/benchmarks"
New-Item -ItemType Directory -Force -Path $resultRoot | Out-Null
Push-Location $repositoryRoot
try {
    $env:BENCHMARK_WARMUP_SECONDS = $WarmupSeconds
    $runSeconds = $WarmupSeconds + $MeasureSeconds
    foreach ($users in 10, 50, 100) {
        foreach ($repeat in 1..$Repeats) {
            $prefix = Join-Path $resultRoot "api-u$users-r$repeat"
            docker run --rm `
                --add-host host.docker.internal:host-gateway `
                --mount "type=bind,source=$repositoryRoot,target=/workspace" `
                -e BENCHMARK_WARMUP_SECONDS=$WarmupSeconds `
                -e PYTHONPATH=/workspace/src `
                -w /workspace `
                fraud-detection-platform-test `
                locust -f /workspace/locustfile.py --headless `
                --host http://host.docker.internal:8000 --users $users --spawn-rate $users `
                --run-time "${runSeconds}s" --csv $prefix
        }
    }
    foreach ($rate in 10, 50, 100) {
        foreach ($repeat in 1..$Repeats) {
            $containerOutput = "/workspace/artifacts/benchmarks/stream-eps$rate-r$repeat.json"
            docker run --rm `
                --add-host host.docker.internal:host-gateway `
                --mount "type=bind,source=$repositoryRoot,target=/workspace" `
                -e PYTHONPATH=/workspace/src `
                -w /workspace `
                fraud-detection-platform-test python /workspace/benchmarks/streaming_benchmark.py `
                --rate $rate --warmup-seconds $WarmupSeconds `
                --measure-seconds $MeasureSeconds `
                --bootstrap host.docker.internal:19092 --output $containerOutput
        }
    }
    docker stats --no-stream --format json | Set-Content `
        -LiteralPath (Join-Path $resultRoot "docker-stats.jsonl")
}
finally {
    Remove-Item Env:BENCHMARK_WARMUP_SECONDS -ErrorAction SilentlyContinue
    Pop-Location
}
