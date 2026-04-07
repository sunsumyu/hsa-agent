$driverPath = Get-ChildItem -Recurse E:\maven-repo -Filter "mysql-connector-j-*.jar" | Select-Object -First 1 -ExpandProperty FullName
if ($driverPath) {
    Write-Host "Found Driver: $driverPath"
    # Run the Java scanner and redirect to report
    java -cp ".;$driverPath" GetMySqlSchemaV2.java > mysql_scan_report.txt 2>&1
    Write-Host "Scan completed. Results in mysql_scan_report.txt"
} else {
    Write-Host "Driver not found in E:\maven-repo"
}
