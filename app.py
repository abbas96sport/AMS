import os
import logging
from datetime import datetime
from flask import send_from_directory
from core import app, db, login_manager

# Ensure models and routes are registered with the app
import models
import routes
import api_routes

# Register the API blueprint for the Flutter app
app.register_blueprint(api_routes.api)

@login_manager.user_loader
def load_user(user_id):
    return models.User.query.get(int(user_id))

def initialize_app():
    """Ensure database is initialized and migrations are run."""
    with app.app_context():
        try:
            db.create_all()
            run_migrations()
            
            # Create default admin user
            admin_user = models.User.query.filter_by(username='abbas96sport').first()
            if not admin_user:
                admin_user = models.User()
                admin_user.username = 'abbas96sport'
                admin_user.email = 'abbas.h@cope.uobaghdad.edu.iq'
                admin_user.full_name = 'Msc Abbas Hussein Khaleefah'
                admin_user.is_admin = True
                admin_user.set_password('11234511')
                db.session.add(admin_user)
                db.session.commit()
                logging.info("Default admin user created")
        except Exception as e:
            logging.error(f"Initialization failed: {e}")

def run_migrations():
    """Run database migrations to add new columns"""
    from sqlalchemy import text, inspect
    current_year = datetime.now().year
    inspector = inspect(db.engine)
    
    def get_columns(table_name):
        try:
            return [col['name'] for col in inspector.get_columns(table_name)]
        except:
            return []
    
    migrations = []
    # (Migration logic from previous app.py)
    tables = inspector.get_table_names()
    
    if 'user' in tables:
        user_cols = get_columns('user')
        if 'data_year' not in user_cols:
            migrations.append(f"ALTER TABLE user ADD COLUMN data_year INTEGER DEFAULT {current_year} NOT NULL")
    
    if 'student' in tables:
        student_cols = get_columns('student')
        if 'data_year' not in student_cols:
            migrations.append(f"ALTER TABLE student ADD COLUMN data_year INTEGER DEFAULT {current_year} NOT NULL")
            
    if 'subject' in tables:
        subject_cols = get_columns('subject')
        if 'data_year' not in subject_cols:
            migrations.append(f"ALTER TABLE subject ADD COLUMN data_year INTEGER DEFAULT {current_year} NOT NULL")

    if 'curriculum' in tables:
        curriculum_cols = get_columns('curriculum')
        if 'data_year' not in curriculum_cols:
            migrations.append(f"ALTER TABLE curriculum ADD COLUMN data_year INTEGER DEFAULT {current_year} NOT NULL")

    if 'academic_timeline' in tables:
        at_cols = get_columns('academic_timeline')
        if 'grade_scheme_id' not in at_cols:
            migrations.append("ALTER TABLE academic_timeline ADD COLUMN grade_scheme_id INTEGER")

    # Run migrations
    for migration in migrations:
        try:
            db.session.execute(text(migration))
            logging.info(f"Migration executed: {migration[:50]}...")
        except Exception as e:
            logging.warning(f"Migration skipped: {e}")
    if migrations:
        db.session.commit()

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

if __name__ == '__main__':
    initialize_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
