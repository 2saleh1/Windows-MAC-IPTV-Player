import tkinter as tk
from tkinter import messagebox, Listbox, Scrollbar, OptionMenu, StringVar, simpledialog

import requests
import subprocess
import os
import json
import urllib.parse


CREDENTIALS_DIR = "credentials"

class IPTVUserSelection:
    """First GUI - User Selection or New User Entry"""
    def __init__(self, root):
        self.root = root
        self.root.title("Select IPTV User")
        self.root.geometry("400x200")

        # Ensure credentials directory exists
        if not os.path.exists(CREDENTIALS_DIR):
            os.makedirs(CREDENTIALS_DIR)

        self.credentials = self.load_credentials()

        tk.Label(root, text="Select User:").pack()
        
        self.selected_user = StringVar(root)
        self.selected_user.set("Choose a user")  # Default option

        # User Dropdown
        self.user_menu = OptionMenu(root, self.selected_user, *self.credentials.keys())
        self.user_menu.pack()

        # Buttons
        self.start_button = tk.Button(root, text="Start", command=self.start_player)
        self.start_button.pack()

        self.new_button = tk.Button(root, text="New", command=self.open_new_user_window)
        self.new_button.pack()

    def load_credentials(self):
        """Load all saved user profiles from the credentials directory."""
        users = {}
        for filename in os.listdir(CREDENTIALS_DIR):
            if filename.endswith(".json"):
                with open(os.path.join(CREDENTIALS_DIR, filename), "r") as f:
                    data = json.load(f)
                    users[filename.replace(".json", "")] = data
        return users

    def start_player(self):
        """Start the IPTV Player with the selected user."""
        username = self.selected_user.get()
        if username not in self.credentials:
            messagebox.showwarning("Warning", "Please select a valid user.")
            return

        user_data = self.credentials[username]
        self.root.destroy()  # Close the selection menu
        self.launch_player(user_data)

    def open_new_user_window(self):
        """Open a window to add a new user."""
        self.root.destroy()
        NewUserWindow()

    def launch_player(self, user_data):
        """Launch IPTV Player with selected user data."""
        root = tk.Tk()
        WindowsIPTVPlayer(root, user_data)
        root.mainloop()


class NewUserWindow:
    """Second GUI - Create a New User Profile"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("New IPTV User")
        self.root.geometry("400x200")

        tk.Label(self.root, text="Enter IPTV Portal URL:").pack()
        self.portal_entry = tk.Entry(self.root, width=50)
        self.portal_entry.pack()

        tk.Label(self.root, text="Enter MAC Address:").pack()
        self.mac_entry = tk.Entry(self.root, width=50)
        self.mac_entry.pack()

        self.save_button = tk.Button(self.root, text="Save", command=self.save_user)
        self.save_button.pack()

    def save_user(self):
        """Save new user credentials."""
        portal_url = self.portal_entry.get().strip()
        mac_address = self.mac_entry.get().strip()

        if not portal_url or not mac_address:
            messagebox.showerror("Error", "Both fields must be filled.")
            return

        # Ask for a username
        username = simpledialog.askstring("User Name", "Enter a name for this profile:")


        if not username:
            messagebox.showerror("Error", "User name is required.")
            return

        # Ensure URL ends with "/"
        if not portal_url.endswith('/'):
            portal_url += '/'

        # Save user profile
        user_data = {"portal_url": portal_url, "mac_address": mac_address}
        with open(os.path.join(CREDENTIALS_DIR, f"{username}.json"), "w") as f:
            json.dump(user_data, f)

        messagebox.showinfo("Success", f"User '{username}' saved successfully!")
        self.root.destroy()  # Close this window

        # Reopen user selection window
        root = tk.Tk()
        IPTVUserSelection(root)
        root.mainloop()


class WindowsIPTVPlayer:
    """Main IPTV Player GUI"""
    def __init__(self, root, user_data):
        self.root = root
        self.root.title("Windows IPTV Player")
        self.root.geometry("500x500")

        self.portal_url = user_data["portal_url"]
        self.mac_address = user_data["mac_address"]

        # Channel List UI
        self.channel_list = Listbox(root, width=60, height=10)
        self.channel_list.pack()

        scrollbar = Scrollbar(root)
        scrollbar.pack(side="right", fill="y")

        self.channel_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.channel_list.yview)

        self.load_button = tk.Button(root, text="Fetch Channels", command=self.fetch_channels)
        self.load_button.pack()

        self.play_button = tk.Button(root, text="Play", command=self.play_stream)
        self.play_button.pack()

        self.channels = []

    def fetch_channels(self):
        """Fetch IPTV channels using MAC authentication."""
        auth_url = f"{self.portal_url}server/load.php?type=stb&action=handshake&mac={self.mac_address}"
        channels_url = f"{self.portal_url}server/load.php?type=itv&action=get_all_channels&mac={self.mac_address}&JsHttpRequest=1-xml"

        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
            "Referer": self.portal_url + "index.html",
            "Origin": self.portal_url
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
        print(f"Playing URL: {stream_url}")

        ffplay_command = [
            "ffplay",
            "-i", stream_url,
            "-autoexit"
        ]
        subprocess.run(ffplay_command)


# Start Application
if __name__ == "__main__":
    root = tk.Tk()
    IPTVUserSelection(root)
    root.mainloop()
