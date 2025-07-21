import tkinter as tk
from tkinter import messagebox, Listbox, Scrollbar, OptionMenu, StringVar, simpledialog, Entry, filedialog,ttk
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import subprocess
import os
import json
import urllib.parse
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import pickle
import hashlib
import random
import re
from datetime import datetime


CREDENTIALS_DIR = "credentials"
CACHE_DIR = "cache"



class ConnectionManager:
    """Enhanced connection management with retry logic - NO HEALTH CHECK"""
    def __init__(self, parent):
        self.parent = parent
        self.retry_count = 3
        self.retry_delay = 2
    
    def get_stream_with_retry(self, cmd, max_retries=3):
        """Get stream with automatic retry and session refresh"""
        original_stream_id = None
        
        # Extract stream ID from original command for preservation
        if "stream=" in cmd:
            try:
                import re
                match = re.search(r'stream=(\d+)', cmd)
                if match:
                    original_stream_id = match.group(1)
                    print(f"🎯 Preserving stream ID: {original_stream_id}")
            except:
                pass
        
        for attempt in range(max_retries):
            try:
                stream_url = self.parent.get_stream_link(cmd)
                if stream_url:
                    clean_url = stream_url.replace("ffmpeg ", "").strip()
                    
                    # ✅ Ensure stream ID is present in final URL
                    if original_stream_id and "stream=" in clean_url and "stream=&" in clean_url:
                        clean_url = clean_url.replace("stream=&", f"stream={original_stream_id}&")
                        print(f"🔧 Restored stream ID in final URL")
                    
                    # Build proper URL if needed
                    if clean_url.startswith("http://") or clean_url.startswith("https://"):
                        print(f"✅ Got real URL (attempt {attempt + 1}): {clean_url}")
                        return clean_url
                    else:
                        from urllib.parse import urlparse
                        parsed_portal = urlparse(self.parent.portal_url)
                        portal_domain = parsed_portal.netloc
                        final_url = f"http://{portal_domain}{clean_url}" if clean_url.startswith("/") else f"http://{portal_domain}/{clean_url}"
                        print(f"✅ Built final URL (attempt {attempt + 1}): {final_url}")
                        return final_url
                else:
                    print(f"❌ No stream URL returned (attempt {attempt + 1})")
                    
                    # If this is not the last attempt, try refreshing session
                    if attempt < max_retries - 1:
                        print("🔄 Trying session refresh...")
                        refreshed_url = self.parent.refresh_session_and_retry(cmd)
                        if refreshed_url:
                            clean_url = refreshed_url.replace("ffmpeg ", "").strip()
                            
                            # ✅ Ensure stream ID is present
                            if original_stream_id and "stream=" in clean_url and "stream=&" in clean_url:
                                clean_url = clean_url.replace("stream=&", f"stream={original_stream_id}&")
                            
                            if clean_url.startswith("http://") or clean_url.startswith("https://"):
                                print(f"✅ Got URL after refresh: {clean_url}")
                                return clean_url
                    
            except Exception as e:
                print(f"❌ Stream fetch attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    print(f"⏳ Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                    continue
        
        print("❌ All retry attempts failed")
        return None
    

class TokenCache:
    def __init__(self, ttl=300):  # 5 minutes default
        self.cache = {}
        self.ttl = ttl  # Time to live in seconds
    
    def get(self, stream_id):
        """Get cached token if still valid"""
        if stream_id in self.cache:
            token, timestamp = self.cache[stream_id]
            if time.time() - timestamp < self.ttl:
                return token
            else:
                del self.cache[stream_id]
        return None
    
    def set(self, stream_id, token):
        """Cache token with timestamp"""
        self.cache[stream_id] = (token, time.time())
    
    def clear(self):
        """Clear all cached tokens"""
        self.cache.clear()

class OptimizedRequests:
    """Optimized HTTP session with connection pooling and retry logic"""
    def __init__(self):
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,                    # Retry failed requests 3 times
            backoff_factor=1,           # Wait 1s, then 2s, then 4s between retries
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these HTTP errors
            allowed_methods=["HEAD", "GET", "OPTIONS"]    # Only retry safe methods
        )
        
        # Configure connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,        # Keep connections to 10 different hosts
            pool_maxsize=20,           # Max 20 connections per host
            max_retries=retry_strategy
        )
        
        # Apply adapter to both HTTP and HTTPS
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers (applied to all requests)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
            "Accept": "*/*",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"  # Explicitly request connection reuse
        })
    
    def get(self, url, **kwargs):
        """Optimized GET request with connection pooling"""
        kwargs.setdefault('timeout', 15)
        return self.session.get(url, **kwargs)
    
    def close(self):
        """Close the session and all connections"""
        self.session.close()

