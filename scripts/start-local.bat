@echo off
title Start HsaFqzAliApplication
set "JAVA_HOME=F:\Program Files\Java\jdk1.8.0_331"
set "PATH=%JAVA_HOME%\bin;%PATH%"

echo ===================================================
echo Checking Java Environment...
java -version
echo ===================================================

echo.
echo Starting hsa-main-ali module via Maven...
echo.

call mvn clean install -Dmaven.repo.local="F:\maven-repo" -DskipTests
call mvn spring-boot:run -Dmaven.repo.local="F:\maven-repo" -Dspring-boot.run.jvmArguments="-Dfile.encoding=UTF-8 -Dspring.profiles.active=local -Dcom.taobao.pandora.boot.loader.check=false -Dspring.cloud.alicloud.acm.enabled=false -Daddress.server.port=54321 -Dspring.cloud.alicloud.acm.endpoint=127.0.0.1:54321 -Dlogging.level.org.springframework.cloud.alicloud.acm.bootstrap.AcmPropertySourceBuilder=OFF -Dlogging.level.com.taobao.diamond=OFF -Dspring.freemarker.template-loader-path=file:E:/Uploadfile/" -pl hsa-main-ali

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Maven build failed. Check logs above.
)

echo.
pause
