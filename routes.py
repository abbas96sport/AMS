import os
import uuid
import logging
import json
from werkzeug.utils import secure_filename
from flask import render_template, redirect, url_for, flash, request, jsonify, Response, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from core import app, db
from models import Student, Attendance, Grade, Curriculum, Schedule, User, UserPermission, AcademicTimeline, SavedTest
from forms import StudentForm, AttendanceForm, GradeForm, CurriculumForm, ScheduleForm, LoginForm, CreateUserForm, EditUserForm
from datetime import date, datetime
from sqlalchemy import func, desc
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, Flowable, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

# Configure upload settings
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'photos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Register Arabic-compatible fonts (done once at module load)
try:
    # Use Windows system fonts for Arabic support
    ARIAL_FONT_PATH = "C:\\Windows\\Fonts\\arial.ttf"
    ARIAL_BOLD_FONT_PATH = "C:\\Windows\\Fonts\\arialbd.ttf"
    
    if os.path.exists(ARIAL_FONT_PATH):
        pdfmetrics.registerFont(TTFont('Arial', ARIAL_FONT_PATH))
        if os.path.exists(ARIAL_BOLD_FONT_PATH):
            pdfmetrics.registerFont(TTFont('Arial-Bold', ARIAL_BOLD_FONT_PATH))
        else:
            # Fallback if bold is not found
            pdfmetrics.registerFont(TTFont('Arial-Bold', ARIAL_FONT_PATH))
            
        ARABIC_FONT_AVAILABLE = True
        ARABIC_FONT_NAME = 'Arial'
        ARABIC_FONT_BOLD_NAME = 'Arial-Bold'
        logging.info("Arabic fonts (Arial) registered successfully for PDF generation")
    else:
        # Fallback to DejaVu if Arial is not found (for other environments)
        DEJAVU_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
        DEJAVU_BOLD_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
        if os.path.exists(DEJAVU_PATH):
            pdfmetrics.registerFont(TTFont('DejaVuSans', DEJAVU_PATH))
            if os.path.exists(DEJAVU_BOLD_PATH):
                pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', DEJAVU_BOLD_PATH))
                ARABIC_FONT_BOLD_NAME = 'DejaVuSans-Bold'
            else:
                pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', DEJAVU_PATH))
                ARABIC_FONT_BOLD_NAME = 'DejaVuSans-Bold'
            
            ARABIC_FONT_AVAILABLE = True
            ARABIC_FONT_NAME = 'DejaVuSans'
        else:
            ARABIC_FONT_AVAILABLE = False
            ARABIC_FONT_NAME = 'Helvetica'
            ARABIC_FONT_BOLD_NAME = 'Helvetica-Bold'
            logging.warning("No Arabic compatible fonts found. PDF reports will use fallback fonts.")
except Exception as e:
    ARABIC_FONT_AVAILABLE = False
    ARABIC_FONT_NAME = 'Helvetica'
    logging.warning(f"Failed to register Arabic fonts: {e}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_photo(photo_file):
    """Save uploaded photo and return filename"""
    if photo_file and allowed_file(photo_file.filename):
        # Generate unique filename
        filename = secure_filename(photo_file.filename)
        name, ext = os.path.splitext(filename)
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        
        # Save file
        photo_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        photo_file.save(photo_path)
        return unique_filename
    return None

def reshape_arabic_text(text):
    """Reshape Arabic text for proper PDF rendering"""
    if not text:
        return ""
    try:
        # Reshape Arabic characters
        reshaped_text = arabic_reshaper.reshape(text)
        # Apply bidirectional algorithm for proper display
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except:
        # If reshaping fails, return original text
        return text

# User-scoped query helpers for data isolation
def student_scope():
    """Return Student query filtered by current user, data_year, and permission restrictions"""
    
    # For users with restricted access, show data from ANY user that matches their restrictions
    # This allows instructors to see students created by admin in their assigned sections
    if current_user.has_restricted_access:
        # Start with all students in the user's assigned data_year
        query = Student.query.filter(
            Student.data_year == current_user.data_year
        )
        
        has_any_restriction = False
        
        # Filter by allowed years (academic years like 1st year, 2nd year, etc.)
        if current_user.allowed_years and current_user.allowed_years.strip():
            try:
                years = [int(y.strip()) for y in current_user.allowed_years.split(',') if y.strip().isdigit()]
                if years:
                    query = query.filter(Student.academic_year.in_(years))
                    has_any_restriction = True
            except ValueError:
                pass
        
        # Filter by allowed sections
        if current_user.allowed_sections and current_user.allowed_sections.strip():
            sections = [s.strip().upper() for s in current_user.allowed_sections.split(',') if s.strip()]
            if sections:
                query = query.filter(Student.section.in_(sections))
                has_any_restriction = True
        
        # If restricted access is enabled but no valid restrictions are set, return empty query
        if not has_any_restriction:
            query = query.filter(Student.id == -1)  # Return no results
        
        return query
    else:
        # For admin users or users without restricted access, show only their own data
        return Student.query.filter(
            Student.user_id == current_user.id,
            Student.data_year == current_user.data_year
        )

def curriculum_scope():
    """Return Curriculum query filtered by current user and data_year"""
    # For users with restricted access, show curriculum from ANY user in their data_year
    if current_user.has_restricted_access:
        return Curriculum.query.filter(
            Curriculum.data_year == current_user.data_year
        )
    else:
        return Curriculum.query.filter(
            Curriculum.user_id == current_user.id,
            Curriculum.data_year == current_user.data_year
        )

def schedule_scope():
    """Return Schedule query filtered by current user and data_year"""
    # For users with restricted access, show schedules from ANY user in their data_year
    if current_user.has_restricted_access:
        query = Schedule.query.filter(
            Schedule.data_year == current_user.data_year
        )
        # Filter by allowed sections if set
        if current_user.allowed_sections and current_user.allowed_sections.strip():
            sections = [s.strip().upper() for s in current_user.allowed_sections.split(',') if s.strip()]
            if sections:
                query = query.filter(Schedule.section.in_(sections))
        # Filter by allowed years if set
        if current_user.allowed_years and current_user.allowed_years.strip():
            try:
                years = [int(y.strip()) for y in current_user.allowed_years.split(',') if y.strip().isdigit()]
                if years:
                    query = query.filter(Schedule.academic_year.in_(years))
            except ValueError:
                pass
        return query
    else:
        return Schedule.query.filter(
            Schedule.user_id == current_user.id,
            Schedule.data_year == current_user.data_year
        )

def get_available_sections(academic_year=None):
    """Get sections available to current user based on their access level and optional academic year filter"""
    sections = db.session.query(Student.section).select_from(Student)
    
    if current_user.has_restricted_access:
        # For restricted users, get sections from their data_year
        sections = sections.filter(Student.data_year == current_user.data_year)
        # If they have allowed sections, filter to only those
        if current_user.allowed_sections and current_user.allowed_sections.strip():
            allowed = [s.strip().upper() for s in current_user.allowed_sections.split(',') if s.strip()]
            if allowed:
                sections = sections.filter(Student.section.in_(allowed))
        # If they have allowed years, filter by those
        if current_user.allowed_years and current_user.allowed_years.strip():
            try:
                allowed_years = [int(y.strip()) for y in current_user.allowed_years.split(',') if y.strip().isdigit()]
                if allowed_years:
                    sections = sections.filter(Student.academic_year.in_(allowed_years))
            except ValueError:
                pass
    else:
        # For non-restricted users, get their own sections
        sections = sections.filter(
            Student.user_id == current_user.id,
            Student.data_year == current_user.data_year
        )
    
    # Filter by academic year if provided
    if academic_year:
        sections = sections.filter(Student.academic_year == academic_year)
    
    result = sections.distinct().order_by(Student.section).all()
    return sorted([s[0] for s in result if s[0]])

def get_available_years():
    """Get academic years available to current user based on their access level"""
    years = db.session.query(Student.academic_year).select_from(Student)
    
    if current_user.has_restricted_access:
        # For restricted users, get years from their data_year
        years = years.filter(Student.data_year == current_user.data_year)
        # If they have allowed years, filter to only those
        if current_user.allowed_years and current_user.allowed_years.strip():
            try:
                allowed = [int(y.strip()) for y in current_user.allowed_years.split(',') if y.strip().isdigit()]
                if allowed:
                    years = years.filter(Student.academic_year.in_(allowed))
            except ValueError:
                pass
    else:
        # For non-restricted users, get their own years
        years = years.filter(
            Student.user_id == current_user.id,
            Student.data_year == current_user.data_year
        )
    
    result = years.distinct().order_by(Student.academic_year).all()
    return sorted([y[0] for y in result if y[0]])

class CircularImage(Flowable):
    """Custom Flowable to display an image in a circular frame"""
    def __init__(self, image_path, size=1*inch):
        Flowable.__init__(self)
        self.image_path = image_path
        self.size = size
        self.width = size
        self.height = size
    
    def draw(self):
        """Draw the image with a circular clipping path"""
        canvas = self.canv
        
        # Save the current state
        canvas.saveState()
        
        # Create a circular clipping path
        center_x = self.size / 2
        center_y = self.size / 2
        radius = self.size / 2
        
        # Create the circle path
        path = canvas.beginPath()
        path.circle(center_x, center_y, radius)
        
        # Clip to the circle
        canvas.clipPath(path, stroke=0, fill=0)
        
        # Draw the image
        canvas.drawImage(self.image_path, 0, 0, 
                        width=self.size, height=self.size,
                        preserveAspectRatio=True, mask='auto')
        
        # Restore the state
        canvas.restoreState()

@app.route('/uploads/photos/<filename>')
def uploaded_photo(filename):
    """Serve uploaded photos"""
    return send_from_directory(UPLOAD_FOLDER, filename)

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            # Check if subscription is valid
            if not user.is_subscription_valid():
                flash('Your subscription has expired. Please contact the administrator to renew your subscription.', 'error')
                return render_template('auth/login.html', form=form)
            
            login_user(user)
            next_page = request.args.get('next')
            
            # Warn if subscription expires soon (within 7 days)
            days_left = user.get_days_until_expiration()
            if days_left is not None and 0 < days_left <= 7:
                flash(f'Warning: Your subscription will expire in {days_left} day(s)', 'warning')
            
            flash(f'Welcome back, {user.full_name or user.username}!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    if request.method == 'POST':
        # Update user profile
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        enrollment_year = request.form.get('enrollment_year', type=int)
        
        if full_name:
            current_user.full_name = full_name
        if email:
            current_user.email = email
        if enrollment_year and 2020 <= enrollment_year <= 2050:
            current_user.enrollment_year = enrollment_year
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('user_profile'))
    
    return render_template('profile.html')

@app.route('/users')
@login_required
def user_list():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    users = User.query.all()
    return render_template('auth/users.html', users=users)

@app.route('/users/create', methods=['GET', 'POST'])
@login_required  
def create_user():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    form = CreateUserForm()
    
    # Get available years and sections from database (filtered by current admin's data_year)
    available_years = sorted(set([s.academic_year for s in Student.query.filter_by(user_id=current_user.id, data_year=current_user.data_year).with_entities(Student.academic_year).distinct().all()]))
    available_sections = sorted(set([s.section for s in Student.query.filter_by(user_id=current_user.id, data_year=current_user.data_year).with_entities(Student.section).distinct().all()]))
    
    # Get academic timelines for data_year selection
    timelines = AcademicTimeline.query.filter_by(is_active=True).order_by(AcademicTimeline.year).all()
    if not timelines:
        current_year = datetime.now().year
        timeline = AcademicTimeline(year=current_year, name=f'Academic Year {current_year}', is_active=True, is_current=True, created_by=current_user.id)
        db.session.add(timeline)
        db.session.commit()
        timelines = [timeline]
    form.data_year.choices = [(t.year, f'{t.year} - {t.name or "Academic Year " + str(t.year)}') for t in timelines]
    
    if form.validate_on_submit():
        # Check if username already exists
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Username already exists!', 'error')
            return render_template('auth/create_user.html', form=form, 
                                 available_years=available_years, 
                                 available_sections=available_sections)
        
        # Check if email already exists
        existing_email = User.query.filter_by(email=form.email.data).first()
        if existing_email:
            flash('Email already exists!', 'error')
            return render_template('auth/create_user.html', form=form,
                                 available_years=available_years,
                                 available_sections=available_sections)
        
        user = User()
        user.username = form.username.data
        user.email = form.email.data
        user.full_name = form.full_name.data
        user.is_admin = form.is_admin.data
        user.data_year = form.data_year.data
        user.set_password(form.password.data)
        
        # Handle subscription expiration
        user.subscription_expires_at = form.subscription_expires_at.data if form.subscription_expires_at.data else None
        
        # Handle access restrictions from checkboxes
        user.has_restricted_access = form.has_restricted_access.data
        
        # Get selected years from checkboxes
        selected_years = request.form.getlist('allowed_years_list')
        user.allowed_years = ','.join(selected_years) if selected_years else None
        
        # Get selected sections from checkboxes
        selected_sections = request.form.getlist('allowed_sections_list')
        user.allowed_sections = ','.join(selected_sections) if selected_sections else None
        
        # Handle photo upload
        if form.photo.data:
            user.photo_filename = save_photo(form.photo.data)
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'User {user.username} created successfully!', 'success')
        return redirect(url_for('user_list'))
    
    return render_template('auth/create_user.html', form=form,
                         available_years=available_years,
                         available_sections=available_sections)

@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    form = EditUserForm(obj=user)
    
    # Get available years and sections from database (filtered by current admin's data_year)
    available_years = sorted(set([s.academic_year for s in Student.query.filter_by(user_id=current_user.id, data_year=current_user.data_year).with_entities(Student.academic_year).distinct().all()]))
    available_sections = sorted(set([s.section for s in Student.query.filter_by(user_id=current_user.id, data_year=current_user.data_year).with_entities(Student.section).distinct().all()]))
    
    # Get academic timelines for data_year selection
    timelines = AcademicTimeline.query.filter_by(is_active=True).order_by(AcademicTimeline.year).all()
    if not timelines:
        current_year = datetime.now().year
        timeline = AcademicTimeline(year=current_year, name=f'Academic Year {current_year}', is_active=True, is_current=True, created_by=current_user.id)
        db.session.add(timeline)
        db.session.commit()
        timelines = [timeline]
    form.data_year.choices = [(t.year, f'{t.year} - {t.name or "Academic Year " + str(t.year)}') for t in timelines]
    
    # Parse user's current allowed values (strip whitespace for proper matching)
    user_allowed_years = [y.strip() for y in user.allowed_years.split(',')] if user.allowed_years else []
    user_allowed_sections = [s.strip() for s in user.allowed_sections.split(',')] if user.allowed_sections else []
    
    if form.validate_on_submit():
        # Check if username is taken by another user
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user and existing_user.id != user_id:
            flash('Username already exists!', 'error')
            return render_template('auth/edit_user.html', form=form, user=user,
                                 available_years=available_years,
                                 available_sections=available_sections,
                                 user_allowed_years=user_allowed_years,
                                 user_allowed_sections=user_allowed_sections)
        
        # Check if email is taken by another user
        existing_email = User.query.filter_by(email=form.email.data).first()
        if existing_email and existing_email.id != user_id:
            flash('Email already exists!', 'error')
            return render_template('auth/edit_user.html', form=form, user=user,
                                 available_years=available_years,
                                 available_sections=available_sections,
                                 user_allowed_years=user_allowed_years,
                                 user_allowed_sections=user_allowed_sections)
        
        user.username = form.username.data
        user.email = form.email.data
        user.full_name = form.full_name.data
        user.data_year = form.data_year.data
        
        # Handle subscription expiration
        user.subscription_expires_at = form.subscription_expires_at.data if form.subscription_expires_at.data else None
        
        # Handle access restrictions from checkboxes
        user.has_restricted_access = form.has_restricted_access.data
        
        # Get selected years from checkboxes
        selected_years = request.form.getlist('allowed_years_list')
        user.allowed_years = ','.join(selected_years) if selected_years else None
        
        # Get selected sections from checkboxes
        selected_sections = request.form.getlist('allowed_sections_list')
        user.allowed_sections = ','.join(selected_sections) if selected_sections else None
        
        # Only update password if provided
        if form.password.data:
            user.set_password(form.password.data)
        
        # Handle photo upload
        if form.photo.data:
            # Delete old photo if exists
            if user.photo_filename:
                old_photo_path = os.path.join(UPLOAD_FOLDER, user.photo_filename)
                if os.path.exists(old_photo_path):
                    os.remove(old_photo_path)
            user.photo_filename = save_photo(form.photo.data)
        
        db.session.commit()
        flash(f'User {user.username} updated successfully!', 'success')
        return redirect(url_for('user_list'))
    
    return render_template('auth/edit_user.html', form=form, user=user,
                         available_years=available_years,
                         available_sections=available_sections,
                         user_allowed_years=user_allowed_years,
                         user_allowed_sections=user_allowed_sections)

@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Prevent deleting yourself
    if user_id == current_user.id:
        flash('You cannot delete your own account!', 'error')
        return redirect(url_for('user_list'))
    
    user = User.query.get_or_404(user_id)
    username = user.username
    
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User {username} has been deleted successfully!', 'success')
    return redirect(url_for('user_list'))

@app.route('/')
@login_required
def index():
    # Dashboard statistics
    total_students = student_scope().count()
    
    # Students by year
    students_by_year = db.session.query(
        Student.academic_year, 
        func.count(Student.id)
    ).filter(Student.user_id == current_user.id).group_by(Student.academic_year).all()
    
    # Recent attendance
    recent_attendance = db.session.query(
        Attendance.date,
        func.count(Attendance.id).label('total_classes'),
        func.sum(func.cast(Attendance.present, db.Integer)).label('present_count')
    ).group_by(Attendance.date).order_by(desc(Attendance.date)).limit(7).all()
    
    # Fetch active grading scheme
    from models import GradeScheme
    active_scheme = GradeScheme.query.filter_by(
        user_id=current_user.id, 
        data_year=current_user.data_year, 
        is_default=True
    ).first()
    
    # Fallback to first available if no default
    if not active_scheme:
        active_scheme = GradeScheme.query.filter_by(
            user_id=current_user.id, 
            data_year=current_user.data_year
        ).first()

    return render_template('index.html', 
                         total_students=total_students,
                         students_by_year=students_by_year,
                         recent_attendance=recent_attendance,
                         active_scheme=active_scheme)

