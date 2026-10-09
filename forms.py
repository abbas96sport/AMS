from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, IntegerField, SelectField, TextAreaField, FloatField, BooleanField, TimeField, DateField, PasswordField
from wtforms.validators import DataRequired, Email, Optional, NumberRange, Length, EqualTo
from datetime import date

class StudentForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    academic_year = SelectField('Academic Year', choices=[
        (1, '1st Year'), (2, '2nd Year'), (3, '3rd Year'), (4, '4th Year')
    ], coerce=int, validators=[DataRequired()])
    section = SelectField('Section', choices=[
        ('A', 'Section A'), ('B', 'Section B'), ('C', 'Section C'), ('D', 'Section D'),
        ('E', 'Section E'), ('F', 'Section F'), ('G', 'Section G'), ('H', 'Section H'),
        ('I', 'Section I'), ('J', 'Section J'), ('K', 'Section K'), ('L', 'Section L'),
        ('M', 'Section M'), ('N', 'Section N'), ('O', 'Section O'), ('P', 'Section P'),
        ('Q', 'Section Q'), ('R', 'Section R'), ('S', 'Section S'), ('T', 'Section T'),
        ('U', 'Section U'), ('V', 'Section V'), ('W', 'Section W'), ('X', 'Section X'),
        ('Y', 'Section Y'), ('Z', 'Section Z')
    ], validators=[DataRequired()])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    photo = FileField('Student Photo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])

class AttendanceForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=date.today)
    notes = TextAreaField('Notes', validators=[Optional()])

class GradeForm(FlaskForm):
    # First Semester
    semester1_theory = FloatField('Semester 1 - Theory (out of 5)', validators=[Optional(), NumberRange(min=0, max=5)])
    semester1_practical = FloatField('Semester 1 - Practical (out of 10)', validators=[Optional(), NumberRange(min=0, max=10)])
    
    # Mid-Year
    midyear_exam = FloatField('Mid-Year Exam (out of 10)', validators=[Optional(), NumberRange(min=0, max=10)])
    
    # Second Semester
    semester2_theory = FloatField('Semester 2 - Theory (out of 5)', validators=[Optional(), NumberRange(min=0, max=5)])
    semester2_practical = FloatField('Semester 2 - Practical (out of 10)', validators=[Optional(), NumberRange(min=0, max=10)])
    
    # Final Exam
    final_theory = FloatField('Final Theory Exam (out of 20)', validators=[Optional(), NumberRange(min=0, max=20)])
    final_practical = FloatField('Final Practical Exam (out of 30)', validators=[Optional(), NumberRange(min=0, max=30)])

class CurriculumForm(FlaskForm):
    academic_year = SelectField('Academic Year', choices=[(1, '1st Year'), (2, '2nd Year'), (3, '3rd Year'), (4, '4th Year')], coerce=int, validators=[DataRequired()])
    topic = StringField('Topic', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional()])
    week_number = IntegerField('Week Number', validators=[Optional(), NumberRange(min=1, max=16)])
    semester = SelectField('Semester', choices=[(1, 'First Semester'), (2, 'Second Semester')], coerce=int, validators=[DataRequired()])
    theory_hours = IntegerField('Theory Hours', validators=[Optional(), NumberRange(min=0, max=10)], default=0)
    practical_hours = IntegerField('Practical Hours', validators=[Optional(), NumberRange(min=0, max=10)], default=0)
    objectives = TextAreaField('Learning Objectives', validators=[Optional()])

