import tkinter as tk
from tkinter import messagebox, Listbox, Scrollbar
import requests
import subprocess
import os
import urllib.parse

class WindowsIPTVPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Windows IPTV Player")
        self.root.geometry("500x500")

        # Portal and MAC Input
        tk.Label(root, text="Enter IPTV Portal URL:").pack()
        self.portal_entry = tk.Entry(root, width=50)
        self.portal_entry.pack()

        tk.Label(root, text="Enter MAC Address:").pack()
        self.mac_entry = tk.Entry(root, width=50)
        self.mac_entry.pack()

        self.load_button = tk.Button(root, text="Fetch Channels", command=self.fetch_channels)
        self.load_button.pack()

        # Channel List
        self.channel_list = Listbox(root, width=60, height=10)
        self.channel_list.pack()

        scrollbar = Scrollbar(root)
        scrollbar.pack(side="right", fill="y")

        self.channel_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.channel_list.yview)

        self.play_button = tk.Button(root, text="Play", command=self.play_stream)
        self.play_button.pack()

        self.channels = []

    def fetch_channels(self):
        """Fetch IPTV channels using MAC authentication."""
        portal_url = self.portal_entry.get().strip()
        mac_address = self.mac_entry.get().strip()

        if not portal_url.endswith('/'):
            portal_url += '/'

        auth_url = f"{portal_url}server/load.php?type=stb&action=handshake&mac={mac_address}"
        channels_url = f"{portal_url}server/load.php?type=itv&action=get_all_channels&mac={mac_address}&JsHttpRequest=1-xml"

        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
            "Referer": portal_url + "index.html",
            "Origin": portal_url
        }

        try:
            auth_response = requests.get(auth_url, headers=headers)
            if auth_response.status_code != 200:
                messagebox.showerror("Error", "Failed to authenticate with the portal.")
                return

            channels_response = requests.get(channels_url, headers=headers)
            if channels_response.status_code != 200:
                messagebox.showerror("Error", "Failed to retrieve the channel list.")
                return

            data = channels_response.json().get("js", {}).get("data", [])
            if not data:
                messagebox.showerror("Error", "No channels found.")
                return

            # Extract the real stream URL
            self.channels = [(ch["name"], ch["cmd"].replace("ffmpeg ", "").strip()) for ch in data]


            self.channel_list.delete(0, tk.END)
            for channel in self.channels:
                self.channel_list.insert(tk.END, channel[0])

        except requests.RequestException as e:
            messagebox.showerror("Error", f"Failed to connect: {e}")

    def play_stream(self):
        selected_index = self.channel_list.curselection()
        if not selected_index:
            messagebox.showwarning("Warning", "Please select a channel to play.")
            return

        _, stream_url = self.channels[selected_index[0]]
        self.play_video(stream_url)

    def play_video(self, stream_url):
        print(f"Playing URL: {stream_url}")  # Debugging step

        ffplay_command = [
            "ffplay",
            "-i", stream_url,
            "-autoexit"
        ]
        subprocess.run(ffplay_command)


root = tk.Tk()
app = WindowsIPTVPlayer(root)
root.mainloop()