# Student Management Routes
@app.route('/students')
@login_required
def student_list():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    search = request.args.get('search', '')
    
    query = student_scope()
    
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    if search:
        query = query.filter(Student.name.contains(search) | Student.student_id.contains(search))
    
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Get sections available to current user (filtered by selected year)
    sections_with_students = get_available_sections(academic_year=year)
    
    # Get available years for filter
    available_years = get_available_years()
    
    return render_template('students/list.html', 
                         students=students, 
                         year=year, 
                         section=section, 
                         search=search, 
                         sections_with_students=sections_with_students,
                         available_years=available_years)

@app.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    form = StudentForm()
    
    if form.validate_on_submit():
        student = Student()
        student.user_id = current_user.id
        student.data_year = current_user.data_year
        student.name = form.name.data
        student.academic_year = form.academic_year.data
        student.section = form.section.data
        student.email = form.email.data
        student.phone = form.phone.data
        
        # Handle photo upload
        if form.photo.data:
            student.photo_filename = save_photo(form.photo.data)
            
        db.session.add(student)
        db.session.flush()  # Get the student ID
        
        # Create empty grade record
        grade = Grade()
        grade.student_id = student.id
        db.session.add(grade)
        
        db.session.commit()
        flash('Student added successfully!', 'success')
        return redirect(url_for('student_list'))
    
    return render_template('students/add.html', form=form)

@app.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    student = student_scope().filter_by(id=student_id).first_or_404()
    form = StudentForm(obj=student)
    
    if form.validate_on_submit():
        student.name = form.name.data
        student.academic_year = form.academic_year.data
        student.section = form.section.data
        student.email = form.email.data
        student.phone = form.phone.data
        
        # Handle photo upload
        if form.photo.data:
            # Delete old photo if exists
            if student.photo_filename:
                old_photo_path = os.path.join(UPLOAD_FOLDER, student.photo_filename)
                if os.path.exists(old_photo_path):
                    os.remove(old_photo_path)
            student.photo_filename = save_photo(form.photo.data)
        
        db.session.commit()
        flash('Student updated successfully!', 'success')
        return redirect(url_for('student_list'))
    
    return render_template('students/edit.html', form=form, student=student)

@app.route('/students/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    student = student_scope().filter_by(id=student_id).first_or_404()
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted successfully!', 'success')
    return redirect(url_for('student_list'))

@app.route('/students/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_students():
    student_ids = request.form.getlist('student_ids')
    
    if not student_ids:
        flash('No students selected for deletion', 'warning')
        return redirect(url_for('student_list'))
    
    try:
        # Convert to integers
        student_ids = [int(id) for id in student_ids]
        
        # Load and delete individual students to trigger cascades properly
        students = student_scope().filter(Student.id.in_(student_ids)).all()
        deleted_count = len(students)
        
        for student in students:
            db.session.delete(student)
        
        db.session.commit()
        flash(f'Successfully deleted {deleted_count} student(s)!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting students: {str(e)}', 'error')
    
    return redirect(url_for('student_list'))

@app.route('/students/import', methods=['GET', 'POST'])
@login_required
def import_students():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash('Invalid file format. Please upload an Excel file (.xlsx or .xls)', 'error')
            return redirect(request.url)
        
        skip_duplicates = request.form.get('skip_duplicates') == 'on'
        
        try:
            from openpyxl import load_workbook
            wb = load_workbook(file)
            ws = wb.active
            
            imported_count = 0
            skipped_count = 0
            error_count = 0
            errors = []
            imported_students = []
            
            # Skip header row and process data rows
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row or not any(row):
                    continue
                
                try:
                    # Extract data from columns
                    name = row[0] if len(row) > 0 else None
                    email = row[1] if len(row) > 1 else None
                    phone = row[2] if len(row) > 2 else None
                    academic_year = row[3] if len(row) > 3 else None
                    section = row[4] if len(row) > 4 else None
                    
                    # Validate required fields
                    if not name or not email or not academic_year or not section:
                        errors.append(f"Row {row_num}: Missing required fields (Name, Email, Academic Year, or Section)")
                        error_count += 1
                        continue
                    
                    # Validate academic year
                    try:
                        academic_year = int(academic_year)
                        if academic_year not in [1, 2, 3, 4]:
                            raise ValueError()
                    except (ValueError, TypeError):
                        errors.append(f"Row {row_num}: Invalid academic year (must be 1, 2, 3, or 4)")
                        error_count += 1
                        continue
                    
                    # Validate section
                    section = str(section).upper().strip()
                    if len(section) != 1 or not section.isalpha():
                        errors.append(f"Row {row_num}: Invalid section (must be a single letter A-Z)")
                        error_count += 1
                        continue
                    
                    # Check for duplicate email
                    existing = student_scope().filter_by(email=email).first()
                    if existing:
                        if skip_duplicates:
                            skipped_count += 1
                            continue
                        else:
                            errors.append(f"Row {row_num}: Email '{email}' already exists")
                            error_count += 1
                            continue
                    
                    # Generate student ID
                    year = datetime.now().year
                    last_student = student_scope().filter(Student.student_id.like(f'FB-{year}-%')).order_by(desc(Student.student_id)).first()
                    
                    if last_student:
                        last_num = int(last_student.student_id.split('-')[-1])
                        new_num = last_num + 1
                    else:
                        new_num = 1
                    
                    student_id_str = f"FB-{year}-{new_num:04d}"
                    
                    # Create student
                    student = Student(
                        user_id=current_user.id,
                        student_id=student_id_str,
                        name=str(name).strip(),
                        email=str(email).strip(),
                        phone=str(phone).strip() if phone else None,
                        academic_year=academic_year,
                        section=section
                    )
                    
                    db.session.add(student)
                    imported_students.append(student)
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    error_count += 1
                    continue
            
            # Commit all students first to get IDs
            db.session.flush()
            
            db.session.commit()
            
            # Show summary
            if imported_count > 0:
                flash(f'Successfully imported {imported_count} student(s)!', 'success')
            if skipped_count > 0:
                flash(f'Skipped {skipped_count} duplicate student(s)', 'info')
            if error_count > 0:
                flash(f'Failed to import {error_count} student(s). See details below.', 'warning')
                for error in errors[:10]:  # Show first 10 errors
                    flash(error, 'error')
                if len(errors) > 10:
                    flash(f'... and {len(errors) - 10} more errors', 'error')
            
            return redirect(url_for('student_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing file: {str(e)}', 'error')
            return redirect(request.url)
    
    return render_template('students/import.html')

@app.route('/students/import/template')
@login_required
def download_import_template():
    # Create a sample Excel template
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    
    # Add headers
    headers = ['Name', 'Email', 'Phone', 'Academic Year', 'Section']
    ws.append(headers)
    
    # Add sample data row
    sample_data = ['Ahmed Hassan', 'ahmed.hassan@example.com', '07701234567', 1, 'A']
    ws.append(sample_data)
    
    # Style headers
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="4CAF50", end_color="4CAF50", fill_type="solid")
    
    # Save to BytesIO
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment;filename=student_import_template.xlsx'}
    )

# Attendance Routes
@app.route('/attendance')
@login_required
def attendance_list():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    selected_date = request.args.get('date')
    search = request.args.get('search', '')
    
    if selected_date:
        try:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = date.today()
    else:
        selected_date = date.today()
    
    # Get all sections available to current user (filtered by selected year)
    sections = get_available_sections(academic_year=year)
    
    query = student_scope()
    
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    if search:
        query = query.filter(Student.name.contains(search) | Student.student_id.contains(search))
    
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Get existing attendance for the selected date
    attendance_records = {}
    for student in students:
        att_query = Attendance.query.filter_by(student_id=student.id, date=selected_date)
        att_query = att_query.filter_by(subject_id=None)
        attendance = att_query.first()
        attendance_records[student.id] = attendance
    
    return render_template('attendance/mark.html', 
                         students=students, 
                         selected_date=selected_date,
                         attendance_records=attendance_records,
                         year=year, 
                         section=section,
                         search=search,
                         sections=sections)

@app.route('/attendance/mark', methods=['POST'])
@login_required
def mark_attendance():
    selected_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    notes = request.form.get('notes', '')
    
    # Get all students for the selected criteria
    year = request.form.get('year', type=int)
    section = request.form.get('section')
    search = request.form.get('search', '')
    
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    if search:
        query = query.filter(Student.name.contains(search) | Student.student_id.contains(search))
    
    students = query.all()
    
    for student in students:
        present = f'student_{student.id}' in request.form
        
        # Check if attendance record exists for this date
        att_query = Attendance.query.filter_by(student_id=student.id, date=selected_date, subject_id=None)
        attendance = att_query.first()
        
        if attendance:
            attendance.present = present
            attendance.notes = notes
        else:
            attendance = Attendance()
            attendance.student_id = student.id
            attendance.date = selected_date
            attendance.subject_id = None
            attendance.present = present
            attendance.notes = notes
            db.session.add(attendance)
    
    db.session.commit()
    flash('Attendance marked successfully!', 'success')
    return redirect(url_for('attendance_list', year=year, section=section, search=search, date=selected_date.strftime('%Y-%m-%d')))

@app.route('/attendance/history')
@login_required
def attendance_history():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Get sections available to current user (filtered by selected year)
    sections = get_available_sections(academic_year=year)
    available_years = get_available_years()
    
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Get attendance statistics for each student
    student_stats = []
    for student in students:
        att_query = Attendance.query.filter_by(student_id=student.id)
        total_classes = att_query.count()
        
        present_query = Attendance.query.filter_by(student_id=student.id, present=True)
        present_classes = present_query.count()
        
        attendance_percentage = (present_classes / total_classes * 100) if total_classes > 0 else 0
        
        student_stats.append({
            'student': student,
            'total_classes': total_classes,
            'present_classes': present_classes,
            'absent_classes': total_classes - present_classes,
            'percentage': attendance_percentage
        })
    
    return render_template('attendance/history.html', 
                         student_stats=student_stats,
                         year=year, 
                         section=section,
                         sections=sections,
                         available_years=available_years)

@app.route('/attendance/history/pdf')
@login_required
def export_attendance_history_pdf():
    """Export attendance history statistics to PDF"""
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Get students based on filters
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Get attendance statistics for each student
    student_stats = []
    for student in students:
        att_query = Attendance.query.filter_by(student_id=student.id)
        total_classes = att_query.count()
        present_classes = att_query.filter_by(present=True).count()
        attendance_percentage = (present_classes / total_classes * 100) if total_classes > 0 else 0
        
        student_stats.append({
            'student': student,
            'total_classes': total_classes,
            'present_classes': present_classes,
            'absent_classes': total_classes - present_classes,
            'percentage': attendance_percentage
        })
    
    # Create PDF with UTF-8 encoding support
    buffer = io.BytesIO()
    
    # Use Arabic-compatible fonts if available
    # Use registered Arabic font or fallback
    if ARABIC_FONT_AVAILABLE:
        default_font = ARABIC_FONT_NAME
        default_font_bold = f"{ARABIC_FONT_NAME}-Bold" if ARABIC_FONT_NAME == 'Arial' else f"{ARABIC_FONT_NAME}-Bold"
    else:
        default_font = 'Helvetica'
        default_font_bold = 'Helvetica-Bold'
    
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Get styles with UTF-8 support
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=20,
        alignment=1,  # Center alignment
        textColor=colors.darkgreen,
        fontName=default_font_bold
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=10,
        textColor=colors.darkgreen,
        fontName=default_font_bold
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=9,
        fontName=default_font
    )
    
    # Build content
    story = []
    
    # Title
    title = "Attendance History Statistics Report"
    story.append(Paragraph(title, title_style))
    
    # Add user profile picture if available
    photo_added = False
    if current_user.photo_filename:
        try:
            photo_path = os.path.join(UPLOAD_FOLDER, current_user.photo_filename)
            if os.path.exists(photo_path):
                user_photo = CircularImage(photo_path, size=0.8*inch)
                user_info_data = [[
                    user_photo,
                    Paragraph(f"<b>Prepared by:</b> {current_user.full_name or current_user.username}", normal_style)
                ]]
                user_info_table = Table(user_info_data, colWidths=[1*inch, 6*inch])
                user_info_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                    ('ALIGN', (1, 0), (1, 0), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(user_info_table)
                story.append(Spacer(1, 10))
                photo_added = True
        except Exception as e:
            import logging
            logging.warning(f"Failed to load user photo: {e}")
    
    if not photo_added:
        story.append(Paragraph(f"<b>Prepared by:</b> {current_user.full_name or current_user.username}", normal_style))
        story.append(Spacer(1, 10))
    
    # Report details
    report_details = [
        ['University:', 'University of Baghdad'],
        ['College:', 'Physical Education and Sports Sciences'],

        ['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    ]
    
    if year:
        report_details.append(['Academic Year:', f"{year} Year"])
    if section:
        report_details.append(['Section:', section])
    
    details_table = Table(report_details, colWidths=[2*inch, 5*inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), default_font_bold),
        ('FONTNAME', (1, 0), (1, -1), default_font),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 20))
    
    # Summary Statistics
    if student_stats:
        good_attendance = len([s for s in student_stats if s['percentage'] >= 80])
        fair_attendance = len([s for s in student_stats if 60 <= s['percentage'] < 80])
        poor_attendance = len([s for s in student_stats if s['percentage'] < 60])
        avg_attendance = sum(s['percentage'] for s in student_stats) / len(student_stats)
        
        story.append(Paragraph("Summary Statistics", heading_style))
        summary_data = [
            ['Total Students', 'Good Attendance (≥80%)', 'Fair Attendance (60-79%)', 'Poor Attendance (<60%)', 'Average Attendance'],
            [
                str(len(student_stats)),
                str(good_attendance),
                str(fair_attendance),
                str(poor_attendance),
                f"{avg_attendance:.1f}%"
            ]
        ]
        # Landscape A4: 10.69" available width - Total: 9.3 inches
        summary_table = Table(summary_data, colWidths=[1.5*inch, 2.0*inch, 2.0*inch, 2.0*inch, 1.8*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), default_font_bold),
            ('FONTNAME', (0, 1), (-1, -1), default_font),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 20))
    
    # Student Statistics Table - Start on new page
    if student_stats:
        story.append(PageBreak())
        
        # Table headers - will repeat on each page
        table_data = [[
            'Student ID',
            'Name',
            'Year',
            'Section',
            'Total Classes',
            'Present',
            'Absent',
            'Percentage',
            'Attendance Grade',
            'Status'
        ]]
        
        # Add student data
        for stat in student_stats:
            student = stat['student']
            percentage = stat['percentage']
            
            # Reshape Arabic text for proper display
            student_name = reshape_arabic_text(student.name) if student.name else ""
            
            # Determine status
            if percentage >= 90:
                status = 'Excellent'
            elif percentage >= 80:
                status = 'Good'
            elif percentage >= 70:
                status = 'Fair'
            elif percentage >= 60:
                status = 'Poor'
            else:
                status = 'Critical'
            
            table_data.append([
                student.student_id,
                student_name,
                str(student.academic_year),
                student.section,
                str(stat['total_classes']),
                str(stat['present_classes']),
                str(stat['absent_classes']),
                f"{percentage:.1f}%",
                f"{student.calculate_attendance_marks()}/5",
                status
            ])
        
        # Create table with adjusted column widths to prevent overlapping
        # Landscape A4: 11.69" wide - 1" margins = 10.69" available
        # Total width: 9.3 inches (matching Summary Statistics table exactly)
        col_widths = [0.9*inch, 2.4*inch, 0.45*inch, 0.6*inch, 0.9*inch, 0.6*inch, 0.6*inch, 0.8*inch, 1.35*inch, 0.7*inch]
        stats_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), default_font_bold),
            ('FONTNAME', (0, 1), (-1, -1), default_font),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.beige, colors.white]),
        ]))
        story.append(stats_table)
    else:
        story.append(Paragraph("No attendance records found for the selected filters.", normal_style))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    # Generate filename
    filename = f"attendance_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filters = []
    if year:
        filters.append(f"year{year}")
    if section:
        filters.append(f"section{section}")
    if filters:
        filename = f"attendance_history_{'_'.join(filters)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/attendance/export')
@login_required
def export_attendance():
    """Export attendance data to Excel"""
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Build query
    query = db.session.query(Student, Attendance).join(Attendance).filter(Student.user_id == current_user.id)
    
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Attendance.date >= start_date)
        except ValueError:
            pass
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Attendance.date <= end_date)
        except ValueError:
            pass
    
    results = query.order_by(Student.academic_year, Student.section, Student.name, Attendance.date).all()
    
    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance Report"
    
    # Add report header
    ws.merge_cells('A1:J1')
    title_cell = ws.cell(row=1, column=1, value="Attendance Report")
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A2:J2')
    date_cell = ws.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    date_cell.alignment = Alignment(horizontal='center')
    
    # Headers
    headers = [
        'Student ID', 'Student Name', 'Academic Year', 'Section',
        'Date', 'Present', 'Notes', 'Email', 'Phone'
    ]
    
    # Style headers
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2E7D32', end_color='2E7D32', fill_type='solid')
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
    
    # Add data
    for row, (student, attendance) in enumerate(results, 5):
        ws.cell(row=row, column=1, value=student.student_id)
        ws.cell(row=row, column=2, value=student.name)
        ws.cell(row=row, column=3, value=f"{student.academic_year}{get_ordinal_suffix(student.academic_year)} Year")
        ws.cell(row=row, column=4, value=f"Section {student.section}")
        ws.cell(row=row, column=5, value=attendance.date.strftime('%Y-%m-%d'))
        ws.cell(row=row, column=6, value='Present' if attendance.present else 'Absent')
        ws.cell(row=row, column=7, value=attendance.notes or '')
        ws.cell(row=row, column=8, value=student.email or '')
        ws.cell(row=row, column=9, value=student.phone or '')
    
    # Auto-adjust column widths
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=4, column=col).column_letter].width = 15
    
    # Create Excel file in memory
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    # Generate filename
    filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filters = []
    if year:
        filters.append(f"year{year}")
    if section:
        filters.append(f"section{section}")
    if filters:
        filename = f"attendance_report_{'_'.join(filters)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/attendance/export-summary')
