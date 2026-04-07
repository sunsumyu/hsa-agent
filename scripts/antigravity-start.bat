@echo off
set "JAVA_HOME=F:\Program Files\Java\jdk1.8.0_331"
set "MAVEN_HOME=F:\Program Files\apache-maven-3.8.6"
set "PATH=%JAVA_HOME%\bin;%MAVEN_HOME%\bin;%PATH%"

echo [Antigravity] Starting HsaFqzAliApplication...
echo [Antigravity] Using JAVA_HOME: %JAVA_HOME%
echo [Antigravity] Using MAVEN_HOME: %MAVEN_HOME%

cd /d "%~dp0"
call mvn spring-boot:run -pl hsa-main-ali -DskipTests

pause