class ScheduleForm(FlaskForm):
    academic_year = SelectField('Academic Year', choices=[(1, '1st Year'), (2, '2nd Year'), (3, '3rd Year'), (4, '4th Year')], coerce=int, validators=[DataRequired()])
    section = SelectField('Section', choices=[
        ('A', 'Section A'), ('B', 'Section B'), ('C', 'Section C'), ('D', 'Section D'),
        ('E', 'Section E'), ('F', 'Section F'), ('G', 'Section G'), ('H', 'Section H'),
        ('I', 'Section I'), ('J', 'Section J'), ('K', 'Section K'), ('L', 'Section L'),
        ('M', 'Section M'), ('N', 'Section N'), ('O', 'Section O'), ('P', 'Section P'),
        ('Q', 'Section Q'), ('R', 'Section R'), ('S', 'Section S'), ('T', 'Section T'),
        ('U', 'Section U'), ('V', 'Section V'), ('W', 'Section W'), ('X', 'Section X'),
        ('Y', 'Section Y'), ('Z', 'Section Z')
    ], validators=[DataRequired()])
    day_of_week = SelectField('Day of Week', choices=[
        ('Monday', 'Monday'), ('Tuesday', 'Tuesday'), ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'), ('Friday', 'Friday'), ('Saturday', 'Saturday'), ('Sunday', 'Sunday')
    ], validators=[DataRequired()])
    start_time = TimeField('Start Time', validators=[DataRequired()])
    end_time = TimeField('End Time', validators=[DataRequired()])
    venue = StringField('Venue', validators=[Optional(), Length(max=100)])
    class_type = SelectField('Class Type', choices=[('Theory', 'Theory'), ('Practical', 'Practical')], validators=[DataRequired()])
    instructor = StringField('Instructor', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('Notes', validators=[Optional()])

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class CreateUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    photo = FileField('Profile Picture', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    is_admin = BooleanField('Admin Privileges')
    data_year = SelectField('Assigned Data Year', coerce=int, validators=[DataRequired()])
    subscription_expires_at = DateField('Subscription Expiration Date', validators=[Optional()])
    has_restricted_access = BooleanField('Restrict Access')
    allowed_years = StringField('Allowed Years (comma-separated, e.g., 1,2,3)', validators=[Optional()])
    allowed_sections = StringField('Allowed Sections (comma-separated, e.g., A,B,C)', validators=[Optional()])

class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    password = PasswordField('New Password (leave blank to keep current)', validators=[Optional(), Length(min=8)])
    confirm_password = PasswordField('Confirm New Password', validators=[Optional(), EqualTo('password', message='Passwords must match')])
    photo = FileField('Profile Picture', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    data_year = SelectField('Assigned Data Year', coerce=int, validators=[DataRequired()])
    subscription_expires_at = DateField('Subscription Expiration Date', validators=[Optional()])
    has_restricted_access = BooleanField('Restrict Access')
    allowed_years = StringField('Allowed Years (comma-separated, e.g., 1,2,3)', validators=[Optional()])
    allowed_sections = StringField('Allowed Sections (comma-separated, e.g., A,B,C)', validators=[Optional()])


class GradeSchemeForm(FlaskForm):
    name = StringField('Scheme Name (e.g. 2025 Standard)', validators=[DataRequired(), Length(max=100)])
    total_marks = FloatField('Total Scale (e.g. 100)', default=100, validators=[DataRequired(), NumberRange(min=1)])

class GradeComponentForm(FlaskForm):
    name = StringField('Component Name (e.g. Semester 1)', validators=[DataRequired(), Length(max=100)])
    max_marks = FloatField('Weight in Total System', validators=[DataRequired(), NumberRange(min=0)])
    order = IntegerField('Order', default=0)

class GradeSubComponentForm(FlaskForm):
    name = StringField('Sub-Category Name (e.g. Theory)', validators=[DataRequired(), Length(max=100)])
    max_marks = FloatField('Weight in Component', validators=[DataRequired(), NumberRange(min=0)])
    type = SelectField('Type', choices=[('manual', 'Manual Entry'), ('attendance', 'Calculate from Attendance')], default='manual')
    order = IntegerField('Order', default=0)

class GeneralSettingsForm(FlaskForm):
    openai_api_key = PasswordField('OpenAI API Key', validators=[Optional(), Length(max=200)], render_kw={"placeholder": "sk-..."})
    gemini_api_key = PasswordField('Gemini API Key', validators=[Optional(), Length(max=200)], render_kw={"placeholder": "Enter Gemini Key"})
    ai_provider = SelectField('Preferred AI Provider', choices=[('openai', 'OpenAI (GPT-4o)'), ('gemini', 'Google Gemini')], default='openai')