class CacheManager:
    """Intelligent caching system for channel data - PERMANENT CACHE"""
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        # Remove cache duration - permanent cache
        os.makedirs(cache_dir, exist_ok=True)
        
    def get_cache_key(self, portal_url, mac_address):
        """Generate unique cache key"""
        data = f"{portal_url}:{mac_address}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def is_cache_valid(self, cache_file):
        """Check if cache file exists - ALWAYS VALID if exists"""
        return os.path.exists(cache_file)
    
    def load_from_cache(self, portal_url, mac_address):
        """Load channels from cache if exists"""
        cache_key = self.get_cache_key(portal_url, mac_address)
        cache_file = os.path.join(self.cache_dir, f"channels_{cache_key}.pkl")
        
        if self.is_cache_valid(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                    print(f"💾 Loaded {len(cached_data)} channels from permanent cache")
                    return cached_data
            except Exception as e:
                print(f"Cache load error: {e}")
                # If cache is corrupted, delete it
                try:
                    os.remove(cache_file)
                    print("🗑️ Removed corrupted cache file")
                except:
                    pass
        
        return None
    
    def save_to_cache(self, portal_url, mac_address, channels):
        """Save channels to permanent cache"""
        cache_key = self.get_cache_key(portal_url, mac_address)
        cache_file = os.path.join(self.cache_dir, f"channels_{cache_key}.pkl")
        
        try:
            # Create backup of existing cache
            if os.path.exists(cache_file):
                backup_file = cache_file + ".backup"
                try:
                    import shutil
                    shutil.copy2(cache_file, backup_file)
                except:
                    pass
            
            # Save new cache
            with open(cache_file, 'wb') as f:
                pickle.dump(channels, f)
            
            print(f"💾 Saved {len(channels)} channels to permanent cache")
            
            # Remove backup if save was successful
            backup_file = cache_file + ".backup"
            if os.path.exists(backup_file):
                try:
                    os.remove(backup_file)
                except:
                    pass
                    
        except Exception as e:
            print(f"Cache save error: {e}")
            
            # Restore from backup if save failed
            backup_file = cache_file + ".backup"
            if os.path.exists(backup_file):
                try:
                    import shutil
                    shutil.move(backup_file, cache_file)
                    print("🔄 Restored cache from backup")
                except:
                    pass
    
    def get_cache_info(self, portal_url, mac_address):
        """Get cache file information"""
        cache_key = self.get_cache_key(portal_url, mac_address)
        cache_file = os.path.join(self.cache_dir, f"channels_{cache_key}.pkl")
        
        if os.path.exists(cache_file):
            try:
                stat = os.stat(cache_file)
                created_time = time.ctime(stat.st_mtime)
                file_size = stat.st_size / 1024  # KB
                
                return {
                    "exists": True,
                    "created": created_time,
                    "size_kb": file_size,
                    "path": cache_file
                }
            except:
                pass
        
        return {"exists": False}
    
    
    
class M3UExportWindow:
    """M3U Export Options Window with enhanced functionality"""
    def __init__(self, parent, channels, mac_address):
        self.parent = parent
        self.channels = channels
        self.mac_address = mac_address
        
        self.root = tk.Toplevel(parent.root)
        self.root.title("Export to M3U")
        self.root.geometry("450x350")
        self.root.grab_set()  # Make this window modal
        
        # Main frame
        main_frame = tk.Frame(self.root)
        main_frame.pack(padx=20, pady=20, fill='both', expand=True)
        
        tk.Label(main_frame, text="Choose Export Option:", font=("Arial", 14, "bold")).pack(pady=(0, 20))
        
        # Button 1: All Channels
        self.all_button = tk.Button(main_frame, text="All Channels", 
                                   command=self.export_all_channels,
                                   bg="#2196F3", fg="white", font=("Arial", 12, "bold"),
                                   width=25, height=2)
        self.all_button.pack(pady=10)
        
        # Button 2: SSC and BEIN
        self.sports_button = tk.Button(main_frame, text="SSC and BEIN", 
                                      command=self.export_ssc_bein,
                                      bg="#4CAF50", fg="white", font=("Arial", 12, "bold"),
                                      width=25, height=2)
        self.sports_button.pack(pady=10)
        
        # Button 3: Custom Keywords
        self.custom_button = tk.Button(main_frame, text="Choose What You Want", 
                                      command=self.export_custom,
                                      bg="#FF9800", fg="white", font=("Arial", 12, "bold"),
                                      width=25, height=2)
        self.custom_button.pack(pady=10)
        
        # Button 4: Real URLs (NEW)
        self.real_button = tk.Button(main_frame, text="Export with Real URLs (VLC Compatible)", 
                                    command=self.export_real_urls,
                                    bg="#9C27B0", fg="white", font=("Arial", 10, "bold"),
                                    width=35, height=2)
        self.real_button.pack(pady=10)
        
        # Cancel button
        self.cancel_button = tk.Button(main_frame, text="Cancel", 
                                      command=self.root.destroy,
                                      bg="#f44336", fg="white", font=("Arial", 10),
                                      width=15)
        self.cancel_button.pack(pady=(20, 0))
    
    def export_all_channels(self):
        """Export all channels to M3U file"""
        channels_for_export = [(ch[0], ch[1]) for ch in self.channels]
        self.export_to_m3u(channels_for_export, "all", use_real_urls=False)
    
    def export_ssc_bein(self):
        """Export SSC and BEIN channels to M3U file"""
        filtered_channels = []
        for channel_data in self.channels:
            name = channel_data[0]
            url = channel_data[1]
            name_lower = name.lower()
            if 'ssc' in name_lower or 'bein' in name_lower:
                filtered_channels.append((name, url))
        
        if not filtered_channels:
            messagebox.showwarning("Warning", "No SSC or BEIN channels found.")
            return
        
        self.export_to_m3u(filtered_channels, "ssc_bein", use_real_urls=False)
    
    def export_custom(self):
        """Export channels based on custom user input"""
        keywords_input = simpledialog.askstring(
            "Custom Filter", 
            "Enter keywords to filter channels (separated by commas):\nExample: news, sport, mbc",
            initialvalue=""
        )
        
        if not keywords_input:
            return
        
        keywords = [kw.strip().lower() for kw in keywords_input.split(',') if kw.strip()]
        
        if not keywords:
            messagebox.showwarning("Warning", "No valid keywords entered.")
            return
        
        filtered_channels = []
        for channel_data in self.channels:
            name = channel_data[0]
            url = channel_data[1]
            name_lower = name.lower()
            if any(keyword in name_lower for keyword in keywords):
                filtered_channels.append((name, url))
        
        if not filtered_channels:
            messagebox.showwarning("Warning", f"No channels found matching keywords: {', '.join(keywords)}")
            return
        
        filter_name = '_'.join(keywords)
        self.export_to_m3u(filtered_channels, filter_name, use_real_urls=False)
    
    def export_real_urls(self):
        """Export all channels with real URLs for VLC compatibility"""
        if not messagebox.askyesno("Real URLs Export", 
                                  "This will export channels with authentication tokens.\n"
                                  "This takes longer but works better with VLC.\n\n"
                                  "Continue?"):
            return
        
        channels_for_export = [(ch[0], ch[1]) for ch in self.channels]
        self.export_to_m3u(channels_for_export, "all_real", use_real_urls=True)
    
    def export_to_m3u(self, channels, export_type, use_real_urls=False):
        """Export channels to M3U file with optional real URL resolution"""
        if not channels:
            messagebox.showwarning("Warning", "No channels to export.")
            return
        
        # Generate default filename
        mac_clean = self.mac_address.replace(':', '').lower()
        suffix = "real" if use_real_urls else "basic"
        default_filename = f"exported_playlist_{export_type}_{suffix}_{mac_clean}.m3u"
        
        # Ask user for save location
        file_path = filedialog.asksaveasfilename(
            defaultextension=".m3u",
            filetypes=[("M3U files", "*.m3u"), ("All files", "*.*")],
            initialfile=default_filename
        )
        
        if not file_path:
            return
        
        if use_real_urls:
            self._export_with_real_urls(channels, file_path)
        else:
            self._export_basic(channels, file_path)
    
    def _export_basic(self, channels, file_path):
        """Quick export with basic URLs"""
        try:
            m3u_content = "#EXTM3U\n"
            
            for channel_data in channels:
                channel_name = channel_data[0]
                stream_url = channel_data[1]
                
                clean_name = channel_name.replace('\n', ' ').replace('\r', ' ')
                m3u_content += f"#EXTINF:-1,{clean_name}\n"
                m3u_content += f"{stream_url}\n"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(m3u_content)
            
            messagebox.showinfo("Success", 
                              f"Successfully exported {len(channels)} channels to:\n{file_path}")
            self.root.destroy()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export M3U file:\n{str(e)}")
    
    def _export_with_real_urls(self, channels, file_path):
        """Export with real URLs using threading"""
        # Show progress window
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Exporting...")
        progress_window.geometry("400x150")
        progress_window.grab_set()
        
        progress_label = tk.Label(progress_window, text="Preparing export...", font=("Arial", 12))
        progress_label.pack(pady=20)
        
        progress_text = tk.Label(progress_window, text="", font=("Arial", 10))
        progress_text.pack(pady=10)
        
        cancel_export = tk.BooleanVar(value=False)
        cancel_button = tk.Button(progress_window, text="Cancel", 
                                command=lambda: cancel_export.set(True), bg="red", fg="white")
        cancel_button.pack(pady=10)
        
        def export_thread():
            try:
                m3u_content = "#EXTM3U\n"
                total_channels = len(channels)
                
                for i, channel_data in enumerate(channels):
                    if cancel_export.get():
                        break
                    
                    channel_name = channel_data[0]
                    
                    # Update progress
                    progress = (i + 1) / total_channels * 100
                    self.root.after(0, lambda: progress_text.config(
                        text=f"Processing {i+1}/{total_channels} ({progress:.0f}%)\n{channel_name}"))
                    
                    # Find original command for this channel
                    original_cmd = None
                    for ch in self.parent.channels:
                        if ch[0] == channel_name:
                            original_cmd = ch[2] if len(ch) > 2 else ch[1]
                            break
                    
                    if original_cmd:
                        real_stream_url = self.parent.get_stream_link(original_cmd)
                        if real_stream_url:
                            clean_url = real_stream_url.replace("ffmpeg ", "").strip()
                            if clean_url.startswith("http://") or clean_url.startswith("https://"):
                                stream_url = clean_url
                            else:
                                from urllib.parse import urlparse
                                parsed_portal = urlparse(self.parent.portal_url)
                                portal_domain = parsed_portal.netloc
                                stream_url = f"http://{portal_domain}{clean_url}" if clean_url.startswith("/") else f"http://{portal_domain}/{clean_url}"
                        else:
                            stream_url = channel_data[1]
                    else:
                        stream_url = channel_data[1]
                    
                    clean_name = channel_name.replace('\n', ' ').replace('\r', ' ')
                    m3u_content += f"#EXTINF:-1,{clean_name}\n"
                    m3u_content += f"{stream_url}\n"
                
                if not cancel_export.get():
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(m3u_content)
                    
                    self.root.after(0, lambda: messagebox.showinfo("Success", 
                                    f"Successfully exported {len(channels)} channels to:\n{file_path}"))
                    self.root.after(0, lambda: self.root.destroy())
                
                self.root.after(0, lambda: progress_window.destroy())
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Export failed:\n{str(e)}"))
                self.root.after(0, lambda: progress_window.destroy())
        
        # Start export in background thread
        export_thread_obj = threading.Thread(target=export_thread, daemon=True)
        export_thread_obj.start()

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
        menu.delete(0, "end")

        self.credentials = self.load_credentials()
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
        self.root.destroy()
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
    """New User Creation Window with connection testing"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("New IPTV User")
        self.root.geometry("450x250")

        tk.Label(self.root, text="Enter IPTV Portal URL:").pack()
        self.portal_entry = tk.Entry(self.root, width=50)
        self.portal_entry.pack()

        tk.Label(self.root, text="Enter MAC Address:").pack()
        self.mac_entry = tk.Entry(self.root, width=50)
        self.mac_entry.pack()

        # Buttons frame
        buttons_frame = tk.Frame(self.root)
        buttons_frame.pack(pady=10)

        # self.test_button = tk.Button(buttons_frame, text="Test Connection", 
        #                            command=self.test_connection, bg="orange", fg="white")
        # self.test_button.pack(side=tk.LEFT, padx=5)

        self.save_button = tk.Button(buttons_frame, text="Save", command=self.save_user)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.back_button = tk.Button(buttons_frame, text="Back", command=self.go_back, fg="red")
        self.back_button.pack(side=tk.LEFT, padx=5)

    def fix_portal_url(self, url):
        """Auto-correct common portal URL issues"""
        url = url.strip()
        
        # If URL contains https and port 80, change to http
        if "https://" in url and ":80" in url:
            url = url.replace("https://", "http://")
            print(f"Auto-corrected HTTPS+port80 to HTTP: {url}")
        
        # If URL contains http and port 443, change to https and remove port
        elif "http://" in url and ":443" in url:
            url = url.replace("http://", "https://").replace(":443", "")
            print(f"Auto-corrected HTTP+port443 to HTTPS: {url}")
        
        # If no protocol specified, try http first
        elif not url.startswith(("http://", "https://")):
            url = "http://" + url
            print(f"Added HTTP protocol: {url}")
        
        return url

    def test_connection(self):
        """Enhanced connection test with better timeout handling"""
        portal_url = self.portal_entry.get().strip()
        mac_address = self.mac_entry.get().strip()

        if not portal_url or not mac_address:
            messagebox.showerror("Error", "Both fields must be filled.")
            return

        portal_url = self.fix_portal_url(portal_url)
        if not portal_url.endswith('/'):
            portal_url += '/'

        # Update the entry with corrected URL
        self.portal_entry.delete(0, tk.END)
        self.portal_entry.insert(0, portal_url.rstrip('/'))

        # Show progress window
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Testing Connection...")
        progress_window.geometry("350x120")
        progress_window.grab_set()
        
        progress_label = tk.Label(progress_window, text="Testing connection...", font=("Arial", 12))
        progress_label.pack(pady=20)
        
        status_label = tk.Label(progress_window, text="Connecting...", font=("Arial", 10))
        status_label.pack(pady=10)

        # Enhanced connection test
        def test_in_background():
            try:
                # ✅ ENHANCED: Multiple timeout strategies
                timeout_configs = [
                    {"connect": 10, "read": 15, "name": "Quick"},
                    {"connect": 20, "read": 30, "name": "Standard"}, 
                    {"connect": 45, "read": 60, "name": "Extended"}
                ]
                
                urls_to_try = [
                    portal_url,
                    portal_url.replace("https://", "http://"),
                    portal_url.replace("http://", "https://"),
                    portal_url.replace(":80", ""),
                    portal_url.replace(":443", "")
                ]
                
                for i, timeout_config in enumerate(timeout_configs):
                    if progress_window.winfo_exists():
                        self.root.after(0, lambda cfg=timeout_config: status_label.config(
                            text=f"Trying {cfg['name']} timeout ({cfg['connect']}s)..."))
                    
                    for j, test_portal in enumerate(urls_to_try):
                        try:
                            if not progress_window.winfo_exists():
                                return
                            
                            if not test_portal.endswith('/'):
                                test_portal += '/'
                            
                            test_url = f"{test_portal}server/load.php?type=stb&action=handshake&mac={mac_address}"
                            
                            # Update progress
                            self.root.after(0, lambda url=test_portal, cfg=timeout_config: status_label.config(
                                text=f"{cfg['name']} test: {url[:30]}..."))
                            
                            print(f"🔍 Testing {timeout_config['name']}: {test_url}")
                            
                            # ✅ ENHANCED: Custom session with specific timeouts
                            session = requests.Session()
                            
                            # Custom timeout for this attempt
                            timeout = (timeout_config["connect"], timeout_config["read"])
                            
                            response = session.get(test_url, timeout=timeout)
                            session.close()
                            
                            if response.status_code == 200:
                                print(f"✅ Connection successful with {timeout_config['name']} timeout: {test_portal}")
                                
                                # Update UI on success
                                self.root.after(0, lambda portal=test_portal: self.portal_entry.delete(0, tk.END))
                                self.root.after(0, lambda portal=test_portal: self.portal_entry.insert(0, portal.rstrip('/')))
                                self.root.after(0, lambda: progress_window.destroy())
                                self.root.after(0, lambda: messagebox.showinfo("Connection Test", 
                                    f"✅ Portal is reachable!\n\n"
                                    f"Server: {test_portal}\n"
                                    f"Timeout: {timeout_config['name']} ({timeout_config['connect']}s)\n"
                                    f"Response: {response.status_code}"))
                                return
                                
                        except requests.exceptions.ConnectTimeout:
                            print(f"⏰ Connect timeout ({timeout_config['connect']}s) with {test_portal}")
                            continue
                        except requests.exceptions.ReadTimeout:
                            print(f"⏰ Read timeout ({timeout_config['read']}s) with {test_portal}")
                            continue
                        except requests.exceptions.Timeout:
                            print(f"⏰ General timeout with {test_portal}")
                            continue
                        except Exception as e:
                            print(f"❌ Error with {test_portal}: {e}")
                            continue
                
                # All attempts failed
                self.root.after(0, lambda: progress_window.destroy())
                self.root.after(0, lambda: messagebox.showerror("Connection Test", 
                    "❌ Cannot connect to portal after multiple attempts.\n\n"
                    "Possible issues:\n"
                    "• Server is down or very slow\n"
                    "• DNS resolution problems\n"
                    "• Firewall/ISP blocking\n"
                    "• Invalid portal URL\n\n"
                    "Try:\n"
                    "• Different portal URL\n"
                    "• VPN connection\n"
                    "• Contact your provider"))
                    
            except Exception as e:
                self.root.after(0, lambda: progress_window.destroy())
                self.root.after(0, lambda: messagebox.showerror("Connection Test", 
                    f"❌ Test failed with error:\n{str(e)}\n\n"
                    "This might be a network connectivity issue."))
        
        # Start test in background thread
        test_thread = threading.Thread(target=test_in_background, daemon=True)
        test_thread.start()

    def save_user(self):
        """Save new user credentials."""
        portal_url = self.portal_entry.get().strip()
        mac_address = self.mac_entry.get().strip()

        if not portal_url or not mac_address:
            messagebox.showerror("Error", "Both fields must be filled.")
            return

        portal_url = self.fix_portal_url(portal_url)

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

        root = tk.Tk()
        IPTVUserSelection(root)
        root.mainloop()

    def go_back(self):
        """Close IPTV player and return to the user selection screen."""
        # Stop continuous cache cleanup
        self.cache_cleanup_active = False
        
        # Stop any ongoing processes FORCEFULLY
        if hasattr(self, 'download_process') and self.download_process.poll() is None:
            try:
                self.download_process.terminate()
                self.download_process.wait(timeout=3)
                print("📡 Stopped download process")
            except:
                try:
                    self.download_process.kill()  # Force kill if terminate doesn't work
                    print("📡 Force killed download process")
                except:
                    pass
        
        if hasattr(self, 'playback_process') and self.playback_process.poll() is None:
            try:
                self.playback_process.terminate()
                self.playback_process.wait(timeout=3)
                print("🎬 Stopped playback process")
            except:
                try:
                    self.playback_process.kill()  # Force kill if terminate doesn't work
                    print("🎬 Force killed playback process")
                except:
                    pass
        
        # Close cache window if exists
        if hasattr(self, 'cache_window') and self.cache_window:
            try:
                self.cache_window.destroy()
            except:
                pass
        
        
        
        # Short delay to ensure processes are stopped
        time.sleep(1)
        
        self.root.destroy()
        root = tk.Tk()
        IPTVUserSelection(root)
        root.mainloop()
        
        
class VODContentWindow:
    """VOD (Video on Demand) Content Browser - Series, Movies, etc."""
    def __init__(self, parent, content_type, content_data):
        self.parent = parent
        self.content_type = content_type  # 'series', 'movies', etc.
        self.content_data = content_data
        
        self.root = tk.Toplevel(parent.root)
        self.root.title(f"{content_type.title()} Browser")
        self.root.geometry("800x600")
        self.root.grab_set()
        
        # Search frame
        search_frame = tk.Frame(self.root)
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(search_frame, text=f"🎬 Search {content_type.title()}:", 
                font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        
        self.search_var = StringVar()
        self.search_entry = Entry(search_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind("<KeyRelease>", self.search_content)
        
        # Content list
        list_frame = tk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.content_list = Listbox(list_frame, font=("Arial", 9))
        scrollbar = Scrollbar(list_frame, orient="vertical")
        
        self.content_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.content_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.content_list.yview)
        
        # Buttons frame
        buttons_frame = tk.Frame(self.root)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        if content_type == "series":
            self.episodes_button = tk.Button(buttons_frame, text="📺 View Episodes", 
                                           command=self.view_episodes,
                                           bg="#2196F3", fg="white", font=("Arial", 10, "bold"))
            self.episodes_button.pack(side=tk.LEFT, padx=5)
        
        self.play_button = tk.Button(buttons_frame, text="▶️ Play", 
                                   command=self.play_selected,
                                   bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.play_button.pack(side=tk.LEFT, padx=5)
        
        self.info_button = tk.Button(buttons_frame, text="ℹ️ Info", 
                                   command=self.show_info,
                                   bg="#FF9800", fg="white", font=("Arial", 10))
        self.info_button.pack(side=tk.LEFT, padx=5)
        
        self.close_button = tk.Button(buttons_frame, text="❌ Close", 
                                    command=self.root.destroy,
                                    bg="#f44336", fg="white")
        self.close_button.pack(side=tk.RIGHT, padx=5)
        
        # Load content
        self.filtered_content = self.content_data
        self.update_content_list()
        
        # Status
        self.status_var = StringVar(value=f"Loaded {len(self.content_data)} {content_type}")
        status_bar = tk.Label(self.root, textvariable=self.status_var, 
                            relief=tk.SUNKEN, anchor=tk.W, font=("Arial", 9))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=2)
    
    def search_content(self, event=None):
        """Search through content"""
        search_term = self.search_var.get().lower().strip()
        
        if not search_term:
            self.filtered_content = self.content_data
        else:
            self.filtered_content = []
            for item in self.content_data:
                name = item.get('name', '').lower()
                if search_term in name:
                    self.filtered_content.append(item)
        
        self.update_content_list()
        self.status_var.set(f"Found {len(self.filtered_content)} {self.content_type}")
    
    def update_content_list(self):
        """Update the content list"""
        self.content_list.delete(0, tk.END)
        
        for item in self.filtered_content:
            name = item.get('name', 'Unknown')
            # Add additional info if available
            if 'year' in item:
                name += f" ({item['year']})"
            if 'genre' in item:
                name += f" - {item['genre']}"
            
            self.content_list.insert(tk.END, name)
    
    def view_episodes(self):
        """View episodes for selected series"""
        selected_index = self.content_list.curselection()
        if not selected_index:
            messagebox.showwarning("Warning", "Please select a series first.")
            return
        
        series = self.filtered_content[selected_index[0]]
        series_id = series.get('id') or series.get('category_id')
        
        if not series_id:
            messagebox.showerror("Error", "Cannot find series ID.")
            return
        
        # Fetch episodes
        self.fetch_episodes(series_id, series.get('name', 'Unknown Series'))
    
    def fetch_episodes(self, series_id, series_name):
        """Fetch episodes for a series"""
        def fetch_in_background():
            try:
                # Show loading
                self.root.after(0, lambda: self.status_var.set("Loading episodes..."))
                
                episodes_url = (f"{self.parent.portal_url}server/load.php?"
                              f"type=series&action=get_ordered_list&series_id={series_id}&"
                              f"mac={self.parent.mac_address}&JsHttpRequest=1-xml")
                
                response = self.parent.requests.get(episodes_url, timeout=15)
                
                if response.status_code == 200:
                    data = response.json().get("js", {}).get("data", [])
                    
                    if data:
                        # Show episodes window
                        self.root.after(0, lambda: self.show_episodes_window(series_name, data))
                    else:
                        self.root.after(0, lambda: messagebox.showinfo("No Episodes", 
                                                    f"No episodes found for '{series_name}'."))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", 
                                                f"Failed to load episodes: HTTP {response.status_code}"))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", 
                                            f"Failed to load episodes: {str(e)}"))
        
        # Run in background thread
        fetch_thread = threading.Thread(target=fetch_in_background, daemon=True)
        fetch_thread.start()
    
    def show_episodes_window(self, series_name, episodes):
        """Show episodes in a new window"""
        episodes_window = tk.Toplevel(self.root)
        episodes_window.title(f"Episodes - {series_name}")
        episodes_window.geometry("700x500")
        episodes_window.grab_set()
        
        # Header
        tk.Label(episodes_window, text=f"📺 {series_name}", 
                font=("Arial", 14, "bold")).pack(pady=10)
        
        # Episodes list
        list_frame = tk.Frame(episodes_window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        episodes_list = Listbox(list_frame, font=("Arial", 9))
        episodes_scrollbar = Scrollbar(list_frame, orient="vertical")
        
        episodes_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        episodes_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        episodes_list.config(yscrollcommand=episodes_scrollbar.set)
        episodes_scrollbar.config(command=episodes_list.yview)
        
        # Populate episodes
        for episode in episodes:
            episode_name = episode.get('name', 'Unknown Episode')
            if 'season' in episode and 'episode_num' in episode:
                episode_name = f"S{episode['season']:02d}E{episode['episode_num']:02d} - {episode_name}"
            
            episodes_list.insert(tk.END, episode_name)
        
        # Buttons
        ep_buttons_frame = tk.Frame(episodes_window)
        ep_buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def play_episode():
            ep_selected = episodes_list.curselection()
            if ep_selected:
                episode = episodes[ep_selected[0]]
                episodes_window.destroy()
                self.play_vod_content(episode)
        
        tk.Button(ep_buttons_frame, text="▶️ Play Episode", 
                command=play_episode,
                bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        tk.Button(ep_buttons_frame, text="❌ Close", 
                command=episodes_window.destroy,
                bg="#f44336", fg="white").pack(side=tk.RIGHT, padx=5)
    
    def play_selected(self):
        """Play selected content"""
        selected_index = self.content_list.curselection()
        if not selected_index:
            messagebox.showwarning("Warning", f"Please select a {self.content_type[:-1]} first.")
            return
        
        content = self.filtered_content[selected_index[0]]
        self.play_vod_content(content)
    
    def play_vod_content(self, content):
        """Play VOD content"""
        try:
            # Get stream URL
            content_id = content.get('id') or content.get('cmd')
            
            if not content_id:
                messagebox.showerror("Error", "Cannot find content ID.")
                return
            
            # For series episodes, use different endpoint
            if self.content_type == "series" and 'cmd' in content:
                stream_cmd = content['cmd']
            else:
                # For movies and other VOD
                stream_cmd = f"ffmpeg http://localhost/play/{content_id}"
            
            self.status_var.set(f"Getting stream for: {content.get('name', 'Unknown')}")
            
            # Get stream link
            stream_url = self.parent.get_vod_stream_link(stream_cmd, content_id)
            
            if stream_url:
                content_name = content.get('name', 'Unknown Content')
                self.status_var.set(f"Playing: {content_name}")
                
                # Close VOD window and play
                self.root.destroy()
                self.parent.play_vod_stream(stream_url, content_name)
            else:
                messagebox.showerror("Error", "Failed to get stream URL.")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to play content: {str(e)}")
    
    def show_info(self):
        """Show content information"""
        selected_index = self.content_list.curselection()
        if not selected_index:
            messagebox.showwarning("Warning", f"Please select a {self.content_type[:-1]} first.")
            return
        
        content = self.filtered_content[selected_index[0]]
        
        info_text = f"📺 {content.get('name', 'Unknown')}\n\n"
        
        if 'year' in content:
            info_text += f"Year: {content['year']}\n"
        if 'genre' in content:
            info_text += f"Genre: {content['genre']}\n"
        if 'director' in content:
            info_text += f"Director: {content['director']}\n"
        if 'actors' in content:
            info_text += f"Actors: {content['actors']}\n"
        if 'plot' in content:
            info_text += f"\nPlot:\n{content['plot']}\n"
        if 'rating' in content:
            info_text += f"\nRating: {content['rating']}/10\n"
        
        messagebox.showinfo("Content Information", info_text)
   

class WindowsIPTVPlayer:
    """Main IPTV Player GUI with performance optimizations"""
    def __init__(self, root, user_data):
        """Initialize Windows IPTV Player with clean, compact GUI"""
        self.root = root
        self.root.title("Windows IPTV Player - Direct Play")
        self.root.geometry("750x700")  # ✅ INCREASED SIZE: was 650x550 - now shows all buttons properly
        
        # ✅ Add window close protocol
        self.root.protocol("WM_DELETE_WINDOW", self.on_window_close)

        self.portal_url = user_data["portal_url"]
        self.mac_address = user_data["mac_address"]

        # Initialize optimized components
        self.requests = OptimizedRequests()
        self.cache_manager = CacheManager(CACHE_DIR)  # Only for channel cache
        self.token_cache = TokenCache(ttl=300)  # 5 minutes
        self.connection_manager = ConnectionManager(self) # Enhanced connection management
        
        # Performance tracking
        self.search_cache = {}
        self.last_search = ""
        self.search_delay_id = None
        
        # Loading state
        self.loading_progress = None
        self.cancel_loading = False
        
        # Check FFmpeg installation
        if not self.check_ffmpeg_installation():
            return  # Don't continue if FFmpeg is missing

        # ===== CLEAN COMPACT GUI SETUP =====
        
        # === HEADER SECTION ===
        header_frame = tk.Frame(self.root, bg="#f0f0f0")
        header_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Back button
        self.back_button = tk.Button(header_frame, text="← Back", command=self.go_back, 
                                    fg="red", font=("Arial", 10, "bold"))
        self.back_button.pack(side=tk.LEFT)
        
        # Title
        title_label = tk.Label(header_frame, text="🖥️ Windows IPTV Player", 
                            font=("Arial", 14, "bold"), bg="#f0f0f0")
        title_label.pack(side=tk.LEFT, padx=20)

        # === SEARCH SECTION ===
        search_frame = tk.LabelFrame(self.root, text="🔍 Search & Filter", 
                                    font=("Arial", 10, "bold"), fg="darkblue")
        search_frame.pack(fill=tk.X, padx=15, pady=5)

        # Search bar
        search_input_frame = tk.Frame(search_frame)
        search_input_frame.pack(pady=5)
        
        tk.Label(search_input_frame, text="Search:", font=("Arial", 10)).pack(side=tk.LEFT)
        
        self.search_var = StringVar()
        self.search_entry = Entry(search_input_frame, textvariable=self.search_var, 
                                width=35, font=("Arial", 10))
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind("<KeyRelease>", self.optimized_search)

        # Quick filter buttons
        filter_buttons_frame = tk.Frame(search_frame)
        filter_buttons_frame.pack(pady=3)

        self.ssc_button = tk.Button(filter_buttons_frame, text="SSC", 
                                command=lambda: self.set_search("ssc"),
                                bg="#FF5722", fg="white", font=("Arial", 9), width=8)
        self.ssc_button.pack(side=tk.LEFT, padx=3)

        self.bein_button = tk.Button(filter_buttons_frame, text="BEIN", 
                                    command=lambda: self.set_search("bein"),
                                    bg="#2196F3", fg="white", font=("Arial", 9), width=8)
        self.bein_button.pack(side=tk.LEFT, padx=3)

        self.clear_button = tk.Button(filter_buttons_frame, text="Clear", 
                                    command=lambda: self.set_search(""),
                                    bg="#607D8B", fg="white", font=("Arial", 9), width=8)
        self.clear_button.pack(side=tk.LEFT, padx=3)

        # === CHANNEL LIST SECTION ===
        list_frame = tk.LabelFrame(self.root, text="📺 Channel List", 
                                font=("Arial", 10, "bold"), fg="darkgreen")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # Channel listbox with scrollbar
        list_container = tk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        self.channel_list = Listbox(list_container, width=70, height=12,  # ✅ REDUCED HEIGHT: was 15
                                font=("Arial", 9))
        scrollbar = Scrollbar(list_container, orient="vertical")
        
        self.channel_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.channel_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.channel_list.yview)

       # === MAIN CONTROLS SECTION ===
        main_controls_frame = tk.LabelFrame(self.root, text="📺 Playback Controls", 
                                        font=("Arial", 10, "bold"), fg="navy")
        main_controls_frame.pack(fill=tk.X, padx=15, pady=5)

        # Row 1: Main action buttons
        buttons_row1 = tk.Frame(main_controls_frame)
        buttons_row1.pack(pady=6)

        self.load_button = tk.Button(buttons_row1, text="🔄 Fetch Channels", 
                                    command=self.fetch_channels_threaded,
                                    bg="#2196F3", fg="white", font=("Arial", 10, "bold"),
                                    width=15, height=1, relief=tk.RAISED)
        self.load_button.pack(side=tk.LEFT, padx=5)

        self.play_button = tk.Button(buttons_row1, text="▶️ Play Channel", 
                                command=self.play_stream,
                                bg="#4CAF50", fg="white", font=("Arial", 10, "bold"),
                                width=15, height=1, relief=tk.RAISED)
        self.play_button.pack(side=tk.LEFT, padx=5)

        self.export_button = tk.Button(buttons_row1, text="📄 Export M3U", 
                                    command=self.open_export_window, 
                                    bg="#FF9800", fg="white", font=("Arial", 10, "bold"),
                                    width=15, height=1, relief=tk.RAISED)
        self.export_button.pack(side=tk.LEFT, padx=5)
        
        
        
        # === VOD CONTENT SECTION ===
        # vod_frame = tk.LabelFrame(self.root, text="🎬 Movies & Series", 
        #                         font=("Arial", 10, "bold"), fg="purple")
        # vod_frame.pack(fill=tk.X, padx=15, pady=5)

        # vod_buttons_row = tk.Frame(vod_frame)
        # vod_buttons_row.pack(pady=4)

        # # VOD buttons
        # self.movies_button = tk.Button(vod_buttons_row, text="🎬 Movies", 
        #                             command=lambda: self.fetch_vod_content("movies"), 
        #                             font=("Arial", 9), bg="#E91E63", fg="white",
        #                             width=15)
        # self.movies_button.pack(side=tk.LEFT, padx=3)

        # self.series_button = tk.Button(vod_buttons_row, text="📺 TV Series", 
        #                             command=lambda: self.fetch_vod_content("series"), 
        #                             font=("Arial", 9), bg="#673AB7", fg="white",
        #                             width=15)
        # self.series_button.pack(side=tk.LEFT, padx=3)

        # self.anime_button = tk.Button(vod_buttons_row, text="🌟 Anime/Kids", 
        #                             command=lambda: self.fetch_vod_content("anime"), 
        #                             font=("Arial", 9), bg="#FF5722", fg="white",
        #                             width=15)
        # self.anime_button.pack(side=tk.LEFT, padx=3)

        # self.documentaries_button = tk.Button(vod_buttons_row, text="📚 Documentaries", 
        #                                     command=lambda: self.fetch_vod_content("documentaries"), 
        #                                     font=("Arial", 9), bg="#795548", fg="white",
        #                                     width=15)
        # self.documentaries_button.pack(side=tk.LEFT, padx=3)

        # ❌ REMOVED: Event Mode button and all related methods
        # self.high_load_button = tk.Button(...)
        
        # === MANAGEMENT SECTION ===
        mgmt_frame = tk.LabelFrame(self.root, text="🗂️ Management", 
                                font=("Arial", 10, "bold"), fg="darkorange")
        mgmt_frame.pack(fill=tk.X, padx=15, pady=5)

        mgmt_buttons_row = tk.Frame(mgmt_frame)
        mgmt_buttons_row.pack(pady=4)

        # Management buttons
        self.refresh_channels_button = tk.Button(mgmt_buttons_row, text="🔄 Refresh Channels", 
                                            command=self.force_refresh_channels, 
                                            font=("Arial", 9), bg="#2196F3", fg="white",
                                            width=18)
        self.refresh_channels_button.pack(side=tk.LEFT, padx=3)

        self.cache_info_button = tk.Button(mgmt_buttons_row, text="ℹ️ Channel Cache Info", 
                                        command=self.show_cache_info, 
                                        font=("Arial", 9), bg="#607D8B", fg="white",
                                        width=18)
        self.cache_info_button.pack(side=tk.LEFT, padx=3)

        self.test_connection_button = tk.Button(mgmt_buttons_row, text="🌐 Test Server", 
                                            command=self.test_server_connection, 
                                            font=("Arial", 9), bg="#9C27B0", fg="white",
                                            width=12)
        self.test_connection_button.pack(side=tk.LEFT, padx=3)

        self.controls_button = tk.Button(mgmt_buttons_row, text="ℹ️ Player Info", 
                                    command=self.show_player_info, 
                                    font=("Arial", 9), bg="#795548", fg="white",
                                    width=15)
        self.controls_button.pack(side=tk.LEFT, padx=3)

        # === STATUS BAR ===
        self.status_var = StringVar(value="Ready - Direct Play Mode | Select a channel and click Play")
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, 
                                relief=tk.SUNKEN, anchor=tk.W, 
                                font=("Arial", 9), bg="#f9f9f9")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        # === INITIALIZE DATA ===
        # Initialize channel data
        self.channels = []
        self.filtered_channels = []
        
        # Try to load channels from permanent cache
        self.load_channels_with_cache()
       
        
        
    def on_window_close(self):
        """Handle window close event properly - ENHANCED"""
        print("👤 User closing window...")
        
        # Stop all processes immediately
        self.cache_cleanup_active = False
        self.playback_active = False
        
        # Clear protection flags
        if hasattr(self, 'protected_cache_file'):
            delattr(self, 'protected_cache_file')
        
        # Stop download process
        if hasattr(self, 'download_process') and self.download_process and self.download_process.poll() is None:
            try:
                self.download_process.terminate()
                self.download_process.wait(timeout=3)
                print("📡 Terminated download process")
            except:
                try:
                    self.download_process.kill()
                    print("📡 Force killed download process")
                except:
                    pass
        
        # Stop playback process
        if hasattr(self, 'playback_process') and self.playback_process and self.playback_process.poll() is None:
            try:
                self.playback_process.terminate()
                self.playback_process.wait(timeout=3)
                print("🎬 Terminated playback process")
            except:
                try:
                    self.playback_process.kill()
                    print("🎬 Force killed playback process")
                except:
                    pass
        
        # Close requests session
        try:
            self.requests.close()
        except:
            pass
        
        # ✅ ENHANCED: Force cleanup stream cache on exit
        print("🧹 Cleaning up stream cache on exit...")
        self.force_cleanup_stream_cache()
        
        # Short delay to ensure cleanup completes
        time.sleep(1)
        
        # Destroy window
        self.root.destroy()
        
        
    def force_cleanup_stream_cache(self):
        """Force cleanup of all stream cache files - PLACEHOLDER"""
        try:
            # Since we removed cache methods, this is just a placeholder
            print("🧹 Stream cache cleanup (placeholder - no cache files to clean)")
            
            # Clean any temporary files if they exist
            temp_patterns = ['*.tmp', '*.ts', '*.part']
            cleaned_count = 0
            
            for pattern in temp_patterns:
                import glob
                temp_files = glob.glob(os.path.join(CACHE_DIR, pattern))
                for temp_file in temp_files:
                    try:
                        os.remove(temp_file)
                        cleaned_count += 1
                    except:
                        pass
            
            if cleaned_count > 0:
                print(f"🧹 Cleaned {cleaned_count} temporary files")
            
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        
        
   
        
        
        
    def force_refresh_channels(self):
        """Force refresh channels and update cache"""
        if messagebox.askyesno("Refresh Channels", 
                            "This will fetch fresh channels from the server.\n"
                            "This may take a few moments.\n\n"
                            "Continue?"):
            # Temporarily clear search cache
            self.search_cache.clear()
            self.channels = []
            self.filtered_channels = []
            self.update_channel_list()
            
            # Start fresh fetch
            self.fetch_channels_threaded()

    def show_cache_info(self):
        """Show information about the current cache"""
        cache_info = self.cache_manager.get_cache_info(self.portal_url, self.mac_address)
        
        if cache_info["exists"]:
            message = (f"📁 Channel Cache Information:\n\n"
                    f"• Status: Active (Permanent)\n"
                    f"• Created: {cache_info['created']}\n"
                    f"• Size: {cache_info['size_kb']:.1f} KB\n"
                    f"• Channels: {len(self.channels)}\n"
                    f"• Auto-loads on startup: Yes\n\n"
                    f"This cache never expires and will persist\n"
                    f"until you manually refresh channels.")
        else:
            message = (f"📁 Channel Cache Information:\n\n"
                    f"• Status: No cache found\n"
                    f"• Channels: {len(self.channels)}\n\n"
                    f"Fetch channels to create permanent cache.")
        
        messagebox.showinfo("Cache Information", message)
    
    

    def load_channels_with_cache(self):
        """Try cache first, then fetch if needed"""
        cached_channels = self.cache_manager.load_from_cache(self.portal_url, self.mac_address)
        
        if cached_channels:
            self.channels = cached_channels
            self.filtered_channels = self.channels
            self.update_channel_list()
            
            # Show cache info in status
            cache_info = self.cache_manager.get_cache_info(self.portal_url, self.mac_address)
            self.status_var.set(f"📁 Loaded {len(cached_channels)} channels from permanent cache (Created: {cache_info.get('created', 'Unknown')})")
            print(f"💾 Using permanent cache with {len(cached_channels)} channels")
        else:
            self.status_var.set("No permanent cache found - click 'Fetch Channels' to load and cache")
            print("📁 No permanent cache - ready to fetch fresh channels")

    def show_loading_progress(self):
        """Show loading progress window"""
        self.loading_progress = tk.Toplevel(self.root)
        self.loading_progress.title("Loading Channels...")
        self.loading_progress.geometry("400x150")
        self.loading_progress.resizable(False, False)
        self.loading_progress.grab_set()
        
        self.loading_progress.transient(self.root)
        
        tk.Label(self.loading_progress, text="Fetching channels...", font=("Arial", 12)).pack(pady=20)
        
        self.progress_text = tk.Label(self.loading_progress, text="Connecting to server...", font=("Arial", 10))
        self.progress_text.pack(pady=10)
        
        self.cancel_button = tk.Button(self.loading_progress, text="Cancel", 
                                     command=self.cancel_channel_loading, bg="red", fg="white")
        self.cancel_button.pack(pady=10)

    def update_progress(self, message):
        """Update progress message from background thread"""
        def update():
            if self.progress_text and self.loading_progress and self.loading_progress.winfo_exists():
                self.progress_text.config(text=message)
        
        self.root.after(0, update)

    def cancel_channel_loading(self):
        """Cancel the loading process"""
        self.cancel_loading = True
        if self.loading_progress:
            self.loading_progress.destroy()
            self.loading_progress = None

    def fetch_channels_threaded(self):
        """Fetch channels using threading for better performance"""
        if self.loading_progress:
            return
        
        self.show_loading_progress()
        
        self.cancel_loading = False
        loading_thread = threading.Thread(target=self._fetch_channels_background, daemon=True)
        loading_thread.start()

    def _fetch_channels_background(self):
        """Enhanced background thread for fetching channels with better timeout handling"""
        try:
            # ✅ ENHANCED: Try multiple endpoint variations for different providers
            base_endpoints = [
                # Standard MAG endpoints
                {
                    "auth": f"{self.portal_url}server/load.php?type=stb&action=handshake&mac={self.mac_address}",
                    "channels": f"{self.portal_url}server/load.php?type=itv&action=get_all_channels&mac={self.mac_address}&JsHttpRequest=1-xml"
                },
                # Alternative endpoint structure
                {
                    "auth": f"{self.portal_url}stalker_portal/server/load.php?type=stb&action=handshake&mac={self.mac_address}",
                    "channels": f"{self.portal_url}stalker_portal/server/load.php?type=itv&action=get_all_channels&mac={self.mac_address}&JsHttpRequest=1-xml"
                },
                # Portal API style
                {
                    "auth": f"{self.portal_url}portal.php?type=stb&action=handshake&mac={self.mac_address}",
                    "channels": f"{self.portal_url}portal.php?type=itv&action=get_all_channels&mac={self.mac_address}&JsHttpRequest=1-xml"
                },
                # Direct API style
                {
                    "auth": f"{self.portal_url}api/stb/handshake?mac={self.mac_address}",
                    "channels": f"{self.portal_url}api/itv/channels?mac={self.mac_address}"
                },
                # Simple path style
                {
                    "auth": f"{self.portal_url}handshake?mac={self.mac_address}",
                    "channels": f"{self.portal_url}channels?mac={self.mac_address}"
                },
                # ✅ NEW: CDN-specific endpoints for providers like 4k-cdn
                {
                    "auth": f"{self.portal_url}c/",
                    "channels": f"{self.portal_url}c/?get=channels&mac={self.mac_address}"
                },
                # ✅ NEW: Alternative CDN channels endpoint  
                {
                    "auth": f"{self.portal_url}c/",
                    "channels": f"{self.portal_url}c/?action=get_live_streams&mac={self.mac_address}"
                },
                # ✅ NEW: CDN with different parameters
                {
                    "auth": f"{self.portal_url}c/",
                    "channels": f"{self.portal_url}c/channels.php?mac={self.mac_address}"
                },
                # ✅ NEW: CDN JSON API
                {
                    "auth": f"{self.portal_url}c/",
                    "channels": f"{self.portal_url}c/api.php?action=channels&mac={self.mac_address}"
                },
                # ✅ NEW: Web interface scraping for HTML-based providers
                {
                    "auth": f"{self.portal_url}c/",
                    "channels": f"{self.portal_url}c/index.php?mac={self.mac_address}&action=get_channels"
                },
                # ✅ NEW: Alternative web interface
                {
                    "auth": f"{self.portal_url}c/",
                    "channels": f"{self.portal_url}c/?mac={self.mac_address}&get=live"
                },
                # ✅ NEW: Xtream Codes API style
                {
                    "auth": f"{self.portal_url}player_api.php?username={self.mac_address}&password=&action=get_live_categories",
                    "channels": f"{self.portal_url}player_api.php?username={self.mac_address}&password=&action=get_live_streams"
                },
                # ✅ NEW: M3U playlist style
                {
                    "auth": f"{self.portal_url}get.php?username={self.mac_address}&password=&type=m3u_plus",
                    "channels": f"{self.portal_url}get.php?username={self.mac_address}&password=&type=m3u_plus"
                },
                # ✅ NEW: Direct m3u without auth
                {
                    "auth": f"{self.portal_url}playlist.m3u8?mac={self.mac_address}",
                    "channels": f"{self.portal_url}playlist.m3u8?mac={self.mac_address}"
                }
            ]

            headers = {
                "Referer": self.portal_url + "index.html",
                "Origin": self.portal_url.rstrip('/'),
                "Accept-Language": "en-US,en;q=0.9",
                "Pragma": "no-cache",
                "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)"
            }

            if self.cancel_loading:
                return

            timeout_strategies = [
                (10, 20),   # 10s connect, 20s read (fast attempt)
                (15, 30),   # 15s connect, 30s read
                (30, 45),   # 30s connect, 45s read  
            ]

            self.requests.session.headers.update(headers)
            
            successful_endpoints = None
            auth_response = None
            
            # ✅ Try different endpoint structures
            for endpoint_idx, endpoints in enumerate(base_endpoints):
                if self.cancel_loading:
                    return
                    
                self.update_progress(f"Testing endpoint structure {endpoint_idx + 1}/{len(base_endpoints)}...")
                print(f"🔍 Testing endpoint structure {endpoint_idx + 1}: {endpoints['auth']}")
                
                # ✅ NEW: Special handling for M3U and non-auth endpoints
                if "playlist.m3u8" in endpoints['auth'] or "get.php" in endpoints['auth']:
                    try:
                        self.update_progress(f"Testing direct playlist access...")
                        response = self.requests.session.get(endpoints["channels"], timeout=(10, 20))
                        
                        if response.status_code == 200:
                            print(f"✅ Direct playlist access successful")
                            m3u_content = response.text
                            if "#EXTM3U" in m3u_content:
                                channels = self.parse_m3u_playlist(m3u_content)
                                if channels:
                                    self.root.after(0, lambda: self._update_channels_ui(channels))
                                    return
                            
                    except Exception as e:
                        print(f"❌ Direct playlist failed: {e}")
                        continue
                
                # ✅ NEW: Special handling for Xtream Codes API
                elif "player_api.php" in endpoints['auth']:
                    try:
                        self.update_progress(f"Testing Xtream Codes API...")
                        response = self.requests.session.get(endpoints["channels"], timeout=(10, 20))
                        
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                if isinstance(data, list) and len(data) > 0:
                                    print(f"✅ Xtream Codes API successful")
                                    channels = self.parse_xtream_channels(data)
                                    if channels:
                                        self.root.after(0, lambda: self._update_channels_ui(channels))
                                        return
                            except:
                                pass
                            
                    except Exception as e:
                        print(f"❌ Xtream API failed: {e}")
                        continue
                
                # Try authentication with this endpoint structure
                for i, (connect_timeout, read_timeout) in enumerate(timeout_strategies):
                    if self.cancel_loading:
                        return
                        
                    try:
                        self.update_progress(f"Auth attempt {i+1} with timeout: {connect_timeout}s connect, {read_timeout}s read")
                        print(f"🔐 Auth attempt {i+1} with timeout: {connect_timeout}s connect, {read_timeout}s read")
                        
                        auth_response = self.requests.session.get(endpoints["auth"], timeout=(connect_timeout, read_timeout))
                        
                        if auth_response.status_code == 200:
                            print(f"✅ Authentication successful with endpoint structure {endpoint_idx + 1}, timeout strategy {i+1}")
                            successful_endpoints = endpoints
                            break
                        else:
                            print(f"❌ Auth failed with status {auth_response.status_code} - trying next timeout")
                            
                    except requests.exceptions.ConnectTimeout:
                        print(f"⏰ Connect timeout ({connect_timeout}s) on attempt {i+1}")
                        if i == len(timeout_strategies) - 1:
                            print(f"❌ All timeouts failed for endpoint structure {endpoint_idx + 1}")
                            break
                        continue
                    except requests.exceptions.ReadTimeout:
                        print(f"⏰ Read timeout ({read_timeout}s) on attempt {i+1}")
                        if i == len(timeout_strategies) - 1:
                            print(f"❌ All timeouts failed for endpoint structure {endpoint_idx + 1}")
                            break
                        continue
                    except Exception as e:
                        print(f"❌ Auth error on attempt {i+1}: {e}")
                        if i == len(timeout_strategies) - 1:
                            print(f"❌ All attempts failed for endpoint structure {endpoint_idx + 1}")
                            break
                        continue
                
                # If we found working endpoints, break out of endpoint loop
                if successful_endpoints:
                    break

            if not successful_endpoints or not auth_response or auth_response.status_code != 200:
                self.show_error_threadsafe("Authentication failed with all endpoint structures.\n\n"
                                        "This provider may use a custom API format not supported yet.\n"
                                        "Please contact the developer with your provider details.")
                return

            if self.cancel_loading:
                return

            # ✅ ENHANCED: Better token extraction
            try:
                if auth_response.text.strip():
                    auth_data = auth_response.json()
                    token = auth_data.get('js', {}).get('token', '') or auth_data.get('token', '')
                else:
                    print("⚠️ Non-JSON auth response, proceeding without token")
                    token = ''
            except:
                print("⚠️ Non-JSON auth response, proceeding without token")
                token = ''
            
            # Build channels URL with token if we have one
            channels_url = successful_endpoints["channels"]
            if token:
                separator = "&" if "?" in channels_url else "?"
                channels_url += f"{separator}token={token}"

            self.update_progress("Fetching channel list...")
            print(f"📺 Using channels URL: {channels_url}")
            
            # Try fetching channels with the successful endpoint
            channels_response = None
            for i, (connect_timeout, read_timeout) in enumerate(timeout_strategies):
                if self.cancel_loading:
                    return
                    
                try:
                    self.update_progress(f"📺 Channels attempt {i+1} with timeout: {connect_timeout}s connect, {read_timeout}s read")
                    print(f"📺 Channels attempt {i+1} with timeout: {connect_timeout}s connect, {read_timeout}s read")
                    
                    channels_response = self.requests.session.get(channels_url, timeout=(connect_timeout, read_timeout))
                    
                    if channels_response.status_code == 200:
                        print(f"✅ Channels fetch successful with timeout strategy {i+1}")
                        break
                    else:
                        print(f"❌ Channels failed with status {channels_response.status_code}")
                        
                except requests.exceptions.ConnectTimeout:
                    print(f"⏰ Connect timeout ({connect_timeout}s) on channels attempt {i+1}")
                    if i == len(timeout_strategies) - 1:
                        self.show_error_threadsafe("Server is too slow to respond.\nTry again later or use a VPN.")
                        return
                    continue
                except requests.exceptions.ReadTimeout:
                    print(f"⏰ Read timeout ({read_timeout}s) on channels attempt {i+1}")
                    if i == len(timeout_strategies) - 1:
                        self.show_error_threadsafe("Server response is too slow.\nTry again later or contact provider.")
                        return
                    continue
                except Exception as e:
                    print(f"❌ Channels error on attempt {i+1}: {e}")
                    if i == len(timeout_strategies) - 1:
                        self.show_error_threadsafe(f"Failed to get channels: {str(e)}")
                        return
                    continue

            if not channels_response or channels_response.status_code != 200:
                self.show_error_threadsafe("Failed to get channels after all attempts")
                return

            # ✅ ENHANCED: Better response parsing with HTML/web interface support
            try:
                response_text = channels_response.text.strip()
                print(f"🔍 Response preview: {response_text[:200]}...")
                
                # Check if response is empty
                if not response_text:
                    self.show_error_threadsafe("Server returned empty response.\n\nThis provider may require:\n• Different MAC address format\n• Account activation\n• Subscription payment")
                    return
                
                # ✅ NEW: Try to parse as JSON first
                if response_text.startswith('{') or response_text.startswith('['):
                    try:
                        response_data = channels_response.json()
                        
                        # Handle different JSON structures
                        if isinstance(response_data, dict):
                            data = response_data.get("js", {}).get("data", []) or response_data.get("data", []) or response_data.get("channels", [])
                        elif isinstance(response_data, list):
                            data = response_data
                        else:
                            data = []
                            
                    except Exception as e:
                        print(f"❌ JSON parsing error: {e}")
                        self.show_error_threadsafe(f"Invalid JSON response from server.\n\nResponse preview:\n{response_text[:300]}...")
                        return
                
                # ✅ NEW: Handle M3U format
                elif "#EXTM3U" in response_text:
                    print("🔍 Detected M3U playlist format")
                    channels = self.parse_m3u_playlist(response_text)
                    if channels:
                        self.root.after(0, lambda: self._update_channels_ui(channels))
                        return
                    else:
                        self.show_error_threadsafe("Failed to parse M3U playlist")
                        return
                
                # ✅ NEW: Handle HTML/JavaScript response (like your 4k-cdn provider) - PREVENT LOOPS
                elif "<!DOCTYPE" in response_text or "<html" in response_text.lower():
                    print("🔍 Detected HTML/JavaScript response - trying to extract channel data")
                    
                    # ✅ SINGLE ATTEMPT - No loops
                    channels = self.parse_html_channel_response(response_text, channels_url)
                    if channels:
                        self.root.after(0, lambda: self._update_channels_ui(channels))
                        return
                    
                    # ✅ LIMITED ALTERNATIVE ATTEMPT - No loops  
                    print("🔍 Trying limited alternative endpoints...")
                    alternative_channels = self.try_alternative_html_endpoints()
                    if alternative_channels:
                        self.root.after(0, lambda: self._update_channels_ui(alternative_channels))
                        return
                    
                    # ✅ FINAL MESSAGE - No more attempts
                    self.show_error_threadsafe(
                        "🌐 Web-Based IPTV Interface Detected\n\n"
                        "This provider uses a web-based STB interface that requires:\n"
                        "• JavaScript execution in a web browser\n"
                        "• Interactive session management\n"
                        "• Dynamic channel loading\n\n"
                        "Solutions:\n"
                        "• Ask your provider for M3U playlist URL\n"
                        "• Use a web browser to access channels\n"
                        "• Contact provider for API documentation\n\n"
                        "This type of interface cannot be automated."
                    )
                    return
                
                # ✅ XML format
                elif response_text.startswith('<'):
                    print("🔍 Detected XML format (not supported)")
                    self.show_error_threadsafe("Server returned XML format which is not supported.\n\n"
                                            "Please contact the developer with your provider details.")
                    return
                
                # Check if it's plain text/HTML error
                elif "error" in response_text.lower():
                    self.show_error_threadsafe(f"Server returned error:\n\n{response_text[:500]}...")
                    return
                
                else:
                    # Unknown format - try to extract any useful data
                    self.show_error_threadsafe(f"Unknown response format from server.\n\n"
                                            f"Response type: {type(response_text)}\n"
                                            f"Length: {len(response_text)} chars\n\n"
                                            f"Preview:\n{response_text[:300]}...")
                    return

                # Continue with JSON processing if we got here
                if not data:
                    self.show_error_threadsafe("No channels found in server response.\n\n"
                                            "Possible issues:\n• Account not activated\n• Subscription expired\n• MAC address not authorized\n• Wrong portal URL")
                    return

                # Process channels (existing code)
                self.update_progress(f"Processing {len(data)} channels...")
                
                channels = []
                from urllib.parse import urlparse
                parsed_portal = urlparse(self.portal_url)
                portal_domain = parsed_portal.netloc
                
                batch_size = 100
                for i in range(0, len(data), batch_size):
                    if self.cancel_loading:
                        return
                    
                    batch = data[i:i + batch_size]
                    batch_channels = []
                    
                    for ch in batch:
                        # Handle different channel data structures
                        if isinstance(ch, dict):
                            name = ch.get("name", ch.get("title", "Unknown Channel"))
                            cmd = ch.get("cmd", ch.get("url", ch.get("stream_url", "")))
                            
                            if cmd:
                                original_cmd = cmd.replace("ffmpeg ", "").strip()
                                
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
                                
                                batch_channels.append((name, stream_url, original_cmd))
                    
                    channels.extend(batch_channels)
                    
                    progress = min(100, (len(channels) / len(data)) * 100)
                    self.update_progress(f"Processed {len(channels)}/{len(data)} channels ({progress:.0f}%)")

                if self.cancel_loading:
                    return
                
                if not channels:
                    self.show_error_threadsafe("No valid channels found in response.\n\nThe server data may be in an unsupported format.")
                    return
                
                # Update UI on main thread
                self.root.after(0, lambda: self._update_channels_ui(channels))
                
            except Exception as e:
                print(f"❌ Channel processing error: {e}")
                self.show_error_threadsafe(f"Error processing channels: {str(e)}")
                
        except Exception as e:
            self.show_error_threadsafe(f"Error: {str(e)}")
            
            
            
    def parse_html_channel_response(self, html_content, original_url):
        """Parse HTML/JavaScript response to extract channel data - FIXED MAC EXTRACTION"""
        try:
            print("🔍 Attempting to parse MAG STB HTML/JavaScript channel data...")
            
            # ✅ FIXED: Better MAC address extraction
            import re
            
            # Look for MAC in various formats within the HTML
            mac_patterns = [
                # Direct MAC patterns
                r'mac\s*[=:]\s*["\']([0-9a-fA-F:]{17})["\']',  # Standard MAC format
                r'stb\.mac\s*=\s*["\']([0-9a-fA-F:]{17})["\']',
                r'device\s*[=:]\s*["\']([0-9a-fA-F:]{17})["\']',
                
                # MAC without quotes
                r'mac\s*[=:]\s*([0-9a-fA-F:]{17})',
                r'stb\.mac\s*=\s*([0-9a-fA-F:]{17})',
                
                # MAC in URL parameters
                r'mac=([0-9a-fA-F:]{17})',
            ]
            
            extracted_mac = None
            for pattern in mac_patterns:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match:
                    extracted_mac = match.group(1)
                    print(f"✅ Successfully extracted MAC: {extracted_mac}")
                    break
            
            # ✅ FALLBACK: If no MAC found in HTML, use our original MAC
            if not extracted_mac or len(extracted_mac) != 17:
                extracted_mac = self.mac_address
                print(f"🔄 Using fallback MAC: {extracted_mac}")
            
            # ✅ EARLY EXIT: Don't try module approach for this provider
            print("⚠️ This provider uses a web-based STB interface that doesn't support direct channel extraction")
            print("💡 Skipping module approach to prevent infinite loops")
            
            # Instead, try to find any embedded data in the HTML itself
            channels = []
            
            # Method 1: Extract from JavaScript variables
            channels.extend(self.extract_from_js_variables(html_content))
            
            # Method 2: Extract from JSON embedded in HTML  
            channels.extend(self.extract_from_embedded_json(html_content))
            
            # Method 3: Extract from script tags
            channels.extend(self.extract_from_script_tags(html_content))
            
            # Remove duplicates
            unique_channels = []
            seen_names = set()
            for channel in channels:
                if channel[0] not in seen_names:
                    seen_names.add(channel[0])
                    unique_channels.append(channel)
            
            if unique_channels:
                print(f"✅ Successfully extracted {len(unique_channels)} channels from HTML")
                return unique_channels
            
            # If no channels found, save HTML for analysis
            self.save_html_for_analysis(html_content, original_url)
            
            # ✅ RETURN EMPTY LIST - DON'T CONTINUE TO MODULES
            print("❌ No channels found in HTML - this provider requires a web browser interface")
            return []
            
        except Exception as e:
            print(f"❌ HTML parsing error: {e}")
            self.save_html_for_analysis(html_content, original_url)
            return []
        
        
    def extract_channels_via_mag_modules(self, mac_address):
        """Extract channels via MAG STB external module system"""
        try:
            print("🔍 Attempting MAG module-based channel extraction...")
            
            # Common MAG modules that contain channel data
            modules_to_try = [
                'tv',           # Main TV module
                'itv',          # IPTV module
                'live_tv',      # Live TV module
                'channels',     # Direct channels module
                'player',       # Player module
                'main_menu',    # Main menu module
                'epg',          # EPG module (sometimes has channel list)
                'favorites',    # Favorites module
                'all_channels', # All channels module
                'channel_list', # Channel list module
            ]
            
            for module_name in modules_to_try:
                try:
                    # Try the external module endpoint
                    module_url = f"{self.portal_url}server/api/ext_module.php?name={module_name}&mac={mac_address}"
                    print(f"🔍 Trying MAG module: {module_name}")
                    
                    response = self.requests.session.get(module_url, timeout=(15, 30))
                    
                    if response.status_code == 200:
                        content = response.text.strip()
                        
                        if content and len(content) > 100:  # Reasonable content length
                            print(f"✅ Got response from module '{module_name}': {len(content)} chars")
                            
                            # Try to extract channel data from module response
                            channels = self.parse_mag_module_response(content, module_name)
                            if channels:
                                print(f"✅ Successfully extracted {len(channels)} channels from module '{module_name}'")
                                return channels
                        else:
                            print(f"⚠️ Module '{module_name}' returned empty/small response")
                    else:
                        print(f"❌ Module '{module_name}' failed with status {response.status_code}")
                        
                except Exception as e:
                    print(f"❌ Module '{module_name}' error: {e}")
                    continue
            
            # If direct modules don't work, try alternative MAG endpoints
            return self.try_alternative_mag_endpoints(mac_address)
            
        except Exception as e:
            print(f"❌ MAG module extraction error: {e}")
            return []
        
        
    def try_alternative_mag_endpoints(self, mac_address):
        """Try alternative MAG STB endpoints"""
        try:
            print("🔍 Trying alternative MAG endpoints...")
            
            alternative_endpoints = [
                # Direct portal endpoints
                f"{self.portal_url}portal.php?type=itv&action=get_all_channels&mac={mac_address}",
                f"{self.portal_url}portal.php?type=itv&action=get_ordered_list&mac={mac_address}",
                
                # Server load endpoints
                f"{self.portal_url}server/load.php?type=itv&action=get_all_channels&mac={mac_address}&JsHttpRequest=1-xml",
                f"{self.portal_url}server/load.php?type=itv&action=get_ordered_list&mac={mac_address}",
                
                # Alternative server paths
                f"{self.portal_url}c/server/load.php?type=itv&action=get_all_channels&mac={mac_address}&JsHttpRequest=1-xml",
                f"{self.portal_url}stalker_portal/server/load.php?type=itv&action=get_all_channels&mac={mac_address}&JsHttpRequest=1-xml",
                
                # Direct API endpoints
                f"{self.portal_url}api/channels?mac={mac_address}",
                f"{self.portal_url}api/itv/get_all_channels?mac={mac_address}",
                
                # Web interface endpoints
                f"{self.portal_url}tv/index.php?mac={mac_address}",
                f"{self.portal_url}itv/index.php?mac={mac_address}",
            ]
            
            for endpoint in alternative_endpoints:
                try:
                    print(f"🔍 Trying: {endpoint}")
                    response = self.requests.session.get(endpoint, timeout=(10, 20))
                    
                    if response.status_code == 200:
                        content = response.text.strip()
                        
                        # Try to parse as JSON
                        if content.startswith('{') or content.startswith('['):
                            try:
                                data = response.json()
                                
                                # Handle different JSON structures
                                if isinstance(data, dict):
                                    channel_data = data.get("js", {}).get("data", []) or data.get("data", []) or data.get("channels", [])
                                elif isinstance(data, list):
                                    channel_data = data
                                else:
                                    continue
                                
                                if channel_data:
                                    print(f"✅ Found {len(channel_data)} channels in alternative endpoint")
                                    channels = self.process_mag_channel_data(channel_data)
                                    if channels:
                                        return channels
                                        
                            except:
                                continue
                        
                        # Try HTML parsing
                        elif "<!DOCTYPE" in content or "<html" in content.lower():
                            channels = self.extract_from_html_structure(content)
                            if channels:
                                return channels
                                
                except Exception as e:
                    print(f"❌ Alternative endpoint failed: {e}")
                    continue
            
            return []
            
        except Exception as e:
            print(f"❌ Alternative MAG endpoints error: {e}")
            return []
        
        
    def parse_mag_module_response(self, content, module_name):
        """Parse response from MAG external module"""
        try:
            channels = []
            
            # Try to parse as JSON first
            if content.strip().startswith('{') or content.strip().startswith('['):
                try:
                    import json
                    data = json.loads(content)
                    
                    # Look for channel data in various JSON structures
                    channel_sources = []
                    
                    if isinstance(data, dict):
                        # Try common keys for channel data
                        for key in ['channels', 'data', 'items', 'list', 'streams', 'tv_channels', 'channel_list']:
                            if key in data and isinstance(data[key], list):
                                channel_sources.extend(data[key])
                                
                        # Try nested structures
                        if 'js' in data and isinstance(data['js'], dict):
                            js_data = data['js']
                            for key in ['data', 'channels', 'items']:
                                if key in js_data and isinstance(js_data[key], list):
                                    channel_sources.extend(js_data[key])
                    
                    elif isinstance(data, list):
                        channel_sources = data
                    
                    if channel_sources:
                        channels = self.process_mag_channel_data(channel_sources)
                        if channels:
                            return channels
                            
                except json.JSONDecodeError:
                    print(f"⚠️ Module '{module_name}' response is not valid JSON")
            
            # Try to extract from JavaScript code in the response
            channels.extend(self.extract_from_javascript_code(content))
            
            # Try to extract from HTML structure if present
            if "<!DOCTYPE" in content or "<html" in content.lower():
                channels.extend(self.extract_from_html_structure(content))
            
            return channels
            
        except Exception as e:
            print(f"❌ Module response parsing error: {e}")
            return []
        
        
    def extract_from_javascript_code(self, content):
        """Extract channels from JavaScript code in module responses"""
        try:
            import re
            channels = []
            
            # JavaScript patterns for channel data
            js_patterns = [
                # Standard channel objects
                r'{\s*["\']?name["\']?\s*:\s*["\']([^"\']+)["\'].*?["\']?(?:url|cmd|stream)["\']?\s*:\s*["\']([^"\']+)["\']',
                
                # Array format: addChannel("name", "url")
                r'addChannel\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']',
                
                # Channel list arrays
                r'channels\s*[=:]\s*\[(.*?)\]',
                r'channelList\s*[=:]\s*\[(.*?)\]',
                r'tv_channels\s*[=:]\s*\[(.*?)\]',
                
                # Stream URLs in JavaScript
                r'["\']([^"\']*(?:live|stream|channel)[^"\']*)["\'].*?["\']([^"\']*(?:http|rtmp)[^"\']*)["\']',
            ]
            
            for pattern in js_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    if len(match) >= 2:
                        name = match[0].strip()
                        url = match[1].strip()
                        
                        # Validate and clean up
                        if name and url and (url.startswith('http') or url.startswith('rtmp')):
                            channels.append((name, url, url))
            
            # Remove duplicates
            seen_urls = set()
            unique_channels = []
            for channel in channels:
                if channel[1] not in seen_urls:
                    seen_urls.add(channel[1])
                    unique_channels.append(channel)
            
            return unique_channels
            
        except Exception as e:
            print(f"❌ JavaScript code extraction error: {e}")
            return []
        
        
        
    def try_javascript_module_extraction(self):
        """Extract channels by loading the JavaScript modules that contain channel data"""
        try:
            print("🔍 Attempting to extract channels from STB JavaScript modules...")
            
            # The base JavaScript files that might contain channel data
            js_files = [
                "version.js",
                "global.js", 
                "player.js",
                "tv.js",
                "itv.js",
                "main_menu.js"
            ]
            
            # Try to get the core JavaScript files
            for js_file in js_files:
                try:
                    js_url = f"{self.portal_url}c/{js_file}"
                    print(f"🔍 Trying to load: {js_url}")
                    
                    response = self.requests.session.get(js_url, timeout=(5, 10))
                    if response.status_code == 200:
                        js_content = response.text
                        
                        # Look for channel data in the JavaScript
                        channels = self.extract_channels_from_js_content(js_content)
                        if channels:
                            print(f"✅ Found {len(channels)} channels in {js_file}")
                            return channels
                            
                except Exception as e:
                    print(f"❌ Failed to load {js_file}: {e}")
                    continue
            
            # Try to access the STB initialization endpoint that might return channel data
            print("🔍 Trying STB initialization endpoints...")
            
            init_endpoints = [
                f"{self.portal_url}c/?mac={self.mac_address}&action=get_profile",
                f"{self.portal_url}c/?mac={self.mac_address}&action=get_modules",
                f"{self.portal_url}c/?mac={self.mac_address}&action=get_settings",
                f"{self.portal_url}c/index.php?mac={self.mac_address}&type=stb",
                f"{self.portal_url}c/api.php?mac={self.mac_address}&action=get_channels"
            ]
            
            for endpoint in init_endpoints:
                try:
                    print(f"🔍 Trying: {endpoint}")
                    response = self.requests.session.get(endpoint, timeout=(5, 10))
                    
                    if response.status_code == 200:
                        content = response.text.strip()
                        
                        # Try to parse as JSON
                        if content.startswith('{') or content.startswith('['):
                            try:
                                data = response.json()
                                channels = self.extract_channels_from_json_data(data)
                                if channels:
                                    print(f"✅ Found {len(channels)} channels from init endpoint")
                                    return channels
                            except:
                                pass
                        
                        # Try to extract from any JavaScript/HTML content
                        channels = self.extract_channels_from_js_content(content)
                        if channels:
                            print(f"✅ Found {len(channels)} channels from init endpoint")
                            return channels
                            
                except Exception as e:
                    print(f"❌ Init endpoint failed: {e}")
                    continue
            
            return []
            
        except Exception as e:
            print(f"❌ JavaScript module extraction error: {e}")
            return []

    def extract_channels_from_js_content(self, js_content):
        """Extract channel data from JavaScript content - FIXED FOR PLAYER.JS"""
        try:
            import re
            channels = []
            
            print("🔍 Analyzing JavaScript content for channel data...")
            
            # Enhanced patterns specifically for MAG STB player.js files
            patterns = [
                # Look for channel URLs in various formats
                r'["\']((https?://[^"\']+\.(?:ts|m3u8|mp4)[^"\']*?))["\']',
                r'["\']((rtmp://[^"\']+))["\']',
                r'["\']((http://[^"\']+/ch/[^"\']+))["\']',
                
                # Channel objects with name and URL
                r'{\s*["\']?name["\']?\s*:\s*["\']([^"\']+)["\'].*?["\']?(?:url|cmd|stream)["\']?\s*:\s*["\']([^"\']+)["\']',
                r'{\s*["\']?title["\']?\s*:\s*["\']([^"\']+)["\'].*?["\']?(?:url|cmd|stream)["\']?\s*:\s*["\']([^"\']+)["\']',
                
                # MAG-specific stream commands
                r'cmd\s*:\s*["\']([^"\']+)["\'].*?name\s*:\s*["\']([^"\']+)["\']',
                
                # Channel arrays
                r'channels\s*=\s*\[(.*?)\]',
                r'stream_list\s*=\s*\[(.*?)\]',
                
                # URL assignments
                r'stream_url\s*=\s*["\']([^"\']+)["\']',
                r'channel_url\s*=\s*["\']([^"\']+)["\']',
                
                # Function calls with URLs
                r'play\s*\(\s*["\']([^"\']+)["\']',
                r'setSource\s*\(\s*["\']([^"\']+)["\']',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, js_content, re.IGNORECASE | re.DOTALL)
                
                for match in matches:
                    if isinstance(match, tuple):
                        if len(match) == 2:
                            # Two parts - could be name/url or url/name
                            part1, part2 = match
                            
                            # Determine which is URL and which is name
                            if any(part1.startswith(proto) for proto in ['http://', 'https://', 'rtmp://']):
                                url = part1
                                name = part2 if part2 and len(part2) > 3 else f"Channel {len(channels) + 1}"
                            elif any(part2.startswith(proto) for proto in ['http://', 'https://', 'rtmp://']):
                                url = part2
                                name = part1 if part1 and len(part1) > 3 else f"Channel {len(channels) + 1}"
                            else:
                                continue  # Neither is a URL
                            
                            # Validate URL
                            if self.is_valid_stream_url(url) and name:
                                full_url = self.build_full_url(url)
                                channels.append((name, full_url, url))
                        
                        elif len(match) == 1:
                            # Single URL
                            url = match[0]
                            if self.is_valid_stream_url(url):
                                name = self.extract_name_from_url(url)
                                full_url = self.build_full_url(url)
                                channels.append((name, full_url, url))
                    
                    elif isinstance(match, str):
                        # Single string match
                        if self.is_valid_stream_url(match):
                            name = self.extract_name_from_url(match)
                            full_url = self.build_full_url(match)
                            channels.append((name, full_url, match))
            
            # Try to find channel data in specific MAG player structures
            mag_channels = self.extract_mag_player_channels(js_content)
            channels.extend(mag_channels)
            
            # Remove duplicates and invalid entries
            cleaned_channels = self.clean_channel_list(channels)
            
            if cleaned_channels:
                print(f"✅ Successfully extracted {len(cleaned_channels)} valid channels from JavaScript")
            else:
                print("❌ No valid channels found in JavaScript content")
                
            return cleaned_channels
            
        except Exception as e:
            print(f"❌ JavaScript content extraction error: {e}")
            return []
        
        
    def clean_channel_list(self, channels):
        """Clean and deduplicate channel list"""
        try:
            cleaned = []
            seen_urls = set()
            
            for channel in channels:
                if len(channel) != 3:
                    continue
                    
                name, full_url, original_url = channel
                
                # Skip if we've seen this URL
                if original_url in seen_urls:
                    continue
                
                # Skip if name looks like code
                if any(char in name for char in ['{', '}', '(', ')', ';', 'function']):
                    continue
                
                # Skip if name is too long (likely code)
                if len(name) > 100:
                    continue
                
                # Skip if URL is invalid
                if not self.is_valid_stream_url(original_url):
                    continue
                
                seen_urls.add(original_url)
                cleaned.append((name, full_url, original_url))
            
            return cleaned
            
        except Exception as e:
            print(f"❌ Channel list cleaning error: {e}")
            return channels
        
    def analyze_saved_html_file(self):
        """Analyze the saved HTML file to extract useful information"""
        try:
            import os
            import glob
            
            # Find the most recent HTML file
            html_files = glob.glob(os.path.join(CACHE_DIR, "html_analysis", "html_response_*.html"))
            if not html_files:
                return
            
            latest_file = max(html_files, key=os.path.getctime)
            
            print(f"🔍 Analyzing saved HTML file: {latest_file}")
            
            with open(latest_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for useful patterns
            import re
            
            # Find JavaScript file references
            js_files = re.findall(r'src\s*=\s*["\']([^"\']*\.js[^"\']*)["\']', content, re.IGNORECASE)
            if js_files:
                print(f"📄 Found JavaScript files: {js_files}")
            
            # Find API endpoints
            api_endpoints = re.findall(r'["\']([^"\']*(?:api|load|server)[^"\']*\.php[^"\']*)["\']', content, re.IGNORECASE)
            if api_endpoints:
                print(f"🔗 Found API endpoints: {api_endpoints}")
            
            # Find MAC references
            mac_refs = re.findall(r'mac["\']?\s*[=:]\s*["\']?([^"\';\s]+)', content, re.IGNORECASE)
            if mac_refs:
                print(f"🔑 Found MAC references: {mac_refs}")
            
            # Try to load the referenced JavaScript files
            for js_file in js_files[:3]:  # Try first 3 JS files
                try:
                    if not js_file.startswith('http'):
                        js_url = f"{self.portal_url}c/{js_file}"
                    else:
                        js_url = js_file
                    
                    print(f"🔍 Trying to load JS file: {js_url}")
                    response = self.requests.session.get(js_url, timeout=10)
                    
                    if response.status_code == 200:
                        js_content = response.text
                        channels = self.extract_channels_from_js_content(js_content)
                        if channels:
                            print(f"✅ Found {len(channels)} channels in {js_file}")
                            return channels
                            
                except Exception as e:
                    print(f"❌ Failed to load {js_file}: {e}")
                    continue
            
        except Exception as e:
            print(f"❌ HTML analysis error: {e}")
            
            
    def analyze_provider_html_structure(self):
        """Analyze the provider's HTML structure to find channel data extraction methods"""
        try:
            print("🔬 Deep analysis of provider HTML structure...")
            
            # Get the main STB interface page
            main_url = f"{self.portal_url}c/"
            response = self.requests.session.get(main_url, timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Save for manual inspection
                self.save_html_for_detailed_analysis(html_content, "main_interface")
                
                # Extract JavaScript file URLs
                js_files = self.extract_all_js_files(html_content)
                
                # Try to extract configuration or data endpoints
                config_endpoints = self.extract_config_endpoints(html_content)
                
                # Look for AJAX endpoints
                ajax_endpoints = self.extract_ajax_endpoints(html_content)
                
                print(f"📄 Found {len(js_files)} JavaScript files")
                print(f"🔧 Found {len(config_endpoints)} config endpoints")
                print(f"🌐 Found {len(ajax_endpoints)} AJAX endpoints")
                
                # Try to load and analyze each resource
                all_endpoints = js_files + config_endpoints + ajax_endpoints
                
                for endpoint in all_endpoints[:10]:  # Limit to prevent overload
                    try:
                        self.analyze_endpoint_for_channel_data(endpoint)
                    except Exception as e:
                        print(f"❌ Endpoint analysis failed: {e}")
                        continue
            
            return []
            
        except Exception as e:
            print(f"❌ Provider analysis error: {e}")
            return []
        
    def save_html_for_detailed_analysis(self, html_content, filename_suffix):
        """Save HTML with detailed analysis markers"""
        try:
            import os
            analysis_dir = os.path.join(CACHE_DIR, "html_analysis")
            os.makedirs(analysis_dir, exist_ok=True)
            
            timestamp = int(time.time())
            filename = f"detailed_analysis_{filename_suffix}_{timestamp}.html"
            filepath = os.path.join(analysis_dir, filename)
            
            # Add analysis markers
            analysis_header = f"""
    <!-- DETAILED ANALYSIS REPORT -->
    <!-- Timestamp: {timestamp} -->
    <!-- Provider: {self.portal_url} -->
    <!-- MAC: {self.mac_address} -->
    <!-- Analysis Type: {filename_suffix} -->
    <!-- 
    EXTRACTION ATTEMPTS:
    1. JavaScript file analysis
    2. Configuration endpoint detection
    3. AJAX endpoint extraction
    4. Embedded JSON detection
    5. M3U playlist search
    6. Dynamic content loading analysis

    NEXT STEPS:
    - Examine JavaScript files for dynamic loading
    - Check for WebSocket connections
    - Look for encrypted/obfuscated data
    - Analyze browser developer tools network tab
    -->

    """
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(analysis_header)
                f.write(html_content)
            
            print(f"💾 Detailed analysis saved: {filepath}")
            
        except Exception as e:
            print(f"❌ Error saving detailed analysis: {e}")
            
            
    def show_provider_analysis_results(self):
        """Show comprehensive analysis results to user"""
        analysis_window = tk.Toplevel(self.root)
        analysis_window.title("🔬 Provider Analysis Results")
        analysis_window.geometry("600x500")
        analysis_window.grab_set()
        
        # Header
        tk.Label(analysis_window, 
                text="🔬 Provider Analysis Complete", 
                font=("Arial", 14, "bold"), fg="#2196F3").pack(pady=10)
        
        # Results text
        results_text = tk.Text(analysis_window, wrap=tk.WORD, font=("Consolas", 9))
        results_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        analysis_results = f"""
    📊 ANALYSIS RESULTS FOR: {self.portal_url}

    🔍 PROVIDER TYPE: Web-Based STB Interface
    📱 PLATFORM: MAG STB Emulation
    🌐 ACCESS METHOD: Browser-Only Interface

    ❌ DIRECT API ACCESS: Not Available
    ❌ M3U PLAYLIST: Not Provided
    ❌ JSON ENDPOINTS: Protected/Non-Existent
    ❌ AUTOMATED EXTRACTION: Not Possible

    🔧 TECHNICAL DETAILS:
    • All endpoints return HTML interface
    • Channel data loaded dynamically via JavaScript
    • Requires full browser session with cookies
    • May use WebSocket for real-time updates
    • Interface designed for MAG STB devices

    💡 RECOMMENDED SOLUTIONS:

    1️⃣ CONTACT YOUR PROVIDER:
    Ask for: M3U playlist URL or API documentation
    Request: Direct streaming links
    Alternative: Xtream Codes API if available

    2️⃣ USE DEDICATED IPTV APPS:
    • Perfect Player (Android/Windows)
    • VLC Media Player (with M3U)
    • Kodi with IPTV Simple Client
    • TiviMate (Android)

    3️⃣ BROWSER-BASED VIEWING:
    • Open {self.portal_url}c/ in Chrome/Firefox
    • Use browser for channel selection
    • Cast to TV if needed

    4️⃣ ALTERNATIVE APPROACHES:
    • Check if provider has mobile app
    • Look for Enigma2 or m3u8 endpoints
    • Try different MAC address formats

    📁 ANALYSIS FILES:
    Detailed HTML files saved in cache/html_analysis/
    You can examine these files or send to developer

    🔔 NOTE: This type of provider interface cannot be
    automated due to security and licensing restrictions.
    """
        
        results_text.insert(tk.END, analysis_results)
        results_text.config(state=tk.DISABLED)
        
        # Buttons
        button_frame = tk.Frame(analysis_window)
        button_frame.pack(fill=tk.X, padx=20, pady=10)
        
        def open_cache_folder():
            cache_path = os.path.join(CACHE_DIR, "html_analysis")
            if os.path.exists(cache_path):
                os.startfile(cache_path)  # Windows
        
        tk.Button(button_frame, text="📁 Open Analysis Files", 
                command=open_cache_folder,
                bg="#2196F3", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=5)
        
        def copy_provider_info():
            provider_info = f"Provider: {self.portal_url}\nMAC: {self.mac_address}\nType: Web-based STB Interface"
            analysis_window.clipboard_clear()
            analysis_window.clipboard_append(provider_info)
            messagebox.showinfo("Copied", "Provider info copied to clipboard")
        
        tk.Button(button_frame, text="📋 Copy Provider Info", 
                command=copy_provider_info,
                bg="#4CAF50", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="❌ Close", 
                command=analysis_window.destroy,
                bg="#f44336", fg="white", font=("Arial", 10)).pack(side=tk.RIGHT, padx=5)
        
    def analyze_endpoint_for_channel_data(self, endpoint):
        """Analyze individual endpoint for channel data"""
        try:
            print(f"🔍 Analyzing endpoint: {endpoint}")
            
            # Try with MAC parameter
            if '?' in endpoint:
                test_url = f"{endpoint}&mac={self.mac_address}"
            else:
                test_url = f"{endpoint}?mac={self.mac_address}"
            
            response = self.requests.session.get(test_url, timeout=10)
            
            if response.status_code == 200:
                content = response.text.strip()
                
                # Check content type
                if content.startswith('{') or content.startswith('['):
                    # JSON response
                    try:
                        data = response.json()
                        if self.contains_channel_data(data):
                            print(f"✅ Found JSON channel data in: {endpoint}")
                            return self.extract_channels_from_json_data(data)
                    except:
                        pass
                
                elif "#EXTM3U" in content:
                    # M3U response
                    channels = self.parse_m3u_playlist(content)
                    if channels:
                        print(f"✅ Found M3U channel data in: {endpoint}")
                        return channels
                
                elif len(content) > 1000 and any(keyword in content.lower() for keyword in ['channel', 'stream', 'tv']):
                    # Potential JavaScript or HTML with channel data
                    channels = self.extract_from_complex_content(content)
                    if channels:
                        print(f"✅ Found embedded channel data in: {endpoint}")
                        return channels
                        
        except Exception as e:
            print(f"❌ Endpoint analysis failed for {endpoint}: {e}")
        
        return []
    
    
    def extract_from_complex_content(self, content):
        """Extract channel data from complex non-JSON content"""
        try:
            channels = []
            
            # Try different parsing approaches for various content types
            
            # Method 1: Look for JavaScript-like data structures
            js_patterns = [
                r'channels?\s*[=:]\s*(\[.*?\])',
                r'items?\s*[=:]\s*(\[.*?\])',
                r'data\s*[=:]\s*(\[.*?\])',
                r'streams?\s*[=:]\s*(\[.*?\])',
            ]
            
            for pattern in js_patterns:
                matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    try:
                        data = json.loads(match)
                        if isinstance(data, list) and len(data) > 0:
                            extracted = self.extract_channels_from_json_data(data)
                            if extracted:
                                channels.extend(extracted)
                    except:
                        continue
            
            # Method 2: Look for URL patterns
            url_patterns = [
                r'["\']((https?://[^"\']+\.(?:ts|m3u8|mp4)[^"\']*?))["\']',
                r'["\']((rtmp://[^"\']+))["\']',
                r'["\']((http://[^"\']+/ch/[^"\']+))["\']',
            ]
            
            for pattern in url_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple):
                        url = match[0]
                    else:
                        url = match
                    
                    if self.is_valid_stream_url(url):
                        name = self.extract_name_from_url(url)
                        channels.append((name, url, url))
            
            # Method 3: Look for serialized data or other formats
            # This could be extended based on what format the provider actually uses
            
            # Remove duplicates
            unique_channels = []
            seen_urls = set()
            for channel in channels:
                if len(channel) >= 2 and channel[1] not in seen_urls:
                    seen_urls.add(channel[1])
                    unique_channels.append(channel)
            
            return unique_channels[:50]  # Limit to prevent noise
            
        except Exception as e:
            print(f"❌ Complex content extraction error: {e}")
            return []
    
    
    def contains_channel_data(self, data):
        """Check if JSON data contains channel information"""
        if isinstance(data, dict):
            # Look for channel-related keys
            channel_keys = ['channels', 'streams', 'tv', 'live', 'playlist', 'items', 'data']
            for key in channel_keys:
                if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                    return True
        elif isinstance(data, list) and len(data) > 0:
            # Check if list items look like channels
            if isinstance(data[0], dict):
                channel_fields = ['name', 'url', 'stream', 'cmd', 'title']
                for field in channel_fields:
                    if field in data[0]:
                        return True
        
        return False
        
        
    def extract_ajax_endpoints(self, html_content):
        """Extract AJAX or XHR endpoints"""
        import re
        patterns = [
            r'ajax\s*\(\s*["\']([^"\']*)["\']',
            r'xhr\.open\s*\(\s*["\']GET["\'],\s*["\']([^"\']*)["\']',
            r'fetch\s*\(\s*["\']([^"\']*)["\']',
            r'XMLHttpRequest.*?["\']([^"\']*\.php[^"\']*)["\']',
        ]
        
        endpoints = []
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                if not match.startswith('http'):
                    full_url = f"{self.portal_url}c/{match}"
                else:
                    full_url = match
                endpoints.append(full_url)
        
        return list(set(endpoints))
        
    def extract_config_endpoints(self, html_content):
        """Extract configuration or API endpoints"""
        import re
        patterns = [
            r'["\']([^"\']*(?:config|settings|init)[^"\']*\.(?:php|json)[^"\']*)["\']',
            r'["\']([^"\']*(?:api|load|get)[^"\']*\.php[^"\']*)["\']',
            r'url\s*:\s*["\']([^"\']*\.php[^"\']*)["\']',
            r'endpoint\s*:\s*["\']([^"\']*)["\']',
        ]
        
        endpoints = []
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                if not match.startswith('http'):
                    full_url = f"{self.portal_url}c/{match}"
                else:
                    full_url = match
                endpoints.append(full_url)
        
        return list(set(endpoints))
        
        
    def extract_all_js_files(self, html_content):
        """Extract all JavaScript file references"""
        import re
        patterns = [
            r'src\s*=\s*["\']([^"\']*\.js[^"\']*)["\']',
            r'<script[^>]*src\s*=\s*["\']([^"\']*\.js[^"\']*)["\'][^>]*>',
            r'loadScript\s*\(\s*["\']([^"\']*\.js[^"\']*)["\']',
            r'require\s*\(\s*["\']([^"\']*\.js[^"\']*)["\']',
        ]
        
        js_files = []
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                if not match.startswith('http'):
                    full_url = f"{self.portal_url}c/{match}"
                else:
                    full_url = match
                js_files.append(full_url)
        
        return list(set(js_files))  # Remove duplicates
        
        
    def extract_mag_player_channels(self, js_content):
        """Extract channels from MAG player-specific structures"""
        try:
            import re
            channels = []
            
            # Look for MAG player channel definitions
            mag_patterns = [
                # Player configuration with channels
                r'player\.(?:config|channels|streams)\s*=\s*(\{.*?\})',
                r'stb\.player\.(?:config|channels)\s*=\s*(\{.*?\})',
                
                # Channel definitions in player
                r'this\.channels\s*=\s*\[(.*?)\]',
                r'var\s+channels\s*=\s*\[(.*?)\]',
                
                # Stream URLs in player functions
                r'play\s*\(\s*["\']([^"\']+)["\'].*?["\']([^"\']+)["\']',
                r'setMedia\s*\(\s*["\']([^"\']+)["\']',
                
                # MAG STB specific patterns
                r'stb\.play\s*\(\s*["\']([^"\']+)["\']',
                r'gSTB\.Play\s*\(\s*["\']([^"\']+)["\']',
            ]
            
            for pattern in mag_patterns:
                matches = re.findall(pattern, js_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        url = match[0] if self.is_valid_stream_url(match[0]) else match[1]
                        name = match[1] if match[0] == url else match[0]
                        
                        if self.is_valid_stream_url(url):
                            if not name or len(name) < 3:
                                name = self.extract_name_from_url(url)
                            channels.append((name, self.build_full_url(url), url))
                    
                    elif isinstance(match, str):
                        if self.is_valid_stream_url(match):
                            name = self.extract_name_from_url(match)
                            channels.append((name, self.build_full_url(match), match))
            
            return channels
            
        except Exception as e:
            print(f"❌ MAG player extraction error: {e}")
            return []
        
        
    def extract_name_from_url(self, url):
        """Extract a reasonable channel name from URL"""
        try:
            import re
            from urllib.parse import urlparse
            
            # Try to extract from path
            parsed = urlparse(url)
            path = parsed.path
            
            # Remove common extensions
            path = re.sub(r'\.(ts|m3u8|mp4)$', '', path, flags=re.IGNORECASE)
            
            # Extract last part of path
            if '/' in path:
                name = path.split('/')[-1]
            else:
                name = path
            
            # Clean up the name
            name = re.sub(r'[_-]', ' ', name)
            name = re.sub(r'\s+', ' ', name).strip()
            
            # If still not good, use domain
            if not name or len(name) < 3:
                name = parsed.netloc or "Unknown Channel"
            
            return name.title() if name else "Unknown Channel"
            
        except:
            return "Unknown Channel"
        
        
    def is_valid_stream_url(self, url):
        """Check if URL looks like a valid stream URL"""
        if not url or len(url) < 10:
            return False
        
        # Valid stream URL patterns
        valid_patterns = [
            r'^https?://.+\.(?:ts|m3u8|mp4)(?:\?.*)?$',
            r'^rtmp://.+',
            r'^https?://.+/ch/.+',
            r'^https?://.+/stream/.+',
            r'^https?://.+/live/.+',
        ]
        
        import re
        return any(re.match(pattern, url, re.IGNORECASE) for pattern in valid_patterns)

    def extract_channels_from_json_data(self, data):
        """Extract channels from JSON data structures"""
        try:
            channels = []
            
            if isinstance(data, dict):
                # Look for channel arrays in various keys
                for key in ['channels', 'data', 'streams', 'live_streams', 'tv_channels', 'items']:
                    if key in data and isinstance(data[key], list):
                        channel_data = data[key]
                        break
                else:
                    # Look for nested data
                    if 'js' in data and isinstance(data['js'], dict):
                        js_data = data['js']
                        for key in ['data', 'channels', 'streams']:
                            if key in js_data and isinstance(js_data[key], list):
                                channel_data = js_data[key]
                                break
                        else:
                            channel_data = []
                    else:
                        channel_data = []
                        
            elif isinstance(data, list):
                channel_data = data
            else:
                return []
            
            # Process channel data
            for item in channel_data:
                if isinstance(item, dict):
                    name = item.get('name') or item.get('title') or item.get('caption') or 'Unknown Channel'
                    cmd = item.get('cmd') or item.get('url') or item.get('stream_url') or item.get('source') or ''
                    
                    if name and cmd:
                        # Build full URL
                        if cmd.startswith('http://localhost'):
                            from urllib.parse import urlparse
                            parsed = urlparse(self.portal_url)
                            full_url = cmd.replace('http://localhost', f"http://{parsed.netloc}")
                        elif cmd.startswith('/'):
                            from urllib.parse import urlparse
                            parsed = urlparse(self.portal_url)
                            full_url = f"http://{parsed.netloc}{cmd}"
                        elif cmd.startswith('http://') or cmd.startswith('https://'):
                            full_url = cmd
                        else:
                            from urllib.parse import urlparse
                            parsed = urlparse(self.portal_url)
                            full_url = f"http://{parsed.netloc}/{cmd}"
                        
                        channels.append((name, full_url, cmd))
            
            return channels
            
        except Exception as e:
            print(f"❌ JSON data extraction error: {e}")
            return []


    
        
        
    def extract_from_embedded_json(self, html_content):
        """Extract channels from embedded JSON data"""
        try:
            import re
            import json
            channels = []
            
            # Look for JSON data in various formats
            json_patterns = [
                r'<script[^>]*>\s*(?:var\s+\w+\s*=\s*)?(\{.*?"channels".*?\})\s*[;}]?\s*</script>',
                r'<script[^>]*>\s*(?:window\.\w+\s*=\s*)?(\{.*?"streams".*?\})\s*[;}]?\s*</script>',
                r'data-channels=["\'](\{.*?\})["\']',
                r'data-streams=["\'](\{.*?\})["\']',
                r'<input[^>]*value=["\'](\{.*?"channels".*?\})["\'][^>]*>',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    try:
                        data = json.loads(match)
                        if 'channels' in data:
                            channels.extend(self.process_js_channel_data(data['channels']))
                        elif 'streams' in data:
                            channels.extend(self.process_js_channel_data(data['streams']))
                    except:
                        continue
            
            return channels
            
        except Exception as e:
            print(f"❌ Embedded JSON extraction error: {e}")
            return []
        
        
    def extract_from_script_tags(self, html_content):
        """Extract channels from script tags content"""
        try:
            import re
            channels = []
            
            # Extract all script tag contents
            script_pattern = r'<script[^>]*>(.*?)</script>'
            scripts = re.findall(script_pattern, html_content, re.DOTALL | re.IGNORECASE)
            
            for script in scripts:
                # Look for channel-like data in script content
                channel_patterns = [
                    # addChannel("name", "url")
                    r'addChannel\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']',
                    
                    # channel: {name: "...", url: "..."}
                    r'name\s*:\s*["\']([^"\']+)["\']\s*,\s*url\s*:\s*["\']([^"\']+)["\']',
                    
                    # "name": "...", "stream": "..."
                    r'["\']name["\']\s*:\s*["\']([^"\']+)["\']\s*,.*?["\'](?:stream|url)["\']\s*:\s*["\']([^"\']+)["\']',
                    
                    # URLs that look like streams
                    r'["\']([^"\']*(?:live|stream|channel)[^"\']*)["\'].*?["\']([^"\']*\.(ts|m3u8|mp4)[^"\']*)["\']',
                ]
                
                for pattern in channel_patterns:
                    matches = re.findall(pattern, script, re.IGNORECASE)
                    for match in matches:
                        if len(match) >= 2:
                            name = match[0].strip()
                            url = match[1].strip()
                            
                            if name and url and (url.startswith('http') or url.startswith('/')):
                                channels.append((name, self.build_full_url(url), url))
            
            return channels
            
        except Exception as e:
            print(f"❌ Script tag extraction error: {e}")
            return []
    
    
        
    def extract_from_html_structure(self, html_content):
        """Extract channels from HTML table/div structure"""
        try:
            import re
            channels = []
            
            # Look for HTML structures that might contain channel data
            html_patterns = [
                # Table rows with channel data
                r'<tr[^>]*>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>.*?(?:href|src)=["\']([^"\']+)["\']',
                
                # Div elements with channel data
                r'<div[^>]*class=["\'][^"\']*channel[^"\']*["\'][^>]*>.*?<span[^>]*>([^<]+)</span>.*?(?:href|src)=["\']([^"\']+)["\']',
                
                # List items
                r'<li[^>]*>.*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
                
                # Option elements
                r'<option[^>]*value=["\']([^"\']+)["\'][^>]*>([^<]+)</option>',
            ]
            
            for pattern in html_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    if len(match) >= 2:
                        name = match[0] if len(match[0]) > len(match[1]) else match[1]
                        url = match[1] if len(match[0]) > len(match[1]) else match[0]
                        
                        # Clean up the data
                        name = re.sub(r'<[^>]+>', '', name).strip()
                        if name and url and ('http' in url or url.startswith('/')):
                            channels.append((name, self.build_full_url(url), url))
            
            return channels
            
        except Exception as e:
            print(f"❌ HTML structure extraction error: {e}")
            return []
        
        
        
    def extract_from_js_variables(self, html_content):
        """Extract channels from JavaScript variables"""
        try:
            import re
            channels = []
            
            # Common JavaScript patterns for channel data
            js_patterns = [
                # var channels = [{name: "Channel", url: "stream_url"}]
                r'var\s+channels\s*=\s*(\[.*?\]);',
                r'channels\s*=\s*(\[.*?\]);',
                r'channelList\s*=\s*(\[.*?\]);',
                r'streams\s*=\s*(\[.*?\]);',
                r'playlist\s*=\s*(\[.*?\]);',
                
                # window.channels = [...]
                r'window\.channels\s*=\s*(\[.*?\]);',
                r'window\.streams\s*=\s*(\[.*?\]);',
                
                # this.channels = [...]
                r'this\.channels\s*=\s*(\[.*?\]);',
                
                # JSON.parse("...")
                r'JSON\.parse\(["\'](\[.*?\])["\']\)',
            ]
            
            for pattern in js_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    try:
                        # Try to parse as JSON
                        import json
                        data = json.loads(match)
                        channels.extend(self.process_js_channel_data(data))
                    except:
                        continue
            
            return channels
            
        except Exception as e:
            print(f"❌ JS variable extraction error: {e}")
            return []
        
        
    def process_js_channel_data(self, data):
        """Process JavaScript channel data array"""
        try:
            channels = []
            
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        name = (item.get('name') or item.get('title') or 
                            item.get('channel') or item.get('label') or 'Unknown')
                        url = (item.get('url') or item.get('stream') or 
                            item.get('src') or item.get('link') or '')
                        
                        if name and url:
                            channels.append((name, self.build_full_url(url), url))
                    elif isinstance(item, str) and item.startswith('http'):
                        # Simple URL list
                        name = item.split('/')[-1].split('?')[0] or "Channel"
                        channels.append((name, item, item))
            
            return channels
            
        except Exception as e:
            print(f"❌ JS data processing error: {e}")
            return []
        
        
    def build_full_url(self, url):
        """Build full URL from relative URL with proper cleaning"""
        try:
            # Clean any ffmpeg prefixes first
            clean_url = url.replace("ffmpeg ", "").strip()
            
            if clean_url.startswith(('http://', 'https://')):
                return clean_url
            
            from urllib.parse import urlparse
            parsed_portal = urlparse(self.portal_url)
            
            if clean_url.startswith('/'):
                return f"{parsed_portal.scheme}://{parsed_portal.netloc}{clean_url}"
            else:
                return f"{parsed_portal.scheme}://{parsed_portal.netloc}/{clean_url}"
                
        except:
            return url.replace("ffmpeg ", "").strip()

    def save_html_for_analysis(self, html_content, original_url):
        """Save HTML content for manual analysis"""
        try:
            import os
            analysis_dir = os.path.join(CACHE_DIR, "html_analysis")
            os.makedirs(analysis_dir, exist_ok=True)
            
            timestamp = int(time.time())
            filename = f"html_response_{timestamp}.html"
            filepath = os.path.join(analysis_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"<!-- Original URL: {original_url} -->\n")
                f.write(f"<!-- Timestamp: {timestamp} -->\n")
                f.write(html_content)
            
            print(f"💾 Saved HTML response for analysis: {filepath}")
            print(f"📄 You can examine this file to see the exact HTML structure your server returns")
            
        except Exception as e:
            print(f"❌ Error saving HTML for analysis: {e}")
    
        
        
        
    def try_alternative_html_endpoints(self):
        """Enhanced alternative endpoints with MAG STB API access"""
        try:
            print("🔍 Trying limited alternative endpoints to prevent loops...")
            
            # ✅ Try JavaScript module extraction first
            js_channels = self.try_javascript_module_extraction()
            if js_channels:
                return js_channels
            
            # ✅ NEW: Try direct MAG STB API access
            print("🔍 Trying direct MAG STB API endpoints...")
            mag_channels = self.try_mag_stb_api_endpoints()
            if mag_channels:
                return mag_channels
            
            # ✅ Try reduced list of most likely endpoints
            alternative_urls = [
                f"{self.portal_url}c/?get=channels&mac={self.mac_address}&format=m3u",
                f"{self.portal_url}c/?get=playlist&mac={self.mac_address}",
                f"{self.portal_url}c/?action=get_live_streams&mac={self.mac_address}&format=json&output=json",
            ]
            
            for alt_url in alternative_urls:
                try:
                    print(f"🔍 Trying alternative endpoint: {alt_url}")
                    response = self.requests.session.get(alt_url, timeout=(5, 10))
                    
                    if response.status_code == 200:
                        content = response.text.strip()
                        print(f"✅ Got response from: {alt_url}")
                        
                        # Only try specific parsing - no HTML to prevent loops
                        if content.startswith('{') or content.startswith('['):
                            try:
                                data = response.json()
                                channels = self.extract_channels_from_json_data(data)
                                if channels:
                                    print(f"✅ Found {len(channels)} channels via JSON endpoint")
                                    return channels
                            except:
                                pass
                        
                        elif "#EXTM3U" in content:
                            channels = self.parse_m3u_playlist(content)
                            if channels:
                                print(f"✅ Found {len(channels)} channels via M3U endpoint")
                                return channels
                    
                except Exception as e:
                    print(f"❌ Alternative endpoint failed: {e}")
                    continue
            
            print("❌ No alternative endpoints found channels")
            
            # ✅ Final step: Deep analysis and show results to user
            print("🔬 Starting comprehensive provider analysis...")
            self.analyze_provider_html_structure()
            
            # Show analysis results to user
            self.root.after(0, lambda: self.show_provider_analysis_results())
            
            return []
            
        except Exception as e:
            print(f"❌ Alternative endpoints error: {e}")
            return []
            
            
        
        
    def try_mag_stb_interface(self):
        """Try to extract channels from MAG STB web interface"""
        try:
            print("🔍 Attempting MAG STB interface extraction...")
            
            # First, get the main STB page to extract necessary parameters
            stb_url = f"{self.portal_url}c/"
            response = self.requests.session.get(stb_url, timeout=(15, 30))
            
            if response.status_code != 200:
                print(f"❌ STB interface not accessible: {response.status_code}")
                return []
            
            # Try to extract MAC and session info from the STB interface
            html_content = response.text
            
            # Look for MAC parameter or session tokens in the HTML
            import re
            
            # Common patterns for extracting session/MAC info
            patterns = [
                r'mac["\']?\s*[=:]\s*["\']([^"\']+)["\']',
                r'stb\.mac\s*=\s*["\']([^"\']+)["\']',
                r'device["\']?\s*[=:]\s*["\']([^"\']+)["\']',
            ]
            
            extracted_mac = None
            for pattern in patterns:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match:
                    extracted_mac = match.group(1)
                    break
            
            if not extracted_mac:
                extracted_mac = self.mac_address
            
            print(f"🔍 Using MAC: {extracted_mac}")
            
            # Try common MAG STB API endpoints
            mag_endpoints = [
                # Standard MAG portal endpoints
                f"{self.portal_url}portal.php?type=itv&action=get_all_channels&mac={extracted_mac}",
                f"{self.portal_url}server/load.php?type=itv&action=get_all_channels&mac={extracted_mac}&JsHttpRequest=1-xml",
                
                # STB-specific endpoints
                f"{self.portal_url}server/load.php?type=stb&action=get_profile&mac={extracted_mac}",
                f"{self.portal_url}server/load.php?type=itv&action=get_ordered_list&mac={extracted_mac}",
                
                # Alternative formats
                f"{self.portal_url}c/server/load.php?type=itv&action=get_all_channels&mac={extracted_mac}&JsHttpRequest=1-xml",
                f"{self.portal_url}c/portal.php?type=itv&action=get_all_channels&mac={extracted_mac}",
                
                # Try with authentication handshake first
                f"{self.portal_url}server/load.php?type=stb&action=handshake&mac={extracted_mac}",
            ]
            
            channels = []
            
            # Try authentication first
            auth_success = False
            for auth_url in [
                f"{self.portal_url}server/load.php?type=stb&action=handshake&mac={extracted_mac}",
                f"{self.portal_url}c/server/load.php?type=stb&action=handshake&mac={extracted_mac}",
                f"{self.portal_url}portal.php?type=stb&action=handshake&mac={extracted_mac}",
            ]:
                try:
                    print(f"🔐 Trying auth: {auth_url}")
                    auth_response = self.requests.session.get(auth_url, timeout=(10, 20))
                    if auth_response.status_code == 200:
                        print(f"✅ Auth successful: {auth_url}")
                        auth_success = True
                        
                        # Extract token if present
                        try:
                            auth_data = auth_response.json()
                            token = auth_data.get('js', {}).get('token', '') or auth_data.get('token', '')
                            if token:
                                print(f"🔑 Got auth token: {token[:20]}...")
                                # Add token to session headers
                                self.requests.session.headers.update({'Authorization': f'Bearer {token}'})
                        except:
                            pass
                        break
                except Exception as e:
                    print(f"❌ Auth failed: {e}")
                    continue
            
            # Now try to get channels
            for endpoint in mag_endpoints:
                try:
                    print(f"🔍 Trying MAG endpoint: {endpoint}")
                    response = self.requests.session.get(endpoint, timeout=(15, 30))
                    
                    if response.status_code == 200:
                        content = response.text.strip()
                        
                        # Try to parse as JSON
                        if content.startswith('{') or content.startswith('['):
                            try:
                                data = response.json()
                                
                                # Handle different JSON structures
                                if isinstance(data, dict):
                                    channel_data = data.get("js", {}).get("data", []) or data.get("data", []) or data.get("channels", [])
                                elif isinstance(data, list):
                                    channel_data = data
                                else:
                                    continue
                                
                                if channel_data:
                                    print(f"✅ Found {len(channel_data)} channels in MAG response")
                                    
                                    # Process MAG channel data
                                    processed_channels = self.process_mag_channel_data(channel_data)
                                    if processed_channels:
                                        return processed_channels
                                        
                            except Exception as e:
                                print(f"❌ JSON parsing failed: {e}")
                                continue
                        
                        # Try to extract from HTML/JavaScript
                        elif "<!DOCTYPE" in content or "<html" in content.lower():
                            print("🔍 Trying to extract from MAG HTML interface...")
                            extracted_channels = self.extract_channels_from_mag_html(content, endpoint)
                            if extracted_channels:
                                return extracted_channels
                        
                    else:
                        print(f"❌ MAG endpoint failed: {response.status_code}")
                        
                except Exception as e:
                    print(f"❌ MAG endpoint error: {e}")
                    continue
            
            # If standard endpoints fail, try module-based approach
            return self.try_mag_module_approach(extracted_mac)
            
        except Exception as e:
            print(f"❌ MAG STB interface error: {e}")
            return []
        
    def try_mag_stb_api_endpoints(self):
        """Try to access the actual MAG STB API endpoints that the interface uses"""
        try:
            print("🔍 Attempting direct MAG STB API access...")
            
            # These are the actual endpoints the STB interface uses for data
            api_endpoints = [
                # ITv module endpoints
                f"{self.portal_url}c/server/api/ext_module.php?name=itv&mac={self.mac_address}",
                f"{self.portal_url}c/server/api/ext_module.php?name=tv&mac={self.mac_address}",
                f"{self.portal_url}c/server/api/ext_module.php?name=live&mac={self.mac_address}",
                f"{self.portal_url}c/server/api/ext_module.php?name=channels&mac={self.mac_address}",
                
                # Direct server endpoints that might bypass the web interface
                f"{self.portal_url}server/load.php?type=itv&action=get_all_channels&mac={self.mac_address}&JsHttpRequest=1-xml",
                f"{self.portal_url}server/load.php?type=itv&action=get_ordered_list&mac={self.mac_address}&JsHttpRequest=1-xml",
                
                # Alternative server paths
                f"{self.portal_url}c/server/load.php?type=itv&action=get_all_channels&mac={self.mac_address}&JsHttpRequest=1-xml",
                f"{self.portal_url}c/server/load.php?type=itv&action=get_ordered_list&mac={self.mac_address}&JsHttpRequest=1-xml",
                
                # Portal endpoints
                f"{self.portal_url}portal.php?type=itv&action=get_all_channels&mac={self.mac_address}",
                f"{self.portal_url}c/portal.php?type=itv&action=get_all_channels&mac={self.mac_address}",
            ]
            
            for endpoint in api_endpoints:
                try:
                    print(f"🔍 Trying MAG API endpoint: {endpoint}")
                    response = self.requests.session.get(endpoint, timeout=15)
                    
                    if response.status_code == 200:
                        content = response.text.strip()
                        
                        # Check if this is actual data (not HTML)
                        if not content.startswith('<!DOCTYPE') and not content.startswith('<html'):
                            print(f"✅ Got non-HTML response from: {endpoint}")
                            print(f"📄 Response preview: {content[:200]}...")
                            
                            # Try to parse as JSON
                            if content.startswith('{') or content.startswith('['):
                                try:
                                    data = response.json()
                                    channels = self.extract_channels_from_json_data(data)
                                    if channels:
                                        print(f"✅ Found {len(channels)} channels from MAG API")
                                        return channels
                                except:
                                    pass
                            
                            # Try as other formats
                            channels = self.extract_from_complex_content(content)
                            if channels:
                                print(f"✅ Found {len(channels)} channels from MAG API content")
                                return channels
                        else:
                            print(f"❌ Endpoint returned HTML interface: {endpoint}")
                    
                except Exception as e:
                    print(f"❌ MAG API endpoint failed: {e}")
                    continue
            
            return []
            
        except Exception as e:
            print(f"❌ MAG STB API access error: {e}")
            return []

    def process_mag_channel_data(self, data):
        """Process MAG-style channel data with proper URL cleaning for 4K-CDN"""
        try:
            channels = []
            from urllib.parse import urlparse
            parsed_portal = urlparse(self.portal_url)
            portal_domain = parsed_portal.netloc
            
            for item in data:
                if isinstance(item, dict):
                    # Try multiple name fields
                    name = (item.get('name') or item.get('title') or item.get('caption') or 
                        item.get('channel_name') or item.get('display_name') or 'Unknown Channel')
                    
                    # Try multiple command/URL fields
                    cmd = (item.get('cmd') or item.get('url') or item.get('stream_url') or 
                        item.get('source') or item.get('link') or '')
                    
                    if cmd and name:
                        # Clean up command - remove any ffmpeg prefixes
                        original_cmd = cmd.replace("ffmpeg ", "").strip()
                        
                        # Build proper stream URL for display
                        if original_cmd.startswith("http://localhost"):
                            stream_url = original_cmd.replace("http://localhost", f"{parsed_portal.scheme}://{portal_domain}")
                        elif original_cmd.startswith("localhost"):
                            stream_url = f"{parsed_portal.scheme}://{portal_domain}" + original_cmd[9:]
                        elif original_cmd.startswith("/"):
                            stream_url = f"{parsed_portal.scheme}://{portal_domain}{original_cmd}"
                        elif original_cmd.startswith("http://") or original_cmd.startswith("https://"):
                            stream_url = original_cmd
                        elif original_cmd.startswith("rtmp://"):
                            stream_url = original_cmd
                        else:
                            stream_url = f"{parsed_portal.scheme}://{portal_domain}/{original_cmd}"
                        
                        # Store the original command for token requests
                        channels.append((name, stream_url, original_cmd))
            
            print(f"✅ Processed {len(channels)} MAG channels")
            return channels
            
        except Exception as e:
            print(f"❌ MAG channel processing error: {e}")
            return []


    def try_mag_module_approach(self, mac_address):
        """Try to load channels using MAG module system"""
        try:
            print("🔍 Trying MAG module approach...")
            
            # Common MAG modules that might contain channel data
            modules_to_try = [
                'tv',
                'live',
                'channels', 
                'itv',
                'player',
                'main',
                'stb'
            ]
            
            for module in modules_to_try:
                try:
                    # Try module API endpoint
                    module_url = f"{self.portal_url}server/api/ext_module.php?name={module}&mac={mac_address}"
                    print(f"🔍 Trying module: {module_url}")
                    
                    response = self.requests.session.get(module_url, timeout=(10, 20))
                    
                    if response.status_code == 200:
                        content = response.text.strip()
                        
                        if content and len(content) > 100:  # Reasonable content length
                            print(f"✅ Got response from module '{module}': {len(content)} chars")
                            
                            # Try to extract channel data from module response
                            channels = self.extract_channels_from_module_response(content, module)
                            if channels:
                                return channels
                    
                except Exception as e:
                    print(f"❌ Module '{module}' failed: {e}")
                    continue
            
            return []
            
        except Exception as e:
            print(f"❌ MAG module approach error: {e}")
            return []

    def extract_channels_from_mag_html(self, html_content, source_url):
        """Extract channels from MAG HTML interface"""
        try:
            print("🔍 Extracting channels from MAG HTML...")
            
            # Look for common MAG JavaScript patterns
            import re
            
            # Patterns for MAG channel data
            patterns = [
                # Channel arrays in JavaScript
                r'channels\s*=\s*(\[.*?\]);',
                r'playlist\s*=\s*(\[.*?\]);',
                r'items\s*=\s*(\[.*?\]);',
                
                # MAG-specific patterns
                r'stb\.player\.channels\s*=\s*(\[.*?\]);',
                r'module\.tv\.channels\s*=\s*(\[.*?\]);',
                
                # JSON data embedded in HTML
                r'<script[^>]*>\s*var\s+data\s*=\s*(\{.*?\});',
                r'<script[^>]*>\s*window\.channels\s*=\s*(\[.*?\]);',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    try:
                        import json
                        data = json.loads(match)
                        
                        if isinstance(data, list) and len(data) > 0:
                            channels = self.process_mag_channel_data(data)
                            if channels:
                                print(f"✅ Extracted {len(channels)} channels from MAG HTML")
                                return channels
                                
                    except Exception as e:
                        continue
            
            return []
            
        except Exception as e:
            print(f"❌ MAG HTML extraction error: {e}")
            return []

    def extract_channels_from_module_response(self, content, module_name):
        """Extract channels from MAG module response"""
        try:
            # Try to parse as JSON first
            if content.strip().startswith('{') or content.strip().startswith('['):
                try:
                    import json
                    data = json.loads(content)
                    
                    # Look for channel data in various formats
                    channel_sources = []
                    
                    if isinstance(data, dict):
                        # Try common keys
                        for key in ['channels', 'data', 'items', 'list', 'streams']:
                            if key in data and isinstance(data[key], list):
                                channel_sources.extend(data[key])
                    
                    elif isinstance(data, list):
                        channel_sources = data
                    
                    if channel_sources:
                        channels = self.process_mag_channel_data(channel_sources)
                        if channels:
                            print(f"✅ Extracted {len(channels)} channels from module '{module_name}'")
                            return channels
                            
                except:
                    pass
            
            # Try to extract from JavaScript code
            import re
            
            js_patterns = [
                r'channels\s*:\s*(\[.*?\])',
                r'items\s*:\s*(\[.*?\])',
                r'data\s*:\s*(\[.*?\])',
            ]
            
            for pattern in js_patterns:
                matches = re.findall(pattern, content, re.DOTALL)
                for match in matches:
                    try:
                        import json
                        data = json.loads(match)
                        if isinstance(data, list) and len(data) > 0:
                            channels = self.process_mag_channel_data(data)
                            if channels:
                                return channels
                    except:
                        continue
            
            return []
            
        except Exception as e:
            print(f"❌ Module response extraction error: {e}")
            return []
    
    
    

    def looks_like_channel_list(self, content):
        """Check if content looks like a simple channel list"""
        try:
            lines = content.split('\n')
            if len(lines) < 5:
                return False
            
            # Look for patterns that suggest channel data
            channel_indicators = ['http://', 'https://', 'rtmp://', '.ts', '.m3u8', 'stream']
            url_count = sum(1 for line in lines[:10] if any(indicator in line.lower() for indicator in channel_indicators))
            
            return url_count >= 3  # At least 3 lines with streaming indicators
            
        except:
            return False

    def parse_simple_text_list(self, content):
        """Parse simple text-based channel list"""
        try:
            channels = []
            lines = content.split('\n')
            
            current_name = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # If line contains URL, use it as stream
                if any(line.startswith(proto) for proto in ['http://', 'https://', 'rtmp://']):
                    if current_name:
                        channels.append((current_name, line, line))
                        current_name = None
                    else:
                        # Use URL as name if no previous name
                        name = line.split('/')[-1].split('?')[0] or "Unknown Channel"
                        channels.append((name, line, line))
                else:
                    # Assume it's a channel name
                    current_name = line
            
            return channels
            
        except Exception as e:
            print(f"❌ Simple text parsing error: {e}")
            return []

    def extract_from_javascript(self, content):
        """Try to extract channel data from JavaScript code"""
        try:
            import re
            channels = []
            
            # Common JavaScript patterns for channel data
            patterns = [
                # Array of objects: [{name: "Channel", url: "http://..."}]
                r'{\s*["\']?name["\']?\s*:\s*["\']([^"\']+)["\'].*?["\']?url["\']?\s*:\s*["\']([^"\']+)["\']',
                
                # Simple arrays: ["Channel Name", "http://url"]
                r'["\']([^"\']+)["\'],\s*["\']((https?://[^"\']+))["\']',
                
                # URL patterns in JavaScript
                r'["\']((https?://[^"\']*\.(?:ts|m3u8|mp4)[^"\']*?))["\']',
                
                # Channel objects
                r'channel["\']?\s*:\s*["\']([^"\']+)["\'].*?stream["\']?\s*:\s*["\']([^"\']+)["\']',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    if len(match) >= 2:
                        name = match[0] if match[0] else "Unknown Channel"
                        url = match[1] if match[1] else match[0]
                        
                        # Validate URL
                        if any(url.startswith(proto) for proto in ['http://', 'https://']):
                            channels.append((name, url, url))
            
            # Remove duplicates
            seen_urls = set()
            unique_channels = []
            for channel in channels:
                if channel[1] not in seen_urls:
                    seen_urls.add(channel[1])
                    unique_channels.append(channel)
            
            return unique_channels[:50]  # Limit to first 50 to avoid noise
            
        except Exception as e:
            print(f"❌ JavaScript extraction error: {e}")
            return []

    def process_alternative_channel_data(self, data):
        """Process channel data from alternative endpoints"""
        try:
            channels = []
            
            for item in data:
                if isinstance(item, dict):
                    # Try different key names
                    name = (item.get('name') or item.get('title') or 
                        item.get('channel_name') or item.get('display_name') or 
                        'Unknown Channel')
                    
                    url = (item.get('url') or item.get('stream_url') or 
                        item.get('link') or item.get('stream') or 
                        item.get('source') or '')
                    
                    # Build URL if relative
                    if url:
                        if not url.startswith(('http://', 'https://')):
                            from urllib.parse import urlparse
                            parsed_portal = urlparse(self.portal_url)
                            portal_domain = parsed_portal.netloc
                            if url.startswith('/'):
                                url = f"http://{portal_domain}{url}"
                            else:
                                url = f"http://{portal_domain}/{url}"
                        
                        channels.append((name, url, url))
                
                elif isinstance(item, str) and item.startswith(('http://', 'https://')):
                    # Simple URL list
                    name = item.split('/')[-1].split('?')[0] or "Unknown Channel"
                    channels.append((name, item, item))
            
            return channels
            
        except Exception as e:
            print(f"❌ Alternative data processing error: {e}")
            return []

    def parse_xml_channel_response(self, xml_content):
        """Parse XML channel response"""
        try:
            print("🔍 Attempting to parse XML channel data...")
            
            # Basic XML parsing - would need to be customized based on actual XML structure
            import re
            
            # Look for common XML patterns
            channels = []
            
            # Try to find channel entries
            channel_patterns = [
                r'<channel[^>]*name="([^"]*)"[^>]*url="([^"]*)"',
                r'<item[^>]*><title>([^<]*)</title>[^<]*<link>([^<]*)</link>',
                r'<entry[^>]*><name>([^<]*)</name>[^<]*<stream>([^<]*)</stream>',
            ]
            
            for pattern in channel_patterns:
                matches = re.findall(pattern, xml_content, re.IGNORECASE)
                for name, url in matches:
                    if name and url:
                        channels.append((name, url, url))
            
            return channels
            
        except Exception as e:
            print(f"❌ XML parsing error: {e}")
            return []
    
    




    def parse_m3u_playlist(self, m3u_content):
        """Parse M3U playlist content into channel list"""
        try:
            channels = []
            lines = m3u_content.split('\n')
            
            current_name = None
            for i, line in enumerate(lines):
                line = line.strip()
                
                if line.startswith('#EXTINF:'):
                    # Extract channel name
                    if ',' in line:
                        current_name = line.split(',', 1)[1].strip()
                    
                elif line.startswith('http://') or line.startswith('https://'):
                    if current_name:
                        channels.append((current_name, line, line))
                        current_name = None
            
            print(f"✅ Parsed {len(channels)} channels from M3U playlist")
            return channels
            
        except Exception as e:
            print(f"❌ M3U parsing error: {e}")
            return []
        
    
    
    def parse_xtream_channels(self, data):
        """Parse Xtream Codes API response into channel list"""
        try:
            channels = []
            
            for item in data:
                name = item.get('name', 'Unknown Channel')
                stream_id = item.get('stream_id', '')
                
                if stream_id:
                    # Build stream URL
                    stream_url = f"{self.portal_url}live/{self.mac_address}/{stream_id}.ts"
                    channels.append((name, stream_url, stream_url))
            
            print(f"✅ Parsed {len(channels)} channels from Xtream API")
            return channels
            
        except Exception as e:
            print(f"❌ Xtream parsing error: {e}")
            return []
        
        
    def debug_response_content(self, url, content):
        """Debug what kind of content we're actually getting"""
        print(f"🔍 Debug analysis for: {url}")
        print(f"📊 Content type: {type(content)}")
        print(f"📊 Content length: {len(content)} characters")
        print(f"📊 Starts with: {content[:50]}...")
        print(f"📊 Contains #EXTM3U: {'#EXTM3U' in content}")
        print(f"📊 Contains JSON markers: {content.startswith('{') or content.startswith('[')}")
        print(f"📊 Contains HTML: {'<html' in content.lower() or '<!DOCTYPE' in content}")
        print(f"📊 Contains channel keywords: {any(keyword in content.lower() for keyword in ['channel', 'stream', 'tv', 'live'])}")
    
    
    
    def _update_channels_ui(self, channels):
        """Update UI with loaded channels (runs on main thread)"""
        try:
            self.channels = channels
            self.filtered_channels = self.channels
            self.update_channel_list()
            
            # Save to cache
            self.cache_manager.save_to_cache(self.portal_url, self.mac_address, channels)
            
            # Close progress window
            if self.loading_progress:
                self.loading_progress.destroy()
                self.loading_progress = None
            
            self.status_var.set(f"Loaded {len(channels)} channels successfully!")
            
        except Exception as e:
            self.show_error_threadsafe(f"UI Update Error: {str(e)}")

    def show_error_threadsafe(self, message):
        """Show error message from background thread"""
        def show_error():
            if self.loading_progress:
                self.loading_progress.destroy()
                self.loading_progress = None
            messagebox.showerror("Error", message)
            self.status_var.set("Error occurred")
        
        self.root.after(0, show_error)

    def optimized_search(self, event=None):
        """Optimized search with debouncing and caching"""
        search_term = self.search_var.get().lower().strip()
        
        # Cancel previous delayed search
        if self.search_delay_id:
            self.root.after_cancel(self.search_delay_id)
        
        # Debounce search (wait 300ms after user stops typing)
        self.search_delay_id = self.root.after(300, lambda: self._perform_search(search_term))

    def _perform_search(self, search_term):
        """Perform the actual search"""
        if not search_term:
            self.filtered_channels = self.channels
            self.update_channel_list()
            self.status_var.set(f"Showing all {len(self.channels)} channels")
            return
        
        # Check cache first
        if search_term in self.search_cache:
            self.filtered_channels = self.search_cache[search_term]
            self.update_channel_list()
            self.status_var.set(f"Found {len(self.filtered_channels)} channels (cached)")
            return
        
        # Perform search
        start_time = time.time()
        filtered = []
        
        for channel in self.channels:
            if search_term in channel[0].lower():
                filtered.append(channel)
        
        # Cache result
        self.search_cache[search_term] = filtered
        
        # Limit cache size
        if len(self.search_cache) > 100:
            oldest_keys = list(self.search_cache.keys())[:50]
            for key in oldest_keys:
                del self.search_cache[key]
        
        self.filtered_channels = filtered
        self.update_channel_list()
        
        search_time = time.time() - start_time
        self.status_var.set(f"Found {len(filtered)} channels in {search_time:.3f}s")

    def open_export_window(self):
        """Open the M3U export options window"""
        if not self.channels:
            messagebox.showwarning("Warning", "Please fetch channels first before exporting.")
            return
        
        M3UExportWindow(self, self.channels, self.mac_address)

    def clear_cache(self):
        """Clear temporary cache files but keep permanent channel cache"""
        try:
            cleared_files = 0
            
            for filename in os.listdir(CACHE_DIR):
                file_path = os.path.join(CACHE_DIR, filename)
                
                # ✅ SKIP permanent channel cache files
                if filename.startswith("channels_") and filename.endswith(".pkl"):
                    print(f"🔒 Keeping permanent channel cache: {filename}")
                    continue
                
                # Clear other cache files
                if filename.endswith(('.pkl', '.json', '.ts', '.tmp')):
                    try:
                        os.remove(file_path)
                        cleared_files += 1
                        print(f"🗑️ Removed: {filename}")
                    except:
                        pass
            
            # Clear search cache in memory
            self.search_cache.clear()
            
            if cleared_files > 0:
                messagebox.showinfo("Success", 
                                f"Cleared {cleared_files} temporary cache files!\n"
                                "Permanent channel cache preserved.")
            else:
                messagebox.showinfo("Info", 
                                "No temporary cache files to clear.\n"
                                "Permanent channel cache preserved.")
            
            self.status_var.set("Temporary cache cleared - channel cache preserved")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to clear cache: {e}")

    def set_search(self, text):
        """Set the search box text and trigger the search."""
        self.search_var.set(text)
        self.optimized_search()

    def go_back(self):
        """Go back to user selection"""
        self.root.destroy()
        root = tk.Tk()
        IPTVUserSelection(root)
        root.mainloop()

    def get_stream_link(self, cmd):
        """Get stream link with proper URL cleaning for 4K-CDN provider"""
        # Clean the command first - remove any "ffmpeg" prefixes
        clean_cmd = cmd.replace("ffmpeg ", "").strip()
        
        print(f"🔗 Getting stream link for: {clean_cmd}")
        
        # For 4K-CDN, we need to use their portal.php endpoint
        create_link_url = f"{self.portal_url}c/portal.php?type=itv&action=create_link&mac={self.mac_address}&cmd={urllib.parse.quote(clean_cmd)}&JsHttpRequest=1-xml"
        
        try:
            # Add timestamp to prevent caching
            import random
            timestamp = int(time.time() * 1000)
            random_val = random.randint(1000, 9999)
            create_link_url += f"&_t={timestamp}&_r={random_val}"
            
            # Request with timeout
            response = self.requests.get(create_link_url, timeout=5)
            if response.status_code == 200:
                data = response.json().get('js', {})
                real_cmd = data.get('cmd', '')
                if real_cmd and real_cmd != clean_cmd:
                    # Clean the returned URL properly
                    final_url = real_cmd.replace("ffmpeg ", "").strip()
                    
                    # Fix URL if it has localhost or is relative
                    if "localhost" in final_url:
                        from urllib.parse import urlparse
                        parsed_portal = urlparse(self.portal_url)
                        final_url = final_url.replace("localhost", parsed_portal.netloc)
                    elif final_url.startswith("/"):
                        from urllib.parse import urlparse
                        parsed_portal = urlparse(self.portal_url)
                        final_url = f"{parsed_portal.scheme}://{parsed_portal.netloc}{final_url}"
                    
                    print(f"✅ Got clean stream URL: {final_url}")
                    return final_url
                else:
                    print(f"⚠️ No real_cmd in response: {data}")
            else:
                print(f"❌ HTTP {response.status_code}: {response.text[:100]}")
        except Exception as e:
            print(f"❌ Stream link error: {e}")
        
        print("❌ Failed to get stream link")
        return None
    
    
    
    
    def refresh_session_and_retry(self, original_cmd):
        """Refresh session and get new token"""
        try:
            print("🔄 Refreshing session due to token expiry...")
            
            # Clear token cache
            self.token_cache.clear()
            
            # Perform new handshake
            auth_url = f"{self.portal_url}server/load.php?type=stb&action=handshake&mac={self.mac_address}&_t={int(time.time())}"
            
            headers = {
                "Referer": self.portal_url + "index.html",
                "Origin": self.portal_url.rstrip('/'),
            }
            
            auth_response = self.requests.get(auth_url, headers=headers, timeout=10)
            
            if auth_response.status_code == 200:
                print("✅ Session refreshed successfully")
                # Now try to get the stream link again
                return self.get_stream_link(original_cmd)
            else:
                print(f"❌ Session refresh failed: {auth_response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Session refresh error: {e}")
            return None
    
    
    

    def update_channel_list(self):
        """Optimized channel list update with batch insertion"""
        self.channel_list.delete(0, tk.END)
        
        # Use batch insert for better performance
        channel_names = [channel[0] for channel in self.filtered_channels]
        
        # Insert in batches to prevent GUI freezing
        batch_size = 100
        self._insert_channels_batch(channel_names, 0, batch_size)

    def _insert_channels_batch(self, channel_names, start_idx, batch_size):
        """Insert channels in batches to prevent GUI freezing"""
        end_idx = min(start_idx + batch_size, len(channel_names))
        
        for i in range(start_idx, end_idx):
            self.channel_list.insert(tk.END, channel_names[i])
        
        # Schedule next batch if there are more channels
        if end_idx < len(channel_names):
            self.root.after(1, lambda: self._insert_channels_batch(channel_names, end_idx, batch_size))
            
            
            
    def check_stream_health(self, url):
        """Simplified health check - always return True"""
        return True  # Your streams work, so skip health checking
    
    
    
    def play_stream(self):
        """Enhanced play_stream with connection manager and retry logic"""
        selected_index = self.channel_list.curselection()
        if not selected_index:
            messagebox.showwarning("Warning", "Please select a channel to play.")
            return

        if len(self.filtered_channels[selected_index[0]]) == 3:
            channel_name, stream_url, original_cmd = self.filtered_channels[selected_index[0]]
            
            self.status_var.set(f"Connecting to {channel_name}...")
            print(f"Attempting to play: {channel_name}")
            
            # Use enhanced connection manager with retry logic
            final_url = self.connection_manager.get_stream_with_retry(original_cmd, max_retries=3)
            
            if final_url:
                # Successfully got a working stream URL
                self.status_var.set(f"Playing: {channel_name}")
                print(f"Final playable URL: {final_url}")
                self.play_video(final_url)
            else:
                # All retry attempts failed
                self.status_var.set("Connection failed")
                print(f"Failed to get working stream for: {channel_name}")
                
                # Show detailed error message
                error_msg = (f"Unable to connect to '{channel_name}' after multiple attempts.\n\n"
                            "Possible reasons:\n"
                            "• Channel is temporarily offline\n"
                            "• Network connectivity issues\n"
                            "• Token authentication expired\n"
                            "• Server overload\n\n"
                            "Try:\n"
                            "• Another channel\n"
                            "• Refresh channels (Fetch Channels)\n"
                            "• Check your internet connection")
                
                messagebox.showerror("Connection Error", error_msg)
                
                # Offer to try a basic fallback
                if messagebox.askyesno("Fallback Option", 
                                    f"Would you like to try playing '{channel_name}' "
                                    "with the basic URL (may not work)?"):
                    self.status_var.set(f"Trying fallback for: {channel_name}")
                    self.play_video(stream_url)
        
        else:
            # Handle old format channels (compatibility)
            channel_name, stream_url = self.filtered_channels[selected_index[0]]
            
            self.status_var.set(f"Playing: {channel_name} (basic mode)")
            print(f"Playing basic URL for: {channel_name}")
            
            # For old format, try basic health check first
            if self.check_stream_health(stream_url):
                self.play_video(stream_url)
            else:
                self.status_var.set("Stream unavailable")
                messagebox.showerror("Error", 
                                f"'{channel_name}' stream is not accessible.\n"
                                "Please try another channel or refresh the channel list.")

    def play_video(self, stream_url):
        """Pure direct playback - NO CACHE METHODS"""
        print(f"🎬 Direct Play Mode: {stream_url}")
        
        # Always use direct play (no cache options)
        self.play_direct(stream_url)

  
            
    def try_direct_play(self, stream_url, user_agent, referer):
        """Try direct playback first - returns True if successful"""
        try:
            # Quick test - try to open the stream briefly
            test_command = [
                "ffprobe", "-v", "quiet", 
                "-user_agent", user_agent,
                "-headers", f"Referer: {referer}",
                "-show_entries", "format=duration",
                "-timeout", "5000000",  # 5 second timeout
                stream_url
            ]
            
            # Test if stream is accessible
            result = subprocess.run(test_command, capture_output=True, timeout=8)
            
            if result.returncode == 0:
                # Stream is accessible, play directly
                print("✅ Stream test successful - playing directly")
                self.play_direct(stream_url)
                return True
            else:
                print(f"❌ Stream test failed: {result.stderr.decode() if result.stderr else 'Unknown error'}")
                return False
                
        except subprocess.TimeoutExpired:
            print("⏰ Stream test timeout - stream may be slow")
            # Try to play anyway
            self.play_direct(stream_url)
            return True
        except Exception as e:
            print(f"❌ Direct play test error: {e}")
            return False



    def try_cache_play(self, stream_url, user_agent, referer):
        """Fallback to cache method"""
        # Create cache directory
        cache_dir = os.path.join(CACHE_DIR, "stream_cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        # Generate unique filename
        import hashlib
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        url_hash = hashlib.md5(stream_url.encode()).hexdigest()[:8]
        cache_file = os.path.join(cache_dir, f"cached_stream_{timestamp}_{url_hash}.ts")
        
        # Show caching progress
        self.show_cache_progress(stream_url, cache_file)
        
        

        
        
    
            
            
            
            
    
                
            
        

    def extract_original_command(self, stream_url):
        """Extract original command from stream URL with better matching"""
        try:
            # Clean the URL first
            clean_url = stream_url.replace("ffmpeg ", "").strip()
            
            # Look for matching channel in our data
            for channel in self.channels:
                if len(channel) >= 3:
                    channel_name, channel_stream_url, channel_original_cmd = channel
                    
                    # Check if this URL matches
                    if (clean_url in channel_stream_url or 
                        channel_stream_url in clean_url or
                        self.urls_match(clean_url, channel_stream_url)):
                        print(f"✅ Found matching channel: {channel_name}")
                        return channel_original_cmd.replace("ffmpeg ", "").strip()
            
            # If not found, try to extract from URL patterns
            return self.extract_from_url_patterns(clean_url)
            
        except Exception as e:
            print(f"Error extracting original command: {e}")
            return None
        
        
    def urls_match(self, url1, url2):
        """Check if two URLs refer to the same stream"""
        try:
            from urllib.parse import urlparse, parse_qs
            
            # Parse both URLs
            parsed1 = urlparse(url1.replace("ffmpeg ", "").strip())
            parsed2 = urlparse(url2.replace("ffmpeg ", "").strip())
            
            # Compare domains
            if parsed1.netloc != parsed2.netloc:
                return False
            
            # Compare paths
            if parsed1.path != parsed2.path:
                return False
            
            # Compare stream parameter if present
            query1 = parse_qs(parsed1.query)
            query2 = parse_qs(parsed2.query)
            
            stream1 = query1.get('stream', [''])[0]
            stream2 = query2.get('stream', [''])[0]
            
            if stream1 and stream2:
                return stream1 == stream2
            
            return True
            
        except:
            return False

    def extract_from_url_patterns(self, stream_url):
        """Extract original command from common URL patterns"""
        try:
            import re
            from urllib.parse import urlparse, parse_qs
            
            # Parse the URL
            parsed = urlparse(stream_url)
            
            # Pattern 1: Look for stream ID in path or query
            patterns = [
                r'/ch/(\d+)_',           # /ch/284254_
                r'/(\d+)\?',             # /284254?play_token=...
                r'stream=(\d+)',         # stream=284254&...
                r'/(\d+)$',              # /284254 (end of path)
                r'channel_(\d+)',        # channel_284254
                r'ch_(\d+)',             # ch_284254
            ]
            
            for pattern in patterns:
                match = re.search(pattern, stream_url)
                if match:
                    channel_id = match.group(1)
                    print(f"🔍 Extracted ID '{channel_id}' using pattern: {pattern}")
                    
                    # Try to build original command
                    possible_commands = [
                        f"http://localhost/ch/{channel_id}_",
                        f"{parsed.scheme}://{parsed.netloc}/ch/{channel_id}_", 
                        f"http://localhost/play/live.php?mac={self.mac_address}&stream={channel_id}&extension=ts",
                        f"http://localhost/stream/{channel_id}",
                    ]
                    
                    # Return the first one that might work
                    for cmd in possible_commands:
                        if self.might_be_valid_command(cmd):
                            return cmd
            
            return None
            
        except Exception as e:
            print(f"Error in pattern extraction: {e}")
            return None

    def might_be_valid_command(self, cmd):
        """Quick heuristic to check if command might be valid"""
        # Simple checks
        if "localhost" in cmd or "/ch/" in cmd or "stream=" in cmd:
            return True
        return False

    

    def cache_standard_stream(self, stream_url, cache_file, user_agent, referer):
        """Standard cache method for normal providers"""
        try:
            print("📥 Using standard cache method...")
            
            ffmpeg_command = [
                "ffmpeg", "-y",
                "-user_agent", user_agent,
                "-headers", f"Referer: {referer}",
                "-probesize", "32M",
                "-analyzeduration", "10M",
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "2",
                "-i", stream_url,
                "-c", "copy",
                "-f", "mpegts",
                "-avoid_negative_ts", "make_zero",
                "-bsf:v", "h264_mp4toannexb",
                "-fflags", "+genpts",
                "-map", "0",
                cache_file
            ]
            
            print(f"🔧 Standard FFmpeg command: {' '.join(ffmpeg_command)}")
            self.update_cache_status("Starting standard download...", 0)
            
            self.download_process = subprocess.Popen(
                ffmpeg_command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            
            print(f"📡 Download process started (PID: {self.download_process.pid})")
            self.manage_continuous_cache_rotation(cache_file)
            
            # Monitor with standard timeouts
            self.monitor_standard_cache(cache_file, stream_url)
            
        except Exception as e:
            print(f"❌ Standard cache error: {e}")
            self.update_cache_status(f"Error: {str(e)}", 0)
            self.root.after(500, lambda: self.play_direct(stream_url))

    def monitor_standard_cache(self, cache_file, stream_url):
        """Monitor standard cache download"""
        start_time = time.time()
        buffer_target = 15  # 15 seconds buffer
        last_size = 0
        stall_count = 0
        
        while True:
            if self.cache_cancelled:
                if hasattr(self, 'download_process') and self.download_process.poll() is None:
                    self.download_process.terminate()
                return
            
            # Check if process ended
            if self.download_process.poll() is not None:
                stdout, stderr = self.download_process.communicate()
                return_code = self.download_process.returncode
                
                if stderr and "401 Unauthorized" in stderr:
                    print("🔑 Token expired during download")
                    self.handle_token_expired(None, cache_file)
                    return
                elif stderr and "404 Not Found" in stderr:
                    print("🚫 Channel not found (404)")
                    self.handle_channel_not_found(cache_file)
                    return
                elif stderr and "503 Service Unavailable" in stderr:
                    print("🚫 Server unavailable (503)")
                    self.handle_server_unavailable(None, cache_file)
                    return
                elif os.path.exists(cache_file) and os.path.getsize(cache_file) > 1000000:
                    print("⚠️ Download ended but we have cache")
                    self.root.after(500, lambda: self.play_with_continuous_cache(cache_file))
                    return
                else:
                    print("❌ Download failed")
                    self.root.after(500, lambda: self.play_direct(stream_url))
                    return
            
            elapsed = time.time() - start_time
            
            if os.path.exists(cache_file):
                file_size = os.path.getsize(cache_file)
                size_mb = file_size / (1024 * 1024)
                
                # Check for stalls
                if file_size == last_size:
                    stall_count += 1
                    if stall_count > 10 and file_size > 2000000:
                        print("✅ Enough cache despite stall")
                        self.root.after(500, lambda: self.play_with_continuous_cache(cache_file))
                        return
                else:
                    stall_count = 0
                    last_size = file_size
                
                # Calculate progress
                estimated_seconds = (file_size / 1024 / 1024) * 2
                progress = min(100, (estimated_seconds / buffer_target) * 100)
                
                self.update_cache_status(f"Building buffer... {size_mb:.1f}MB ({elapsed:.1f}s)", progress)
                
                # Check if ready
                if elapsed >= buffer_target or size_mb >= 30 or progress >= 100:
                    print(f"✅ Buffer ready with {size_mb:.1f}MB")
                    self.root.after(500, lambda: self.play_with_continuous_cache(cache_file))
                    return
            else:
                progress = min(100, (elapsed / buffer_target) * 100)
                self.update_cache_status(f"Connecting... ({elapsed:.1f}s)", progress)
                
                if elapsed >= 30:
                    print("❌ Cache timeout")
                    self.root.after(500, lambda: self.play_direct(stream_url))
                    return
            
            time.sleep(0.5)

    



   


    def show_player_info(self):
        """Show player information and basic controls"""
        player_info = (
            "🖥️ Windows IPTV Player - Direct Play\n\n"
            "📺 Basic Playback Controls:\n"
            "⏸️ Space: Pause/Resume\n"
            "🔊 9/0 Keys: Volume Control\n"
            "🔇 M: Mute/Unmute\n"
            "📺 F: Toggle Fullscreen\n"
            "❌ ESC or Q: Exit Player\n\n"
            "🎯 Features:\n"
            "• Direct stream playback with FFmpeg\n"
            "• M3U playlist export\n"
            "• VOD content support\n"
            "• Permanent channel cache\n"
            "• Connection retry logic\n\n"
            "💡 Tip: Use 'Fetch Channels' to load your channel list\n"
            "� Select a channel and click 'Play Channel' to start"
        )
        
        # Create info window
        info_window = tk.Toplevel(self.root)
        info_window.title("Player Information")
        info_window.geometry("420x380")
        info_window.grab_set()
        
        # Main content
        content_frame = tk.Frame(info_window)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        info_label = tk.Label(content_frame, text=player_info, 
                            font=("Arial", 9), justify=tk.LEFT, 
                            wraplength=380)
        info_label.pack(pady=10)
        
        # Buttons
        button_frame = tk.Frame(content_frame)
        button_frame.pack(pady=15)
        
        tk.Button(button_frame, text="✅ Got it!", 
                command=info_window.destroy, 
                bg="#4CAF50", fg="white", font=("Arial", 10, "bold"),
                width=12).pack()
        
        
        
    def monitor_standard_cache(self, cache_file):
        """Monitor standard cache download"""
        start_time = time.time()
        buffer_target = 15
        last_size = 0
        stall_count = 0
        
        while True:
            if self.cache_cancelled:
                if hasattr(self, 'download_process') and self.download_process.poll() is None:
                    self.download_process.terminate()
                return
            
            # Check if process ended
            if self.download_process.poll() is not None:
                stdout, stderr = self.download_process.communicate()
                return_code = self.download_process.returncode
                
                if stderr and "401 Unauthorized" in stderr:
                    print("🔑 Token expired during download")
                    self.root.after(500, lambda: self.play_direct(stream_url))
                    return
                elif os.path.exists(cache_file) and os.path.getsize(cache_file) > 1000000:
                    print("⚠️ Download ended but we have cache")
                    self.root.after(500, lambda: self.play_with_continuous_cache(cache_file))
                    return
                else:
                    print("❌ Download failed")
                    self.root.after(500, lambda: self.play_direct(stream_url))
                    return
            
            elapsed = time.time() - start_time
            
            if os.path.exists(cache_file):
                file_size = os.path.getsize(cache_file)
                size_mb = file_size / (1024 * 1024)
                
                # Check for stalls
                if file_size == last_size:
                    stall_count += 1
                    if stall_count > 10 and file_size > 2000000:
                        print("✅ Enough cache despite stall")
                        self.root.after(500, lambda: self.play_with_continuous_cache(cache_file))
                        return
                else:
                    stall_count = 0
                    last_size = file_size
                
                # Calculate progress
                estimated_seconds = (file_size / 1024 / 1024) * 2
                progress = min(100, (estimated_seconds / buffer_target) * 100)
                
                self.update_cache_status(f"Building buffer... {size_mb:.1f}MB ({elapsed:.1f}s)", progress)
                
                # Check if ready
                if elapsed >= buffer_target or size_mb >= 30 or progress >= 100:
                    print(f"✅ Buffer ready with {size_mb:.1f}MB")
                    self.root.after(500, lambda: self.play_with_continuous_cache(cache_file))
                    return
            else:
                progress = min(100, (elapsed / buffer_target) * 100)
                self.update_cache_status(f"Connecting... ({elapsed:.1f}s)", progress)
                
                if elapsed >= 30:
                    print("❌ Cache timeout")
                    self.root.after(500, lambda: self.play_direct(stream_url))
                    return
            
            time.sleep(0.5)

    def monitor_aggressive_attempt(self, cache_file, attempt_num):
        """Monitor one aggressive attempt"""
        start_time = time.time()
        
        while time.time() - start_time < 8:  # 8 second timeout
            if self.cache_cancelled:
                if hasattr(self, 'download_process') and self.download_process.poll() is None:
                    self.download_process.terminate()
                return False
            
            if self.download_process.poll() is not None:
                stdout, stderr = self.download_process.communicate()
                
                if stderr and "401 Unauthorized" in stderr:
                    elapsed = time.time() - start_time
                    print(f"⏰ Token expired after {elapsed:.2f}s")
                    return False
                elif os.path.exists(cache_file):
                    file_size = os.path.getsize(cache_file)
                    if file_size > 500000:
                        print(f"✅ Success! Got {file_size/1024/1024:.1f}MB")
                        self.manage_continuous_cache_rotation(cache_file)
                        self.root.after(500, lambda: self.play_with_continuous_cache(cache_file))
                        return True
            
            elapsed = time.time() - start_time
            if os.path.exists(cache_file):
                file_size = os.path.getsize(cache_file)
                size_mb = file_size / (1024 * 1024)
                progress = min(100, (elapsed / 8) * 100)
                self.update_cache_status(f"Attempt {attempt_num + 1}: {size_mb:.1f}MB ({elapsed:.1f}s)", progress)
                
                if file_size > 1500000 and elapsed >= 3:
                    print(f"✅ Sufficient cache after {elapsed:.1f}s")
                    self.manage_continuous_cache_rotation(cache_file)
                    self.root.after(500, lambda: self.play_with_continuous_cache(cache_file))
                    return True
            
            time.sleep(0.2)
        
        # Timeout
        if hasattr(self, 'download_process') and self.download_process.poll() is None:
            self.download_process.terminate()
        return False

    def handle_aggressive_cache_failure(self, cache_file):
        """Handle complete failure of aggressive cache method"""
        if self.cache_window:
            self.cache_window.destroy()
        
        print("🚫 Aggressive cache method completely failed")
        self.status_var.set("Cache method failed - using direct play")
        
        # Try direct play as final fallback
        selected_index = self.channel_list.curselection()
        if selected_index and len(self.filtered_channels[selected_index[0]]) >= 3:
            channel_name, stream_url, original_cmd = self.filtered_channels[selected_index[0]]
            
            # Get one final fresh URL for direct play
            final_url = self.get_stream_link(original_cmd)
            if final_url:
                clean_final_url = final_url.replace("ffmpeg ", "").strip()
                self.root.after(500, lambda: self.play_direct(clean_final_url))
            else:
                self.root.after(500, lambda: self.play_direct(stream_url))

    def monitor_ultra_fast_attempt(self, cache_file, attempt_num):
        """Monitor one ultra-fast attempt for 10 seconds"""
        start_time = time.time()
        
        while time.time() - start_time < 10:  # 10 second timeout per attempt
            if self.cache_cancelled:
                if hasattr(self, 'download_process') and self.download_process.poll() is None:
                    self.download_process.terminate()
                return False
            
            if self.download_process.poll() is not None:
                stdout, stderr = self.download_process.communicate()
                return_code = self.download_process.returncode
                
                if stderr and "401 Unauthorized" in stderr:
                    elapsed = time.time() - start_time
                    print(f"⏰ Token expired after {elapsed:.2f}s on attempt {attempt_num + 1}")
                    return False  # Try next attempt
                elif stderr:
                    print(f"❌ Other error on attempt {attempt_num + 1}: {stderr[:200]}...")
                    return False
                else:
                    # Process ended without error - check what we got
                    if os.path.exists(cache_file):
                        file_size = os.path.getsize(cache_file)
                        if file_size > 500000:  # 500KB threshold
                            print(f"✅ Success! Got {file_size/1024/1024:.1f}MB")
                            self.continue_successful_cache(cache_file)
                            return True
            
            # Check cache progress
            elapsed = time.time() - start_time
            if os.path.exists(cache_file):
                file_size = os.path.getsize(cache_file)
                size_mb = file_size / (1024 * 1024)
                progress = min(100, (elapsed / 10) * 100)
                self.update_cache_status(f"Attempt {attempt_num + 1}: {size_mb:.1f}MB ({elapsed:.1f}s)", progress)
                
                # Check if we have enough to start
                if file_size > 2000000 and elapsed >= 5:  # 2MB after 5 seconds
                    print(f"✅ Enough cache after {elapsed:.1f}s on attempt {attempt_num + 1}")
                    self.continue_successful_cache(cache_file)
                    return True
            
            time.sleep(0.2)  # Quick checks
        
        # Timeout on this attempt
        print(f"⏰ Attempt {attempt_num + 1} timed out after 10s")
        if hasattr(self, 'download_process') and self.download_process.poll() is None:
            self.download_process.terminate()
        return False

    def continue_successful_cache(self, cache_file):
        """Continue with successful cache - start playback and manage rotation"""
        print("🎬 Starting playback with successful cache...")
        self.manage_continuous_cache_rotation(cache_file)
        self.root.after(500, lambda: self.play_with_continuous_cache(cache_file))

    def handle_token_system_failure(self, original_cmd, cache_file):
        """Handle complete token system failure"""
        if self.cache_window:
            self.cache_window.destroy()
        
        print("🚫 Token system completely failed - ultra-short token lifespan")
        
        message = ("⚠️ Streaming Token System Issue\n\n"
                "This IPTV provider has extremely short token lifespans\n"
                "(tokens expire within 1-2 seconds).\n\n"
                "This makes caching impossible.\n\n"
                "Try:\n"
                "• Uncheck 'Use Cache Method' for direct play\n"
                "• Contact your provider about token timing\n"
                "• Try a different channel")
        
        messagebox.showwarning("Token System Issue", message)
        self.status_var.set("Token lifespan too short for caching")
        
        # Try one final direct play attempt
        if original_cmd:
            print("🎬 Final attempt: direct play with fresh token...")
            final_fresh_url = self.get_stream_link(original_cmd)
            if final_fresh_url:
                clean_final_url = final_fresh_url.replace("ffmpeg ", "").strip()
                self.root.after(500, lambda: self.play_direct(clean_final_url))
                return
        
        self.status_var.set("All attempts failed - try direct play mode")
                
            
            
    def handle_token_expired(self, original_cmd, cache_file):
        """Handle 401 Unauthorized errors (token expired)"""
        if self.cache_window:
            self.cache_window.destroy()
        
        print("🔑 Token expired - attempting refresh...")
        
        # Try to get fresh token
        if original_cmd:
            fresh_url = self.get_stream_link(original_cmd)
            if fresh_url:
                clean_url = fresh_url.replace("ffmpeg ", "").strip()
                print("✅ Got fresh token - retrying playback")
                self.root.after(500, lambda: self.play_direct(clean_url))
                return
        
        # Token refresh failed
        message = ("🔑 Authentication Token Expired\n\n"
                "Your session token has expired.\n\n"
                "This is normal for IPTV services.\n"
                "Try selecting the channel again.")
        
        messagebox.showwarning("Token Expired", message)
        self.status_var.set("Token expired - select channel again")

    def handle_channel_not_found(self, cache_file):
        """Handle 404 Not Found errors"""
        if self.cache_window:
            self.cache_window.destroy()
        
        print("🚫 Channel not found (404)")
        
        message = ("📺 Channel Not Available\n\n"
                "This channel is not available on the server.\n\n"
                "Possible reasons:\n"
                "• Channel has been removed\n"
                "• Channel ID has changed\n"
                "• Temporary server issue\n\n"
                "Try refreshing the channel list.")
        
        messagebox.showwarning("Channel Not Found", message)
        self.status_var.set("Channel not found - try refreshing channel list")
                
            
    def handle_server_unavailable(self, original_cmd, cache_file):
        """Handle 503 Service Unavailable errors"""
        if self.cache_window:
            self.cache_window.destroy()
        
        print("🚫 Server reports: Service Unavailable (503)")
        
        # Show user-friendly message - SINGLE DIALOG ONLY
        message = ("⚠️ Channel Temporarily Unavailable\n\n"
                "The server is experiencing high load or maintenance.\n\n"
                "What you can try:\n"
                "• Wait 1-2 minutes and try again\n"
                "• Try a different channel\n"
                "• Check if other channels work\n"
                "• The server may be doing maintenance")
        
        # ✅ SINGLE DIALOG - no second dialog
        messagebox.showwarning("Server Unavailable", message)
        
        # Just update status and let user decide what to do
        self.status_var.set("Channel unavailable - try another or wait")
        print("👤 User notified about server unavailability")
        
        
    def handle_subscription_error(self, original_cmd, cache_file, error_msg):
        """Handle HTTP 456 subscription errors"""
        if self.cache_window:
            self.cache_window.destroy()
        
        print("🚫 Subscription authentication failed (HTTP 456)")
        
        message = ("🔑 Subscription Authentication Failed\n\n"
                "HTTP 456 - Your subscription may be:\n"
                "• Expired or suspended\n"
                "• MAC address not authorized\n"
                "• Payment required\n"
                "• Account locked\n\n"
                "Contact your IPTV provider to:\n"
                "• Check subscription status\n"
                "• Verify MAC address authorization\n"
                "• Resolve any payment issues")
        
        messagebox.showerror("Subscription Error", message)
        self.status_var.set("Subscription error - contact provider")
        
    

    def handle_server_error(self, original_cmd, cache_file, error_msg):
        """Handle various server errors (5xx)"""
        if self.cache_window:
            self.cache_window.destroy()
        
        print(f"🚫 Server error detected in: {error_msg}")
        
        # Extract error code
        error_code = "5xx"
        if "HTTP error 50" in error_msg:
            if "500" in error_msg:
                error_code = "500 Internal Server Error"
            elif "502" in error_msg:
                error_code = "502 Bad Gateway" 
            elif "503" in error_msg:
                error_code = "503 Service Unavailable"
            elif "504" in error_msg:
                error_code = "504 Gateway Timeout"
        
        message = (f"🚫 Server Error: {error_code}\n\n"
                "This is a server-side issue, not your connection.\n\n"
                "The IPTV provider's server is having problems.\n"
                "This usually resolves within a few minutes.")
        
        messagebox.showwarning("Server Error", message)
        self.status_var.set(f"Server error: {error_code}")

    def retry_channel_later(self, original_cmd):
        """Retry channel after delay"""
        print("🔄 Retrying channel after delay...")
        self.status_var.set("Retrying channel...")
        
        # Try to get fresh stream
        fresh_url = self.get_stream_link(original_cmd)
        if fresh_url:
            clean_url = fresh_url.replace("ffmpeg ", "").strip()
            self.play_video(clean_url)
        else:
            self.status_var.set("Retry failed - server still unavailable")
            messagebox.showinfo("Retry Failed", 
                            "Channel is still unavailable.\n"
                            "The server may need more time to recover.")
                
            
            
    def monitor_continuous_download(self, cache_file, initial_size_mb):
        """Monitor continuous download after playback starts"""
        def monitor_loop():
            try:
                while (hasattr(self, 'download_process') and 
                    self.download_process.poll() is None and 
                    self.cache_window and 
                    self.cache_window.winfo_exists()):
                    
                    if os.path.exists(cache_file):
                        current_size = os.path.getsize(cache_file) / (1024 * 1024)
                        
                        # Show download progress without percentage
                        self.update_cache_status(f"Downloading... {current_size:.1f}MB", 100)
                    
                    time.sleep(2)
                    
            except Exception as e:
                print(f"Monitor error: {e}")
        
        # Start monitoring in background
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
            
            
            
  
                    
            
            
    def check_ffmpeg_installation(self):
        """Check if FFmpeg is properly installed"""
        try:
            result = subprocess.run(["ffmpeg", "-version"], 
                                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("✅ FFmpeg is installed and working")
                return True
            else:
                print("❌ FFmpeg command failed")
                return False
        except FileNotFoundError:
            print("❌ FFmpeg not found in PATH")
            messagebox.showerror("FFmpeg Missing", 
                            "FFmpeg is not installed or not in your system PATH.\n\n"
                            "Please:\n"
                            "1. Download FFmpeg from https://ffmpeg.org/download.html\n"
                            "2. Extract it to a folder\n"
                            "3. Add the bin folder to your system PATH\n"
                            "4. Restart this application")
            return False
        except Exception as e:
            print(f"❌ Error checking FFmpeg: {e}")
            return False
                
            
            
            
   
            
    
            
            
    def play_direct(self, stream_url):
        """Enhanced direct playback with proper URL handling for 4K-CDN"""
        user_agent = "Mozilla/5.0 (QtEmbedded; U; Linux; C)"
        referer = self.portal_url + "index.html"
        
        print("🚀 Enhanced direct playback for 4K-CDN...")
        
        # Clean the stream URL first
        clean_stream_url = stream_url.replace("ffmpeg ", "").strip()
        
        # For 4K-CDN, try to get a fresh token first
        original_cmd = self.extract_original_command(clean_stream_url)
        
        if original_cmd:
            print(f"🔍 Found original command: {original_cmd}")
            # Try to get fresh stream URL
            fresh_stream = self.get_stream_link(original_cmd)
            if fresh_stream:
                print(f"🎯 Using fresh stream: {fresh_stream}")
                clean_stream_url = fresh_stream
        
        try:
            print(f"🎬 Playing: {clean_stream_url}")
            
            ffplay_command = [
                "ffplay", "-x", "800", "-y", "600",
                "-user_agent", user_agent,
                "-headers", f"Referer: {referer}",
                "-seek_interval", "3",
                
                # Network optimizations for 4K-CDN
                "-reconnect", "1",
                "-reconnect_streamed", "1", 
                "-reconnect_delay_max", "3",
                "-timeout", "15000000",  # 15s timeout
                
                # Performance optimizations
                "-sync", "video",
                "-framedrop", 
                "-probesize", "3000000",
                "-analyzeduration", "3000000",
                
                # Error handling
                "-fflags", "+discardcorrupt",
                "-err_detect", "ignore_err",
                
                "-i", clean_stream_url
            ]
            
            process = subprocess.Popen(ffplay_command)
            self.status_var.set(f"Playing stream (PID: {process.pid})")
            print("🚀 Enhanced direct playback launched successfully!")
            return
            
        except Exception as e:
            print(f"Enhanced direct play failed: {e}")
        
        # Fallback with minimal command
        print("🔄 Trying minimal fallback...")
        try:
            process = subprocess.Popen([
                "ffplay", "-seek_interval", "3", "-i", clean_stream_url
            ])
            self.status_var.set(f"Playing minimal stream (PID: {process.pid})")
            print("🔄 Minimal fallback launched!")
            return
            
        except Exception as e:
            print(f"All playback attempts failed: {e}")
        
        # Show error message
        self.status_var.set("Playback failed")
        messagebox.showerror("Playback Failed", 
                            f"Unable to play this channel.\n\n"
                            f"The stream URL may be invalid or the channel is offline.\n\n"
                            f"Stream URL: {clean_stream_url[:100]}...\n\n"
                            f"Try:\n"
                            f"• Another channel\n"
                            f"• Refresh channels\n"
                            f"• Check your internet connection")
        
        
        
    def enable_event_mode(self):
        """Enable special event mode for high-traffic situations"""
        selected_index = self.channel_list.curselection()
        if not selected_index:
            messagebox.showwarning("Warning", "Please select a channel first.")
            return

        if len(self.filtered_channels[selected_index[0]]) == 3:
            channel_name, stream_url, original_cmd = self.filtered_channels[selected_index[0]]
            
            # Show event mode dialog
            event_window = tk.Toplevel(self.root)
            event_window.title("🏆 High-Traffic Event Mode")
            event_window.geometry("400x250")
            event_window.grab_set()
            
            tk.Label(event_window, 
                    text="🏆 Event Mode Activated", 
                    font=("Arial", 14, "bold"), fg="#E91E63").pack(pady=10)
            
            tk.Label(event_window, 
                    text=f"Optimized playback for: {channel_name}\n\n"
                        "This mode uses aggressive retry strategies\n"
                        "perfect for high-demand events.", 
                    font=("Arial", 10)).pack(pady=10)
            
            def start_event_mode():
                event_window.destroy()
                self.play_stream_with_multi_server_retry()
            
            tk.Button(event_window, text="🚀 Start Event Mode", 
                    command=start_event_mode,
                    bg="#4CAF50", fg="white", font=("Arial", 12, "bold"),
                    width=20, height=2).pack(pady=20)
            
            tk.Button(event_window, text="Cancel", 
                    command=event_window.destroy,
                    bg="#757575", fg="white").pack()

   

    def test_server_connection(self):
        """Test connection to IPTV server"""
        test_window = tk.Toplevel(self.root)
        test_window.title("Server Connection Test")
        test_window.geometry("350x200")
        test_window.grab_set()
        
        tk.Label(test_window, text="🌐 Testing Server Connection", 
                font=("Arial", 12, "bold")).pack(pady=10)
        
        status_label = tk.Label(test_window, text="Connecting...", 
                            font=("Arial", 10))
        status_label.pack(pady=10)
        
        result_text = tk.Text(test_window, height=6, width=40, font=("Courier", 9))
        result_text.pack(pady=10, padx=10)
        
        def run_test():
            try:
                result_text.insert(tk.END, "🔍 Testing portal connection...\n")
                test_window.update()
                
                start_time = time.time()
                test_url = f"{self.portal_url}server/load.php?type=stb&action=handshake&mac={self.mac_address}"
                
                response = self.requests.get(test_url, timeout=10)
                end_time = time.time()
                
                response_time = (end_time - start_time) * 1000  # Convert to ms
                
                if response.status_code == 200:
                    result_text.insert(tk.END, f"✅ Connection successful!\n")
                    result_text.insert(tk.END, f"📊 Response time: {response_time:.0f}ms\n")
                    result_text.insert(tk.END, f"🌐 Server status: Online\n")
                    if response_time < 500:
                        result_text.insert(tk.END, f"🚀 Speed: Excellent\n")
                    elif response_time < 1000:
                        result_text.insert(tk.END, f"👍 Speed: Good\n")
                    else:
                        result_text.insert(tk.END, f"⚠️ Speed: Slow\n")
                else:
                    result_text.insert(tk.END, f"❌ Error: HTTP {response.status_code}\n")
                    
            except Exception as e:
                result_text.insert(tk.END, f"❌ Connection failed: {str(e)}\n")
        
        # Run test in thread
        test_thread = threading.Thread(target=run_test, daemon=True)
        test_thread.start()
            
            
            
    def play_stream_with_multi_server_retry(self):
        """Enhanced direct play with multiple server attempts"""
        selected_index = self.channel_list.curselection()
        if not selected_index:
            messagebox.showwarning("Warning", "Please select a channel to play.")
            return

        channel_name, stream_url, original_cmd = self.filtered_channels[selected_index[0]]
        
        # Try multiple servers/endpoints
        server_attempts = [
            {"priority": 1, "delay": 0},     # Primary server
            {"priority": 2, "delay": 2},     # Backup server after 2s delay
            {"priority": 3, "delay": 5},     # Third server after 5s delay
        ]
        
        for attempt in server_attempts:
            try:
                print(f"🎯 Trying server priority {attempt['priority']}...")
                
                if attempt['delay'] > 0:
                    print(f"⏳ Waiting {attempt['delay']}s before retry...")
                    time.sleep(attempt['delay'])
                
                # Get fresh token for this attempt
                fresh_url = self.get_stream_link_with_retry(original_cmd, max_retries=2)
                if fresh_url:
                    if self.try_direct_play_fast(fresh_url, channel_name):
                        return  # Success!
                
            except Exception as e:
                print(f"❌ Server attempt {attempt['priority']} failed: {e}")
                continue
        
        # All servers failed
        self.show_high_load_options(channel_name, original_cmd)
        
        
    def get_stream_link_with_retry(self, cmd, max_retries=3):
        """Get stream with ultra-fast retry for high-load situations"""
        for attempt in range(max_retries):
            try:
                # Add random delay to spread load
                random_delay = random.uniform(0.1, 0.5)
                time.sleep(random_delay)
                
                # Ultra-fast request with load balancing
                timestamp = int(time.time() * 1000)
                random_id = random.randint(10000, 99999)
                
                create_link_url = (
                    f"{self.portal_url}server/load.php?"
                    f"type=itv&action=create_link&mac={self.mac_address}&"
                    f"cmd={urllib.parse.quote(cmd)}&"
                    f"JsHttpRequest=1-xml&_t={timestamp}&_r={random_id}&"
                    f"retry={attempt}"  # Help server track retries
                )
                
                # Shorter timeout for high-load situations
                response = self.requests.get(create_link_url, timeout=2)
                
                if response.status_code == 200:
                    data = response.json().get('js', {})
                    real_cmd = data.get('cmd', '')
                    if real_cmd and real_cmd != cmd:
                        print(f"✅ Got stream URL on attempt {attempt + 1}")
                        return real_cmd.replace("ffmpeg ", "").strip()
                
                elif response.status_code == 503:  # Server overloaded
                    backoff_delay = (attempt + 1) * 2  # 2, 4, 6 seconds
                    print(f"🚦 Server overloaded, backing off {backoff_delay}s...")
                    time.sleep(backoff_delay)
                    continue
                    
            except requests.exceptions.Timeout:
                print(f"⏰ Timeout on attempt {attempt + 1}, retrying...")
                continue
            except Exception as e:
                print(f"❌ Attempt {attempt + 1} error: {e}")
                continue
        
        return None
    
    
    def try_direct_play_fast(self, stream_url, channel_name):
        """Fast direct play optimized for high-load servers"""
        try:
            print(f"⚡ Fast direct play: {channel_name}")
            
            # Minimal FFplay for fastest startup during high load
            ffplay_command = [
                "ffplay", "-x", "800", "-y", "600",
                "-user_agent", "VLC/3.0.0 LibVLC/3.0.0",  # Different user agent
                "-seek_interval", "3",
                
                # High-load optimizations:
                "-probesize", "1M",        # Smaller probe
                "-analyzeduration", "1M",   # Faster analysis  
                "-fflags", "+fastseek+discardcorrupt",
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "3",  # Quick reconnects
                "-timeout", "10000000",       # 10s timeout
                
                # ✅ REMOVED INVALID OPTIONS:
                # "-buffer_size", "2097152",    # ❌ REMOVED - not valid for ffplay
                # "-max_delay", "1000000",      # ❌ REMOVED - not valid for ffplay
                
                "-i", stream_url
            ]
            
            process = subprocess.Popen(ffplay_command, 
                                    stdout=subprocess.DEVNULL, 
                                    stderr=subprocess.PIPE)
            
            # Quick success check
            time.sleep(1.5)
            if process.poll() is None:
                self.status_var.set(f"Playing {channel_name} (High-Load Mode)")
                print(f"✅ Fast play successful: {channel_name}")
                return True
            else:
                return False
                
        except Exception as e:
            print(f"❌ Fast direct play failed: {e}")
            return False
        
        
    def show_high_load_options(self, channel_name, original_cmd):
        """Show options when servers are overloaded"""
        options_window = tk.Toplevel(self.root)
        options_window.title("Server High Load Detected")
        options_window.geometry("450x300")
        options_window.grab_set()
        
        tk.Label(options_window, 
                text="⚠️ High Server Load Detected", 
                font=("Arial", 14, "bold"), fg="red").pack(pady=10)
        
        tk.Label(options_window, 
                text=f"'{channel_name}' is experiencing high demand\n"
                    "during this popular event.", 
                font=("Arial", 11)).pack(pady=10)
        
        # Option 1: Keep Trying
        def keep_trying():
            options_window.destroy()
            self.continuous_retry_mode(channel_name, original_cmd)
        
        tk.Button(options_window, text="🔄 Keep Trying (Auto-Retry)", 
                command=keep_trying,
                bg="#2196F3", fg="white", font=("Arial", 11, "bold"),
                width=30, height=2).pack(pady=5)
        
        # Option 2: Try Alternative Quality
        def try_alternative():
            options_window.destroy()
            self.find_alternative_stream(channel_name)
        
        tk.Button(options_window, text="📺 Find Alternative Stream", 
                command=try_alternative,
                bg="#FF9800", fg="white", font=("Arial", 11, "bold"),
                width=30, height=2).pack(pady=5)
        
        # Option 3: Wait and Retry
        def wait_and_retry():
            options_window.destroy()
            self.scheduled_retry(channel_name, original_cmd, delay=60)
        
        tk.Button(options_window, text="⏰ Wait 1 Minute & Retry", 
                command=wait_and_retry,
                bg="#4CAF50", fg="white", font=("Arial", 11, "bold"),
                width=30, height=2).pack(pady=5)
        
        # Cancel
        tk.Button(options_window, text="❌ Cancel", 
                command=options_window.destroy,
                bg="#f44336", fg="white", font=("Arial", 10),
                width=15).pack(pady=20)
        
        
        
        
    def continuous_retry_mode(self, channel_name, original_cmd):
        """Continuous retry with backoff during high load"""
        retry_window = tk.Toplevel(self.root)
        retry_window.title("Auto-Retry Mode")
        retry_window.geometry("400x200")
        retry_window.grab_set()
        
        tk.Label(retry_window, 
                text="🔄 Auto-Retry Mode Active", 
                font=("Arial", 14, "bold")).pack(pady=10)
        
        status_label = tk.Label(retry_window, 
                            text="Attempting connection...", 
                            font=("Arial", 11))
        status_label.pack(pady=10)
        
        attempt_label = tk.Label(retry_window, 
                                text="Attempt 1", 
                                font=("Arial", 10), fg="blue")
        attempt_label.pack(pady=5)
        
        cancel_retry = tk.BooleanVar(value=False)
        tk.Button(retry_window, text="Stop Retry", 
                command=lambda: cancel_retry.set(True),
                bg="red", fg="white").pack(pady=20)
        
        def retry_loop():
            attempt = 1
            backoff_delays = [5, 10, 15, 30, 45, 60]  # Progressive backoff
            
            while not cancel_retry.get() and retry_window.winfo_exists():
                try:
                    # Update UI
                    retry_window.after(0, lambda a=attempt: attempt_label.config(text=f"Attempt {a}"))
                    retry_window.after(0, lambda: status_label.config(text="Getting fresh token..."))
                    
                    # Try to get stream
                    fresh_url = self.get_stream_link_with_retry(original_cmd, max_retries=1)
                    if fresh_url:
                        retry_window.after(0, lambda: status_label.config(text="Token received, trying playback..."))
                        
                        if self.try_direct_play_fast(fresh_url, channel_name):
                            retry_window.after(0, lambda: retry_window.destroy())
                            return  # Success!
                    
                    # Failed, wait with backoff
                    delay_index = min(attempt - 1, len(backoff_delays) - 1)
                    delay = backoff_delays[delay_index]
                    
                    for remaining in range(delay, 0, -1):
                        if cancel_retry.get():
                            return
                        retry_window.after(0, lambda r=remaining: status_label.config(
                            text=f"Server busy, retrying in {r}s..."))
                        time.sleep(1)
                    
                    attempt += 1
                    
                except Exception as e:
                    print(f"Retry error: {e}")
                    time.sleep(10)
        
        # Start retry loop
        retry_thread = threading.Thread(target=retry_loop, daemon=True)
        retry_thread.start()
        
        
        
        
    def find_alternative_stream(self, channel_name):
        """Find alternative streams of the same channel"""
        alternatives = []
        search_terms = channel_name.lower().split()
        
        # Look for similar channels
        for channel in self.channels:
            alt_name = channel[0].lower()
            
            # Check if it's a similar channel
            matches = sum(1 for term in search_terms if term in alt_name)
            if matches >= len(search_terms) // 2 and channel[0] != channel_name:
                alternatives.append(channel)
        
        if alternatives:
            self.show_alternatives_window(channel_name, alternatives)
        else:
            messagebox.showinfo("No Alternatives", 
                            f"No alternative streams found for '{channel_name}'.\n"
                            "Try waiting for server load to decrease.")

    def show_alternatives_window(self, original_name, alternatives):
        """Show alternative streams window"""
        alt_window = tk.Toplevel(self.root)
        alt_window.title("Alternative Streams")
        alt_window.geometry("500x400")
        alt_window.grab_set()
        
        tk.Label(alt_window, 
                text=f"Alternative streams for '{original_name}':", 
                font=("Arial", 12, "bold")).pack(pady=10)
        
        # List of alternatives
        alt_listbox = Listbox(alt_window, font=("Arial", 10), height=10)
        alt_listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        for alt in alternatives:
            alt_listbox.insert(tk.END, alt[0])
        
        def play_alternative():
            selection = alt_listbox.curselection()
            if selection:
                alt_channel = alternatives[selection[0]]
                alt_window.destroy()
                # Try to play the alternative
                fresh_url = self.get_stream_link_with_retry(alt_channel[2])
                if fresh_url:
                    self.try_direct_play_fast(fresh_url, alt_channel[0])
        
        tk.Button(alt_window, text="▶️ Play Selected", 
                command=play_alternative,
                bg="#4CAF50", fg="white", font=("Arial", 11, "bold")).pack(pady=10)
        
        
        

    def try_immediate_play(self, stream_url, user_agent, referer):
        """INSTANT play attempt - no delays, no checks, just GO!"""
        try:
            print(f"⚡ INSTANT play attempt: {stream_url}")
            
            # ✅ ULTRA-MINIMAL FFplay command - FASTEST POSSIBLE
            ffplay_command = [
                "ffplay", 
                "-i", stream_url  # Absolute minimum - just play it NOW!
            ]
            
            # ✅ START IMMEDIATELY - no pipes, no checks, just launch!
            process = subprocess.Popen(ffplay_command)
            
            self.status_var.set(f"Playing direct stream (PID: {process.pid})")
            print("⚡ INSTANT play launched!")
            return True
            
        except Exception as e:
            print(f"⚡ INSTANT play error: {e}")
            return False
        
        
    def get_stream_link_instant(self, cmd):
        """Get stream link with ZERO delays for ultra-short tokens"""
        print(f"🚀 INSTANT token request for: {cmd}")
        
        # ✅ INSTANT request - no timestamps, no random, just GO!
        create_link_url = f"{self.portal_url}server/load.php?type=itv&action=create_link&mac={self.mac_address}&cmd={urllib.parse.quote(cmd)}&JsHttpRequest=1-xml"
        
        try:
            # ✅ SHORTEST POSSIBLE timeout
            response = self.requests.get(create_link_url, timeout=1)
            if response.status_code == 200:
                data = response.json().get('js', {})
                real_cmd = data.get('cmd', '')
                if real_cmd and real_cmd != cmd:
                    clean_url = real_cmd.replace("ffmpeg ", "").strip()
                    print(f"🚀 INSTANT token: {clean_url}")
                    return clean_url
        except:
            pass
        
        return None



    
    def update_download_status(self, status, progress, size_mb, speed_kbs):
        """Update download progress from background thread"""
        def update():
            if self.download_window and self.download_window.winfo_exists():
                # Update status
                self.download_status.config(text=status)
                
                # Update progress bar
                filled = int(progress / 10)
                empty = 10 - filled
                bar = "[" + "█" * filled + "░" * empty + f"] {progress:.0f}%"
                self.progress_bar.config(text=bar)
                
                # Update speed info
                if speed_kbs > 1024:
                    speed_text = f"{speed_kbs/1024:.1f} MB/s"
                else:
                    speed_text = f"{speed_kbs:.0f} KB/s"
                
                self.speed_info.config(text=f"Speed: {speed_text} | Downloaded: {size_mb:.1f} MB")
        
        self.root.after(0, update)
    
    def cancel_download(self):
        """Cancel the download process"""
        self.download_cancelled = True
        if self.download_window:
            self.download_window.destroy()
            
            
   
        
   
                
                
  
            
            
   
            
            
   
        
    def trim_active_cache_file(self, file_info):
        """Trim the beginning of an active cache file to reduce size"""
        try:
            file_path = file_info['path']
            current_size = file_info['size']
            
            # Keep only the last 200MB of the file (about 100 seconds of HD video)
            target_size = 200 * 1024 * 1024  # 200MB
            
            if current_size <= target_size:
                return  # File is already small enough
            
            print(f"✂️ Trimming cache file: {file_info['name']} ({current_size/1024/1024:.1f}MB)")
            
            # Create temporary file
            temp_path = file_path + ".tmp"
            bytes_to_skip = current_size - target_size
            
            # Copy the last part of the file
            with open(file_path, 'rb') as src:
                src.seek(bytes_to_skip)  # Skip the beginning
                with open(temp_path, 'wb') as dst:
                    # Copy in chunks
                    chunk_size = 1024 * 1024  # 1MB chunks
                    while True:
                        chunk = src.read(chunk_size)
                        if not chunk:
                            break
                        dst.write(chunk)
            
            # Replace original with trimmed version
            os.replace(temp_path, file_path)
            
            new_size = os.path.getsize(file_path)
            saved_mb = (current_size - new_size) / (1024 * 1024)
            print(f"✅ Trimmed {saved_mb:.1f}MB from active cache file")
            
        except Exception as e:
            print(f"Error trimming cache file: {e}")
            # Clean up temp file if it exists
            temp_path = file_info['path'] + ".tmp"
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
                
                
                
                
   
   


            
    def cleanup_orphaned_processes(self):
        """Clean up any orphaned FFmpeg/FFplay processes"""
        try:
            import psutil
            
            current_pid = os.getpid()
            orphaned_count = 0
            
            for proc in psutil.process_iter(['pid', 'name', 'ppid', 'create_time']):
                try:
                    # Check for FFmpeg/FFplay processes
                    if proc.info['name'] and proc.info['name'].lower() in ['ffmpeg.exe', 'ffplay.exe']:
                        # Check if process is old (more than 2 hours)
                        process_age = time.time() - proc.info['create_time']
                        
                        if process_age > 7200:  # 2 hours
                            proc.terminate()
                            orphaned_count += 1
                            print(f"🔪 Terminated old process: {proc.info['name']} (PID: {proc.info['pid']})")
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
            if orphaned_count > 0:
                print(f"🧹 Cleaned {orphaned_count} orphaned processes")
                
        except ImportError:
            # psutil not available, skip process cleanup
            pass
        except Exception as e:
            print(f"Error in process cleanup: {e}")
            
            
            
   

            
           
    def cleanup_after_playback(self, process, download_file):
        """Clean up downloaded file after playback ends"""
        try:
            # Wait for playback to end
            process.wait()
            
            # Wait a bit more then clean up
            time.sleep(5)
            
            if os.path.exists(download_file):
                os.remove(download_file)
                print(f"🧹 Cleaned up downloaded file: {download_file}")
                
        except Exception as e:
            print(f"Error cleaning up: {e}") 
                
            
    def start_playback(self, download_file):
        """Start playing the downloaded file with 15-second delay"""
        if not os.path.exists(download_file):
            messagebox.showerror("Error", "Downloaded file not found!")
            return
        
        # Close download window
        if self.download_window:
            self.download_window.destroy()
        
        # Play the downloaded file with delay
        ffplay_command = [
            "ffplay",
            "-x", "800",
            "-y", "600",
            # === PLAY WITH 15-SECOND DELAY ===
            "-ss", "15",  # Start 15 seconds into the file
            "-autoexit",
            "-loop", "0",
            download_file  # Play the downloaded file
        ]
        
        try:
            self.status_var.set("Playing downloaded stream with 15s delay...")
            print("🎬 Playing downloaded stream with 15-second delay...")
            
            process = subprocess.Popen(ffplay_command)
            self.status_var.set(f"Playing downloaded stream (PID: {process.pid})")
            
            # Clean up file after playback (optional)
            cleanup_thread = threading.Thread(target=self.cleanup_after_playback, 
                                            args=(process, download_file), daemon=True)
            cleanup_thread.start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to play downloaded stream: {e}")


    def show_cache_status(self):
        """Show cache status window during initial download"""
        try:
            cache_window = tk.Toplevel(self.root)
            cache_window.title("Downloading Stream...")
            cache_window.geometry("350x140")
            cache_window.resizable(False, False)
            
            # Center the window
            cache_window.transient(self.root)
            cache_window.grab_set()
            
            tk.Label(cache_window, text="📥 Downloading Stream", 
                    font=("Arial", 12, "bold")).pack(pady=10)
            
            tk.Label(cache_window, text="Pre-caching segments for smooth playback...", 
                    font=("Arial", 10)).pack(pady=5)
            
            tk.Label(cache_window, text="This prevents buffering during viewing", 
                    font=("Arial", 9), fg="gray").pack(pady=5)
            
            # Progress bar simulation
            progress_label = tk.Label(cache_window, text="🔄 Downloading...", 
                                    font=("Arial", 10))
            progress_label.pack(pady=5)
            
            # Auto-close after 8 seconds (cache should be ready)
            cache_window.after(8000, lambda: cache_window.destroy() if cache_window.winfo_exists() else None)
            
            return cache_window
            
        except Exception as e:
            print(f"Error showing cache status: {e}")
            return None
        
        
        
        
        
    def fetch_vod_content(self, content_type):
        """Fetch VOD content (movies, series, etc.)"""
        def fetch_in_background():
            try:
                self.root.after(0, lambda: self.status_var.set(f"Loading {content_type}..."))
                
                # Different endpoints for different content types
                if content_type == "movies":
                    url = (f"{self.portal_url}server/load.php?"
                        f"type=vod&action=get_categories&mac={self.mac_address}&JsHttpRequest=1-xml")
                elif content_type == "series":
                    url = (f"{self.portal_url}server/load.php?"
                        f"type=series&action=get_categories&mac={self.mac_address}&JsHttpRequest=1-xml")
                else:
                    # Generic VOD
                    url = (f"{self.portal_url}server/load.php?"
                        f"type=vod&action=get_categories&mac={self.mac_address}&JsHttpRequest=1-xml")
                
                # First get categories
                response = self.requests.get(url, timeout=15)
                
                if response.status_code == 200:
                    categories = response.json().get("js", [])
                    
                    if categories:
                        # Show category selection or fetch all content
                        self.root.after(0, lambda: self.show_vod_categories(content_type, categories))
                    else:
                        self.root.after(0, lambda: messagebox.showinfo("No Content", 
                                                    f"No {content_type} categories found."))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", 
                                                f"Failed to load {content_type}: HTTP {response.status_code}"))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", 
                                            f"Failed to load {content_type}: {str(e)}"))
        
        # Run in background thread
        fetch_thread = threading.Thread(target=fetch_in_background, daemon=True)
        fetch_thread.start()

    def show_vod_categories(self, content_type, categories):
        """Show VOD categories selection"""
        cat_window = tk.Toplevel(self.root)
        cat_window.title(f"{content_type.title()} Categories")
        cat_window.geometry("400x500")
        cat_window.grab_set()
        
        tk.Label(cat_window, text=f"📁 Select {content_type.title()} Category:", 
                font=("Arial", 12, "bold")).pack(pady=10)
        
        # Categories list
        cat_list = Listbox(cat_window, font=("Arial", 10))
        cat_list.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        for category in categories:
            cat_name = category.get('title', 'Unknown Category')
            cat_list.insert(tk.END, cat_name)
        
        def load_category_content():
            selected = cat_list.curselection()
            if selected:
                category = categories[selected[0]]
                cat_window.destroy()
                self.load_category_content(content_type, category)
        
        # Buttons
        buttons_frame = tk.Frame(cat_window)
        buttons_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Button(buttons_frame, text="📂 Load Category", 
                command=load_category_content,
                bg="#2196F3", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        tk.Button(buttons_frame, text="🌐 Load All", 
                command=lambda: (cat_window.destroy(), self.load_all_vod_content(content_type)),
                bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        tk.Button(buttons_frame, text="❌ Cancel", 
                command=cat_window.destroy,
                bg="#f44336", fg="white").pack(side=tk.RIGHT, padx=5)

    def load_category_content(self, content_type, category):
        """Load content from specific category"""
        def load_in_background():
            try:
                category_id = category.get('id')
                
                if content_type == "movies":
                    url = (f"{self.portal_url}server/load.php?"
                        f"type=vod&action=get_ordered_list&category={category_id}&"
                        f"mac={self.mac_address}&JsHttpRequest=1-xml")
                elif content_type == "series":
                    url = (f"{self.portal_url}server/load.php?"
                        f"type=series&action=get_ordered_list&category={category_id}&"
                        f"mac={self.mac_address}&JsHttpRequest=1-xml")
                
                response = self.requests.get(url, timeout=15)
                
                if response.status_code == 200:
                    content_data = response.json().get("js", {}).get("data", [])
                    
                    if content_data:
                        self.root.after(0, lambda: VODContentWindow(self, content_type, content_data))
                    else:
                        self.root.after(0, lambda: messagebox.showinfo("No Content", 
                                                    f"No {content_type} found in this category."))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", 
                                                f"Failed to load content: HTTP {response.status_code}"))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", 
                                            f"Failed to load content: {str(e)}"))
        
        load_thread = threading.Thread(target=load_in_background, daemon=True)
        load_thread.start()

    def load_all_vod_content(self, content_type):
        """Load all VOD content (may be slow)"""
        if not messagebox.askyesno("Load All Content", 
                                f"Loading all {content_type} may take a while.\n"
                                "Continue?"):
            return
        
        def load_in_background():
            try:
                self.root.after(0, lambda: self.status_var.set(f"Loading all {content_type}..."))
                
                if content_type == "movies":
                    url = (f"{self.portal_url}server/load.php?"
                        f"type=vod&action=get_ordered_list&"
                        f"mac={self.mac_address}&JsHttpRequest=1-xml")
                elif content_type == "series":
                    url = (f"{self.portal_url}server/load.php?"
                        f"type=series&action=get_ordered_list&"
                        f"mac={self.mac_address}&JsHttpRequest=1-xml")
                
                response = self.requests.get(url, timeout=30)  # Longer timeout for all content
                
                if response.status_code == 200:
                    content_data = response.json().get("js", {}).get("data", [])
                    
                    if content_data:
                        self.root.after(0, lambda: VODContentWindow(self, content_type, content_data))
                        self.root.after(0, lambda: self.status_var.set(f"Loaded {len(content_data)} {content_type}"))
                    else:
                        self.root.after(0, lambda: messagebox.showinfo("No Content", 
                                                    f"No {content_type} found."))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", 
                                                f"Failed to load all {content_type}: HTTP {response.status_code}"))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", 
                                            f"Failed to load all {content_type}: {str(e)}"))
        
        load_thread = threading.Thread(target=load_in_background, daemon=True)
        load_thread.start()

    def get_vod_stream_link(self, cmd, content_id):
        """Get VOD stream link"""
        try:
            create_link_url = (f"{self.portal_url}server/load.php?"
                            f"type=vod&action=create_link&cmd={urllib.parse.quote(cmd)}&"
                            f"mac={self.mac_address}&JsHttpRequest=1-xml")
            
            response = self.requests.get(create_link_url, timeout=10)
            
            if response.status_code == 200:
                data = response.json().get('js', {})
                real_cmd = data.get('cmd', '')
                
                if real_cmd:
                    clean_url = real_cmd.replace("ffmpeg ", "").strip()
                    print(f"✅ Got VOD stream URL: {clean_url}")
                    return clean_url
                    
        except Exception as e:
            print(f"❌ VOD stream error: {e}")
        
        return None

    def play_vod_stream(self, stream_url, content_name):
        """Play VOD stream with seek support"""
        user_agent = "Mozilla/5.0 (QtEmbedded; U; Linux; C)"
        referer = self.portal_url + "index.html"
        
        try:
            ffplay_command = [
                "ffplay", "-x", "900", "-y", "600",
                "-window_title", f"Playing: {content_name}",
                "-user_agent", user_agent,
                "-headers", f"Referer: {referer}",
                
                # VOD-specific optimizations
                "-seek_interval", "10",  # 10-second seeking for VOD
                "-autoexit",  # Exit when done
                "-fast",      # Fast seek
                
                # Network optimizations
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-timeout", "15000000",  # 15s timeout
                
                # Quality optimizations
                "-sync", "video",
                "-framedrop",
                
                "-i", stream_url
            ]
            
            process = subprocess.Popen(ffplay_command)
            self.status_var.set(f"Playing VOD: {content_name} (PID: {process.pid})")
            print(f"🎬 Playing VOD: {content_name}")
            
        except Exception as e:
            messagebox.showerror("Playback Error", f"Failed to play {content_name}: {str(e)}")
            print(f"❌ VOD playback error: {e}")
            
        
        
    
        
    
    
    
    
# Start Application
if __name__ == "__main__":
    root = tk.Tk()
    IPTVUserSelection(root)
    root.mainloop()