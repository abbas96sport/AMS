# +--------------------------------------------------------------------------------+
# | PythonAnywhere WSGI Configuration file                                          |
# | Academic Management System (AMS)                                              |
# +--------------------------------------------------------------------------------+
#
# INSTRUCTIONS FOR PYTHONANYWHERE:
# 1. Open the "Web" tab in PythonAnywhere dashboard.
# 2. Click on the link next to "WSGI configuration file:" (e.g. /var/www/yourusername_pythonanywhere_com_wsgi.py).
# 3. Replace all the content of that file with the code below.
# 4. Replace 'YOUR_PYTHONANYWHERE_USERNAME' with your actual PythonAnywhere username.
# 5. Save the file and click the green "Reload" button in the Web tab.

import os
import sys

# Change 'YOUR_PYTHONANYWHERE_USERNAME' to your actual PythonAnywhere username
USERNAME = 'YOUR_PYTHONANYWHERE_USERNAME'
PROJECT_DIR = f'/home/{USERNAME}/Academic-System-Clean'

# Add project directory to python path if not present
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Change current working directory to project directory
try:
    os.chdir(PROJECT_DIR)
except Exception:
    pass

# Import the Flask application and initialization function
from app import app as application, initialize_app

# Ensure database tables and migrations are up to date
initialize_app()
