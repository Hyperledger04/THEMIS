#!/usr/bin/env python3
"""
Course server — serves the course directory over HTTP on localhost.

Usage:
    cd /Users/anshoosareen/Lexagent/course
    python serve.py

Then open:  http://localhost:8765

The server only binds to 127.0.0.1 — it is not accessible from the network.
"""
import http.server
import os
import webbrowser

PORT = 8765
BIND = "127.0.0.1"

# Change into the course directory so relative paths work
os.chdir(os.path.dirname(os.path.abspath(__file__)))


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Suppress the per-request noise; only print errors
        if args and str(args[1]) >= "400":
            super().log_message(fmt, *args)


print(f"Course server → http://{BIND}:{PORT}")
print("Press Ctrl+C to stop.\n")
webbrowser.open(f"http://{BIND}:{PORT}")
http.server.HTTPServer((BIND, PORT), Handler).serve_forever()
