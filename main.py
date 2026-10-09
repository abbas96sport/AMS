from app import app, initialize_app
from waitress import serve

if __name__ == '__main__':
    # Initialize database and migrations
    initialize_app()
    
    print("Starting server with Waitress on http://0.0.0.0:5000")
    serve(app, host='0.0.0.0', port=5000)
