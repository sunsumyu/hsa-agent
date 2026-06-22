@echo off
set JAVA_HOME=F:\Program Files\Java\jdk-17
set PATH=%JAVA_HOME%\bin;%PATH%
mvn exec:java -pl hsa-agent -Dexec.mainClass="cn.hsa.fqz.agent.StressOfflineTest"
