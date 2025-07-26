# Windows IPTV Player

A simple IPTV player for Windows using Python and Tkinter. Fetch and play IPTV channels using MAC authentication.

![Screenshot](Screenshot.png)

---

## Download

**Windows EXE:**  
[Download Player](https://github.com/2saleh1/Windows-MAC-IPTV-Player/releases/download/V1.0.2/MAC.IPTV.Player.exe)

---

## Features

- Save multiple IPTV users
- Search channels
- Delete users
- Play streams with ffplay

---

## Requirements

- Python 3.10+
- `requests` library
- FFmpeg (`ffplay`)

---

## Quick Start

1. **Install Python:**  
   [python.org/downloads](https://www.python.org/downloads/)

2. **Install dependencies:**  
   ```sh
   pip install -r requirements.txt
   ```

3. **Install FFmpeg:**  
   [ffmpeg.org/download.html](https://ffmpeg.org/download.html)  
   Add `C:\ffmpeg\bin` to PATH.

4. **Run the player:**  
   ```sh
   python player.py
   ```
   Or double-click `run.bat`.

---

## Build EXE (Optional)

```sh
pyinstaller --onefile --noconsole player.py
```
Find the EXE in the `dist` folder.

---

## FFplay Controls

- `0` / `9`: Volume up/down
- `m`: Mute
- `c`: Cycle audio channels
- `a`: Cycle audio tracks

---

## Notes

- Check portal URL and MAC address if channels don’t load.
- Make sure `ffplay` works from the command
