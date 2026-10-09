from app import app, db
from models import GradeScheme, GradeComponent, GradeSubComponent, GradeEntry

def create_tables():
    with app.app_context():
        print("Creating all tables from models...")
        db.create_all()
        print("Tables created successfully.")

if __name__ == '__main__':
    create_tables()
