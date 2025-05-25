"""
TI-CSC Shortcuts Manager
Handles desktop shortcut creation across different platforms.
"""

import os
import sys
import platform
import subprocess
import shutil


class ShortcutsManager:
    """Manages desktop shortcut creation for different platforms"""
    
    def __init__(self, logger=None):
        self.logger = logger
        
    def log_message(self, message, level="INFO"):
        """Log a message if logger is available"""
        if self.logger:
            self.logger(message, level)
    
    def create_desktop_shortcut(self):
        """Create a desktop shortcut based on the current platform"""
        try:
            system = platform.system()
            
            if system == "Darwin":  # macOS
                return self._create_macos_desktop_shortcut()
            elif system == "Windows":
                return self._create_windows_desktop_shortcut()
            elif system == "Linux":
                return self._create_linux_desktop_shortcut()
            else:
                self.log_message(f"❌ Desktop shortcuts not supported on {system}", "ERROR")
                return False
                
        except Exception as e:
            self.log_message(f"❌ Error creating desktop shortcut: {str(e)}", "ERROR")
            return False

    def _create_macos_desktop_shortcut(self):
        """Create desktop shortcut on macOS"""
        try:
            # Get the path to the current executable with better detection
            app_path = None
            
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                executable_path = sys.executable
                self.log_message(f"Frozen executable path: {executable_path}", "INFO")
                
                if executable_path.endswith('MacOS/TI-CSC'):
                    # We're inside the .app bundle - go up to get the .app bundle
                    app_path = os.path.dirname(os.path.dirname(os.path.dirname(executable_path)))
                    self.log_message(f"Detected app bundle path: {app_path}", "INFO")
                else:
                    # Fallback - try to find .app bundle
                    current_dir = os.path.dirname(executable_path)
                    while current_dir and current_dir != '/':
                        if current_dir.endswith('.app'):
                            app_path = current_dir
                            break
                        current_dir = os.path.dirname(current_dir)
            
            if not app_path:
                # Running as script or couldn't detect - search for .app bundle
                base_dir = os.path.dirname(os.path.abspath(__file__))
                self.log_message(f"Searching for .app bundle from: {base_dir}", "INFO")
                
                app_name = "TI-CSC.app"
                possible_paths = [
                    os.path.join(base_dir, "dist", app_name),
                    os.path.join(base_dir, app_name),
                    os.path.join(os.path.dirname(base_dir), app_name),
                    os.path.join(os.path.dirname(base_dir), "dist", app_name)
                ]
                
                for path in possible_paths:
                    self.log_message(f"Checking path: {path}", "INFO")
                    if os.path.exists(path) and os.path.isdir(path):
                        app_path = path
                        self.log_message(f"Found app bundle: {path}", "SUCCESS")
                        break
                
                if not app_path:
                    self.log_message("❌ Could not find TI-CSC.app bundle in any expected location", "ERROR")
                    self.log_message(f"Searched in: {possible_paths}", "ERROR")
                    return False

            # Verify the app bundle exists and is a directory
            if not os.path.exists(app_path):
                self.log_message(f"❌ App bundle does not exist: {app_path}", "ERROR")
                return False
                
            if not os.path.isdir(app_path):
                self.log_message(f"❌ App bundle is not a directory: {app_path}", "ERROR")
                return False

            # Get user's Desktop directory
            desktop_path = os.path.expanduser("~/Desktop")
            if not os.path.exists(desktop_path):
                self.log_message("❌ Desktop directory not found", "ERROR")
                return False

            # Extract the app name with extension for the alias
            app_name = os.path.basename(app_path)  # This will be "TI-CSC.app"
            desktop_shortcut_path = os.path.join(desktop_path, app_name)
            
            self.log_message(f"Creating alias from {app_path} to {desktop_shortcut_path}", "INFO")
            
            # Remove existing shortcut if it exists
            if os.path.exists(desktop_shortcut_path):
                try:
                    if os.path.islink(desktop_shortcut_path) or os.path.isfile(desktop_shortcut_path):
                        os.remove(desktop_shortcut_path)
                    elif os.path.isdir(desktop_shortcut_path):
                        shutil.rmtree(desktop_shortcut_path)
                    self.log_message(f"Removed existing shortcut: {desktop_shortcut_path}", "INFO")
                except Exception as e:
                    self.log_message(f"Warning: Could not remove existing shortcut: {e}", "WARNING")
            
            # Create alias using AppleScript - preserve the .app extension
            applescript = f'''
            tell application "Finder"
                set the source_file to POSIX file "{app_path}" as alias
                set the dest_folder to POSIX file "{desktop_path}" as alias
                try
                    make alias file to source_file at dest_folder with properties {{name:"{app_name}"}}
                    return "success"
                on error error_message
                    return "error: " & error_message
                end try
            end tell
            '''
            
            result = subprocess.run(['osascript', '-e', applescript], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                if "success" in result.stdout:
                    self.log_message(f"✅ Created desktop alias: {app_name}", "SUCCESS")
                    return True
                else:
                    self.log_message(f"AppleScript returned: {result.stdout}", "WARNING")
                    self.log_message(f"AppleScript stderr: {result.stderr}", "WARNING")
                    return False
            else:
                self.log_message(f"❌ AppleScript failed with return code {result.returncode}", "ERROR")
                self.log_message(f"AppleScript error: {result.stderr}", "ERROR")
                return False
            
        except Exception as e:
            self.log_message(f"❌ macOS desktop shortcut error: {str(e)}", "ERROR")
            return False

    def _create_windows_desktop_shortcut(self):
        """Create desktop shortcut on Windows"""
        try:
            try:
                import winshell
                from win32com.client import Dispatch
            except ImportError as e:
                self.log_message("⚠️ Windows shortcut creation requires pywin32 and winshell packages", "WARNING")
                self.log_message("  Install with: pip install pywin32 winshell", "INFO")
                return False
            
            # Get the path to the current executable
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "TI-CSC.exe")
                if not os.path.exists(exe_path):
                    self.log_message("❌ Could not find TI-CSC.exe", "ERROR")
                    return False

            desktop = winshell.desktop()
            # Use the proper executable name for the shortcut
            exe_name = os.path.basename(exe_path)  # This will be "TI-CSC.exe"
            shortcut_name = exe_name.replace('.exe', '.lnk')  # This will be "TI-CSC.lnk"
            shortcut_path = os.path.join(desktop, shortcut_name)
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = exe_path
            shortcut.WorkingDirectory = os.path.dirname(exe_path)
            shortcut.Description = "TI-CSC Docker Launcher"
            
            # Try to set icon if available
            icon_path = os.path.join(os.path.dirname(exe_path), "icon.ico")
            if os.path.exists(icon_path):
                shortcut.IconLocation = icon_path
            
            shortcut.save()
            
            self.log_message(f"✅ Created desktop shortcut: {shortcut_name}", "SUCCESS")
            return True
            
        except Exception as e:
            self.log_message(f"❌ Windows desktop shortcut error: {str(e)}", "ERROR")
            return False

    def _create_linux_desktop_shortcut(self):
        """Create desktop shortcut on Linux"""
        try:
            # Get the path to the current executable
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "TI-CSC")
                if not os.path.exists(exe_path):
                    self.log_message("❌ Could not find TI-CSC executable", "ERROR")
                    return False

            desktop_path = os.path.expanduser("~/Desktop")
            if not os.path.exists(desktop_path):
                self.log_message("❌ Desktop directory not found", "ERROR")
                return False

            # Use the proper executable name for the .desktop file
            exe_name = os.path.basename(exe_path)  # This will be "TI-CSC"
            desktop_file_name = f"{exe_name}.desktop"  # This will be "TI-CSC.desktop"
            desktop_file_path = os.path.join(desktop_path, desktop_file_name)
            
            # Try to find icon
            icon_path = os.path.join(os.path.dirname(exe_path), "icon.png")
            if not os.path.exists(icon_path):
                icon_path = "application-x-executable"  # Fallback to system icon
            
            desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=TI-CSC Docker Launcher
Comment=Temporal Interference Computational Stimulation Core
Exec={exe_path}
Icon={icon_path}
Terminal=false
StartupNotify=true
Categories=Science;Education;
"""
            
            with open(desktop_file_path, 'w') as f:
                f.write(desktop_content)
            
            # Make the desktop file executable
            os.chmod(desktop_file_path, 0o755)
            
            self.log_message(f"✅ Created desktop shortcut: {desktop_file_name}", "SUCCESS")
            return True
            
        except Exception as e:
            self.log_message(f"❌ Linux desktop shortcut error: {str(e)}", "ERROR")
            return False 