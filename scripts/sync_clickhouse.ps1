# ClickHouse Sync Script
# Syncs fqz_all_yy_yd from MySQL to ClickHouse

$ckHost = "121.196.219.211"
$ckPort = "8123"
$ckUser = "default"
$ckPass = "zmjk2018"

$myHost = "192.168.68.172:3308"
$myDb   = "fylqz_platform_new"
$myUser = "root"
$myPass = "62901990552"

# SQL to perform the sync
$sql = @"
INSERT INTO fqz_all_yy_yd
SELECT * FROM mysql('$myHost', '$myDb', 'fqz_all_yy_yd', '$myUser', '$myPass')
"@

Write-Host "Starting ClickHouse sync for table fqz_all_yy_yd..."
Write-Host "Target ClickHouse: ${ckHost}:${ckPort}"
Write-Host "Source MySQL: $myHost/$myDb"

# Use curl to call ClickHouse HTTP interface with query params
$url = "http://${ckHost}:${ckPort}/?user=${ckUser}&password=${ckPass}"
$response = curl.exe -s -d "$sql" "$url"

if ($LASTEXITCODE -eq 0) {
    Write-Host "Sync request successfully sent to ClickHouse."
    if ($response) {
        Write-Host "Response from ClickHouse: $response"
    } else {
        Write-Host "ClickHouse returned no message (usually means success for INSERT)."
    }
} else {
    Write-Error "Failed to send sync request to ClickHouse. Exit code: $LASTEXITCODE"
}
