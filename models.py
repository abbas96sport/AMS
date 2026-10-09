from core import db
from datetime import datetime
from sqlalchemy import func
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    data_year = db.Column(db.Integer, default=2025, nullable=False)
    academic_year = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    photo_filename = db.Column(db.String(255))
    qr_code = db.Column(db.String(64), unique=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __init__(self, **kwargs):
        super(Student, self).__init__(**kwargs)
        if not self.student_id:
            self.student_id = self.generate_student_id()
    
    def generate_student_id(self):
        """Generate auto-incrementing student ID in format STU-YYYY-NNNN"""
        from flask_login import current_user
        year = current_user.enrollment_year if hasattr(current_user, 'enrollment_year') and current_user.enrollment_year else datetime.now().year
        prefix_new = f"STU-{year}-"
        prefix_old = f"FB-{year}-"
        query = Student.query.filter(
            db.or_(
                Student.student_id.like(f'{prefix_new}%'),
                Student.student_id.like(f'{prefix_old}%')
            )
        )
        if hasattr(current_user, 'id') and current_user.id:
            query = query.filter(Student.user_id == current_user.id)
        last_student = query.order_by(Student.student_id.desc()).first()
        
        if last_student:
            number_part = int(last_student.student_id.split('-')[-1])
            next_number = number_part + 1
        else:
            next_number = 1
            
        return f"STU-{year}-{next_number:04d}"
    
    # Relationships
    attendances = db.relationship('Attendance', backref='student', lazy=True, cascade='all, delete-orphan')
    grades = db.relationship('Grade', backref='student', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Student {self.name} - Year {self.academic_year}{self.section}>'
    
    def get_attendance_percentage(self):
        result = db.session.query(
            func.count(Attendance.id).label('total'),
            func.sum(func.cast(Attendance.present, db.Integer)).label('present')
        ).filter(Attendance.student_id == self.id).first()
        
        total_classes = result.total if result and result.total else 0
        if total_classes == 0:
            return 100
        
        present_classes = result.present if result and result.present else 0
        return round((present_classes / total_classes) * 100, 2)
    
    def calculate_attendance_marks(self):
        """Calculate attendance marks out of 5 based on attendance percentage"""
        percentage = self.get_attendance_percentage()
        if percentage >= 90:
            return 5
        elif percentage >= 80:
            return 4
        elif percentage >= 70:
            return 3
        elif percentage >= 60:
            return 2
        elif percentage >= 50:
            return 1
        else:
            return 0
    
    def get_final_grade(self):
        """Calculate final grade out of 100"""
        grade = Grade.query.filter_by(student_id=self.id).first()
        if not grade:
            return 0
        
        total = 0
        total += grade.semester1_theory or 0
        total += grade.semester1_practical or 0
        total += grade.semester1_attendance or 0
        total += grade.midyear_exam or 0
        total += grade.semester2_theory or 0
        total += grade.semester2_practical or 0
        total += grade.semester2_attendance or 0
        total += grade.final_theory or 0
        total += grade.final_practical or 0
        
        return total


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, nullable=True)
    date = db.Column(db.Date, nullable=False)
    present = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Attendance {self.student.name} - {self.date} - {"Present" if self.present else "Absent"}>'


class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, nullable=True)
    
    # First Semester (20 marks total)
    semester1_theory = db.Column(db.Float, default=0)
    semester1_practical = db.Column(db.Float, default=0)
    semester1_attendance = db.Column(db.Float, default=0)
    semester1_finalized = db.Column(db.Boolean, default=False)
    
    # Mid-Year Exam (10 marks)
    midyear_exam = db.Column(db.Float, default=0)
    
    # Second Semester (20 marks total)
    semester2_theory = db.Column(db.Float, default=0)
    semester2_practical = db.Column(db.Float, default=0)
    semester2_attendance = db.Column(db.Float, default=0)
    semester2_finalized = db.Column(db.Boolean, default=False)
    
    # Final Exam (50 marks total)
    final_theory = db.Column(db.Float, default=0)
    final_practical = db.Column(db.Float, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_semester1_total(self):
        return (self.semester1_theory or 0) + (self.semester1_practical or 0) + (self.semester1_attendance or 0)
    
    def get_semester2_total(self):
        return (self.semester2_theory or 0) + (self.semester2_practical or 0) + (self.semester2_attendance or 0)
    
    def get_final_total(self):
        return (self.final_theory or 0) + (self.final_practical or 0)
    
    def get_total_grade(self):
        return self.get_semester1_total() + (self.midyear_exam or 0) + self.get_semester2_total() + self.get_final_total()
    
    def is_passed(self):
        return self.get_total_grade() >= 50


class Curriculum(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    data_year = db.Column(db.Integer, default=2025, nullable=False)
    academic_year = db.Column(db.Integer, nullable=False)
    topic = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    week_number = db.Column(db.Integer)
    semester = db.Column(db.Integer)
    theory_hours = db.Column(db.Integer, default=0)
    practical_hours = db.Column(db.Integer, default=0)
    objectives = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Curriculum Year {self.academic_year} - {self.topic}>'


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    subject_id = db.Column(db.Integer, nullable=True)
    data_year = db.Column(db.Integer, default=2025, nullable=False)
    academic_year = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(1), nullable=False)
    day_of_week = db.Column(db.String(10), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    venue = db.Column(db.String(100))
    class_type = db.Column(db.String(20))
    instructor = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Schedule Year {self.academic_year}{self.section} - {self.day_of_week} {self.start_time}>'


class UserPermission(db.Model):
    """Stores permission settings for users (allowed years, sections)"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    permission_type = db.Column(db.String(20), nullable=False)
    permission_value = db.Column(db.String(50), nullable=False)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'permission_type', 'permission_value', name='unique_user_permission'),)


class AcademicTimeline(db.Model):
    """Represents an academic calendar year timeline (2025, 2026, etc.)"""
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    is_current = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    grade_scheme_id = db.Column(db.Integer, db.ForeignKey('grade_scheme.id'), nullable=True)
    
    # Relationship to the default grade scheme for this year (optional)
    grade_scheme = db.relationship('GradeScheme', foreign_keys=[grade_scheme_id])
    
    def __repr__(self):
        return f'<AcademicTimeline {self.year}>'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    full_name = db.Column(db.String(100))
    enrollment_year = db.Column(db.Integer, default=2025, nullable=False)
    data_year = db.Column(db.Integer, default=2025, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active_user = db.Column(db.Boolean, default=True)
    photo_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Subscription management
    subscription_expires_at = db.Column(db.Date, nullable=True)
    
    # Permission settings
    has_restricted_access = db.Column(db.Boolean, default=False)
    allowed_years = db.Column(db.String(50), nullable=True)
    allowed_sections = db.Column(db.String(100), nullable=True)
    allowed_subjects = db.Column(db.String(200), nullable=True)
    
    # Relationships
    students = db.relationship('Student', backref='owner', lazy=True)
    curricula = db.relationship('Curriculum', backref='owner', lazy=True)
    schedules = db.relationship('Schedule', backref='owner', lazy=True)
    permissions = db.relationship('UserPermission', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_allowed_years(self):
        """Get list of academic years this user can access"""
        if not self.has_restricted_access or self.is_admin:
            return None
        if not self.allowed_years:
            return None
        return [int(y.strip()) for y in self.allowed_years.split(',') if y.strip().isdigit()]
    
    def get_allowed_sections(self):
        """Get list of sections this user can access"""
        if not self.has_restricted_access or self.is_admin:
            return None
        if not self.allowed_sections:
            return None
        return [s.strip() for s in self.allowed_sections.split(',') if s.strip()]
    
    def can_access_year(self, year):
        """Check if user can access a specific academic year"""
        allowed = self.get_allowed_years()
        return allowed is None or year in allowed
    
    def can_access_section(self, section):
        """Check if user can access a specific section"""
        allowed = self.get_allowed_sections()
        return allowed is None or section in allowed
    
    def is_subscription_valid(self):
        """Check if user's subscription is still valid"""
        if self.is_admin:
            return True
        if self.subscription_expires_at is None:
            return True
        from datetime import date
        return self.subscription_expires_at >= date.today()
    
    def get_days_until_expiration(self):
        """Get number of days until subscription expires"""
        if self.subscription_expires_at is None:
            return None
        from datetime import date
        delta = self.subscription_expires_at - date.today()
        return delta.days
    
    def __repr__(self):
        return f'<User {self.username}>'


class SavedTest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    test_name = db.Column(db.String(200), nullable=False)
    test_data = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('saved_tests', lazy=True))

    def __repr__(self):
        return f'<SavedTest {self.test_name}>'


class GradeScheme(db.Model):
    """Overall grading scheme for a subject/year"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), default="Standard Scheme")
    subject_id = db.Column(db.Integer, nullable=True) # If null, applies to all subjects for this user
    data_year = db.Column(db.Integer, nullable=False)
    total_marks = db.Column(db.Float, default=100.0)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    components = db.relationship('GradeComponent', backref='scheme', lazy=True, cascade='all, delete-orphan', order_by='GradeComponent.order')

class GradeComponent(db.Model):
    """Major blocks like 'First Semester', 'Final Exam'"""
    id = db.Column(db.Integer, primary_key=True)
    scheme_id = db.Column(db.Integer, db.ForeignKey('grade_scheme.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    order = db.Column(db.Integer, default=0)
    is_finalized = db.Column(db.Boolean, default=False)
    
    sub_components = db.relationship('GradeSubComponent', backref='component', lazy=True, cascade='all, delete-orphan', order_by='GradeSubComponent.order')

class GradeSubComponent(db.Model):
    """Detailed items like 'Theory', 'Practical', 'Attendance'"""
    id = db.Column(db.Integer, primary_key=True)
    component_id = db.Column(db.Integer, db.ForeignKey('grade_component.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20), default='manual') # 'manual', 'attendance'
    order = db.Column(db.Integer, default=0)

class GradeEntry(db.Model):
    """Actual marks for a student per sub-component"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    sub_component_id = db.Column(db.Integer, db.ForeignKey('grade_sub_component.id'), nullable=False)
    value = db.Column(db.Float, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SystemSetting(db.Model):
    """Stores global system settings and configuration"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.String(200))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @staticmethod
    def get(key, default=None):
        setting = SystemSetting.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @staticmethod
    def set(key, value, description=None):
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = SystemSetting(key=key, value=value, description=description)
            db.session.add(setting)
        db.session.commit()
        return setting