@login_required
def export_attendance_summary():
    """Export attendance summary statistics to Excel"""
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Build query for students
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Get attendance statistics for each student
    student_stats = []
    for student in students:
        att_query = Attendance.query.filter_by(student_id=student.id)
        total_classes = att_query.count()
        present_query = Attendance.query.filter_by(student_id=student.id, present=True)
        present_classes = present_query.count()
        attendance_percentage = (present_classes / total_classes * 100) if total_classes > 0 else 0
        attendance_marks = student.calculate_attendance_marks()
        
        student_stats.append({
            'student': student,
            'total_classes': total_classes,
            'present_classes': present_classes,
            'absent_classes': total_classes - present_classes,
            'percentage': attendance_percentage,
            'attendance_marks': attendance_marks
        })
    
    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance Summary"
    
    # Add report header
    ws.merge_cells('A1:L1')
    title_cell = ws.cell(row=1, column=1, value="Attendance Summary Report")
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A2:L2')
    date_cell = ws.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    date_cell.alignment = Alignment(horizontal='center')
    
    # Headers
    headers = [
        'Student ID', 'Student Name', 'Academic Year', 'Section',
        'Total Classes', 'Present', 'Absent', 'Attendance %', 
        'Attendance Marks', 'Status', 'Email', 'Phone'
    ]
    
    # Style headers
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2E7D32', end_color='2E7D32', fill_type='solid')
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
    
    # Add data
    for row, stat in enumerate(student_stats, 5):
        student = stat['student']
        ws.cell(row=row, column=1, value=student.student_id)
        ws.cell(row=row, column=2, value=student.name)
        ws.cell(row=row, column=3, value=f"{student.academic_year}{get_ordinal_suffix(student.academic_year)} Year")
        ws.cell(row=row, column=4, value=f"Section {student.section}")
        ws.cell(row=row, column=5, value=stat['total_classes'])
        ws.cell(row=row, column=6, value=stat['present_classes'])
        ws.cell(row=row, column=7, value=stat['absent_classes'])
        ws.cell(row=row, column=8, value=f"{stat['percentage']:.1f}%")
        ws.cell(row=row, column=9, value=stat['attendance_marks'])
        
        # Status based on percentage
        if stat['percentage'] >= 80:
            status = "Excellent"
        elif stat['percentage'] >= 60:
            status = "Good"
        elif stat['percentage'] >= 50:
            status = "Warning"
        else:
            status = "At Risk"
        ws.cell(row=row, column=10, value=status)
        
        ws.cell(row=row, column=11, value=student.email or '')
        ws.cell(row=row, column=12, value=student.phone or '')
    
    # Auto-adjust column widths
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=4, column=col).column_letter].width = 15
    
    # Create Excel file in memory
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    # Generate filename
    filters = []
    if year:
        filters.append(f"year{year}")
    if section:
        filters.append(f"section{section}")
    filter_text = '_'.join(filters) if filters else ""
    filename = f"attendance_summary{'_' + filter_text if filter_text else ''}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

def get_ordinal_suffix(num):
    """Get ordinal suffix for numbers (1st, 2nd, 3rd, 4th)"""
    if 10 <= num % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(num % 10, 'th')
    return suffix

# Grade Management Routes
@app.route('/grades')
@login_required
def grade_list():
    # Find active default scheme for this year
    default_scheme = GradeScheme.query.filter_by(
        user_id=current_user.id, 
        data_year=current_user.data_year, 
        is_default=True
    ).first()
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    search = request.args.get('search', '').strip()
    
    # Get sections available to current user (filtered by selected year)
    sections = get_available_sections(academic_year=year)
    available_years = get_available_years()
    
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    
    # Add search functionality
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Student.name.ilike(search_term),
                Student.student_id.ilike(search_term)
            )
        )
    
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Get available grade schemes for management
    schemes = GradeScheme.query.filter_by(user_id=current_user.id, data_year=current_user.data_year).all()
    
    # If using dynamic scheme, prepare student grades as a dict for easier lookup
    dynamic_grades = {}
    if default_scheme:
        for student in students:
            for comp in default_scheme.components:
                for sub in comp.sub_components:
                    entry = GradeEntry.query.filter_by(student_id=student.id, sub_component_id=sub.id).first()
                    if entry:
                        dynamic_grades[f"{student.id}_{sub.id}"] = entry.value
    
    return render_template('grades/view.html', students=students, year=year, section=section, 
                          sections=sections, available_years=available_years, search=search,
                          schemes=schemes, default_scheme=default_scheme, dynamic_grades=dynamic_grades)

@app.route('/grades/pdf')
@login_required
def export_grades_pdf():
    """Export grades report to PDF"""
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Get students based on filters
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Create PDF with UTF-8 encoding support
    buffer = io.BytesIO()
    
    # Use Arabic-compatible fonts if available
    if ARABIC_FONT_AVAILABLE:
        default_font = ARABIC_FONT_NAME
        default_font_bold = ARABIC_FONT_BOLD_NAME
    else:
        default_font = 'Helvetica'
        default_font_bold = 'Helvetica-Bold'
    
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Get styles with UTF-8 support
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=20,
        alignment=1,
        textColor=colors.darkgreen,
        fontName=default_font_bold
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=10,
        textColor=colors.darkgreen,
        fontName=default_font_bold
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=9,
        fontName=default_font
    )
    
    # Build content
    story = []
    
    # Title
    title = "Student Grades Report"
    story.append(Paragraph(title, title_style))
    
    # Add user profile picture if available
    photo_added = False
    if current_user.photo_filename:
        try:
            photo_path = os.path.join(UPLOAD_FOLDER, current_user.photo_filename)
            if os.path.exists(photo_path):
                user_photo = CircularImage(photo_path, size=0.8*inch)
                user_info_data = [[
                    user_photo,
                    Paragraph(f"<b>Prepared by:</b> {current_user.full_name or current_user.username}", normal_style)
                ]]
                user_info_table = Table(user_info_data, colWidths=[1*inch, 6*inch])
                user_info_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                    ('ALIGN', (1, 0), (1, 0), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(user_info_table)
                story.append(Spacer(1, 10))
                photo_added = True
        except Exception as e:
            import logging
            logging.warning(f"Failed to load user photo: {e}")
    
    if not photo_added:
        story.append(Paragraph(f"<b>Prepared by:</b> {current_user.full_name or current_user.username}", normal_style))
        story.append(Spacer(1, 10))
    
    # Report details
    report_details = [
        ['University:', 'University of Baghdad'],
        ['College:', 'Physical Education and Sports Sciences'],

        ['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    ]
    
    if year:
        report_details.append(['Academic Year:', f"{year} Year"])
    if section:
        report_details.append(['Section:', section])
    
    details_table = Table(report_details, colWidths=[2*inch, 5*inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), default_font_bold),
        ('FONTNAME', (1, 0), (1, -1), default_font),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 20))
    
    # Summary Statistics
    if students:
        students_with_grades = [s for s in students if s.grades]
        total_grades = [s.grades[0].get_total_grade() for s in students_with_grades if s.grades]
        passed = len([g for g in total_grades if g >= 50])
        failed = len([g for g in total_grades if g < 50])
        avg_grade = sum(total_grades) / len(total_grades) if total_grades else 0
        
        story.append(Paragraph("Summary Statistics", heading_style))
        summary_data = [
            ['Total Students', 'Students with Grades', 'Passed', 'Failed', 'Average Grade'],
            [
                str(len(students)),
                str(len(students_with_grades)),
                str(passed),
                str(failed),
                f"{avg_grade:.1f}/100"
            ]
        ]
        summary_table = Table(summary_data, colWidths=[1.8*inch, 2.0*inch, 1.8*inch, 1.8*inch, 1.9*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), default_font_bold),
            ('FONTNAME', (0, 1), (-1, -1), default_font),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 20))
    
    # Student Grades Table
    if students:
        story.append(PageBreak())
        
        # Check for dynamic scheme
        default_scheme = GradeScheme.query.filter_by(
            user_id=current_user.id, 
            data_year=current_user.data_year, 
            is_default=True
        ).first()
        
        if default_scheme:
            # --- DYNAMIC PDF LOGIC ---
            sub_components = []
            for comp in default_scheme.components:
                for sub in comp.sub_components:
                    sub_components.append(sub)
            
            # Title and header
            title = reshape_arabic_text(f"Grades Report - {default_scheme.name}")
            story.append(Paragraph(title, title_style))
            
            # Flat header with component names as prefixes
            table_headers = [
                reshape_arabic_text('ID'),
                reshape_arabic_text('Name'),
                reshape_arabic_text('Year'),
                reshape_arabic_text('Sec')
            ]
            for sub in sub_components:
                # Add Semester prefix and max marks for PDF clarity
                comp_prefix = "S1" if "1" in sub.component.name else ("S2" if "2" in sub.component.name else sub.component.name[:2])
                short_name = f"{comp_prefix}\n{sub.name}\n({int(sub.max_marks)})"
                table_headers.append(reshape_arabic_text(short_name))
            
            table_headers.extend([reshape_arabic_text('Total'), reshape_arabic_text('Status')])
            table_data = [table_headers]
            
            # Fetch entries
            from models import GradeEntry
            for student in students:
                student_name = reshape_arabic_text(student.name) if student.name else ""
                row = [
                    student.student_id,
                    student_name,
                    str(student.academic_year),
                    student.section
                ]
                total_sum = 0
                for sub in sub_components:
                    entry = GradeEntry.query.filter_by(student_id=student.id, sub_component_id=sub.id).first()
                    val = entry.value if entry else 0
                    row.append(str(val))
                    total_sum += val
                
                row.append(f"{total_sum:.1f}")
                row.append('PASS' if total_sum >= (default_scheme.total_marks * 0.5) else 'FAIL')
                table_data.append(row)
            
            # Adjust column widths (10.69 inches available)
            fixed_cols_width = 3.69 * inch
            remaining_width = 7.0 * inch
            dynamic_col_width = remaining_width / (len(sub_components) + 2)
            col_widths = [0.8*inch, 2.0*inch, 0.4*inch, 0.49*inch] + [dynamic_col_width] * (len(sub_components) + 2)
            
            grades_table = Table(table_data, colWidths=col_widths, repeatRows=1)
            grades_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), default_font_bold),
                ('FONTNAME', (0, 1), (-1, -1), default_font),
                ('FONTSIZE', (0, 0), (-1, -1), 7 if len(sub_components) > 8 else 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(grades_table)
            
        else:
            # --- LEGACY PDF LOGIC ---
            title = "Grades Report (Legacy)"
            story.append(Paragraph(title, title_style))
            
            table_data = [[
                'ID', 'Name', 'Year', 'Sec',
                'S1', 'Mid', 'S2', 'Final', 'Total', 'Res'
            ]]
            
            for student in students:
                grade = student.grades[0] if student.grades else None
                student_name = reshape_arabic_text(student.name) if student.name else ""
                
                if grade:
                    s1_total = grade.get_semester1_total()
                    s2_total = grade.get_semester2_total()
                    final_total = grade.get_final_total()
                    total_grade = grade.get_total_grade()
                    result = 'P' if total_grade >= 50 else 'F'
                else:
                    s1_total = s2_total = final_total = total_grade = 0
                    result = '-'
                
                table_data.append([
                    student.student_id, student_name, str(student.academic_year), student.section,
                    str(s1_total), str(grade.midyear_exam if grade else 0),
                    str(s2_total), str(final_total), str(total_grade), result
                ])
            
            col_widths = [0.8*inch, 2.5*inch, 0.5*inch, 0.6*inch, 0.9*inch, 0.9*inch, 0.9*inch, 1.0*inch, 1.0*inch, 0.6*inch]
            grades_table = Table(table_data, colWidths=col_widths, repeatRows=1)
            grades_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), default_font_bold),
                ('FONTNAME', (0, 1), (-1, -1), default_font),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(grades_table)
    else:
        story.append(Paragraph("No students found with the selected filters.", normal_style))
    
    # Build PDF
    doc.build(story)
    
    # Return PDF
    buffer.seek(0)
    filename = f"grades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filters = []
    if year:
        filters.append(f"year{year}")
    if section:
        filters.append(f"section{section}")
    if filters:
        filename = f"grades_{'_'.join(filters)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/grades/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_grades(student_id):
    student = student_scope().filter_by(id=student_id).first_or_404()
    
    # Check if a dynamic scheme is default
    default_scheme = GradeScheme.query.filter_by(
        user_id=current_user.id, 
        data_year=current_user.data_year, 
        is_default=True
    ).first()
    
    if default_scheme:
        return redirect(url_for('edit_student_grades_dynamic', student_id=student.id, scheme_id=default_scheme.id))

    grade = Grade.query.filter_by(student_id=student_id).first()
    
    # Get return filters to preserve state
    return_year = request.args.get('return_year', type=int)
    return_section = request.args.get('return_section')
    return_search = request.args.get('return_search')
    
    if not grade:
        grade = Grade()
        grade.student_id = student_id
        db.session.add(grade)
        db.session.commit()
    
    form = GradeForm(obj=grade)
    
    if form.validate_on_submit():
        grade.semester1_theory = form.semester1_theory.data
        grade.semester1_practical = form.semester1_practical.data
        grade.midyear_exam = form.midyear_exam.data
        grade.semester2_theory = form.semester2_theory.data
        grade.semester2_practical = form.semester2_practical.data
        grade.final_theory = form.final_theory.data
        grade.final_practical = form.final_practical.data
        
        db.session.commit()
        flash('Grades updated successfully!', 'success')
        
        # Build return URL with preserved filters
        return_params = {}
        if return_year:
            return_params['year'] = return_year
        if return_section:
            return_params['section'] = return_section
        if return_search:
            return_params['search'] = return_search
        return redirect(url_for('grade_list', **return_params))
    
    return render_template('grades/enter.html', form=form, student=student, grade=grade,
                          return_year=return_year, return_section=return_section, return_search=return_search)

@app.route('/grades/finalize/<int:semester>')
@login_required
def finalize_grades(semester):
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    
    students = query.all()
    finalized_count = 0
    
    for student in students:
        grade = Grade.query.filter_by(student_id=student.id).first()
        if not grade:
            grade = Grade()
            grade.student_id = student.id
            db.session.add(grade)
        
        attendance_marks = student.calculate_attendance_marks()
        
        if semester == 1 and not grade.semester1_finalized:
            grade.semester1_attendance = attendance_marks
            grade.semester1_finalized = True
            finalized_count += 1
        elif semester == 2 and not grade.semester2_finalized:
            grade.semester2_attendance = attendance_marks
            grade.semester2_finalized = True
            finalized_count += 1
    
    db.session.commit()
    flash(f'Attendance marks finalized for {finalized_count} students in semester {semester}!', 'success')
    return redirect(url_for('finalize_grades_page'))

@app.route('/grades/finalize')
@login_required
def finalize_grades_page():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Get sections available to current user (filtered by selected year)
    sections = get_available_sections(academic_year=year)
    available_years = get_available_years()
    
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Pre-calculate attendance data to avoid N+1 queries
    student_data = []
    for student in students:
        attendance_percentage = student.get_attendance_percentage()
        attendance_marks = student.calculate_attendance_marks()
        grade = student.grades[0] if student.grades else None
        
        student_data.append({
            'student': student,
            'attendance_percentage': attendance_percentage,
            'attendance_marks': attendance_marks,
            'grade': grade
        })
    
    return render_template('grades/finalize.html', student_data=student_data, year=year, section=section, sections=sections)

# Curriculum Management Routes
@app.route('/curriculum')
@login_required
def curriculum_list():
    year = request.args.get('year', type=int)
    semester = request.args.get('semester', type=int)
    
    query = curriculum_scope()
    if year:
        query = query.filter(Curriculum.academic_year == year)
    if semester:
        query = query.filter(Curriculum.semester == semester)
    
    curriculum_items = query.order_by(Curriculum.academic_year, Curriculum.semester, Curriculum.week_number).all()
    
    form = CurriculumForm()
    return render_template('curriculum/manage.html', curriculum_items=curriculum_items, year=year, semester=semester, form=form)

@app.route('/curriculum/add', methods=['GET', 'POST'])
@login_required
def add_curriculum():
    form = CurriculumForm()
    
    if form.validate_on_submit():
        curriculum = Curriculum()
        curriculum.user_id = current_user.id
        curriculum.data_year = current_user.data_year
        curriculum.academic_year = form.academic_year.data
        curriculum.topic = form.topic.data
        curriculum.description = form.description.data
        curriculum.week_number = form.week_number.data
        curriculum.semester = form.semester.data
        curriculum.theory_hours = form.theory_hours.data
        curriculum.practical_hours = form.practical_hours.data
        curriculum.objectives = form.objectives.data
        db.session.add(curriculum)
        db.session.commit()
        flash('Curriculum item added successfully!', 'success')
        return redirect(url_for('curriculum_list'))
    
    return render_template('curriculum/manage.html', form=form, curriculum_items=[])

@app.route('/curriculum/<int:curriculum_id>/delete', methods=['POST'])
@login_required
def delete_curriculum(curriculum_id):
    curriculum = curriculum_scope().filter_by(id=curriculum_id).first_or_404()
    db.session.delete(curriculum)
    db.session.commit()
    flash('Curriculum item deleted successfully!', 'success')
    return redirect(url_for('curriculum_list'))

