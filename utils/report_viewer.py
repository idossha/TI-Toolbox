#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC Report Viewer
This script provides an easy way to view HTML reports with interactive NIfTI visualization.
It automatically starts a local web server and opens the report in the default browser.
"""

import os
import sys
import time
import threading
import webbrowser
import socketserver
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import argparse
import signal
import socket

class ReportHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Custom HTTP request handler with CORS headers for NIfTI files."""
    
    def end_headers(self):
        """Add CORS headers to allow cross-origin requests."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    
    def do_OPTIONS(self):
        """Handle preflight OPTIONS requests."""
        self.send_response(200)
        self.end_headers()
    
    def guess_type(self, path):
        """Guess the type of a file based on its URL."""
        mimetype, encoding = super().guess_type(path)
        
        # Add specific MIME types for NIfTI files
        if path.lower().endswith(('.nii', '.nii.gz')):
            return 'application/octet-stream'
        elif path.lower().endswith('.gz'):
            return 'application/gzip'
        
        return mimetype, encoding
    
    def log_message(self, format, *args):
        """Override to reduce server log verbosity."""
        if not getattr(self.server, 'quiet', False):
            super().log_message(format, *args)

class ReportViewer:
    """Main report viewer class."""
    
    def __init__(self, port=8000, quiet=False):
        self.port = port
        self.quiet = quiet
        self.server = None
        self.server_thread = None
        
    def find_free_port(self, start_port=8000, max_attempts=10):
        """Find a free port starting from start_port."""
        for i in range(max_attempts):
            port = start_port + i
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('localhost', port))
                    return port
            except OSError:
                continue
        raise RuntimeError(f"Could not find a free port after {max_attempts} attempts")
    
    def start_server(self, directory=None):
        """Start the HTTP server in the specified directory."""
        if directory:
            os.chdir(directory)
        
        # Find a free port
        try:
            self.port = self.find_free_port(self.port)
        except RuntimeError as e:
            print(f"Error: {e}")
            sys.exit(1)
        
        # Set up the server
        handler = ReportHTTPRequestHandler
        self.server = HTTPServer(('localhost', self.port), handler)
        self.server.quiet = self.quiet
        
        # Start server in a separate thread
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        
        if not self.quiet:
            print(f"🌐 Starting local web server...")
            print(f"📍 Server running at: http://localhost:{self.port}")
            print(f"📁 Serving directory: {os.getcwd()}")
        
        return self.port
    
    def stop_server(self):
        """Stop the HTTP server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            if not self.quiet:
                print("🛑 Server stopped")
    
    def open_report(self, report_path, auto_open=True):
        """Open a specific report in the browser."""
        if not os.path.exists(report_path):
            print(f"Error: Report file not found: {report_path}")
            sys.exit(1)
        
        # Get absolute path and convert to relative URL
        abs_report_path = os.path.abspath(report_path)
        current_dir = os.getcwd()
        
        try:
            rel_path = os.path.relpath(abs_report_path, current_dir)
            # Convert backslashes to forward slashes for URLs
            url_path = rel_path.replace('\\', '/')
            full_url = f"http://localhost:{self.port}/{url_path}"
        except ValueError:
            # If we can't get relative path, use absolute path conversion
            url_path = abs_report_path.replace('\\', '/').lstrip('/')
            full_url = f"http://localhost:{self.port}/{url_path}"
        
        if not self.quiet:
            print(f"📊 Report URL: {full_url}")
        
        if auto_open:
            if not self.quiet:
                print(f"🔗 Opening report in browser...")
            
            # Wait a moment for server to be ready
            time.sleep(0.5)
            webbrowser.open(full_url)
        
        return full_url
    
    def run_interactive(self, report_path=None):
        """Run in interactive mode with user commands."""
        print("\n=== TI-CSC Report Viewer ===")
        print("Commands:")
        print("  help, h     - Show this help")
        print("  open <path> - Open a specific report")
        print("  list, ls    - List available reports")
        print("  quit, q     - Quit the viewer")
        print("  url         - Show current server URL")
        print()
        
        if report_path:
            self.open_report(report_path)
        
        try:
            while True:
                try:
                    command = input("report-viewer> ").strip().lower()
                    
                    if command in ['quit', 'q', 'exit']:
                        break
                    elif command in ['help', 'h', '?']:
                        print("Commands: help, open <path>, list, quit, url")
                    elif command in ['list', 'ls']:
                        self.list_reports()
                    elif command == 'url':
                        print(f"Server URL: http://localhost:{self.port}")
                    elif command.startswith('open '):
                        path = command[5:].strip()
                        if path:
                            try:
                                self.open_report(path)
                            except Exception as e:
                                print(f"Error opening report: {e}")
                        else:
                            print("Usage: open <report_path>")
                    elif command == '':
                        continue
                    else:
                        print(f"Unknown command: {command}. Type 'help' for available commands.")
                        
                except KeyboardInterrupt:
                    print("\nUse 'quit' to exit properly.")
                except EOFError:
                    break
                    
        except KeyboardInterrupt:
            pass
        
        print("\n👋 Goodbye!")
    
    def list_reports(self):
        """List available HTML reports in common locations."""
        report_patterns = [
            "**/derivatives/reports/**/*.html",
            "**/*report*.html",
            "**/*Report*.html",
            "**/reports/**/*.html"
        ]
        
        reports = []
        for pattern in report_patterns:
            reports.extend(Path('.').glob(pattern))
        
        # Remove duplicates and sort
        reports = sorted(set(reports))
        
        if reports:
            print(f"\n📊 Found {len(reports)} report(s):")
            for i, report in enumerate(reports, 1):
                rel_path = report.relative_to('.')
                size = report.stat().st_size
                modified = report.stat().st_mtime
                print(f"  {i:2d}. {rel_path} ({size:,} bytes)")
        else:
            print("\n📊 No HTML reports found in current directory")
            print("💡 Tip: Navigate to your project directory first")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print("\n🛑 Stopping server...")
    sys.exit(0)

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="TI-CSC Report Viewer - Local web server for interactive HTML reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Start server and interactive mode
  %(prog)s report.html                        # Open specific report
  %(prog)s -p 8080 report.html               # Use custom port
  %(prog)s -d /path/to/project report.html   # Serve from different directory
  %(prog)s --no-browser report.html          # Start server but don't open browser
  %(prog)s --list                            # List available reports and exit

