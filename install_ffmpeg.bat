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
mkdir "%FF_DIR%"
powershell -Command "& {Expand-Archive -Path 'ffmpeg.zip' -DestinationPath '%FF_DIR%' -Force}"

:: Move contents out of subfolder if necessary
for /d %%i in (%FF_DIR%\*) do ( 
    if exist "%%i\bin" (
        xcopy /E /H /Y "%%i\*" "%FF_DIR%\"
        rmdir /S /Q "%%i"
    )
)

:: Add FFmpeg to system PATH
echo Adding FFmpeg to system PATH...
setx PATH "%FF_DIR%\bin;%PATH%" /M

:: Clean up
del ffmpeg.zip

echo FFmpeg installation complete!
pause
