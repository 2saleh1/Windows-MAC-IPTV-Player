@echo off
setlocal

:: Define FFmpeg version and destination
set FF_VERSION=latest
set FF_DIR=C:\ffmpeg

:: Download and extract FFmpeg
echo Downloading FFmpeg...
powershell -Command "& {Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z' -OutFile 'ffmpeg.7z'}"

echo Extracting FFmpeg...
powershell -Command "& {Expand-Archive -Path 'ffmpeg.7z' -DestinationPath '%FF_DIR%' -Force}"

:: Add to system PATH
echo Adding FFmpeg to system PATH...
setx /M PATH "%FF_DIR%\ffmpeg-*\bin;%PATH%"

echo FFmpeg installation complete!
pause