# Reports and Analytics Routes
@app.route('/reports')
@login_required
def reports():
    from models import GradeScheme, GradeEntry
    # Overall statistics
    total_students = student_scope().count()
    
    # Get active grading scheme
    default_scheme = GradeScheme.query.filter_by(
        user_id=current_user.id, 
        data_year=current_user.data_year, 
        is_default=True
    ).first()
    
    # Pass/Fail statistics (Dynamic)
    if default_scheme:
        # Calculate pass/fail based on dynamic scheme total
        pass_mark = default_scheme.total_marks * 0.5
        all_students = student_scope().all()
        passed_students = 0
        for student in all_students:
            total = db.session.query(func.sum(GradeEntry.value)).filter(GradeEntry.student_id == student.id).scalar() or 0
            if total >= pass_mark:
                passed_students += 1
        failed_students = len(all_students) - passed_students
        
        # Component Analysis (Dynamic)
        component_stats = []
        for comp in default_scheme.components:
            # We'll calculate the avg across all sub-components for this top-level component
            sub_ids = [s.id for s in comp.sub_components]
            if sub_ids:
                avg_val = db.session.query(func.avg(GradeEntry.value)).filter(GradeEntry.sub_component_id.in_(sub_ids)).scalar() or 0
                max_val = sum(s.max_marks for s in comp.sub_components)
                perf_percent = (avg_val / max_val * 100) if max_val > 0 else 0
                
                label = 'secondary'
                level = 'TBD'
                if perf_percent >= 85: label, level = 'success', 'Excellent'
                elif perf_percent >= 75: label, level = 'primary', 'Very Good'
                elif perf_percent >= 65: label, level = 'info', 'Good'
                elif perf_percent >= 50: label, level = 'warning', 'Average'
                else: label, level = 'danger', 'Poor'
                
                component_stats.append({
                    'name': comp.name,
                    'max': max_val,
                    'avg': round(avg_val, 1),
                    'label': label,
                    'level': level,
                    'percent': perf_percent
                })
    else:
        # Legacy/Fallback
        students_with_grades = db.session.query(Student, Grade).join(Grade).filter(Student.user_id == current_user.id).all()
        passed_students = sum(1 for _, grade in students_with_grades if grade.is_passed())
        failed_students = len(students_with_grades) - passed_students
        
        component_names = ['Semester 1', 'Mid-Year', 'Semester 2', 'Final Exam']
        # Rough estimation for legacy
        component_stats = [{'name': n, 'max': 25, 'avg': 0, 'label': 'secondary', 'level': 'TBD', 'percent': 0} for n in component_names]

    # Attendance statistics
    best_attendance = db.session.query(Student).filter(Student.user_id == current_user.id, Student.data_year == current_user.data_year).order_by(desc(
        func.coalesce(
            func.sum(func.cast(Attendance.present, db.Integer)) * 100.0 / func.count(Attendance.id),
            0
        )
    )).join(Attendance, Student.id == Attendance.student_id, isouter=True).group_by(Student.id).limit(5).all()
    
    worst_attendance = db.session.query(Student).filter(Student.user_id == current_user.id, Student.data_year == current_user.data_year).order_by(
        func.coalesce(
            func.sum(func.cast(Attendance.present, db.Integer)) * 100.0 / func.count(Attendance.id),
            0
        )
    ).join(Attendance, Student.id == Attendance.student_id, isouter=True).group_by(Student.id).limit(5).all()
    
    # Grade distribution by year (Dynamic if scheme exists)
    if default_scheme:
        # Use GradeEntry totals
        grade_distribution = db.session.query(
            Student.academic_year,
            func.avg(db.session.query(func.sum(GradeEntry.value)).filter(GradeEntry.student_id == Student.id).label('sum_val'))
        ).group_by(Student.academic_year).all()
    else:
        grade_distribution = db.session.query(
            Student.academic_year,
            func.avg(
                func.coalesce(Grade.semester1_theory, 0) +
                func.coalesce(Grade.semester1_practical, 0) +
                func.coalesce(Grade.semester1_attendance, 0) +
                func.coalesce(Grade.midyear_exam, 0) +
                func.coalesce(Grade.semester2_theory, 0) +
                func.coalesce(Grade.semester2_practical, 0) +
                func.coalesce(Grade.semester2_attendance, 0) +
                func.coalesce(Grade.final_theory, 0) +
                func.coalesce(Grade.final_practical, 0)
            ).label('avg_grade')
        ).join(Grade).group_by(Student.academic_year).all()
    
    return render_template('reports/analytics.html',
                         total_students=total_students,
                         passed_students=passed_students,
                         failed_students=failed_students,
                         best_attendance=best_attendance,
                         worst_attendance=worst_attendance,
                         grade_distribution=grade_distribution,
                         component_stats=component_stats)

# Schedule Management Routes (Bonus feature)
@app.route('/schedule')
@login_required
def schedule_list():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    day = request.args.get('day')
    
    query = schedule_scope()
    if year:
        query = query.filter(Schedule.academic_year == year)
    if section:
        query = query.filter(Schedule.section == section)
    if day:
        query = query.filter(Schedule.day_of_week == day)
    
    schedules = query.order_by(Schedule.day_of_week, Schedule.start_time, Schedule.academic_year, Schedule.section).all()
    
    # Get sections available to current user (filtered by selected year)
    sections_with_students = get_available_sections(academic_year=year)
    available_years = get_available_years()
    
    # Create form and set dynamic section and subject choices
    form = ScheduleForm()
    form.section.choices = [(sect, f'Section {sect}') for sect in sections_with_students]
    
    return render_template('schedule/manage.html', schedules=schedules, year=year, section=section, day=day, form=form, sections_with_students=sections_with_students, available_years=available_years)

@app.route('/schedule/add', methods=['POST'])
@login_required
def add_schedule():
    form = ScheduleForm()
    
    # Get sections available to current user (all sections for add form)
    sections_with_students = get_available_sections()
    form.section.choices = [(sect, f'Section {sect}') for sect in sections_with_students]
    
    if form.validate_on_submit():
        schedule = Schedule()
        schedule.user_id = current_user.id
        schedule.data_year = current_user.data_year
        schedule.academic_year = form.academic_year.data
        schedule.section = form.section.data
        schedule.day_of_week = form.day_of_week.data
        schedule.start_time = form.start_time.data
        schedule.end_time = form.end_time.data
        schedule.venue = form.venue.data
        schedule.class_type = form.class_type.data
        schedule.instructor = form.instructor.data
        schedule.notes = form.notes.data
        db.session.add(schedule)
        db.session.commit()
        flash('Class added to schedule successfully!', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
    
    return redirect(url_for('schedule_list'))

@app.route('/schedule/<int:schedule_id>/edit', methods=['POST'])
@login_required
def edit_schedule(schedule_id):
    schedule = schedule_scope().filter_by(id=schedule_id).first_or_404()
    
    schedule.academic_year = int(request.form.get('academic_year'))
    schedule.section = request.form.get('section')
    schedule.day_of_week = request.form.get('day_of_week')
    schedule.start_time = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
    schedule.end_time = datetime.strptime(request.form.get('end_time'), '%H:%M').time()
    schedule.venue = request.form.get('venue')
    schedule.class_type = request.form.get('class_type')
    schedule.instructor = request.form.get('instructor')
    schedule.notes = request.form.get('notes')
    
    db.session.commit()
    flash('Schedule updated successfully!', 'success')
    return redirect(url_for('schedule_list'))

@app.route('/schedule/<int:schedule_id>/delete', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    schedule = schedule_scope().filter_by(id=schedule_id).first_or_404()
    db.session.delete(schedule)
    db.session.commit()
    flash('Class removed from schedule!', 'success')
    return redirect(url_for('schedule_list'))

@app.route('/schedule/export/pdf')
@login_required
def export_schedule_pdf():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    day = request.args.get('day')
    
    # Build query
    query = schedule_scope()
    if year:
        query = query.filter(Schedule.academic_year == year)
    if section:
        query = query.filter(Schedule.section == section)
    if day:
        query = query.filter(Schedule.day_of_week == day)
    
    schedules = query.order_by(Schedule.day_of_week, Schedule.start_time, Schedule.academic_year, Schedule.section).all()
    
    # Create PDF
    buffer = io.BytesIO()
    
    # Use Arabic-compatible fonts if available
    if ARABIC_FONT_AVAILABLE:
        default_font = ARABIC_FONT_NAME
        default_font_bold = ARABIC_FONT_BOLD_NAME
    else:
        default_font = 'Helvetica'
        default_font_bold = 'Helvetica-Bold'
    
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.5*inch, rightMargin=0.5*inch)
    
    # Get styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=20,
        alignment=1,
        textColor=colors.darkgreen,
        fontName=default_font_bold
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=default_font,
        fontSize=8
    )
    
    # Build content
    story = []
    
    # Title
    title = "Weekly Class Schedule - Academic Management System"
    story.append(Paragraph(title, title_style))
    
    # Add user profile picture if available
    photo_added = False
    if current_user.photo_filename:
        try:
            photo_path = os.path.join(UPLOAD_FOLDER, current_user.photo_filename)
            if os.path.exists(photo_path):
                # Use CircularImage for a circular profile picture
                user_photo = CircularImage(photo_path, size=1*inch)
                
                # Create a table to display photo and user info side by side
                user_name = reshape_arabic_text(current_user.full_name or current_user.username)
                user_info_data = [[
                    user_photo,
                    Paragraph(f"<b>Prepared by:</b> {user_name}", normal_style)
                ]]
                user_info_table = Table(user_info_data, colWidths=[1.2*inch, 4.8*inch])
                user_info_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                    ('ALIGN', (1, 0), (1, 0), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]))
                story.append(user_info_table)
                story.append(Spacer(1, 10))
                photo_added = True
        except Exception as e:
            # If photo fails to load, log and continue with fallback
            import logging
            logging.warning(f"Failed to load user photo {current_user.photo_filename}: {e}")
    
    # Always add user name if photo wasn't successfully added
    if not photo_added:
        user_name = reshape_arabic_text(current_user.full_name or current_user.username)
        story.append(Paragraph(f"<b>Prepared by:</b> {user_name}", normal_style))
        story.append(Spacer(1, 10))
    
    # Report details
    report_details = [
        ['University:', 'University of Baghdad'],
        ['College:', 'Physical Education and Sports Sciences'],
        ['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    ]
    
    if year:
        report_details.append(['Academic Year:', f"{year} Year"])
    if section:
        report_details.append(['Section:', section])
    if day:
        report_details.append(['Day:', day])
    
    info_table = Table(report_details, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), default_font_bold),
        ('FONTNAME', (1, 0), (1, -1), default_font),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))
    
    # Create weekly schedule table
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    # Group schedules by time slot and day
    time_slots = {}
    for schedule in schedules:
        time_key = schedule.start_time.strftime('%H:%M')
        if time_key not in time_slots:
            time_slots[time_key] = {}
        time_slots[time_key][schedule.day_of_week] = schedule
    
    # Build table data
    table_data = [['Time'] + days]
    
    for time_slot in sorted(time_slots.keys()):
        row = [Paragraph(f"<b>{time_slot}</b>", normal_style)]
        for day in days:
            if day in time_slots[time_slot]:
                schedule = time_slots[time_slot][day]
                cell_text = f"<b>Year {schedule.academic_year}{schedule.section}</b><br/>"
                cell_text += f"{reshape_arabic_text(schedule.class_type)}<br/>"
                if schedule.instructor:
                    cell_text += f"Inst: {reshape_arabic_text(schedule.instructor)}<br/>"
                if schedule.venue:
                    cell_text += f"Venue: {reshape_arabic_text(schedule.venue)}"
                row.append(Paragraph(cell_text, normal_style))
            else:
                row.append('')
        table_data.append(row)
    
    # Create table
    schedule_table = Table(table_data, colWidths=[0.8*inch] + [1.3*inch] * 7)
    schedule_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), default_font_bold),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), default_font),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ]))
    
    story.append(schedule_table)
    
    # Build PDF
    doc.build(story)
    
    # Return PDF
    buffer.seek(0)
    filename = f"schedule_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    if year or section or day:
        filters = []
        if year:
            filters.append(f"year{year}")
        if section:
            filters.append(f"section{section}")
        if day:
            filters.append(day.lower())
        filename = f"schedule_{'_'.join(filters)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

# Excel Export Routes
@app.route('/export/students/filters')
@login_required
def export_students_filters():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Get sections available to current user (filtered by selected year)
    sections = get_available_sections(academic_year=year)
    available_years = get_available_years()
    
    return render_template('students/export_filters.html', sections=sections, year=year, section=section, 
                          available_years=available_years)

@app.route('/export/students')
@login_required
def export_students():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    
    # Add report header
    ws.merge_cells('A1:G1')
    title_cell = ws.cell(row=1, column=1, value="Students Report")
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A2:G2')
    date_cell = ws.cell(row=2, column=2, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    date_cell.alignment = Alignment(horizontal='center')
    
    # Headers
    headers = ['Student ID', 'Name', 'Academic Year', 'Section', 'Email', 'Phone', 'Date Created']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(start_color="28a745", end_color="28a745", fill_type="solid")
    
    # Data
    for row, student in enumerate(students, 5):
        ws.cell(row=row, column=1, value=student.student_id)
        ws.cell(row=row, column=2, value=student.name)
        ws.cell(row=row, column=3, value=student.academic_year)
        ws.cell(row=row, column=4, value=student.section)
        ws.cell(row=row, column=5, value=student.email or '')
        ws.cell(row=row, column=6, value=student.phone or '')
        ws.cell(row=row, column=7, value=student.date_created.strftime('%Y-%m-%d %H:%M'))
    
    # Adjust column widths
    for column_cells in ws.columns:
        length = max(len(str(cell.value or '')) for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(length + 2, 50)
    
    # Save to memory
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    # Generate filename
    filename = f"students_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filters = []
    if year:
        filters.append(f"year{year}")
    if section:
        filters.append(f"section{section}")
    if filters:
        filename = f"students_{'_'.join(filters)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/export/grades/filters')
@login_required
def export_grades_filters():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Get sections available to current user (filtered by selected year)
    sections = get_available_sections(academic_year=year)
    available_years = get_available_years()
    
    return render_template('grades/export_filters.html', sections=sections, year=year, section=section, 
                          available_years=available_years)

@app.route('/export/grades')
@login_required
def export_grades():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Check if a dynamic scheme is default
    default_scheme = GradeScheme.query.filter_by(
        user_id=current_user.id, 
        data_year=current_user.data_year, 
        is_default=True
    ).first()
    
    # Get students
    query = student_scope()
    if year:
        query = query.filter(Student.academic_year == year)
    if section:
        query = query.filter(Student.section == section)
    students = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Grades"
    
    if default_scheme:
        # --- DYNAMIC EXCEL LOGIC ---
        sub_components = []
        for comp in default_scheme.components:
            for sub in comp.sub_components:
                sub_components.append(sub)
        
        # Headers
        headers = ['Student ID', 'Name', 'Year', 'Section']
        for sub in sub_components:
            # Component: Sub (Max) format
            headers.append(f"{sub.component.name}: {sub.name} ({sub.max_marks})")
        headers.extend(['Total Grade', 'Status'])
        
        # Add report header
        total_cols = len(headers)
        from openpyxl.utils import get_column_letter
        last_col = get_column_letter(total_cols)
        ws.merge_cells(f'A1:{last_col}1')
        title_cell = ws.cell(row=1, column=1, value=f"Grades Report - {default_scheme.name}")
        title_cell.font = Font(bold=True, size=14)
        title_cell.alignment = Alignment(horizontal='center')
        
        ws.merge_cells(f'A2:{last_col}2')
        date_cell = ws.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        date_cell.alignment = Alignment(horizontal='center')

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col, value=header)
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color="28a745", end_color="28a745", fill_type="solid")
            cell.alignment = Alignment(horizontal='center', wrap_text=True)
        
        # Data
        from models import GradeEntry
        for row_idx, student in enumerate(students, 5):
            ws.cell(row=row_idx, column=1, value=student.student_id)
            ws.cell(row=row_idx, column=2, value=student.name)
            ws.cell(row=row_idx, column=3, value=student.academic_year)
            ws.cell(row=row_idx, column=4, value=student.section)
            
            total_sum = 0
            for col_idx, sub in enumerate(sub_components, 5):
                entry = GradeEntry.query.filter_by(student_id=student.id, sub_component_id=sub.id).first()
                val = entry.value if entry else 0
                ws.cell(row=row_idx, column=col_idx, value=val)
                total_sum += val
                
            ws.cell(row=row_idx, column=4 + len(sub_components) + 1, value=total_sum)
            status = "PASS" if total_sum >= (default_scheme.total_marks * 0.5) else "FAIL"
            ws.cell(row=row_idx, column=4 + len(sub_components) + 2, value=status)

    else:
        # --- LEGACY EXCEL LOGIC ---
        headers = ['Student ID', 'Name', 'Year', 'Section', 'Sem1 Theory', 'Sem1 Practical', 
                   'Midyear', 'Sem2 Theory', 'Sem2 Practical', 'Final Theory', 'Final Practical', 
                   'Attendance', 'Total Grade', 'Status']
        
        ws.merge_cells('A1:N1')
        title_cell = ws.cell(row=1, column=1, value="Grades Report (Legacy)")
        title_cell.font = Font(bold=True, size=14)
        title_cell.alignment = Alignment(horizontal='center')
        
        ws.merge_cells('A2:N2')
        date_cell = ws.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        date_cell.alignment = Alignment(horizontal='center')

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col, value=header)
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color="28a745", end_color="28a745", fill_type="solid")

        for row_idx, student in enumerate(students, 5):
            grade = Grade.query.filter_by(student_id=student.id).first()
            if grade:
                ws.cell(row=row_idx, column=1, value=student.student_id)
                ws.cell(row=row_idx, column=2, value=student.name)
                ws.cell(row=row_idx, column=3, value=student.academic_year)
                ws.cell(row=row_idx, column=4, value=student.section)
                ws.cell(row=row_idx, column=5, value=grade.semester1_theory or 0)
                ws.cell(row=row_idx, column=6, value=grade.semester1_practical or 0)
                ws.cell(row=row_idx, column=7, value=grade.midyear_exam or 0)
                ws.cell(row=row_idx, column=8, value=grade.semester2_theory or 0)
                ws.cell(row=row_idx, column=9, value=grade.semester2_practical or 0)
                ws.cell(row=row_idx, column=10, value=grade.final_theory or 0)
                ws.cell(row=row_idx, column=11, value=grade.final_practical or 0)
                ws.cell(row=row_idx, column=12, value=student.calculate_attendance_marks())
                ws.cell(row=row_idx, column=13, value=grade.get_total_grade())
                ws.cell(row=row_idx, column=14, value="PASS" if grade.is_passed() else "FAIL")
    
    # Adjust column widths
    from openpyxl.utils import get_column_letter
    for col_num in range(1, len(headers) + 1):
        col_letter = get_column_letter(col_num)
        ws.column_dimensions[col_letter].width = 15
    
    # Save to memory
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    # Generate filename
    filename = f"grades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filters = []
    if year: filters.append(f"year{year}")
    if section: filters.append(f"section{section}")
    if filters: filename = f"grades_{'_'.join(filters)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/export/attendance/pdf-filters')
@login_required
def attendance_pdf_filters():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Get sections available to current user (filtered by selected year)
    sections = get_available_sections(academic_year=year)
    available_years = get_available_years()
    
    return render_template('attendance/export_pdf.html', sections=sections, year=year, section=section, 
                          available_years=available_years)

