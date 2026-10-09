"""
Academic Management System - Deployment Exporter
Creates a clean .zip package ready to upload to PythonAnywhere.
"""
import os
import zipfile
import shutil

def export_project(output_zip_name="academic_system_pythonanywhere.zip"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(base_dir, output_zip_name)
    
    # Folders and files to include
    include_files = [
        "app.py",
        "core.py",
        "models.py",
        "routes.py",
        "forms.py",
        "api_routes.py",
        "create_missing_tables.py",
        "wsgi.py",
        "pythonanywhere_wsgi.py",
        "requirements.txt",
        "main.py",
        "PYTHONANYWHERE_DEPLOYMENT_GUIDE.md"
    ]
    
    include_dirs = [
        "templates",
        "static",
        "instance"
    ]
    
    # Exclude unwanted patterns
    exclude_patterns = ["__pycache__", ".pyc", ".DS_Store", "Thumbs.db", ".git"]
    
    print("Packaging project into deployment zip...")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add root files
        for fname in include_files:
            file_path = os.path.join(base_dir, fname)
            if os.path.exists(file_path):
                zipf.write(file_path, arcname=fname)
                print(f" + Added file: {fname}")
        
        # Add folders recursively
        for dir_name in include_dirs:
            dir_path = os.path.join(base_dir, dir_name)
            if os.path.exists(dir_path):
                for root, dirs, files in os.walk(dir_path):
                    # Filter out excluded directories
                    dirs[:] = [d for d in dirs if not any(pat in d for pat in exclude_patterns)]
                    
                    for file in files:
                        if any(pat in file for pat in exclude_patterns):
                            continue
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, base_dir)
                        # Normalize path separators for zip
                        arc_rel_path = rel_path.replace("\\", "/")
                        zipf.write(full_path, arcname=arc_rel_path)
                        
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"\nSUCCESS: Package created: {output_zip_name} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    export_project()
