from flask import Blueprint, request, jsonify
from core import db
from models import User, Student, Curriculum, Grade, Schedule
from datetime import datetime

api = Blueprint('api', __name__, url_prefix='/api')

# ==========================================
# 1. AUTHENTICATION API
# ==========================================
@api.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Please provide username and password'}), 400

    user = User.query.filter_by(username=data['username']).first()
    
    if user and user.check_password(data['password']):
        # Simple token for demonstration (In production use PyJWT)
        token = f"TOKEN_{user.id}_{datetime.now().timestamp()}"
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'email': user.email,
                'is_admin': user.is_admin
            }
        }), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401

# ==========================================
# 2. DASHBOARD API
# ==========================================
@api.route('/dashboard/<int:user_id>', methods=['GET'])
def get_dashboard(user_id):
    # Security: check if user exists
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    students_count = Student.query.count() if user.is_admin else Student.query.filter_by(user_id=user.id).count()
    curriculum_count = Curriculum.query.count() if user.is_admin else Curriculum.query.filter_by(user_id=user.id).count()
    
    return jsonify({
        'total_students': students_count,
        'total_subjects': curriculum_count,
        'recent_activity': 'No recent activity yet',
        'academic_year': user.data_year
    }), 200

# ==========================================
# 3. STUDENTS API
# ==========================================
@api.route('/students/<int:user_id>', methods=['GET'])
def get_students(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    query = Student.query if user.is_admin else Student.query.filter_by(user_id=user.id)
    students = query.all()
    
    result = []
    for s in students:
        result.append({
            'id': s.id,
            'student_id': s.student_id,
            'name': s.name,
            'section': s.section,
            'academic_year': s.academic_year,
            'attendance_percentage': s.get_attendance_percentage(),
            'final_grade': s.get_final_grade()
        })
        
    return jsonify({'students': result}), 200

# ==========================================
# 4. SUBJECTS/CURRICULUM API
# ==========================================
@api.route('/subjects/<int:user_id>', methods=['GET'])
def get_subjects(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    query = Curriculum.query if user.is_admin else Curriculum.query.filter_by(user_id=user.id)
    subjects = query.all()
    
    result = []
    for sub in subjects:
        result.append({
            'id': sub.id,
            'topic': sub.topic,
            'academic_year': sub.academic_year,
            'theory_hours': sub.theory_hours,
            'practical_hours': sub.practical_hours
        })
        
    return jsonify({'subjects': result}), 200
