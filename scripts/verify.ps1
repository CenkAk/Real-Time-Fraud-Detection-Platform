param(
    [switch]$Integration,
    [switch]$Frontend
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repositoryRoot
try {
    docker compose config --quiet
    docker build --target test --tag fraud-detection-platform-test .
    docker run --rm fraud-detection-platform-test python -m ruff check .
    docker run --rm fraud-detection-platform-test python -m mypy src apps pipelines
    if ($Integration) {
        docker run --rm `
            --mount type=bind,source=//var/run/docker.sock,target=/var/run/docker.sock `
            -e TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal `
            fraud-detection-platform-test python -m pytest
    }
    else {
        docker run --rm fraud-detection-platform-test python -m pytest -m "not integration"
    }

    if ($Frontend) {
        Push-Location "apps/web"
        try {
            npm.cmd ci
            npm.cmd run lint
            npm.cmd run typecheck
            $edgeExecutable = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            if (Test-Path -LiteralPath $edgeExecutable) {
                $env:PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH = $edgeExecutable
            }
            try {
                npm.cmd run test
            }
            finally {
                Remove-Item Env:PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH -ErrorAction SilentlyContinue
            }
            npm.cmd run build
        }
        finally {
            Pop-Location
        }
    }
}
finally {
    Pop-Location
}
