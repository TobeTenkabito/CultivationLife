# Dot-source this script before Gradle/SDK commands. All new caches stay on F:.
$androidTools = if ($env:CULTIVATION_ANDROID_TOOLS) { $env:CULTIVATION_ANDROID_TOOLS } else { 'F:\CultivationLife-Android-Tools' }
$env:ANDROID_HOME = Join-Path $androidTools 'sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:ANDROID_USER_HOME = Join-Path $androidTools 'android-user'
$env:ANDROID_EMULATOR_HOME = $env:ANDROID_USER_HOME
$env:ANDROID_AVD_HOME = Join-Path $androidTools 'avd'
$env:GRADLE_USER_HOME = Join-Path $androidTools 'gradle-cache'
$env:TEMP = Join-Path $androidTools 'temp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $androidTools 'pip-cache'
if (-not $env:JAVA_HOME -and (Test-Path 'D:\java\java17\bin\javac.exe')) { $env:JAVA_HOME = 'D:\java\java17' }
$env:CULTIVATION_BUILD_PYTHON = (Get-Command python).Source
$androidGradle = Join-Path $androidTools 'gradle-8.11.1\bin\gradle.bat'
$androidAdb = Join-Path $env:ANDROID_HOME 'platform-tools\adb.exe'
