from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import csv
import os
import time
from datetime import datetime
import calendar
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)
app.secret_key = 'institutional_grade_high_security_key_string_hash_encoder'

# --- SMART PATH CHECKER FOR WINDOWS vs RENDER ---
IS_RENDER = os.path.exists('/etc/secrets/')

if IS_RENDER:
    DATA_DIR = '/opt/render/project/src/data/'
    UPLOAD_FOLDER = '/opt/render/project/src/data/static/uploads/'
    
    DATABASES = {
        'students.csv': ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'],
        # Added Password column to staff dataset framework
        'staff.csv': ['Emp_ID', 'Name', 'Department', 'Password'],
        'timetable.csv': ['ID', 'Day', 'Time', 'Subject', 'Teacher'],
        'assignments.csv': ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'],
        'attendance.csv': ['Roll_No', 'Date', 'Status'],
        'holidays.csv': ['Date']
    }
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    for file, columns in DATABASES.items():
        dest_path = os.path.join(DATA_DIR, file)
        source_path = os.path.join('/etc/secrets/', file)
        
        if not os.path.exists(dest_path):
            if os.path.exists(source_path) and os.path.getsize(source_path) > 0:
                shutil.copy(source_path, dest_path)
            else:
                with open(dest_path, mode='w', newline='', encoding='utf-8') as f:
                    csv.writer(f).writerow(columns)
else:
    DATA_DIR = ''
    UPLOAD_FOLDER = 'static/uploads/'
    DATABASES = {
        'students.csv': ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'],
        'staff.csv': ['Emp_ID', 'Name', 'Department', 'Password'],
        'timetable.csv': ['ID', 'Day', 'Time', 'Subject', 'Teacher'],
        'assignments.csv': ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'],
        'attendance.csv': ['Roll_No', 'Date', 'Status'],
        'holidays.csv': ['Date']
    }
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    for file, columns in DATABASES.items():
        if not os.path.exists(file):
            with open(file, mode='w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(columns)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_path(filename):
    if IS_RENDER:
        return os.path.join(DATA_DIR, filename)
    return filename

def safe_read_rows(filename, default_columns):
    path = get_file_path(filename)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    try:
        with open(path, mode='r', newline='', encoding='utf-8') as f:
            return [dict(row) for row in csv.DictReader(f)]
    except Exception:
        return []

def safe_write_rows(rows, filename, columns):
    path = get_file_path(filename)
    try:
        with open(path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row[k] for k in columns if k in row})
    except Exception:
        pass

def calculate_student_percentage(roll_no, current_month_days):
    h_rows = safe_read_rows('holidays.csv', ['Date'])
    holidays_set = {row['Date'] for row in h_rows if 'Date' in row and row['Date']}
    active_open_days = [d for d in current_month_days if d not in holidays_set]
    total_working_days = len(active_open_days)
    
    attended_count = 0
    att_rows = safe_read_rows('attendance.csv', ['Roll_No', 'Date', 'Status'])
    if att_rows and total_working_days > 0:
        for row in att_rows:
            if row.get('Roll_No') == str(roll_no) and row.get('Status') == '1' and row.get('Date') in active_open_days:
                attended_count += 1
                    
    percentage = round((attended_count / total_working_days * 100), 2) if total_working_days > 0 else 0
    return percentage, attended_count, total_working_days

# ================= LOGIN PORTAL SECURITY CONTROLLERS =================
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        if 'role' in session:
            return redirect(url_for('index'))
        return render_template('login.html', error=None)
        
    username = request.form.get('username','').strip()
    password = request.form.get('password','').strip()
    login_type = request.form.get('login_type')
    
    if login_type == 'staff':
        # Master system administrator bypass fallback
        if username == 'admin' and password == 'admin123':
            session['role'] = 'staff'
            session['user_id'] = 'Admin Setup Account'
            return redirect(url_for('index', active_tab='admin_students'))
            
        # Check dynamic registered staff database entries
        rows = safe_read_rows('staff.csv', DATABASES['staff.csv'])
        target_faculty = next((r for r in rows if r.get('Emp_ID') == str(username)), None)
        
        if target_faculty and str(target_faculty.get('Password')) == str(password):
            session['role'] = 'staff'
            session['user_id'] = target_faculty.get('Name')
            return redirect(url_for('index', active_tab='admin_students'))
        return render_template('login.html', error="Invalid Faculty Credentials or Password")
        
    elif login_type == 'student':
        rows = safe_read_rows('students.csv', DATABASES['students.csv'])
        target = next((r for r in rows if r.get('Roll_No') == str(username)), None)
        
        if target and str(target.get('Password')) == str(password):
            session['role'] = 'student'
            session['user_id'] = target.get('Roll_No')
            return redirect(url_for('index', active_tab='student_portal'))
        return render_template('login.html', error="Invalid Student Roll Identity or Password Code")

