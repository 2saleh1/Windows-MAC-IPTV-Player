# Windows IPTV Player

A simple IPTV player for Windows using Python and Tkinter. Easily fetch and play IPTV channels using MAC authentication.

## Features
- Save multiple IPTV users
- Search for channels
- Delete saved users
- Play IPTV streams using `ffplay`

---

## Requirements
- Python 3.10 or newer
- `requests` library
- `ffplay` (part of FFmpeg)

---

## Installation
### 1️⃣ Install Python
Download and install Python from: [https://www.python.org/downloads/](https://www.python.org/downloads/)
Ensure `Add Python to PATH` is checked during installation.

### 2️⃣ Install Dependencies
Open a terminal (Command Prompt or PowerShell) and run:
```sh
pip install -r requirements.txt
```

### 3️⃣ Install FFmpeg (Required for Video Playback)
1. Download FFmpeg from: [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
2. Extract the folder (e.g., `C:\ffmpeg`)
3. Add `C:\ffmpeg\bin` to the system PATH
4. Verify by running:
```sh
ffplay -version
```

---

## Running the IPTV Player
Run the app using:
```sh
python player.py
```
Or double-click `run.bat` (if available).

---

## Building an Executable (Optional)
To create a standalone `.exe` file:
```sh
pyinstaller --onefile --noconsole player.py
```
The executable will be inside the `dist/` folder.

---
## FFplay Keyboard Controls
Volume Controls
- 0: Increase volume
- 9 (zero): Decrease volume
- m: Toggle mute

Audio Channel Controls
- c: Cycle through audio channels (mono, stereo, etc.)
- a: Cycle through audio tracks (when multiple audio tracks are available)

## Notes
- If IPTV channels do not load, check your portal URL and MAC address.
- Ensure `ffplay` is correctly installed and accessible from the command line.

---



