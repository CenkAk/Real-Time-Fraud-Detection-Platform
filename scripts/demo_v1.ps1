param(
    [string]$ApiBase = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
$demoId = [Guid]::NewGuid().ToString("N")
$demoUser = "demo-user-$demoId"
$lastPrediction = $null

Write-Host "Checking API readiness..."
Invoke-RestMethod "$ApiBase/health/ready" | ConvertTo-Json -Compress

Write-Host "Creating a deterministic velocity sequence..."
for ($index = 1; $index -le 9; $index++) {
    $body = @{
        transaction_id = "demo-$demoId-$index"
        user_id = $demoUser
        merchant_id = "demo-merchant"
        timestamp = [DateTime]::UtcNow.ToString("o")
        amount = 149.95
        currency = "USD"
        merchant_category = "electronics"
        country = "US"
        device_id = "demo-device"
        ip_address = "192.0.2.10"
        channel = "web"
    } | ConvertTo-Json
    $lastPrediction = Invoke-RestMethod `
        -Method Post `
        -Uri "$ApiBase/transactions" `
        -ContentType "application/json" `
        -Body $body
}

$lastPrediction | ConvertTo-Json -Depth 6
$transactionId = $lastPrediction.transaction_id

Write-Host "Waiting for the alert and SHAP explanation..."
$alert = $null
for ($attempt = 1; $attempt -le 20; $attempt++) {
    $alert = Invoke-RestMethod "$ApiBase/alerts?limit=100" |
        Where-Object { $_.transaction_id -eq $transactionId } |
        Select-Object -First 1
    if ($null -ne $alert -and $null -ne $alert.explanation) {
        break
    }
    Start-Sleep -Seconds 1
}

if ($null -eq $alert) {
    throw "No alert was created for $transactionId"
}

Invoke-RestMethod "$ApiBase/transactions/$transactionId/investigation" |
    ConvertTo-Json -Depth 10

Write-Host "Resolving the alert as confirmed fraud..."
$resolution = @{
    status = "RESOLVED"
    resolution = "FRAUD"
    analyst_note = "V1 demo verification"
} | ConvertTo-Json
Invoke-RestMethod `
    -Method Patch `
    -Uri "$ApiBase/alerts/$($alert.alert_id)" `
    -ContentType "application/json" `
    -Body $resolution | ConvertTo-Json -Depth 8

Write-Host "Demo complete. Open http://localhost:8501 to inspect the transaction."