# ================= NEW: FACULTY REGISTRATION CONTROLLER =================
@app.route('/register_faculty', methods=['GET', 'POST'])
def register_faculty():
    if request.method == 'GET':
        return render_template('register_faculty.html', error=None, success=None)
        
    emp_id = request.form.get('emp_id','').strip()
    name = request.form.get('name','').strip()
    department = request.form.get('department','').strip()
    password = request.form.get('password','').strip()
    
    rows = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    
    # Check if the Employee ID is already registered
    if any(r.get('Emp_ID') == str(emp_id) for r in rows) or emp_id.lower() == 'admin':
        return render_template('register_faculty.html', error="Employee ID is already registered.", success=None)
        
    # Append the new faculty profile details directly to the CSV file array structure
    rows.append({
        'Emp_ID': str(emp_id),
        'Name': name,
        'Department': department,
        'Password': str(password)
    })
    safe_write_rows(rows, 'staff.csv', DATABASES['staff.csv'])
    return render_template('register_faculty.html', error=None, success="Account registered successfully! You can now log in.")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ================= CORE ROOT DASHBOARD ROUTE =================
@app.route('/')
def index():
    if 'role' not in session:
        return redirect(url_for('login_page'))
        
    is_staff = session['role'] == 'staff'
    user_roll = session.get('user_id')
    
    students = safe_read_rows('students.csv', DATABASES['students.csv'])
    staff = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    timetable = safe_read_rows('timetable.csv', DATABASES['timetable.csv'])
    assignments = safe_read_rows('assignments.csv', DATABASES['assignments.csv'])
    
    now = datetime.now()
    selected_month = int(request.args.get('month', now.month))
    selected_year = int(request.args.get('year', now.year))
    
    default_tab = 'admin_students' if is_staff else 'student_portal'
    active_tab = request.args.get('active_tab', default_tab)
    
    num_days = calendar.monthrange(selected_year, selected_month)[1]
    days_list = [f"{selected_year}-{selected_month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    
    h_rows = safe_read_rows('holidays.csv', ['Date'])
    holidays_list = [row['Date'] for row in h_rows if 'Date' in row]
    
    attendance_map = {}
    att_rows = safe_read_rows('attendance.csv', ['Roll_No', 'Date', 'Status'])
    for row in att_rows:
        if row.get('Roll_No') and row.get('Date'):
            attendance_map[(str(row['Roll_No']), str(row['Date']))] = int(row.get('Status', 0))
    
    current_student = None
    for s in students:
        pct, att, tot = calculate_student_percentage(s.get('Roll_No'), days_list)
        s['Attendance_Percent'] = pct
        s['Attended'] = att
        s['Total_Classes'] = tot
        if not is_staff and s.get('Roll_No') == str(user_roll):
            current_student = s

    return render_template(
        'index.html', 
        students=students, staff=staff, timetable=timetable, assignments=assignments, 
        current_student=current_student, is_staff=is_staff, active_tab=active_tab,
        days_list=days_list, selected_month=selected_month, selected_year=selected_year,
        attendance_map=attendance_map, holidays_list=holidays_list
    )

# ================= BACKEND SECURITY GUARDS =================
@app.route('/toggle_attendance', methods=['POST'])
def toggle_attendance():
    if session.get('role') != 'staff': return jsonify({'success': False}), 403
    roll_no, date = request.form.get('roll_no'), request.form.get('date')
    status, month, year = int(request.form.get('status', 0)), int(request.form.get('month')), int(request.form.get('year'))

    rows = safe_read_rows('attendance.csv', DATABASES['attendance.csv'])
    filtered_rows = [r for r in rows if not (r.get('Roll_No') == str(roll_no) and r.get('Date') == str(date))]
    filtered_rows.append({'Roll_No': str(roll_no), 'Date': str(date), 'Status': str(status)})
    safe_write_rows(filtered_rows, 'attendance.csv', DATABASES['attendance.csv'])
    
    num_days = calendar.monthrange(year, month)[1]
    days_list = [f"{year}-{month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    pct, att, tot = calculate_student_percentage(roll_no, days_list)
    return jsonify({'success': True, 'new_percent': pct})

@app.route('/add_student', methods=['POST'])
def add_student():
    if session.get('role') != 'staff': return "Unauthorized", 403
    roll_no = request.form.get('roll_no')
    rows = safe_read_rows('students.csv', DATABASES['students.csv'])
    if not any(r.get('Roll_No') == str(roll_no) for r in rows):
        rows.append({'Roll_No': str(roll_no), 'Name': request.form.get('name'), 'Course': request.form.get('course'), 'Password': str(request.form.get('password', '12345')), 'Profile_Pic': ''})
        safe_write_rows(rows, 'students.csv', DATABASES['students.csv'])
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/delete_student/<roll_no>')
def delete_student(roll_no):
    if session.get('role') != 'staff': return "Unauthorized", 403
    rows = safe_read_rows('students.csv', DATABASES['students.csv'])
    safe_write_rows([r for r in rows if r.get('Roll_No') != str(roll_no)], 'students.csv', DATABASES['students.csv'])
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/toggle_holiday', methods=['POST'])
def toggle_holiday():
    if session.get('role') != 'staff': return "Unauthorized", 403
    date, month, year = request.form.get('date'), request.form.get('month'), request.form.get('year')
    rows = safe_read_rows('holidays.csv', DATABASES['holidays.csv'])
    if str(date) in [r.get('Date') for r in rows]:
        rows = [r for r in rows if r.get('Date') != str(date)]
    else: rows.append({'Date': str(date)})
    safe_write_rows(rows, 'holidays.csv', DATABASES['holidays.csv'])
    return redirect(url_for('index', month=month, year=year, active_tab='admin_students'))

@app.route('/add_timetable', methods=['POST'])
def add_timetable():
    if session.get('role') != 'staff': return "Unauthorized", 403
    rows = safe_read_rows('timetable.csv', DATABASES['timetable.csv'])
    rows.append({'ID': str(int(time.time())), 'Day': request.form.get('day'), 'Time': request.form.get('time'), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher')})
    safe_write_rows(rows, 'timetable.csv', DATABASES['timetable.csv'])
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/delete_timetable/<entry_id>')
def delete_timetable(entry_id):
    if session.get('role') != 'staff': return "Unauthorized", 403
    rows = safe_read_rows('timetable.csv', DATABASES['timetable.csv'])
    safe_write_rows([r for r in rows if r.get('ID') != str(entry_id)], 'timetable.csv', DATABASES['timetable.csv'])
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/add_assignment', methods=['POST'])
def add_assignment():
    if session.get('role') != 'staff': return "Unauthorized", 403
    rows = safe_read_rows('assignments.csv', DATABASES['assignments.csv'])
    rows.append({'ID': str(int(time.time())), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher'), 'Deadline': request.form.get('deadline'), 'Question': request.form.get('question')})
    safe_write_rows(rows, 'assignments.csv', DATABASES['assignments.csv'])
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/delete_assignment/<entry_id>')
def delete_assignment(entry_id):
    if session.get('role') != 'staff': return "Unauthorized", 403
    rows = safe_read_rows('assignments.csv', DATABASES['assignments.csv'])
    safe_write_rows([r for r in rows if r.get('ID') != str(entry_id)], 'assignments.csv', DATABASES['assignments.csv'])
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/add_staff', methods=['POST'])
def add_staff():
    if session.get('role') != 'staff': return "Unauthorized", 403
    rows = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    if not any(r.get('Emp_ID') == str(request.form.get('emp_id')) for r in rows):
        rows.append({'Emp_ID': str(request.form.get('emp_id')), 'Name': request.form.get('name'), 'Department': request.form.get('department'), 'Password': str(request.form.get('password', '12345'))})
        safe_write_rows(rows, 'staff.csv', DATABASES['staff.csv'])
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/delete_staff/<emp_id>')
def delete_staff(emp_id):
    if session.get('role') != 'staff': return "Unauthorized", 403
    rows = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    safe_write_rows([r for r in rows if r.get('Emp_ID') != str(emp_id)], 'staff.csv', DATABASES['staff.csv'])
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    if 'role' not in session: return "Unauthorized", 401
    roll_no = request.form.get('roll_no')
    file = request.files.get('profile_image')
    if file and allowed_file(file.filename):
        filename = secure_filename(f"avatar_{roll_no}_{int(time.time())}.{file.filename.rsplit('.', 1)[1].lower()}")
        if IS_RENDER:
            render_upload_path = '/opt/render/project/src/data/static/uploads/'
            os.makedirs(render_upload_path, exist_ok=True)
            file.save(os.path.join(render_upload_path, filename))
        else:
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
        rows = safe_read_rows('students.csv', DATABASES['students.csv'])
        for r in rows:
            if r.get('Roll_No') == str(roll_no): r['Profile_Pic'] = filename
        safe_write_rows(rows, 'students.csv', DATABASES['students.csv'])
    return redirect(url_for('index', active_tab='student_portal'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)