@app.route('/export/attendance/pdf')
@login_required
def export_attendance_pdf():
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    date_filter = request.args.get('date')
    
    # Validate required filters
    if not year or not section:
        flash('Please select both Academic Year and Section to generate the PDF report.', 'error')
        return redirect(url_for('attendance_pdf_filters'))
    
    # Build query
    query = db.session.query(Student, Attendance).join(Attendance, Student.id == Attendance.student_id).filter(Student.user_id == current_user.id)
    
    # Apply required filters
    query = query.filter(Student.academic_year == year)
    query = query.filter(Student.section == section)
    if date_filter:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
        query = query.filter(Attendance.date == filter_date)
    
    results = query.order_by(Student.academic_year, Student.section, Student.name).all()
    
    # Create PDF with UTF-8 encoding support
    buffer = io.BytesIO()
    
    # Use Arabic-compatible fonts if available
    if ARABIC_FONT_AVAILABLE:
        default_font = ARABIC_FONT_NAME
        default_font_bold = ARABIC_FONT_BOLD_NAME
    else:
        default_font = 'Helvetica'
        default_font_bold = 'Helvetica-Bold'
    
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Get styles with UTF-8 support
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor=colors.darkgreen,
        fontName=default_font_bold
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=default_font
    )
    
    # Build content
    story = []
    
    # Title and header
    title = "Daily Attendance Report"
    story.append(Paragraph(title, title_style))
    
    # Add user profile picture if available
    photo_added = False
    if current_user.photo_filename:
        try:
            photo_path = os.path.join(UPLOAD_FOLDER, current_user.photo_filename)
            if os.path.exists(photo_path):
                # Use CircularImage for a circular profile picture
                user_photo = CircularImage(photo_path, size=1*inch)
                
                # Create a table to display photo and user info side by side
                user_info_data = [[
                    user_photo,
                    Paragraph(f"<b>Prepared by:</b> {current_user.full_name or current_user.username}", normal_style)
                ]]
                user_info_table = Table(user_info_data, colWidths=[1.2*inch, 4.8*inch])
                user_info_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                    ('ALIGN', (1, 0), (1, 0), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]))
                story.append(user_info_table)
                story.append(Spacer(1, 10))
                photo_added = True
        except Exception as e:
            # If photo fails to load, log and continue with fallback
            import logging
            logging.warning(f"Failed to load user photo {current_user.photo_filename}: {e}")
    
    # Always add user name if photo wasn't successfully added
    if not photo_added:
        story.append(Paragraph(f"<b>Prepared by:</b> {current_user.full_name or current_user.username}", normal_style))
        story.append(Spacer(1, 10))
    
    # Report details in a structured table format
    report_details = [
        ['University:', 'University of Baghdad'],
        ['College:', 'Physical Education and Sports Sciences'],

        ['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    ]
    
    # Add filter details if present
    filter_row = []
    if year:
        filter_row.append(['Academic Year:', f"{year} Year"])
    if section:
        filter_row.append(['Section:', section])
    if date_filter:
        filter_row.append(['Date:', date_filter])
    
    # Add filter information
    report_details.extend(filter_row)
    
    # Create a clean info table
    info_table = Table(report_details, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), default_font_bold),
        ('FONTNAME', (1, 0), (1, -1), default_font),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(info_table)
    story.append(Spacer(1, 20))
    
    # Create attendance table
    if results:
        # Table headers
        data = [['Student ID', 'Student Name', 'Academic Year', 'Section', 'Date', 'Present', 'Notes']]
        
        # Add data rows with proper encoding for Arabic
        for student, attendance in results:
            # Reshape Arabic text for proper display
            student_name = reshape_arabic_text(student.name) if student.name else ""
            notes_text = reshape_arabic_text(attendance.notes) if attendance.notes else ""
            
            data.append([
                student.student_id,
                student_name,
                f"{student.academic_year} Year",
                student.section,
                attendance.date.strftime('%Y-%m-%d'),
                "Present" if attendance.present else "Absent",
                notes_text
            ])
        
        # Create table with adjusted column widths to prevent overlapping
        table = Table(data, colWidths=[1.1*inch, 2*inch, 1.1*inch, 0.7*inch, 1*inch, 0.8*inch, 1.4*inch])
        
        # Style the table with UTF-8 compatible fonts
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), default_font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('FONTNAME', (0, 1), (-1, -1), default_font),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        
        story.append(table)
        
        # Summary statistics
        story.append(Spacer(1, 20))
        total_records = len(results)
        present_count = sum(1 for _, attendance in results if attendance.present)
        absent_count = total_records - present_count
        
        summary_data = [
            ['Total Students', str(total_records)],
            ['Present', str(present_count)],
            ['Absent', str(absent_count)],
            ['Attendance Rate', f"{(present_count/total_records*100):.1f}%" if total_records > 0 else "0%"]
        ]
        
        summary_table = Table(summary_data, colWidths=[2*inch, 1*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), default_font_bold),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        heading_style = ParagraphStyle(
            'CustomHeading2',
            parent=styles['Heading2'],
            fontName=default_font_bold
        )
        story.append(Paragraph("<b>Attendance Summary</b>", heading_style))
        story.append(summary_table)
    else:
        story.append(Paragraph("No attendance records found for the selected criteria.", normal_style))
    
    # Footer
    story.append(Spacer(1, 30))
    footer_text = "© Msc Abbas Hussein Khaleefah | Email: abbas.h@cope.uobaghdad.edu.iq | University of Baghdad"
    story.append(Paragraph(footer_text, normal_style))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    # Generate filename
    filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filters = []
    if year:
        filters.append(f"year{year}")
    if section:
        filters.append(f"section{section}")
    if date_filter:
        filters.append(f"date{date_filter}")
    if filters:
        filename = f"attendance_report_{'_'.join(filters)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/export/attendance/monthly-absence/pdf')
@login_required
def export_monthly_absence_pdf():
    """Export monthly absence hours report to PDF"""
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    selected_months = request.args.getlist('months', type=int)  # Multiple month filter
    
    # Validate required filters
    if not year or not section:
        flash('Please select both Academic Year and Section to generate the PDF report.', 'error')
        return redirect(url_for('attendance_pdf_filters'))
    
    # Query to get all students in the year/section with their attendance records
    from sqlalchemy import extract
    
    query = student_scope().filter(
        Student.academic_year == year,
        Student.section == section
    )
    
    students = query.order_by(Student.name).all()
    
    if not students:
        flash('No students found for the selected criteria.', 'warning')
        return redirect(url_for('attendance_pdf_filters'))
    
    # Get all attendance records for these students grouped by month
    student_ids = [s.id for s in students]
    
    # Build query to aggregate absences by student and month
    absence_query_builder = db.session.query(
        Attendance.student_id,
        extract('month', Attendance.date).label('month'),
        func.count(Attendance.id).label('absences')
    ).filter(
        Attendance.student_id.in_(student_ids),
        Attendance.present == False  # Only count absences
    )
    
    # Add month filter if specified (multiple months)
    if selected_months:
        absence_query_builder = absence_query_builder.filter(
            extract('month', Attendance.date).in_(selected_months)
        )
    
    absence_query = absence_query_builder.group_by(
        Attendance.student_id,
        extract('month', Attendance.date)
    ).all()
    
    # Build data structure: {student_id: {month: absence_count}}
    student_monthly_absences = {}
    all_months = set()
    
    for student_id, month, absences in absence_query:
        if student_id not in student_monthly_absences:
            student_monthly_absences[student_id] = {}
        month_int = int(month)
        student_monthly_absences[student_id][month_int] = int(absences) if absences else 0
        all_months.add(month_int)
    
    # Sort months chronologically or use selected months
    if selected_months:
        sorted_months = sorted(selected_months)
    else:
        sorted_months = sorted(list(all_months)) if all_months else []
    
    # Month names for headers
    month_names = {
        1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
        7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
    }
    
    # Create PDF with UTF-8 encoding support (landscape for wider table)
    buffer = io.BytesIO()
    
    # Use Arabic-compatible fonts if available
    if ARABIC_FONT_AVAILABLE:
        default_font = ARABIC_FONT_NAME
        default_font_bold = ARABIC_FONT_BOLD_NAME
    else:
        default_font = 'Helvetica'
        default_font_bold = 'Helvetica-Bold'
    
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Get styles with UTF-8 support
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1,
        textColor=colors.darkgreen,
        fontName=default_font_bold
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=default_font
    )
    
    # Build content
    story = []
    
    # Title
    title = "Monthly Absence Hours Report"
    story.append(Paragraph(title, title_style))
    
    # Add user profile picture if available
    photo_added = False
    if current_user.photo_filename:
        try:
            photo_path = os.path.join(UPLOAD_FOLDER, current_user.photo_filename)
            if os.path.exists(photo_path):
                user_photo = CircularImage(photo_path, size=1*inch)
                user_info_data = [[
                    user_photo,
                    Paragraph(f"<b>Prepared by:</b> {current_user.full_name or current_user.username}", normal_style)
                ]]
                user_info_table = Table(user_info_data, colWidths=[1.2*inch, 4.8*inch])
                user_info_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                    ('ALIGN', (1, 0), (1, 0), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]))
                story.append(user_info_table)
                story.append(Spacer(1, 10))
                photo_added = True
        except Exception as e:
            import logging
            logging.warning(f"Failed to load user photo {current_user.photo_filename}: {e}")
    
    if not photo_added:
        story.append(Paragraph(f"<b>Prepared by:</b> {current_user.full_name or current_user.username}", normal_style))
        story.append(Spacer(1, 10))
    
    # Report details
    report_details = [
        ['University:', 'University of Baghdad'],
        ['College:', 'Physical Education and Sports Sciences'],

        ['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        ['Academic Year:', f"{year} Year"],
        ['Section:', section]
    ]
    
    # Add month filter to report details if specified
    if selected_months:
        month_full_names = {
            1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
            7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'
        }
        selected_month_names = [month_full_names.get(m, str(m)) for m in sorted(selected_months)]
        report_details.append(['Month Filter:', ', '.join(selected_month_names)])
    
    info_table = Table(report_details, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), default_font_bold),
        ('FONTNAME', (1, 0), (1, -1), default_font),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(info_table)
    story.append(Spacer(1, 20))
    
    # Note about calculation
    story.append(Paragraph("<b>Note:</b> Each missed lecture = 2 hours of absence", normal_style))
    story.append(Spacer(1, 15))
    
    # Create table headers
    headers = ['Student ID', 'Student Name']
    headers.extend([month_names[m] for m in sorted_months])
    headers.append('Total Hours')
    
    # Calculate column widths dynamically for full page width
    # Landscape A4 is 11.69 inches wide, minus margins (0.5 inch on each side) = ~10.69 inches available
    page_width = 10.69 * inch
    num_months = len(sorted_months)
    
    # Allocate space for static columns
    student_id_width = 1.3 * inch
    student_name_width = 3.0 * inch  # Wider for Arabic names
    total_width = 1.0 * inch
    
    # Remaining width for month columns
    remaining_width = page_width - student_id_width - student_name_width - total_width
    
    if num_months > 0:
        month_col_width = remaining_width / num_months
    else:
        month_col_width = 0
    
    col_widths = [student_id_width, student_name_width]  # Student ID and Name
    col_widths.extend([month_col_width] * num_months)  # Month columns - evenly distributed
    col_widths.append(total_width)  # Total column
    
    # Build table data
    data = [headers]
    
    for student in students:
        row = [
            student.student_id,
            reshape_arabic_text(student.name) if student.name else ""
        ]
        
        total_absences = 0
        student_absences = student_monthly_absences.get(student.id, {})
        
        for month in sorted_months:
            absences = student_absences.get(month, 0)
            hours = absences * 2
            row.append(str(hours))
            total_absences += absences
        
        total_hours = total_absences * 2
        row.append(str(total_hours))
        
        data.append(row)
    
    # Create and style table with header repetition on every page
    table = Table(data, colWidths=col_widths, repeatRows=1)  # Repeat header row on each page
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), default_font_bold),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('FONTNAME', (0, 1), (-1, -1), default_font),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),  # Left-align student names
    ]))
    
    story.append(table)
    
    # Footer
    story.append(Spacer(1, 30))
    footer_text = "© Msc Abbas Hussein Khaleefah | Email: abbas.h@cope.uobaghdad.edu.iq | University of Baghdad"
    story.append(Paragraph(footer_text, normal_style))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    # Generate filename
    filters = [f"year{year}", f"section{section}"]
    if selected_months:
        month_full_names = {
            1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
        }
        month_names_list = [month_full_names.get(m, str(m)) for m in sorted(selected_months)]
        months_str = '_'.join(month_names_list)
        filters.append(months_str)
    else:
        filters.append("all_months")
    filename = f"monthly_absence_hours_{'_'.join(filters)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

# ==================== QR Code Attendance System ====================

import qrcode
import base64
from io import BytesIO

def generate_qr_code_for_student(student):
    """Generate a unique QR code for a student if not exists"""
    if not student.qr_code:
        # Create unique QR code using student_id and a random component
        unique_id = f"STU-{student.student_id}-{uuid.uuid4().hex[:8]}"
        student.qr_code = unique_id
        db.session.commit()
    return student.qr_code

