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
    def __init__(self, root: tk.Tk):
        self.root = root 
        self.root.title("Select IPTV User")
        self.root.geometry("400x250")
       
        

        # Ensure credentials directory exists
        if not os.path.exists(CREDENTIALS_DIR): 
            os.makedirs(CREDENTIALS_DIR)

        self.credentials = self.load_credentials()

        tk.Label(root, text="Select User:").pack() 
        
        self.selected_user = StringVar(root)

        # If no users exist, prompt the user to create one
        if not self.credentials:
            messagebox.showinfo("No Users Found", "No IPTV users found. Please create a new user.")
            self.root.destroy()
            NewUserWindow()
            return

        # Set the first available user as default
        self.selected_user.set(next(iter(self.credentials)))  

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
            messagebox.showinfo("No Users Found", "No IPTV users left. Please create a new user.")
            self.root.destroy()
            NewUserWindow()

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


class NewUserWindow:
    """New User Creation Window"""
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

         # Back Button
        self.back_button = tk.Button(self.root, text="Back", command=self.go_back, fg="red")
        self.back_button.pack()

    def save_user(self):
        """Save new user credentials."""
        portal_url = self.portal_entry.get().strip()
        mac_address = self.mac_entry.get().strip()
        

        if not portal_url or not mac_address:
            messagebox.showerror("Error", "Both fields must be filled.")
            return

        username = simpledialog.askstring("User Name", "Enter a name for this profile:")

        if not username:
            messagebox.showerror("Error", "User name is required.")
            return

        if not portal_url.endswith('/'):
            portal_url += '/'

        user_data = {"portal_url": portal_url, "mac_address": mac_address}
        with open(os.path.join(CREDENTIALS_DIR, f"{username}.json"), "w") as f:
            json.dump(user_data, f)

        messagebox.showinfo("Success", f"User '{username}' saved successfully!")
        self.root.destroy()  

        # Reopen user selection window
        root = tk.Tk()
        IPTVUserSelection(root)
        root.mainloop()

    def go_back(self):
        """Close the New User window and return to the user selection screen."""
        self.root.destroy()  # Close current window
        root = tk.Tk()
        IPTVUserSelection(root)  # Reopen user selection window

    

class WindowsIPTVPlayer:
    """Main IPTV Player GUI"""
    def __init__(self, root, user_data):
        self.root = root
        self.root.title("Windows IPTV Player")
        self.root.geometry("500x500")

        self.portal_url = user_data["portal_url"]
        self.mac_address = user_data["mac_address"]

        # Back Button
        self.back_button = tk.Button(root, text="Back", command=self.go_back, fg="red")
        self.back_button.pack()

        # Search Bar
        tk.Label(root, text="Search Channels:").pack()
        
        search_frame = tk.Frame(root)
        search_frame.pack()

        self.search_var = StringVar()
        self.search_entry = Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT)
        self.search_entry.bind("<KeyRelease>", self.search_channels)

        # SSC Button
        self.ssc_button = tk.Button(search_frame, text="SSC", command=lambda: self.set_search("ssc"))
        self.ssc_button.pack(side=tk.LEFT, padx=5)

        # BEIN Button
        self.bein_button = tk.Button(search_frame, text="BEIN", command=lambda: self.set_search("bein"))
        self.bein_button.pack(side=tk.LEFT, padx=5)

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

    def set_search(self, text):
        """Set the search box text and trigger the search."""
        self.search_var.set(text)
        self.search_channels()

    def go_back(self):
        """Close IPTV player and return to the user selection screen."""
        self.root.destroy()
        root = tk.Tk()
        IPTVUserSelection(root)
        root.mainloop()

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

            # Process stream URLs properly based on format
            self.channels = []
            for ch in data:
                name = ch["name"]
                cmd = ch["cmd"].replace("ffmpeg ", "").strip()
                
                # Check if the URL is a relative path or contains "localhost"
                if cmd.startswith("/") or "localhost" in cmd:
                    # Convert relative URL to absolute using portal URL
                    base_url = self.portal_url.rstrip('/')
                    # Extract the stream ID from the command
                    stream_id = cmd.split('/')[-1].rstrip('_')
                    
                    # Reconstruct the URL with proper parameters
                    stream_url = f"{base_url}/play/live.php?mac={self.mac_address}&stream={stream_id}&extension=ts"
                else:
                    # URL is already in correct format
                    stream_url = cmd
                
                self.channels.append((name, stream_url))

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
        
        # Get the directory where the executable is located
        if getattr(sys, 'frozen', False):
            # If running as compiled executable
            application_path = os.path.dirname(sys.executable)
        else:
            # If running as script
            application_path = os.path.dirname(os.path.abspath(__file__))
        
        # Path to ffplay relative to the executable
        ffplay_path = os.path.join(application_path, "ffplay.exe")
        
        ffplay_command = [
            ffplay_path,
            "-autoexit",
            "-x", "800",
            "-y", "600",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-sync", "ext",
            "-avioflags", "direct",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "2",
            "-loglevel", "quiet",
            "-i", stream_url
        ]
        subprocess.run(ffplay_command)


# Start Application
if __name__ == "__main__":
    root = tk.Tk()
    IPTVUserSelection(root)
    root.mainloop()
