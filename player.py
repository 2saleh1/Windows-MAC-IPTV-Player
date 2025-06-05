import tkinter as tk
from tkinter import messagebox, Listbox, Scrollbar, OptionMenu, StringVar, simpledialog, Entry, filedialog
import requests
import subprocess
import os
import json
import urllib.parse
import time

CREDENTIALS_DIR = "credentials"
CACHE_DIR = "cache"

class M3UExportWindow:
    """M3U Export Options Window with 3 Simple Buttons"""
    def __init__(self, parent, channels, mac_address):
        self.parent = parent
        self.channels = channels
        self.mac_address = mac_address
        
        self.root = tk.Toplevel(parent.root)
        self.root.title("Export to M3U")
        self.root.geometry("400x300")
        self.root.grab_set()  # Make this window modal
        
        # Main frame
        main_frame = tk.Frame(self.root)
        main_frame.pack(padx=20, pady=20, fill='both', expand=True)
        
        tk.Label(main_frame, text="Choose Export Option:", font=("Arial", 14, "bold")).pack(pady=(0, 20))
        
        # Button 1: All Channels
        self.all_button = tk.Button(main_frame, text="All Channels", 
                                   command=self.export_all_channels,
                                   bg="#2196F3", fg="white", font=("Arial", 12, "bold"),
                                   width=20, height=2)
        self.all_button.pack(pady=10)
        
        # Button 2: SSC and BEIN
        self.sports_button = tk.Button(main_frame, text="SSC and BEIN", 
                                      command=self.export_ssc_bein,
                                      bg="#4CAF50", fg="white", font=("Arial", 12, "bold"),
                                      width=20, height=2)
        self.sports_button.pack(pady=10)
        
        # Button 3: Custom Keywords
        self.custom_button = tk.Button(main_frame, text="Choose What You Want", 
                                      command=self.export_custom,
                                      bg="#FF9800", fg="white", font=("Arial", 12, "bold"),
                                      width=20, height=2)
        self.custom_button.pack(pady=10)
        
        # Cancel button
        self.cancel_button = tk.Button(main_frame, text="Cancel", 
                                      command=self.root.destroy,
                                      bg="#f44336", fg="white", font=("Arial", 10),
                                      width=15)
        self.cancel_button.pack(pady=(20, 0))
    
    def export_all_channels(self):
        """Export all channels to M3U file"""
        self.export_to_m3u(self.channels, "all")
    
    def export_ssc_bein(self):
        """Export SSC and BEIN channels to M3U file"""
        filtered_channels = []
        for name, url in self.channels:
            name_lower = name.lower()
            if 'ssc' in name_lower or 'bein' in name_lower:
                filtered_channels.append((name, url))
        
        if not filtered_channels:
            messagebox.showwarning("Warning", "No SSC or BEIN channels found.")
            return
        
        self.export_to_m3u(filtered_channels, "ssc_bein")
    
    def export_custom(self):
        """Export channels based on custom user input"""
        # Ask user for keywords
        keywords_input = simpledialog.askstring(
            "Custom Filter", 
            "Enter keywords to filter channels (separated by commas):\nExample: news, sport, mbc",
            initialvalue=""
        )
        
        if not keywords_input:
            return  # User cancelled
        
        keywords = [kw.strip().lower() for kw in keywords_input.split(',') if kw.strip()]
        
        if not keywords:
            messagebox.showwarning("Warning", "No valid keywords entered.")
            return
        
        # Filter channels based on keywords
        filtered_channels = []
        for name, url in self.channels:
            name_lower = name.lower()
            if any(keyword in name_lower for keyword in keywords):
                filtered_channels.append((name, url))
        
        if not filtered_channels:
            messagebox.showwarning("Warning", f"No channels found matching keywords: {', '.join(keywords)}")
            return
        
        # Use the keywords for filename
        filter_name = '_'.join(keywords)
        self.export_to_m3u(filtered_channels, filter_name)
    
    def export_to_m3u(self, channels, export_type):
        """Export the given channels to M3U file"""
        if not channels:
            messagebox.showwarning("Warning", "No channels to export.")
            return
        
        # Generate default filename
        mac_clean = self.mac_address.replace(':', '').lower()
        default_filename = f"exported_playlist_{export_type}_{mac_clean}.m3u"
        
        # Ask user for save location
        file_path = filedialog.asksaveasfilename(
            defaultextension=".m3u",
            filetypes=[("M3U files", "*.m3u"), ("All files", "*.*")],
            initialfile=default_filename
        )
        
        if not file_path:
            return  # User cancelled
        
        try:
            # Generate M3U content
            m3u_content = "#EXTM3U\n"
            
            for channel_data in channels:
                channel_name = channel_data[0]
                # Use the basic URL for M3U (position 1), not the original command
                stream_url = channel_data[1]
                
                # Clean channel name for M3U format
                clean_name = channel_name.replace('\n', ' ').replace('\r', ' ')
                m3u_content += f"#EXTINF:-1,{clean_name}\n"
                m3u_content += f"{stream_url}\n"
            
            # Write to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(m3u_content)
            
            messagebox.showinfo("Success", 
                            f"Successfully exported {len(channels)} channels to:\n{file_path}")
            self.root.destroy()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export M3U file:\n{str(e)}")


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
        self.root.geometry("500x600")

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

        # Buttons frame
        buttons_frame = tk.Frame(root)
        buttons_frame.pack(pady=10)

        self.load_button = tk.Button(buttons_frame, text="Fetch Channels", command=self.fetch_channels)
        self.load_button.pack(side=tk.LEFT, padx=5)

        self.play_button = tk.Button(buttons_frame, text="Play", command=self.play_stream)
        self.play_button.pack(side=tk.LEFT, padx=5)

        # Export to M3U button
        self.export_button = tk.Button(buttons_frame, text="Export to M3U", command=self.open_export_window, 
                                     bg="green", fg="white", font=("Arial", 10, "bold"))
        self.export_button.pack(side=tk.LEFT, padx=5)

        # Clear Cache button
        self.clear_cache_button = tk.Button(buttons_frame, text="Clear Cache", command=self.clear_cache, fg="red")
        self.clear_cache_button.pack(side=tk.LEFT, padx=5)

        self.channels = []  # Stores (name, url) tuples
        self.filtered_channels = []  # Stores channels filtered by search
        self.cache_file = os.path.join(CACHE_DIR, f"{self.mac_address.replace(':', '_')}_channels.json")
        
        # Create cache directory if it doesn't exist
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        
        # Try to load channels from cache
        self.load_from_cache()

    def open_export_window(self):
        """Open the M3U export options window"""
        if not self.channels:
            messagebox.showwarning("Warning", "Please fetch channels first before exporting.")
            return
        
        M3UExportWindow(self, self.channels, self.mac_address)
        
    def load_from_cache(self):
        """Load channels from cache file if it exists"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cached_data = json.load(f)
                    self.channels = cached_data
                    self.filtered_channels = self.channels
                    self.update_channel_list()
                    return True
            except Exception as e:
                print(f"Error loading cache: {e}")
        return False

    def save_to_cache(self):
        """Save channels to cache file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.channels, f)
        except Exception as e:
            print(f"Error saving cache: {e}")

    def clear_cache(self):
        """Delete the cache file"""
        if os.path.exists(self.cache_file):
            try:
                os.remove(self.cache_file)
                messagebox.showinfo("Success", "Cache cleared successfully!")
                self.channels = []
                self.filtered_channels = []
                self.update_channel_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear cache: {e}")
        else:
            messagebox.showinfo("Info", "No cache file exists.")

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
        
    def get_stream_link(self, cmd):
        """Get the actual stream link using create_link API"""
        create_link_url = f"{self.portal_url}server/load.php?type=itv&action=create_link&mac={self.mac_address}&cmd={urllib.parse.quote(cmd)}&JsHttpRequest=1-xml"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
            "Referer": self.portal_url + "index.html",
            "Origin": self.portal_url.rstrip('/'),
            "Accept": "*/*",
            "Cache-Control": "no-cache"
        }
        
        try:
            response = requests.get(create_link_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json().get('js', {})
                real_cmd = data.get('cmd', '')
                if real_cmd and real_cmd != cmd:
                    print(f"Real stream URL from create_link: {real_cmd}")
                    return real_cmd
        except Exception as e:
            print(f"Error getting stream link: {e}")
        
        return None

    def fetch_channels(self):
        """Fetch IPTV channels using MAC authentication."""
        auth_url = f"{self.portal_url}server/load.php?type=stb&action=handshake&mac={self.mac_address}"
        channels_url = f"{self.portal_url}server/load.php?type=itv&action=get_all_channels&mac={self.mac_address}&JsHttpRequest=1-xml"

        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
            "Referer": self.portal_url + "index.html",
            "Origin": self.portal_url.rstrip('/'),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }

        try:
            # Create a session to maintain cookies
            session = requests.Session()
            session.headers.update(headers)
            
            # First, perform handshake
            auth_response = session.get(auth_url)
            if auth_response.status_code != 200:
                messagebox.showerror("Error", "Failed to authenticate with the portal.")
                return

            # Extract token if available
            auth_data = auth_response.json() if auth_response.text.strip().startswith('{') else {}
            token = auth_data.get('js', {}).get('token', '')
            
            # Add token to subsequent requests if available
            if token:
                channels_url += f"&token={token}"

            channels_response = session.get(channels_url)
            if channels_response.status_code != 200:
                messagebox.showerror("Error", "Failed to retrieve the channel list.")
                return

            data = channels_response.json().get("js", {}).get("data", [])
            if not data:
                messagebox.showerror("Error", "No channels found.")
                return

            # Process stream URLs with basic logic only (no API calls per channel)
            self.channels = []
            
            # Extract portal domain for localhost replacement
            from urllib.parse import urlparse
            parsed_portal = urlparse(self.portal_url)
            portal_domain = parsed_portal.netloc
            
            for ch in data:
                name = ch["name"]
                original_cmd = ch["cmd"].replace("ffmpeg ", "").strip()
                
                # Store the original command - we'll resolve the real URL when playing
                # Just do basic localhost replacement for now
                if original_cmd.startswith("http://localhost"):
                    stream_url = original_cmd.replace("http://localhost", f"http://{portal_domain}")
                elif original_cmd.startswith("localhost"):
                    stream_url = f"http://{portal_domain}" + original_cmd[9:]
                elif original_cmd.startswith("/"):
                    stream_url = f"http://{portal_domain}{original_cmd}"
                elif original_cmd.startswith("http://") or original_cmd.startswith("https://"):
                    stream_url = original_cmd
                else:
                    stream_url = f"http://{portal_domain}/{original_cmd}"
                
                # Store both the processed URL and the original command for later use
                self.channels.append((name, stream_url, original_cmd))

            # Save to cache after successful fetch
            self.save_to_cache()

            # Initially, display all channels
            self.filtered_channels = self.channels
            self.update_channel_list()

        except requests.RequestException as e:
            messagebox.showerror("Error", f"Failed to connect: {e}")
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid response format: {e}")
        
        
    def update_channel_list(self):
        """Update the Listbox with filtered channels."""
        self.channel_list.delete(0, tk.END)
        for channel in self.filtered_channels:
            self.channel_list.insert(tk.END, channel[0])  # Always use the first element (name)

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

        if len(self.filtered_channels[selected_index[0]]) == 3:
            # New format with original_cmd
            _, stream_url, original_cmd = self.filtered_channels[selected_index[0]]
            
            # Try to get the real stream URL using create_link
            print(f"Getting real stream URL for: {original_cmd}")
            real_stream_url = self.get_stream_link(original_cmd)
            
            if real_stream_url:
                # Clean the real stream URL
                clean_url = real_stream_url.replace("ffmpeg ", "").strip()
                if clean_url.startswith("http://") or clean_url.startswith("https://"):
                    final_url = clean_url
                else:
                    from urllib.parse import urlparse
                    parsed_portal = urlparse(self.portal_url)
                    portal_domain = parsed_portal.netloc
                    final_url = f"http://{portal_domain}{clean_url}" if clean_url.startswith("/") else f"http://{portal_domain}/{clean_url}"
            else:
                # Fallback to the basic URL
                final_url = stream_url
        else:
            # Old format compatibility
            _, final_url = self.filtered_channels[selected_index[0]]
        
        self.play_video(final_url)

    def play_video(self, stream_url):
        """Play IPTV stream using ffplay with proper headers."""
        print(f"Playing URL: {stream_url}")

        # Add proper headers for authentication
        user_agent = "Mozilla/5.0 (QtEmbedded; U; Linux; C)"
        referer = self.portal_url + "index.html"
        
        ffplay_command = [
            "ffplay",
            "-autoexit",
            "-x", "800",
            "-y", "600",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-sync", "ext",
            "-avioflags", "direct",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "2",
            "-user_agent", user_agent,
            "-headers", f"Referer: {referer}",
            "-loglevel", "error",  # Changed from quiet to error to see what's happening
            "-i", stream_url
        ]
        
        try:
            result = subprocess.run(ffplay_command, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"FFplay error: {result.stderr}")
                messagebox.showerror("Playback Error", f"Failed to play stream:\n{result.stderr}")
        except Exception as e:
            print(f"Exception running ffplay: {e}")
            messagebox.showerror("Error", f"Failed to start player: {e}")


# Start Application
if __name__ == "__main__":
    root = tk.Tk()
    IPTVUserSelection(root)
    root.mainloop()