def get_qr_code_image(data, size=200):
    """Generate QR code image and return as base64"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Resize if needed
    from PIL import Image
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return base64.b64encode(buffer.getvalue()).decode()

@app.route('/qr/generate-all')
@login_required
def generate_all_qr_codes():
    """Generate QR codes for all students without one"""
    students = student_scope().filter(Student.qr_code == None).all()
    count = 0
    
    for student in students:
        generate_qr_code_for_student(student)
        count += 1
    
    db.session.commit()
    flash(f'Generated QR codes for {count} students!', 'success')
    return redirect(url_for('qr_attendance_page'))

@app.route('/qr/scan')
@login_required
def qr_attendance_page():
    """QR code scanning page for attendance"""
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    scan_date_str = request.args.get('scan_date')
    
    # Parse scan_date or default to today
    if scan_date_str:
        try:
            scan_date = datetime.strptime(scan_date_str, '%Y-%m-%d').date()
        except ValueError:
            scan_date = date.today()
    else:
        scan_date = date.today()
    
    # Get available years and sections
    years_query = db.session.query(Student.academic_year).filter(
        Student.user_id == current_user.id
    ).distinct().order_by(Student.academic_year)
    available_years = [y[0] for y in years_query.all()]
    
    sections_query = db.session.query(Student.section).filter(
        Student.user_id == current_user.id
    ).distinct().order_by(Student.section)
    available_sections = [s[0] for s in sections_query.all()]
    
    # Get attendance records for the selected date
    today_attendance = []
    
    if year and section:
        students = student_scope().filter(
            Student.academic_year == year,
            Student.section == section
        ).all()
        
        for student in students:
            att = Attendance.query.filter_by(
                student_id=student.id,
                date=scan_date
            ).first()
            today_attendance.append({
                'student': student,
                'present': att.present if att else None,
                'time': att.created_at.strftime('%H:%M') if att and att.created_at else None
            })
    
    return render_template('qr/scan.html',
                         year=year,
                         section=section,
                         available_years=available_years,
                         available_sections=available_sections,
                         today_attendance=today_attendance,
                         scan_date=scan_date.strftime('%Y-%m-%d'))

@app.route('/api/qr/record-attendance', methods=['POST'])
@login_required
def record_qr_attendance():
    """API endpoint to record attendance from QR scan"""
    data = request.get_json()
    qr_code = data.get('qr_code')
    scan_date_str = data.get('scan_date')
    
    if not qr_code:
        return jsonify({'status': 'error', 'message': 'No QR code provided'}), 400
    
    # Parse scan_date or default to today
    if scan_date_str:
        try:
            attendance_date = datetime.strptime(scan_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid date format. Use YYYY-MM-DD'}), 400
    else:
        attendance_date = date.today()
    
    # Find student by QR code
    student = student_scope().filter_by(qr_code=qr_code).first()
    
    if not student:
        return jsonify({'status': 'error', 'message': 'Student not found'}), 404
    
    # Check if already marked present on this date
    existing = Attendance.query.filter_by(
        student_id=student.id,
        date=attendance_date
    ).first()
    
    if existing and existing.present:
        date_display = attendance_date.strftime('%Y-%m-%d')
        return jsonify({
            'status': 'duplicate',
            'message': f'{student.name} already marked present on {date_display}!',
            'student_name': student.name,
            'student_id': student.student_id,
            'time': existing.created_at.strftime('%H:%M') if existing.created_at else None
        })
    
    # Record attendance
    if existing:
        existing.present = True
        existing.created_at = datetime.utcnow()
    else:
        attendance = Attendance(
            student_id=student.id,
            date=attendance_date,
            present=True,
            notes='Recorded via QR scan'
        )
        db.session.add(attendance)
    
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': f'Attendance recorded for {student.name}',
        'student_name': student.name,
        'student_id': student.student_id,
        'academic_year': student.academic_year,
        'section': student.section,
        'time': datetime.now().strftime('%H:%M'),
        'date': attendance_date.strftime('%Y-%m-%d')
    })

@app.route('/qr/student-cards')
@login_required
def qr_student_cards():
    """Page to view and print student QR cards"""
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    # Get available years and sections
    years_query = db.session.query(Student.academic_year).filter(
        Student.user_id == current_user.id
    ).distinct().order_by(Student.academic_year)
    available_years = [y[0] for y in years_query.all()]
    
    sections_query = db.session.query(Student.section).filter(
        Student.user_id == current_user.id
    ).distinct().order_by(Student.section)
    available_sections = [s[0] for s in sections_query.all()]
    
    students = []
    if year and section:
        students = student_scope().filter(
            Student.academic_year == year,
            Student.section == section
        ).order_by(Student.name).all()
        
        # Generate QR codes for students who don't have one
        for student in students:
            if not student.qr_code:
                generate_qr_code_for_student(student)
    
    # Generate QR images for display
    student_cards = []
    for student in students:
        qr_image = get_qr_code_image(student.qr_code, size=150)
        student_cards.append({
            'student': student,
            'qr_image': qr_image
        })
    
    return render_template('qr/student_cards.html',
                         year=year,
                         section=section,
                         available_years=available_years,
                         available_sections=available_sections,
                         student_cards=student_cards)

@app.route('/qr/print-cards-pdf')
@login_required
def print_qr_cards_pdf():
    """Generate PDF with student QR cards for printing"""
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    if not year or not section:
        flash('Please select year and section', 'error')
        return redirect(url_for('qr_student_cards'))
    
    students = student_scope().filter(
        Student.academic_year == year,
        Student.section == section
    ).order_by(Student.name).all()
    
    # Ensure all students have QR codes
    for student in students:
        if not student.qr_code:
            generate_qr_code_for_student(student)
    
    db.session.commit()
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                          leftMargin=0.5*inch, rightMargin=0.5*inch,
                          topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    story = []
    
    # Use DejaVu fonts for Arabic support
    default_font = ARABIC_FONT_NAME if ARABIC_FONT_AVAILABLE else 'Helvetica'
    default_font_bold = ARABIC_FONT_BOLD_NAME if ARABIC_FONT_AVAILABLE else 'Helvetica-Bold'
    
    # Title
    title_style = ParagraphStyle(
        'Title',
        fontName=default_font_bold,
        fontSize=16,
        alignment=1,
        spaceAfter=20
    )
    
    title_text = f"Student QR Cards - Year {year} Section {section}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 20))
    
    # Create cards in a 2-column layout
    card_data = []
    row = []
    
    for i, student in enumerate(students):
        # Generate QR code image
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(student.qr_code)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to buffer
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        
        # Create card content as table
        name_text = reshape_arabic_text(student.name) if ARABIC_FONT_AVAILABLE else student.name
        
        card_style = ParagraphStyle(
            'Card',
            fontName=default_font,
            fontSize=10,
            alignment=1
        )
        
        card_content = [
            [RLImage(qr_buffer, width=1.2*inch, height=1.2*inch)],
            [Paragraph(f"<b>{name_text}</b>", card_style)],
            [Paragraph(f"ID: {student.student_id}", card_style)],
            [Paragraph(f"Year {student.academic_year} - Section {student.section}", card_style)]
        ]
        
        card_table = Table(card_content, colWidths=[2.5*inch])
        card_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        row.append(card_table)
        
        if len(row) == 3:  # 3 cards per row
            card_data.append(row)
            row = []
    
    # Add remaining cards
    if row:
        while len(row) < 3:
            row.append('')
        card_data.append(row)
    
    # Create main table
    if card_data:
        main_table = Table(card_data, colWidths=[2.6*inch, 2.6*inch, 2.6*inch])
        main_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(main_table)
    
    doc.build(story)
    buffer.seek(0)
    
    filename = f"qr_cards_year{year}_section{section}_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/qr/student/<int:student_id>')
@login_required
def view_student_qr(student_id):
    """View individual student QR code"""
    student = student_scope().filter_by(id=student_id).first_or_404()
    
    if not student.qr_code:
        generate_qr_code_for_student(student)
    
    qr_image = get_qr_code_image(student.qr_code, size=300)
    
    return render_template('qr/student_qr.html',
                         student=student,
                         qr_image=qr_image)

# ============= Academic Timeline Management Routes =============

@app.route('/admin/timelines')
@login_required
def timeline_list():
    """List all academic timelines (admin only)"""
    if not current_user.is_admin:
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard'))
    
    timelines = AcademicTimeline.query.order_by(AcademicTimeline.year.desc()).all()
    
    # Create current year timeline if no timelines exist
    if not timelines:
        current_year = datetime.now().year
        default_timeline = AcademicTimeline(
            year=current_year,
            name=f'Academic Year {current_year}',
            is_active=True,
            is_current=True,
            created_by=current_user.id
        )
        db.session.add(default_timeline)
        db.session.commit()
        timelines = AcademicTimeline.query.order_by(AcademicTimeline.year.desc()).all()
    
    from models import GradeScheme
    schemes = GradeScheme.query.filter_by(user_id=current_user.id).all()
    
    return render_template('admin/timelines.html', timelines=timelines, schemes=schemes)


@app.route('/admin/timelines/add', methods=['POST'])
@login_required
def add_timeline():
    """Add a new academic timeline (admin only)"""
    if not current_user.is_admin:
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard'))
    
    year = request.form.get('year', type=int)
    name = request.form.get('name', '').strip()
    
    if not year:
        flash('Year is required.', 'danger')
        return redirect(url_for('timeline_list'))
    
    if year < 2020:
        flash('Cannot create timelines before 2020.', 'danger')
        return redirect(url_for('timeline_list'))
    
    existing = AcademicTimeline.query.filter_by(year=year).first()
    if existing:
        flash(f'Timeline for year {year} already exists.', 'danger')
        return redirect(url_for('timeline_list'))
    
    grade_scheme_id = request.form.get('grade_scheme_id', type=int)
    
    timeline = AcademicTimeline(
        year=year,
        name=name or f'Academic Year {year}',
        is_active=True,
        is_current=False,
        created_by=current_user.id,
        grade_scheme_id=grade_scheme_id if grade_scheme_id else None
    )
    db.session.add(timeline)
    db.session.commit()
    
    flash(f'Timeline for year {year} created successfully!', 'success')
    return redirect(url_for('timeline_list'))


@app.route('/admin/timelines/<int:timeline_id>/set-current', methods=['POST'])
@login_required
def set_current_timeline(timeline_id):
    """Set a timeline as the current default (admin only)"""
    if not current_user.is_admin:
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard'))
    
    timeline = AcademicTimeline.query.get_or_404(timeline_id)
    
    # Clear current flag from all timelines
    AcademicTimeline.query.update({'is_current': False})
    
    # Set this timeline as current
    timeline.is_current = True
    db.session.commit()
    
    flash(f'Timeline {timeline.year} is now the current timeline.', 'success')
    return redirect(url_for('timeline_list'))


@app.route('/admin/timelines/<int:timeline_id>/toggle-active', methods=['POST'])
@login_required
def toggle_timeline_active(timeline_id):
    """Toggle timeline active status (admin only)"""
    if not current_user.is_admin:
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard'))
    
    timeline = AcademicTimeline.query.get_or_404(timeline_id)
    timeline.is_active = not timeline.is_active
    db.session.commit()
    
    status = 'activated' if timeline.is_active else 'deactivated'
    flash(f'Timeline {timeline.year} {status}.', 'success')
    return redirect(url_for('timeline_list'))


@app.route('/admin/timelines/<int:timeline_id>/delete', methods=['POST'])
@login_required
def delete_timeline(timeline_id):
    """Delete an academic timeline and all its data (admin only)"""
    if not current_user.is_admin:
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard'))
    
    timeline = AcademicTimeline.query.get_or_404(timeline_id)
    
    if timeline.is_current:
        flash('Cannot delete the current active timeline.', 'danger')
        return redirect(url_for('timeline_list'))
    
    year = timeline.year
    
    try:
        # Get models we need for deletion
        from models import Student, Attendance, Grade, GradeEntry, GradeScheme, Curriculum, Schedule
        
        # 1. Delete Student-related data
        students = Student.query.filter_by(academic_year=year).all()
        student_ids = [s.id for s in students]
        
        if student_ids:
            # Delete Attendances
            Attendance.query.filter(Attendance.student_id.in_(student_ids)).delete(synchronize_session=False)
            
            # Delete Grades (Legacy)
            Grade.query.filter(Grade.student_id.in_(student_ids)).delete(synchronize_session=False)
            
            # Delete GradeEntries (Dynamic)
            GradeEntry.query.filter(GradeEntry.student_id.in_(student_ids)).delete(synchronize_session=False)
            
            # Delete Students
            Student.query.filter_by(academic_year=year).delete(synchronize_session=False)

        # 2. Delete Year-specific records
        # Delete Curricula and Schedules
        Curriculum.query.filter_by(data_year=year).delete(synchronize_session=False)
        Schedule.query.filter_by(data_year=year).delete(synchronize_session=False)
        
        # Delete Grade Schemes (and components/subcomponents via cascade)
        GradeScheme.query.filter_by(data_year=year).delete(synchronize_session=False)
        
        # 3. Delete the Timeline record
        db.session.delete(timeline)
        db.session.commit()
        
        flash(f'Academic Year {year} and all associated data have been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting timeline: {str(e)}', 'danger')
        
    return redirect(url_for('timeline_list'))


@app.route('/switch-year/<int:year>')
@login_required
def switch_year(year):
    """Switch the current user's active data year"""
    # Verify the timeline exists and is active
    timeline = AcademicTimeline.query.filter_by(year=year, is_active=True).first()
    if not timeline:
        flash('Invalid or inactive year.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))
    
    # Update user's data_year
    current_user.data_year = year
    db.session.commit()
    
    flash(f'Switched to year {year}.', 'success')
    return redirect(request.referrer or url_for('dashboard'))


# ============= AI Sports Test Generator =============

def get_openai_client():
    from openai import OpenAI
    from models import SystemSetting
    api_key = SystemSetting.get('openai_api_key') or os.environ.get("OPENAI_API_KEY")
    return OpenAI(
        api_key=api_key,
    )

@app.route('/ai-test-generator')
@login_required
def ai_test_generator():
    return render_template('ai_test/generator.html')

@app.route('/ai-test-generator/generate', methods=['POST'])
@login_required
def ai_generate_test():
    from models import SystemSetting
    provider = SystemSetting.get('ai_provider', 'openai')
    
    data = request.get_json()
    test_title = data.get('test_title', '').strip()
    # ... (rest of data extraction)
    description = data.get('description', '').strip()
    num_cones = data.get('num_cones', '')
    num_players = data.get('num_players', '')
    distances = data.get('distances', '').strip()
    start_end = data.get('start_end', '').strip()
    components = data.get('components', [])
    notes = data.get('notes', '').strip()

    if not test_title:
        return jsonify({'error': 'Test title is required'}), 400

    components_str = ', '.join(components) if components else 'none specified'
    prompt = f"""You are an expert sports science academic specializing in football (soccer). Generate a complete, professional football skills test document based on the following information.

Test Input:
- Test Title/Idea: {test_title}
- Sport: Football (Soccer)
- Description: {description or 'Not provided'}
- Number of Cones/Tools: {num_cones or 'Not specified'}
- Number of Players: {num_players or 'Not specified'}
- Distances: {distances or 'Not specified'}
- Start and End Point: {start_end or 'Not specified'}
- Components: {components_str}
- Additional Notes: {notes or 'None'}

IMPORTANT: If this is a well-known football test (e.g., Illinois Agility Test, T-Test, Ronaldo Test, 505 Agility Test, Yo-Yo Test, RAST Test, Slalom Dribbling Test, Shooting Accuracy Test, etc.), generate accurate details for that test. If it is a rough idea, intelligently expand it into a full professional football test. All content must be football-specific.

Respond with ONLY a valid JSON object (no markdown, no extra text) with these exact keys:
{{
  "test_name": "Full official name of the test",
  "objective": "What this test measures and its purpose",
  "tools": "List of required equipment and tools",
  "field_setup": "Detailed description of how to set up the field/court with measurements",
  "procedure": "Step-by-step numbered procedure for conducting the test",
  "performance_instructions": "Instructions for the athlete/player during the test",
  "scoring_method": "How to calculate and record the score",
  "variables_measured": "What physical/motor variables are measured",
  "notes": "Important considerations, safety notes, and validity information",
  "academic_description": "Full academic/research-style description of the test (3-4 paragraphs)",
  "practical_description": "Simple plain-language description for coaches and players (2-3 paragraphs)",
  "image_prompt": "A detailed prompt for generating a diagram image of the test layout, suitable for DALL-E or similar AI image tools. Describe the field, cone positions, player path, distances, and labels in detail.",
  "diagram_config": {{
    "field_type": "rectangle|circle|track",
    "field_width": 800,
    "field_height": 500,
    "cones": [
      {{"id": "A", "x": 100, "y": 250, "label": "Start", "color": "green"}},
      {{"id": "B", "x": 400, "y": 150, "label": "5m", "color": "orange"}},
      {{"id": "C", "x": 700, "y": 250, "label": "Finish", "color": "red"}}
    ],
    "path": [
      {{"from": "A", "to": "B", "style": "dashed", "label": "5m"}},
      {{"from": "B", "to": "C", "style": "dashed", "label": "5m"}}
    ],
    "labels": [
      {{"x": 100, "y": 30, "text": "Test Layout Diagram", "size": 16, "bold": true}}
    ],
    "show_start_finish": true,
    "description": "Brief description of what the diagram shows"
  }}
}}"""

    try:
        if provider == 'gemini':
            import google.generativeai as genai
            gemini_key = SystemSetting.get('gemini_api_key')
            if not gemini_key:
                return jsonify({'error': 'Gemini API Key is missing. Please set it in General Settings.'}), 400
            
            try:
                genai.configure(api_key=gemini_key)
                
                # Dynamic model discovery
                available_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
                
                if not available_models:
                    return jsonify({'error': 'No accessible Gemini models found for your API key.'}), 400
                
                # Prioritize models: 1.5 Pro -> 1.5 Flash -> others
                m_chosen = None
                for candidate in ["models/gemini-1.5-pro", "models/gemini-1.5-flash", "models/gemini-pro"]:
                    if candidate in available_models:
                        m_chosen = candidate
                        break
                
                if not m_chosen:
                    m_chosen = available_models[0]
                
                logging.info(f"AI Generator: Dynamic Discovery chose model: {m_chosen}")
                model = genai.GenerativeModel(m_chosen)
                
                # Gemini response usually doesn't need as much cleaning but we'll be safe
                response = model.generate_content(
                    f"System: You are a sports science expert. Always respond with valid JSON only.\n\nUser: {prompt}",
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.7,
                        max_output_tokens=3000,
                    )
                )
                raw = response.text.strip()
            except Exception as e:
                logging.error(f"Gemini dynamic discovery or generation failed: {e}")
                return jsonify({'error': f'Gemini Error: {str(e)}'}), 500
        else:
            client = get_openai_client()
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a sports science expert. Always respond with valid JSON only, no markdown code blocks."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=3000,
                temperature=0.7
            )
            raw = response.choices[0].message.content.strip()

        if raw.startswith('```'):
            if 'json' in raw[:20]:
                raw = raw.split('```json')[1].split('```')[0]
            else:
                raw = raw.split('```')[1].split('```')[0]
        else:
            # Look for the first { and last } to extract JSON if preamble exists
            start = raw.find('{')
            end = raw.rfind('}')
            if start != -1 and end != -1 and end > start:
                raw = raw[start:end+1]
                
        raw = raw.strip()
        result = json.loads(raw)
        return jsonify({'success': True, 'test': result})
    except json.JSONDecodeError as e:
        logging.error(f"JSON parse error from AI: {e}")
        logging.error(f"RAW Response (first 500 chars): {raw[:500] if 'raw' in locals() else 'Raw not defined'}")
        return jsonify({'error': 'AI response could not be parsed. Please try again.'}), 500
    except Exception as e:
        logging.error(f"AI generation error: {e}")
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500

