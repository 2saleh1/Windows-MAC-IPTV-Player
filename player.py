import tkinter as tk
from tkinter import messagebox, Listbox, Scrollbar, OptionMenu, StringVar, simpledialog, Entry
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
        self.root.geometry("400x250")

        # Ensure credentials directory exists
        if not os.path.exists(CREDENTIALS_DIR):
            os.makedirs(CREDENTIALS_DIR)

        self.credentials = self.load_credentials()

        tk.Label(root, text="Select User:").pack()
        
        self.selected_user = StringVar(root)
        self.selected_user.set("Choose a user")  # Default option

        # Ensure there's at least one user in the dropdown
        if self.credentials:
            self.selected_user.set(next(iter(self.credentials)))  # Set the first user as default
        else:
            self.selected_user.set("No users available")  # Placeholder text

        # Create the dropdown menu
        self.user_menu = OptionMenu(root, self.selected_user, *self.credentials.keys())
        self.user_menu.pack()

        # Buttons
        self.start_button = tk.Button(root, text="Start", command=self.start_player)
        self.start_button.pack()

        self.new_button = tk.Button(root, text="New", command=self.open_new_user_window)
        self.new_button.pack()

        self.delete_button = tk.Button(root, text="Delete User", command=self.delete_user, fg="red")
        self.delete_button.pack()

    def load_credentials(self):
        """Load all saved user profiles from the credentials directory."""
        users = {}
        for filename in os.listdir(CREDENTIALS_DIR):
            if filename.endswith(".json"):
                with open(os.path.join(CREDENTIALS_DIR, filename), "r") as f:
                    data = json.load(f)
                    users[filename.replace(".json", "")] = data
        return users

    def update_user_menu(self):
        """Refresh the dropdown menu after adding or deleting users."""
        menu = self.user_menu["menu"]
        menu.delete(0, "end")  # Clear existing menu options

        self.credentials = self.load_credentials()  # Reload users
        for user in self.credentials.keys():
            menu.add_command(label=user, command=lambda value=user: self.selected_user.set(value))

        if self.credentials:
            self.selected_user.set(list(self.credentials.keys())[0])
        else:
            self.selected_user.set("Choose a user")

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

    def delete_user(self):
        """Delete the selected user profile."""
        username = self.selected_user.get()
        if username not in self.credentials:
            messagebox.showwarning("Warning", "Please select a valid user.")
            return

        confirm = messagebox.askyesno("Delete User", f"Are you sure you want to delete '{username}'?")
        if confirm:
            file_path = os.path.join(CREDENTIALS_DIR, f"{username}.json")
            os.remove(file_path)
            messagebox.showinfo("Deleted", f"User '{username}' has been deleted.")
            self.update_user_menu()

    def launch_player(self, user_data):
        """Launch IPTV Player with selected user data."""
        root = tk.Tk()
        WindowsIPTVPlayer(root, user_data)
        root.mainloop()


class WindowsIPTVPlayer:
    """Main IPTV Player GUI"""
    def __init__(self, root, user_data):
        self.root = root
        self.root.title("Windows IPTV Player")
        self.root.geometry("500x500")

        self.portal_url = user_data["portal_url"]
        self.mac_address = user_data["mac_address"]

        # Search Bar
        tk.Label(root, text="Search Channels:").pack()
        self.search_var = StringVar()
        self.search_entry = Entry(root, textvariable=self.search_var)
        self.search_entry.pack()
        self.search_entry.bind("<KeyRelease>", self.search_channels)

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

        self.channels = []  # Stores (name, url) tuples
        self.filtered_channels = []  # Stores channels filtered by search

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

            # Initially, display all channels
            self.filtered_channels = self.channels
            self.update_channel_list()

        except requests.RequestException as e:
            messagebox.showerror("Error", f"Failed to connect: {e}")

    def update_channel_list(self):
        """Update the Listbox with filtered channels."""
        self.channel_list.delete(0, tk.END)
        for channel in self.filtered_channels:
            self.channel_list.insert(tk.END, channel[0])

    def search_channels(self, event=None):
        """Filter channels based on the search query."""
        query = self.search_var.get().lower()
        if query:
            self.filtered_channels = [ch for ch in self.channels if query in ch[0].lower()]
        else:
            self.filtered_channels = self.channels
        self.update_channel_list()

    def play_stream(self):
        """Play the selected channel."""
        selected_index = self.channel_list.curselection()
        if not selected_index:
            messagebox.showwarning("Warning", "Please select a channel to play.")
            return

        _, stream_url = self.filtered_channels[selected_index[0]]
        self.play_video(stream_url)

    def play_video(self, stream_url):
        """Play IPTV stream using ffplay."""
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
