"""
Standard WSGI entry point for WSGI servers (Gunicorn, uWSGI, PythonAnywhere, etc.)
"""
import os
import sys

# Ensure current directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app as application, initialize_app

# Run startup initialization and migrations
initialize_app()

if __name__ == '__main__':
    application.run()