@app.route('/ai-test-generator/export-pdf', methods=['POST'])
@login_required
def ai_export_test_pdf():
    import unicodedata, urllib.parse, base64
    # Accept both form-POST (preferred) and JSON
    if request.content_type and 'application/json' in request.content_type:
        data = request.get_json(silent=True) or {}
        test = data.get('test', {})
        diagram_data_url = data.get('diagram_data_url', '')
    else:
        raw = request.form.get('test_data', '')
        diagram_data_url = request.form.get('diagram_data_url', '')
        try:
            test = json.loads(raw) if raw else {}
        except Exception as json_err:
            logging.error(f"PDF export: JSON parse error: {json_err}, raw[:200]={raw[:200]!r}")
            test = {}
    logging.info(f"PDF export: content_type={request.content_type!r}, test_name={test.get('test_name','<empty>')!r}, keys={list(test.keys())}")
    if not test:
        return jsonify({'error': 'No test data provided'}), 400

    # ── Arabic font ──────────────────────────────────────────────────
    fn = ARABIC_FONT_NAME
    fb = ARABIC_FONT_BOLD_NAME

    # ── English font ──────────────────────────────────────────────────
    # Try to find a serif font, or fallback to Arial/Helvetica
    en, eb = 'Times-Roman', 'Times-Bold'
    if ARABIC_FONT_AVAILABLE and ARABIC_FONT_NAME == 'Arial':
        en, eb = 'Arial', 'Arial-Bold'
    elif ARABIC_FONT_AVAILABLE:
        en, eb = ARABIC_FONT_NAME, ARABIC_FONT_BOLD_NAME

    # ── Colors ────────────────────────────────────────────────────────
    C_GREEN  = colors.HexColor('#1b5e20')
    C_MGREEN = colors.HexColor('#2e7d32')
    C_LGREEN = colors.HexColor('#e8f5e9')
    C_GREY   = colors.HexColor('#555555')
    C_WHITE  = colors.white
    C_BLACK  = colors.black

    def has_arabic(text):
        return any('\u0600' <= c <= '\u06FF' for c in str(text))

    # ── PIL — measurement only (not rendering) ────────────────────────
    CONTENT_W  = 6.5 * inch
    _MDPI      = 200
    _PAGE_W_PX = int(CONTENT_W / inch * _MDPI)
    _pil_cache = {}

    def _pil_font(size_pt, bold=False):
        key = (size_pt, bold)
        if key not in _pil_cache:
            from PIL import ImageFont as _IF
            # Match the paths used at the top of routes.py for Windows
            p = "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf"
            if not os.path.exists(p):
                # Fallback to any existings path or default
                p = 'arial.ttf' 
            try:   _pil_cache[key] = _IF.truetype(p, int(size_pt * _MDPI / 72))
            except: _pil_cache[key] = _IF.load_default()
        return _pil_cache[key]

    def _measure_px(text, size_pt, bold=False):
        from PIL import Image as _PI, ImageDraw as _PD
        f = _pil_font(size_pt, bold)
        img = _PI.new('RGB', (1, 1))
        draw = _PD.Draw(img)
        bb = draw.textbbox((0, 0), text, font=f)
        return bb[2] - bb[0]

    def ar_lines(text, size=11, rl_align='RIGHT', rl_color=C_BLACK, bold=False):
        """Pre-wrap Arabic in logical order → get_display per line → raw Table-cell strings."""
        raw = str(text).strip()
        words = raw.split()
        if not words:
            return [Spacer(1, 2)]
        display_lines, current = [], []
        for word in words:
            trial = get_display(arabic_reshaper.reshape(' '.join(current + [word])))
            if _measure_px(trial, size, bold) > _PAGE_W_PX - 4 and current:
                display_lines.append(get_display(arabic_reshaper.reshape(' '.join(current))))
                current = [word]
            else:
                current.append(word)
        if current:
            display_lines.append(get_display(arabic_reshaper.reshape(' '.join(current))))
        font_name = fb if bold else fn
        result = []
        for line in display_lines:
            t = Table([[line]], colWidths=[CONTENT_W])
            t.setStyle(TableStyle([
                ('FONTNAME',      (0,0), (-1,-1), font_name),
                ('FONTSIZE',      (0,0), (-1,-1), size),
                ('TEXTCOLOR',     (0,0), (-1,-1), rl_color),
                ('ALIGN',         (0,0), (-1,-1), rl_align),
                ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING',   (0,0), (-1,-1), 0),
                ('RIGHTPADDING',  (0,0), (-1,-1), 0),
                ('TOPPADDING',    (0,0), (-1,-1), 1),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('ROWBACKGROUNDS',(0,0), (-1,-1), [C_WHITE]),
            ]))
            result.append(t)
        return result

    # ── Section header helpers ────────────────────────────────────────
    def sec_header_en(label):
        t = Table([[label]], colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), C_MGREEN),
            ('TEXTCOLOR',     (0,0), (-1,-1), C_WHITE),
            ('FONTNAME',      (0,0), (-1,-1), eb),
            ('FONTSIZE',      (0,0), (-1,-1), 12),
            ('ALIGN',         (0,0), (-1,-1), 'LEFT'),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING',   (0,0), (-1,-1), 10),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        return t

    def sec_header_ar(label):
        shaped = get_display(arabic_reshaper.reshape(str(label)))
        t = Table([[shaped]], colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), C_MGREEN),
            ('TEXTCOLOR',     (0,0), (-1,-1), C_WHITE),
            ('FONTNAME',      (0,0), (-1,-1), fb),
            ('FONTSIZE',      (0,0), (-1,-1), 13),
            ('ALIGN',         (0,0), (-1,-1), 'RIGHT'),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
            ('RIGHTPADDING',  (0,0), (-1,-1), 10),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        return t

    # ── Paragraph styles ──────────────────────────────────────────────
    styles = getSampleStyleSheet()
    title_style_en = ParagraphStyle('AITitleEN',
        fontName=eb, fontSize=22, leading=28,
        textColor=C_GREEN, alignment=1, spaceAfter=4)
    body_ltr = ParagraphStyle('AIBodyLTR',
        fontName=en, fontSize=11, leading=17,
        textColor=C_BLACK, alignment=4, spaceAfter=4, leftIndent=6)
    sub_style = ParagraphStyle('AISubHdr',
        fontName=en, fontSize=9, leading=13,
        textColor=C_GREY, alignment=1)

    # ── Page header / footer on every page ───────────────────────────
    from reportlab.lib.pagesizes import A4 as _A4
    _PW, _PH = _A4

    def _page_frame(canv, doc):
        canv.saveState()
        canv.setFillColor(C_GREEN)
        canv.rect(0.5*inch, _PH - 0.65*inch, 7.5*inch, 0.45*inch, fill=1, stroke=0)
        canv.setFillColor(C_WHITE)
        canv.setFont(eb, 9)
        canv.drawCentredString(_PW / 2, _PH - 0.38*inch,
            'University of Baghdad  \u00b7  College of Physical Education and Sports Sciences')
        canv.setStrokeColor(C_GREEN)
        canv.setLineWidth(1.2)
        canv.line(0.5*inch, 0.55*inch, 8.0*inch, 0.55*inch)
        canv.setFont(en, 8)
        canv.setFillColor(C_GREY)
        canv.drawString(0.5*inch, 0.38*inch,
            '\u00a9 Abbas Hussein Khaleefah  |  University of Baghdad')
        canv.drawRightString(8.0*inch, 0.38*inch, f'Page {doc.page}')
        canv.restoreState()

    # ── Document ──────────────────────────────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        topMargin=0.85*inch, bottomMargin=0.75*inch,
        leftMargin=0.75*inch, rightMargin=0.75*inch)

    sections = [
        ('Objective',                'الهدف',                   'objective'),
        ('Tools Required',           'الأدوات المطلوبة',        'tools'),
        ('Field Setup',              'إعداد الملعب',            'field_setup'),
        ('Procedure',                'الإجراءات',               'procedure'),
        ('Performance Instructions', 'تعليمات الأداء',          'performance_instructions'),
        ('Scoring Method',           'طريقة التسجيل',           'scoring_method'),
        ('Variables Measured',       'المتغيرات المقاسة',       'variables_measured'),
        ('Important Notes',          'ملاحظات مهمة',            'notes'),
        ('Academic Description',     'الوصف الأكاديمي',        'academic_description'),
        ('Practical Description',    'الوصف العملي للمدربين',  'practical_description'),
    ]

    story = []
    content_is_arabic = False

    # Title
    test_name = test.get('test_name', 'Football Test')
    story.append(Spacer(1, 8))
    if has_arabic(test_name):
        story.extend(ar_lines(test_name, size=22, rl_align='CENTER', rl_color=C_GREEN, bold=True))
    else:
        story.append(Paragraph(test_name, title_style_en))

    # Decorative double rule under title
    story.append(Spacer(1, 6))
    rule = Table([['']], colWidths=[CONTENT_W])
    rule.setStyle(TableStyle([
        ('LINEABOVE',     (0,0), (-1,-1), 2.5, C_GREEN),
        ('LINEBELOW',     (0,0), (-1,-1), 0.8, C_MGREEN),
        ('TOPPADDING',    (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(rule)
    story.append(Spacer(1, 10))

    # Info box
    gen_date = datetime.now().strftime('%Y-%m-%d  %H:%M')
    meta = Table([
        ['Sport',        'Football'],
        ['Date',         gen_date],
        ['Institution',  'University of Baghdad'],
        ['College',      'Physical Education & Sports Sciences'],
    ], colWidths=[1.4*inch, 5.1*inch])
    meta.setStyle(TableStyle([
        ('FONTNAME',      (0,0), (0,-1), eb),
        ('FONTNAME',      (1,0), (1,-1), en),
        ('FONTSIZE',      (0,0), (-1,-1), 10),
        ('TEXTCOLOR',     (0,0), (0,-1), C_MGREEN),
        ('TEXTCOLOR',     (1,0), (1,-1), C_BLACK),
        ('ROWBACKGROUNDS',(0,0), (-1,-1), [C_LGREEN, C_WHITE]),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('ALIGN',         (0,0), (-1,-1), 'LEFT'),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('BOX',           (0,0), (-1,-1), 1, C_GREEN),
        ('GRID',          (0,0), (-1,-1), 0.3, colors.HexColor('#c8e6c9')),
    ]))
    story.append(meta)
    story.append(Spacer(1, 14))

    # Sections
    for eng_label, ar_label, key in sections:
        val = test.get(key, '')
        if not val:
            continue
        content_is_arabic = has_arabic(str(val))
        story.append(Spacer(1, 6))
        story.append(sec_header_ar(ar_label) if content_is_arabic else sec_header_en(eng_label))
        story.append(Spacer(1, 5))
        for line in str(val).split('\n'):
            s = line.strip()
            if not s:
                continue
            if content_is_arabic:
                story.extend(ar_lines(s, size=11, rl_align='RIGHT'))
            else:
                story.append(Paragraph(s, body_ltr))
        story.append(Spacer(1, 4))

    # Diagram
    diagram_added = False
    if diagram_data_url and ('base64,' in diagram_data_url):
        try:
            _hdr, b64data = diagram_data_url.split(',', 1)
            img_data = base64.b64decode(b64data)
            img_buffer = io.BytesIO(img_data)
            story.append(PageBreak())
            story.append(sec_header_ar('مخطط الاختبار') if content_is_arabic else sec_header_en('Test Layout Diagram'))
            story.append(Spacer(1, 12))
            story.append(RLImage(img_buffer, width=6.5*inch, height=4*inch))
            story.append(Spacer(1, 10))
            diagram_added = True
        except Exception as e:
            logging.error(f"Diagram image error in PDF: {e}")

    # Results table
    story.append(PageBreak())
    story.append(sec_header_ar('جدول النتائج') if content_is_arabic else sec_header_en('Sample Results Table'))
    story.append(Spacer(1, 10))
    t_data = [['No.', 'Player Name', 'Attempt 1', 'Attempt 2', 'Attempt 3', 'Best', 'Score', 'Level']]
    for i in range(1, 16):
        t_data.append([str(i), '', '', '', '', '', '', ''])
    t = Table(t_data, colWidths=[0.35*inch, 1.6*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.7*inch, 0.65*inch, 0.8*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), C_GREEN),
        ('TEXTCOLOR',     (0,0), (-1,0), C_WHITE),
        ('FONTNAME',      (0,0), (-1,0), eb),
        ('FONTNAME',      (0,1), (-1,-1), en),
        ('FONTSIZE',      (0,0), (-1,-1), 9),
        ('ALIGN',         (0,0), (-1,-1), 'CENTER'),
        ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#c8e6c9')),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [C_WHITE, C_LGREEN]),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
    ]))
    story.append(t)

    doc.build(story, onFirstPage=_page_frame, onLaterPages=_page_frame)
    buffer.seek(0)
    raw_name = test.get('test_name', 'sports_test')
    ascii_name = unicodedata.normalize('NFKD', raw_name).encode('ascii', 'ignore').decode('ascii')
    ascii_name = ''.join(c if c.isalnum() or c in ' _-' else '_' for c in ascii_name).strip().replace(' ', '_').lower()[:40] or 'sports_test'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename_ascii = f"football_test_{ascii_name}_{timestamp}.pdf"
    filename_utf8 = urllib.parse.quote(f"football_test_{raw_name.replace(' ', '_')}_{timestamp}.pdf")
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f"attachment; filename=\"{filename_ascii}\"; filename*=UTF-8''{filename_utf8}"}
    )


@app.route('/ai-test-generator/save', methods=['POST'])
@login_required
def ai_save_test():
    data = request.get_json()
    test = data.get('test', {})
    if not test or not test.get('test_name'):
        return jsonify({'error': 'No test data to save'}), 400
    saved = SavedTest(
        user_id=current_user.id,
        test_name=test.get('test_name', 'Unnamed Test'),
        test_data=json.dumps(test, ensure_ascii=False)
    )
    db.session.add(saved)
    db.session.commit()
    return jsonify({'success': True, 'id': saved.id, 'name': saved.test_name})


@app.route('/ai-test-generator/saved', methods=['GET'])
@login_required
def ai_list_saved_tests():
    tests = SavedTest.query.filter_by(user_id=current_user.id).order_by(SavedTest.created_at.desc()).all()
    return jsonify({'tests': [{'id': t.id, 'name': t.test_name, 'created_at': t.created_at.strftime('%Y-%m-%d %H:%M')} for t in tests]})


@app.route('/ai-test-generator/saved/<int:test_id>', methods=['GET'])
@login_required
def ai_load_saved_test(test_id):
    saved = SavedTest.query.filter_by(id=test_id, user_id=current_user.id).first_or_404()
    return jsonify({'success': True, 'test': json.loads(saved.test_data), 'name': saved.test_name})


@app.route('/ai-test-generator/saved/<int:test_id>/delete', methods=['POST'])
@login_required
def ai_delete_saved_test(test_id):
    saved = SavedTest.query.filter_by(id=test_id, user_id=current_user.id).first_or_404()
    db.session.delete(saved)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/ai-test-generator/translate', methods=['POST'])
@login_required
def ai_translate_test():
    data = request.get_json()
    test = data.get('test', {})
    if not test:
        return jsonify({'error': 'No test data provided'}), 400

    fields_to_translate = ['test_name', 'objective', 'tools', 'field_setup', 'procedure',
                           'performance_instructions', 'scoring_method', 'variables_measured',
                           'notes', 'academic_description', 'practical_description']

    text_to_translate = {}
    for f in fields_to_translate:
        if test.get(f):
            text_to_translate[f] = test[f]

    prompt = f"""Translate the following football test fields to Arabic. Return ONLY a valid JSON object with the same keys but Arabic values. Use proper academic Arabic suitable for a university sports science context.

Fields to translate:
{json.dumps(text_to_translate, ensure_ascii=False)}

Return ONLY the JSON object, no extra text."""

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a professional Arabic translator specializing in sports science. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=3000,
            temperature=0.3
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        raw = raw.strip()
        translated = json.loads(raw)
        merged = dict(test)
        merged.update(translated)
        return jsonify({'success': True, 'test': merged})
    except json.JSONDecodeError as e:
        logging.error(f"JSON parse error from AI translation: {e}")
        return jsonify({'error': 'Translation could not be parsed. Please try again.'}), 500
    except Exception as e:
        logging.error(f"Translation error: {e}")
        return jsonify({'error': f'Translation failed: {str(e)}'}), 500