The server will automatically find a free port if the default is in use.
        """
    )
    
    parser.add_argument('report', nargs='?', help='Path to HTML report file')
    parser.add_argument('-p', '--port', type=int, default=8000, 
                       help='Port for HTTP server (default: 8000)')
    parser.add_argument('-d', '--directory', help='Directory to serve from (default: current)')
    parser.add_argument('--no-browser', action='store_true', 
                       help='Start server but do not open browser')
    parser.add_argument('-q', '--quiet', action='store_true', 
                       help='Suppress server output')
    parser.add_argument('--list', action='store_true', 
                       help='List available reports and exit')
    parser.add_argument('--interactive', action='store_true', 
                       help='Run in interactive mode even with report argument')
    
    args = parser.parse_args()
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize viewer
    viewer = ReportViewer(port=args.port, quiet=args.quiet)
    
    # Handle list mode
    if args.list:
        if args.directory:
            os.chdir(args.directory)
        viewer.list_reports()
        return
    
    try:
        # Start server
        port = viewer.start_server(args.directory)
        
        if args.report:
            # Open specific report
            url = viewer.open_report(args.report, auto_open=not args.no_browser)
            
            if args.interactive:
                # Run interactive mode even with report argument
                viewer.run_interactive()
            else:
                # Just keep server running
                if not args.quiet:
                    print("\n💡 Server is running. Press Ctrl+C to stop.")
                    print(f"🔗 Report URL: {url}")
                
                try:
                    # Keep server running until interrupted
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass
        else:
            # Interactive mode
            viewer.run_interactive()
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        viewer.stop_server()

if __name__ == '__main__':
    main() 