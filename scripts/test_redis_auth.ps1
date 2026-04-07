
$server = "192.168.68.172"
$port = 6379
$password = "zmjk2018"

Write-Host "Connecting to $server:$port..."
try {
    $client = New-Object System.Net.Sockets.TcpClient($server, $port)
    $stream = $client.GetStream()
    $reader = New-Object System.IO.StreamReader($stream)
    $writer = New-Object System.IO.StreamWriter($stream)
    $writer.AutoFlush = $true

    Write-Host "Sending AUTH command..."
    $writer.WriteLine("AUTH $password")
    
    $response = $reader.ReadLine()
    Write-Host "Redis Response: $response"

    if ($response -match "\+OK") {
        Write-Host "SUCCESS: Password is correct and required."
    } elseif ($response -match "ERR Client sent AUTH, but no password is set") {
        Write-Host "CONFIRMED: The server has NO password set."
    } else {
        Write-Host "FAILED: $response"
    }

    $client.Close()
} catch {
    Write-Host "ERROR: Could not connect to $server:$port - $($_.Exception.Message)"
}