@app.route('/export/database')
@login_required
def export_full_database():
    """Export all database tables for the current data_year into one Excel workbook."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    DY = current_user.data_year

    wb = Workbook()
    wb.remove(wb.active)  # remove default blank sheet

    # ── Style helpers ─────────────────────────────────────────────────
    HDR_FILL   = PatternFill("solid", fgColor="1B5E20")
    HDR_FONT   = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    HDR_ALIGN  = Alignment(horizontal="center", vertical="center", wrap_text=True)
    TITLE_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=13)
    TITLE_FILL = PatternFill("solid", fgColor="2E7D32")
    EVEN_FILL  = PatternFill("solid", fgColor="E8F5E9")
    ODD_FILL   = PatternFill("solid", fgColor="FFFFFF")
    BODY_FONT  = Font(name="Calibri", size=10)
    CENTER     = Alignment(horizontal="center", vertical="center")
    LEFT       = Alignment(horizontal="left", vertical="center")
    THIN_SIDE  = Side(style="thin", color="C8E6C9")
    THIN       = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

    def add_sheet(name, headers, rows, col_widths=None):
        ws = wb.create_sheet(title=name)
        # Title row
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        title_cell = ws.cell(row=1, column=1, value=f"{name}  —  Data Year: {DY}")
        title_cell.font   = TITLE_FONT
        title_cell.fill   = TITLE_FILL
        title_cell.alignment = CENTER
        ws.row_dimensions[1].height = 24
        # Header row
        for col_i, h in enumerate(headers, 1):
            c = ws.cell(row=2, column=col_i, value=h)
            c.font      = HDR_FONT
            c.fill      = HDR_FILL
            c.alignment = HDR_ALIGN
            c.border    = THIN
        ws.row_dimensions[2].height = 20
        # Data rows
        for row_i, row in enumerate(rows, 3):
            fill = EVEN_FILL if row_i % 2 == 0 else ODD_FILL
            for col_i, val in enumerate(row, 1):
                c = ws.cell(row=row_i, column=col_i, value=val)
                c.font      = BODY_FONT
                c.fill      = fill
                c.border    = THIN
                c.alignment = CENTER if col_i != 2 else LEFT
        # Column widths
        if col_widths:
            for i, w in enumerate(col_widths, 1):
                ws.column_dimensions[get_column_letter(i)].width = w
        else:
            for col_i in range(1, len(headers) + 1):
                ws.column_dimensions[get_column_letter(col_i)].width = 18
        # Freeze header rows
        ws.freeze_panes = "A3"
        return ws

    # ── 1. Students ───────────────────────────────────────────────────
    students = Student.query.filter_by(data_year=DY).order_by(
        Student.academic_year, Student.section, Student.name).all()
    add_sheet(
        "Students",
        ["#", "Student ID", "Full Name", "Acad. Year", "Section",
         "Email", "Phone", "Attendance %", "Final Grade", "Date Added"],
        [
            (i, s.student_id, s.name, s.academic_year, s.section,
             s.email or '', s.phone or '',
             s.get_attendance_percentage(),
             s.get_final_grade(),
             s.date_created.strftime('%Y-%m-%d') if s.date_created else '')
            for i, s in enumerate(students, 1)
        ],
        col_widths=[5, 16, 28, 10, 10, 26, 14, 14, 13, 14]
    )

    # ── 2. Grades ─────────────────────────────────────────────────────
    grades_q = (db.session.query(Grade, Student)
                .join(Student, Grade.student_id == Student.id)
                .filter(Student.data_year == DY)
                .order_by(Student.academic_year, Student.section, Student.name)
                .all())
    add_sheet(
        "Grades",
        ["#", "Student Name", "Student ID", "Year", "Section",
         "S1 Theory", "S1 Practical", "S1 Attend",
         "Mid Exam",
         "S2 Theory", "S2 Practical", "S2 Attend",
         "Final Theory", "Final Practical",
         "Total /100", "Pass/Fail"],
        [
            (i, st.name, st.student_id, st.academic_year, st.section,
             g.semester1_theory or 0, g.semester1_practical or 0, g.semester1_attendance or 0,
             g.midyear_exam or 0,
             g.semester2_theory or 0, g.semester2_practical or 0, g.semester2_attendance or 0,
             g.final_theory or 0, g.final_practical or 0,
             g.get_total_grade(),
             'Pass' if g.is_passed() else 'Fail')
            for i, (g, st) in enumerate(grades_q, 1)
        ],
        col_widths=[5, 28, 14, 8, 8, 10, 12, 10, 10, 10, 12, 10, 13, 15, 12, 10]
    )

    # ── 3. Attendance ─────────────────────────────────────────────────
    att_q = (db.session.query(Attendance, Student)
             .join(Student, Attendance.student_id == Student.id)
             .filter(Student.data_year == DY)
             .order_by(Student.academic_year, Student.section, Attendance.date, Student.name)
             .all())
    add_sheet(
        "Attendance",
        ["#", "Student Name", "Student ID", "Year", "Section", "Date", "Status", "Notes"],
        [
            (i, st.name, st.student_id, st.academic_year, st.section,
             a.date.strftime('%Y-%m-%d') if a.date else '',
             'Present' if a.present else 'Absent',
             a.notes or '')
            for i, (a, st) in enumerate(att_q, 1)
        ],
        col_widths=[5, 28, 14, 8, 8, 14, 10, 28]
    )

    # ── 4. Curriculum ─────────────────────────────────────────────────
    currs = Curriculum.query.filter_by(data_year=DY).order_by(
        Curriculum.academic_year, Curriculum.semester, Curriculum.week_number).all()
    add_sheet(
        "Curriculum",
        ["#", "Topic", "Year", "Semester", "Week", "Theory Hrs", "Practical Hrs", "Description", "Objectives"],
        [
            (i, c.topic, c.academic_year, c.semester or '', c.week_number or '',
             c.theory_hours or 0, c.practical_hours or 0,
             c.description or '', c.objectives or '')
            for i, c in enumerate(currs, 1)
        ],
        col_widths=[5, 32, 8, 10, 8, 12, 14, 36, 36]
    )

    # ── 5. Schedule ───────────────────────────────────────────────────
    scheds = Schedule.query.filter_by(data_year=DY).order_by(
        Schedule.academic_year, Schedule.section, Schedule.day_of_week, Schedule.start_time).all()
    add_sheet(
        "Schedule",
        ["#", "Year", "Section", "Day", "Start", "End", "Venue", "Type", "Instructor", "Notes"],
        [
            (i, s.academic_year, s.section, s.day_of_week,
             s.start_time.strftime('%H:%M') if s.start_time else '',
             s.end_time.strftime('%H:%M') if s.end_time else '',
             s.venue or '', s.class_type or '', s.instructor or '', s.notes or '')
            for i, s in enumerate(scheds, 1)
        ],
        col_widths=[5, 8, 8, 12, 10, 10, 22, 14, 24, 28]
    )

    # ── 6. Summary ───────────────────────────────────────────────────
    ws_sum = wb.create_sheet(title="Summary", index=0)
    ws_sum.column_dimensions["A"].width = 36
    ws_sum.column_dimensions["B"].width = 18
    summary_rows = [
        ("Export Date", datetime.now().strftime('%Y-%m-%d  %H:%M')),
        ("Data Year", DY),
        ("Exported By", current_user.username),
        ("", ""),
        ("Total Students", len(students)),
        ("Total Grade Records", len(grades_q)),
        ("Total Attendance Records", len(att_q)),
        ("Total Curriculum Entries", len(currs)),
        ("Total Schedule Entries", len(scheds)),
    ]
    ws_sum.merge_cells("A1:B1")
    t = ws_sum.cell(row=1, column=1,
        value="University of Baghdad — College of Physical Education and Sports Sciences")
    t.font      = TITLE_FONT
    t.fill      = TITLE_FILL
    t.alignment = CENTER
    ws_sum.row_dimensions[1].height = 28
    for ri, (label, val) in enumerate(summary_rows, 2):
        c_lbl = ws_sum.cell(row=ri, column=1, value=label)
        c_val = ws_sum.cell(row=ri, column=2, value=val)
        c_lbl.font = Font(name="Calibri", bold=True, size=11)
        c_val.font = Font(name="Calibri", size=11)
        if label:
            c_lbl.fill = EVEN_FILL if ri % 2 == 0 else ODD_FILL
            c_val.fill = EVEN_FILL if ri % 2 == 0 else ODD_FILL
        c_lbl.border = THIN
        c_val.border = THIN

    # ── Output ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = f"database_export_{DY}_{ts}.xlsx"
    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'}
    )


from models import GradeScheme, GradeComponent, GradeSubComponent, GradeEntry, SystemSetting
from forms import GradeSchemeForm, GradeComponentForm, GradeSubComponentForm, GeneralSettingsForm

# General Settings Route
@app.route('/settings/general', methods=['GET', 'POST'])
@login_required
def general_settings():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    current_openai_key = SystemSetting.get('openai_api_key', '')
    current_gemini_key = SystemSetting.get('gemini_api_key', '')
    current_provider = SystemSetting.get('ai_provider', 'openai')
    
    form = GeneralSettingsForm()
    
    if form.validate_on_submit():
        openai_key = form.openai_api_key.data
        gemini_key = form.gemini_api_key.data
        provider = form.ai_provider.data
        
        # Only update keys if they aren't the masked version
        if openai_key and '*' not in openai_key:
            SystemSetting.set('openai_api_key', openai_key, 'OpenAI API Key')
        if gemini_key and '*' not in gemini_key:
            SystemSetting.set('gemini_api_key', gemini_key, 'Gemini API Key')
            
        SystemSetting.set('ai_provider', provider, 'Preferred AI Provider')
        flash('General settings updated successfully!', 'success')
        return redirect(url_for('general_settings'))
    
    # Pre-fill form
    if not form.is_submitted():
        if current_openai_key:
            form.openai_api_key.data = current_openai_key[:6] + '*' * (len(current_openai_key)-6) if len(current_openai_key)>6 else '********'
        if current_gemini_key:
            form.gemini_api_key.data = current_gemini_key[:6] + '*' * (len(current_gemini_key)-6) if len(current_gemini_key)>6 else '********'
        form.ai_provider.data = current_provider
        
    return render_template('settings/general.html', form=form)

@app.route('/settings/test-ai-key', methods=['POST'])
@login_required
def test_ai_key():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    provider = data.get('provider')
    api_key = data.get('api_key', '').strip()
    
    if not api_key or '*' in api_key:
        # Fallback to stored key if stars are provided
        from models import SystemSetting
        if provider == 'openai':
            api_key = SystemSetting.get('openai_api_key')
        else:
            api_key = SystemSetting.get('gemini_api_key')
            
    if not api_key:
        return jsonify({'success': False, 'message': 'No key provided to test.'})
        
    try:
        if provider == 'openai':
            if not api_key.startswith('sk-'):
                return jsonify({'success': False, 'message': 'Invalid format. OpenAI keys usually start with "sk-".'})
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            # Simple list models to test key
            client.models.list()
        else:
            if not (api_key.startswith('AIza') or len(api_key) > 30):
                return jsonify({'success': False, 'message': 'Invalid format. Gemini keys usually start with "AIza" and are ~40 chars.'})
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            list(genai.list_models()) # Test by listing models
            
        return jsonify({'success': True, 'message': f'Success! Your {provider} key is valid and working.'})
    except Exception as e:
        err_msg = str(e)
        if 'API_KEY_INVALID' in err_msg:
            err_msg = "Invalid API Key. Please check for extra spaces or typos."
        return jsonify({'success': False, 'message': f'Test Failed: {err_msg}'})

# Grade System Configuration Routes
@app.route('/settings/grade-system')
@login_required
def grade_system_list():
    schemes = GradeScheme.query.filter_by(user_id=current_user.id, data_year=current_user.data_year).all()
    # Get subjects from curriculum
    subjects = Curriculum.query.filter_by(user_id=current_user.id, data_year=current_user.data_year).with_entities(Curriculum.id, Curriculum.topic).distinct().all()
    return render_template('settings/grade_schemes.html', schemes=schemes, subjects=subjects)

@app.route('/settings/grade-system/add', methods=['GET', 'POST'])
@login_required
def add_grade_scheme():
    form = GradeSchemeForm()
    if form.validate_on_submit():
        scheme = GradeScheme(
            user_id=current_user.id,
            name=form.name.data,
            data_year=current_user.data_year,
            total_marks=form.total_marks.data
        )
        db.session.add(scheme)
        db.session.commit()
        flash(f'Grade scheme "{scheme.name}" created! Now add components.', 'success')
        return redirect(url_for('view_grade_scheme', scheme_id=scheme.id))
    return render_template('settings/grade_scheme_form.html', form=form, title="Create Grade Scheme")

@app.route('/settings/grade-system/<int:scheme_id>', methods=['GET', 'POST'])
@login_required
def view_grade_scheme(scheme_id):
    scheme = GradeScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('grade_system_list'))
    
    if request.method == 'POST':
        new_name = request.form.get('scheme_name')
        if new_name:
            scheme.name = new_name
            db.session.commit()
            flash(f'Scheme renamed to "{new_name}"', 'success')
            return redirect(url_for('view_grade_scheme', scheme_id=scheme_id))

    comp_form = GradeComponentForm()
    sub_form = GradeSubComponentForm()
    
    return render_template('settings/grade_scheme_detail.html', 
                          scheme=scheme, 
                          comp_form=comp_form, 
                          sub_form=sub_form)

@app.route('/settings/grade-system/<int:scheme_id>/component/add', methods=['POST'])
@login_required
def add_grade_component(scheme_id):
    scheme = GradeScheme.query.get_or_404(scheme_id)
    form = GradeComponentForm()
    if form.validate_on_submit():
        component = GradeComponent(
            scheme_id=scheme.id,
            name=form.name.data,
            max_marks=form.max_marks.data,
            order=form.order.data
        )
        db.session.add(component)
        db.session.commit()
        flash('Component added successfully.', 'success')
    return redirect(url_for('view_grade_scheme', scheme_id=scheme_id))

@app.route('/settings/grade-system/component/<int:comp_id>/edit', methods=['POST'])
@login_required
def edit_grade_component(comp_id):
    component = GradeComponent.query.get_or_404(comp_id)
    if component.scheme.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('grade_system_list'))
    
    name = request.form.get('name')
    max_marks = request.form.get('max_marks', type=float)
    
    if name and max_marks:
        component.name = name
        component.max_marks = max_marks
        db.session.commit()
        flash('Component updated.', 'success')
    return redirect(url_for('view_grade_scheme', scheme_id=component.scheme_id))

@app.route('/settings/grade-system/component/<int:comp_id>/delete', methods=['POST'])
@login_required
def delete_grade_component(comp_id):
    component = GradeComponent.query.get_or_404(comp_id)
    scheme_id = component.scheme_id
    if component.scheme.user_id != current_user.id:
        flash('Access denied.', 'error')
    else:
        db.session.delete(component)
        db.session.commit()
        flash('Component deleted.', 'info')
    return redirect(url_for('view_grade_scheme', scheme_id=scheme_id))

@app.route('/settings/grade-system/component/<int:comp_id>/sub/add', methods=['POST'])
@login_required
def add_grade_sub_component(comp_id):
    component = GradeComponent.query.get_or_404(comp_id)
    form = GradeSubComponentForm()
    if form.validate_on_submit():
        sub = GradeSubComponent(
            component_id=component.id,
            name=form.name.data,
            max_marks=form.max_marks.data,
            type=form.type.data,
            order=form.order.data
        )
        db.session.add(sub)
        db.session.commit()
        flash('Sub-category added.', 'success')
    return redirect(url_for('view_grade_scheme', scheme_id=component.scheme_id))

@app.route('/settings/grade-system/sub-component/<int:sub_id>/edit', methods=['POST'])
@login_required
def edit_grade_sub_component(sub_id):
    sub = GradeSubComponent.query.get_or_404(sub_id)
    if sub.component.scheme.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('grade_system_list'))
    
    name = request.form.get('name')
    max_marks = request.form.get('max_marks', type=float)
    comp_type = request.form.get('type')
    
    if name and max_marks:
        sub.name = name
        sub.max_marks = max_marks
        sub.type = comp_type
        db.session.commit()
        flash('Sub-category updated.', 'success')
    return redirect(url_for('view_grade_scheme', scheme_id=sub.component.scheme_id))

@app.route('/settings/grade-system/sub-component/<int:sub_id>/delete', methods=['POST'])
@login_required
def delete_grade_sub_component(sub_id):
    sub = GradeSubComponent.query.get_or_404(sub_id)
    scheme_id = sub.component.scheme_id
    if sub.component.scheme.user_id != current_user.id:
        flash('Access denied.', 'error')
    else:
        db.session.delete(sub)
        db.session.commit()
        flash('Sub-category deleted.', 'info')
    return redirect(url_for('view_grade_scheme', scheme_id=scheme_id))

@app.route('/settings/grade-system/scheme/<int:scheme_id>/delete', methods=['POST'])
@login_required
def delete_grade_scheme(scheme_id):
    scheme = GradeScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id:
        flash('Access denied.', 'error')
    else:
        db.session.delete(scheme)
        db.session.commit()
        flash('Grade scheme deleted.', 'info')
    return redirect(url_for('grade_system_list'))

@app.route('/settings/grade-system/scheme/<int:scheme_id>/activate', methods=['POST'])
@login_required
def activate_grade_scheme(scheme_id):
    """Set a scheme as default and migrate legacy grades ONLY to Semester 1"""
    scheme = GradeScheme.query.get_or_404(scheme_id)
    if scheme.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('grade_system_list'))
    
    # Reset other defaults for this year
    GradeScheme.query.filter_by(user_id=current_user.id, data_year=current_user.data_year).update({"is_default": False})
    scheme.is_default = True
    
    # 1. Clear previous dynamic grades for this scheme to avoid confusion from previous errors
    for comp in scheme.components:
        for sub in comp.sub_components:
            GradeEntry.query.filter_by(sub_component_id=sub.id).delete()
    
    # 2. Find ONLY sub-components in the FIRST component (Semester 1)
    sub_map = {}
    if scheme.components:
        first_comp = scheme.components[0]
        for sub in first_comp.sub_components:
            name_lower = sub.name.lower()
            if "theory" in name_lower and 'theory' not in sub_map:
                sub_map['theory'] = sub.id
            if "practical" in name_lower and 'practical' not in sub_map:
                sub_map['practical'] = sub.id
            if "attendance" in name_lower and 'attendance' not in sub_map:
                sub_map['attendance'] = sub.id
    
    # 3. Migration Logic
    students = student_scope().all()
    count = 0
    
    for student in students:
        legacy_grade = Grade.query.filter_by(student_id=student.id).first()
        if not legacy_grade:
            continue
            
        # Migrate Mid-Year Exam -> Theory
        if 'theory' in sub_map and (legacy_grade.midyear_exam or 0) > 0:
            entry = GradeEntry(student_id=student.id, sub_component_id=sub_map['theory'], value=legacy_grade.midyear_exam)
            db.session.add(entry)
            
        # Migrate Semester 1 Practical -> Practical
        if 'practical' in sub_map and (legacy_grade.semester1_practical or 0) > 0:
            entry = GradeEntry(student_id=student.id, sub_component_id=sub_map['practical'], value=legacy_grade.semester1_practical)
            db.session.add(entry)
            
        # Migrate Semester 1 Attendance -> Attendance
        if 'attendance' in sub_map and (legacy_grade.semester1_attendance or 0) > 0:
            entry = GradeEntry(student_id=student.id, sub_component_id=sub_map['attendance'], value=legacy_grade.semester1_attendance)
            db.session.add(entry)
        
        count += 1
        
    db.session.commit()
    flash(f'Scheme "{scheme.name}" activated. {count} students migrated to Semester 1.', 'success')
    return redirect(url_for('grade_system_list'))

@app.route('/settings/grade-system/component/<int:comp_id>/finalize', methods=['POST'])
@login_required
def toggle_finalize_component(comp_id):
    comp = GradeComponent.query.get_or_404(comp_id)
    if comp.scheme.user_id != current_user.id:
        flash('Access denied.', 'error')
    else:
        comp.is_finalized = not comp.is_finalized
        db.session.commit()
        status = "Finalized" if comp.is_finalized else "Re-opened for editing"
        flash(f'Component "{comp.name}" {status}.', 'success')
    return redirect(url_for('view_grade_scheme', scheme_id=comp.scheme_id))

@app.route('/grades/student/<int:student_id>/scheme/<int:scheme_id>', methods=['GET', 'POST'])
@login_required
def edit_student_grades_dynamic(student_id, scheme_id):
    student = student_scope().filter_by(id=student_id).first_or_404()
    scheme = GradeScheme.query.get_or_404(scheme_id)
    
    if request.method == 'POST':
        for comp in scheme.components:
            for sub in comp.sub_components:
                key = f"grade_{sub.id}"
                val_str = request.form.get(key)
                if val_str is not None:
                    try:
                        val = float(val_str)
                    except ValueError:
                        val = 0
                    
                    entry = GradeEntry.query.filter_by(student_id=student.id, sub_component_id=sub.id).first()
                    if not entry:
                        entry = GradeEntry(student_id=student.id, sub_component_id=sub.id)
                        db.session.add(entry)
                    entry.value = val
        
        db.session.commit()
        flash(f'Grades updated for {student.name}', 'success')
        return redirect(url_for('grade_list', year=student.academic_year, section=student.section))

    # Get existing entries
    existing_entries = {}
    for comp in scheme.components:
        for sub in comp.sub_components:
            entry = GradeEntry.query.filter_by(student_id=student.id, sub_component_id=sub.id).first()
            existing_entries[sub.id] = entry.value if entry else 0

    return render_template('grades/edit_student_dynamic.html', student=student, scheme=scheme, existing_entries=existing_entries)


    return redirect(url_for('grade_system_list'))


@app.route('/grades/dynamic/<int:scheme_id>', methods=['GET', 'POST'])
@login_required
def dynamic_grade_entry(scheme_id):
    scheme = GradeScheme.query.get_or_404(scheme_id)
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    
    if not year or not section:
        flash('Please select year and section first.', 'warning')
        return redirect(url_for('grade_list'))
        
    students = student_scope().filter_by(academic_year=year, section=section).all()
    
    # Pre-calculate attendance grades for all students
    attendance_grades = {}
    for student in students:
        for comp in scheme.components:
            for sub in comp.sub_components:
                if sub.type == 'attendance':
                    # Calculate attendance marks: (Present / Total Recorded) * sub.max_marks
                    # Get total attendance records in the system for this student
                    total_records = Attendance.query.filter_by(student_id=student.id).count()
                    present_records = Attendance.query.filter_by(student_id=student.id, present=True).count()
                    
                    if total_records > 0:
                        calc_grade = round((present_records / total_records) * sub.max_marks)
                    else:
                        calc_grade = sub.max_marks # Assume full marks if no attendance recorded yet
                    
                    attendance_grades[f"{student.id}_{sub.id}"] = calc_grade

    if request.method == 'POST':
        # Save grades
        for student in students:
            for comp in scheme.components:
                for sub in comp.sub_components:
                    key = f"grade_{student.id}_{sub.id}"
                    val_str = request.form.get(key)
                    
                    if val_str is not None:
                        try:
                            val = float(val_str)
                        except ValueError:
                            val = 0
                            
                        # Save to GradeEntry
                        entry = GradeEntry.query.filter_by(student_id=student.id, sub_component_id=sub.id).first()
                        if not entry:
                            entry = GradeEntry(student_id=student.id, sub_component_id=sub.id)
                            db.session.add(entry)
                        
                        entry.value = val
        
        db.session.commit()
        flash('Grades saved successfully!', 'success')
        return redirect(url_for('dynamic_grade_entry', scheme_id=scheme_id, year=year, section=section))

    # Get existing entries
    existing_entries = {}
    for student in students:
        for comp in scheme.components:
            for sub in comp.sub_components:
                entry = GradeEntry.query.filter_by(student_id=student.id, sub_component_id=sub.id).first()
                if entry:
                    existing_entries[f"{student.id}_{sub.id}"] = entry.value
                elif sub.type == 'attendance':
                    existing_entries[f"{student.id}_{sub.id}"] = attendance_grades.get(f"{student.id}_{sub.id}", 0)

    return render_template('grades/dynamic_entry.html', 
                          scheme=scheme, 
                          students=students, 
                          year=year, 
                          section=section,
                          existing_entries=existing_entries,
                          attendance_grades=attendance_grades)


# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
