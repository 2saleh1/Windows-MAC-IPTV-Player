@echo off
setlocal

:: Define FFmpeg version and directory
set FF_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
set FF_DIR=C:\ffmpeg

:: Download FFmpeg
echo Downloading FFmpeg...
powershell -Command "& {Invoke-WebRequest -Uri '%FF_URL%' -OutFile 'ffmpeg.zip'}"

:: Extract FFmpeg
echo Extracting FFmpeg...
tar -xf ffmpeg.zip -C C:\

:: Rename extracted folder to C:\ffmpeg
for /d %%i in (C:\ffmpeg-*) do rename "%%i" ffmpeg

:: Add FFmpeg to system PATH
echo Adding FFmpeg to system PATH...
powershell -Command "& {Start-Process powershell -ArgumentList 'Set-ExecutionPolicy Unrestricted -Scope Process; [System.Environment]::SetEnvironmentVariable(\"Path\", \"$Env:Path;C:\ffmpeg\bin\", [System.EnvironmentVariableTarget]::Machine)' -Verb RunAs}"

echo FFmpeg installation complete!
pause
