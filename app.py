from flask import Flask, render_template, request, redirect, url_for, jsonify
import csv
import os
import time
from datetime import datetime
import calendar
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)

# --- SMART PATH CHECKER FOR WINDOWS vs RENDER ---
IS_RENDER = os.path.exists('/etc/secrets/')

if IS_RENDER:
    # PERMANENT STORAGE: Files stored here will NEVER be deleted when the site closes
    DATA_DIR = '/opt/render/project/src/data/'
    UPLOAD_FOLDER = os.path.join(DATA_DIR, 'static/uploads/')
    
    DATABASES = {
        'students.csv': ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'],
        'staff.csv': ['Emp_ID', 'Name', 'Department'],
        'timetable.csv': ['ID', 'Day', 'Time', 'Subject', 'Teacher'],
        'assignments.csv': ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'],
        'attendance.csv': ['Roll_No', 'Date', 'Status'],
        'holidays.csv': ['Date']
    }
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Check all CSV files: copy them from secrets to permanent storage if missing
    for file, columns in DATABASES.items():
        dest_path = os.path.join(DATA_DIR, file)
        source_path = os.path.join('/etc/secrets/', file)
        
        if not os.path.exists(dest_path):
            if os.path.exists(source_path) and os.path.getsize(source_path) > 0:
                shutil.copy(source_path, dest_path)
            else:
                with open(dest_path, mode='w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(columns)
else:
    # Local Windows Configuration Paths
    DATA_DIR = ''
    UPLOAD_FOLDER = 'static/uploads/'
    DATABASES = {
        'students.csv': ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'],
        'staff.csv': ['Emp_ID', 'Name', 'Department'],
        'timetable.csv': ['ID', 'Day', 'Time', 'Subject', 'Teacher'],
        'assignments.csv': ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'],
        'attendance.csv': ['Roll_No', 'Date', 'Status'],
        'holidays.csv': ['Date']
    }
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    for file, columns in DATABASES.items():
        if not os.path.exists(file):
            with open(file, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- FIXED PATH DEFINITION UTILITY ---
def get_file_path(filename):
    """Ensures files are read and written strictly to the permanent disk path on Render."""
    if IS_RENDER:
        return os.path.join(DATA_DIR, filename)
    return filename

# --- LIGHTWEIGHT PLAIN TEXT CSV UTILITIES ---
def safe_read_rows(filename, default_columns):
    path = get_file_path(filename)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    try:
        with open(path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except Exception:
        return []

def safe_write_rows(rows, filename, columns):
    path = get_file_path(filename)
    try:
        with open(path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                filtered_row = {k: row[k] for k in columns if k in row}
                writer.writerow(filtered_row)
    except Exception as e:
        print(f"Write error: {e}")

def calculate_student_percentage(roll_no, current_month_days):
    h_rows = safe_read_rows('holidays.csv', ['Date'])
    holidays_set = {row['Date'] for row in h_rows if 'Date' in row and row['Date']}
            
    active_open_days = [d for d in current_month_days if d not in holidays_set]
    total_working_days = len(active_open_days)
    
    attended_count = 0
    att_rows = safe_read_rows('attendance.csv', ['Roll_No', 'Date', 'Status'])
    if att_rows and total_working_days > 0:
        for row in att_rows:
            if row.get('Roll_No') == str(roll_no) and row.get('Status') == '1':
                if row.get('Date') in active_open_days:
                    attended_count += 1
                    
    percentage = round((attended_count / total_working_days * 100), 2) if total_working_days > 0 else 0
    return percentage, attended_count, total_working_days

@app.route('/')
def index():
    students = safe_read_rows('students.csv', DATABASES['students.csv'])
    staff = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    timetable = safe_read_rows('timetable.csv', DATABASES['timetable.csv'])
    assignments = safe_read_rows('assignments.csv', DATABASES['assignments.csv'])
    
    now = datetime.now()
    selected_month = int(request.args.get('month', now.month))
    selected_year = int(request.args.get('year', now.year))
    active_tab = request.args.get('active_tab', 'admin_students')
    
    num_days = calendar.monthrange(selected_year, selected_month)[1]
    days_list = [f"{selected_year}-{selected_month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    
    h_rows = safe_read_rows('holidays.csv', ['Date'])
    holidays_list = [row['Date'] for row in h_rows if 'Date' in row]
    
    attendance_map = {}
    att_rows = safe_read_rows('attendance.csv', ['Roll_No', 'Date', 'Status'])
    for row in att_rows:
        if row.get('Roll_No') and row.get('Date'):
            attendance_map[(str(row['Roll_No']), str(row['Date']))] = int(row.get('Status', 0))
    
    for student in students:
        pct, att, tot = calculate_student_percentage(student.get('Roll_No'), days_list)
        student['Attendance_Percent'] = pct
        student['Attended'] = att
        student['Total_Classes'] = tot

    return render_template(
        'index.html', 
        students=students, staff=staff, timetable=timetable, assignments=assignments, 
        current_student=None, active_tab=active_tab, login_error=None,
        days_list=days_list, selected_month=selected_month, selected_year=selected_year,
        attendance_map=attendance_map, month_name=calendar.month_name[selected_month],
        holidays_list=holidays_list
    )

@app.route('/toggle_attendance', methods=['POST'])
def toggle_attendance():
    roll_no = request.form.get('roll_no')
    date = request.form.get('date')
    status = int(request.form.get('status', 0))
    month = int(request.form.get('month', datetime.now().month))
    year = int(request.form.get('year', datetime.now().year))

    rows = safe_read_rows('attendance.csv', DATABASES['attendance.csv'])
    filtered_rows = [r for r in rows if not (r.get('Roll_No') == str(roll_no) and r.get('Date') == str(date))]
    
    filtered_rows.append({'Roll_No': str(roll_no), 'Date': str(date), 'Status': str(status)})
    safe_write_rows(filtered_rows, 'attendance.csv', DATABASES['attendance.csv'])
    
    num_days = calendar.monthrange(year, month)[1]
    days_list = [f"{year}-{month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    
    pct, att, tot = calculate_student_percentage(roll_no, days_list)
    return jsonify({
        'success': True, 'new_percent': pct, 'new_attended': att, 'new_total': tot
    })

@app.route('/toggle_holiday', methods=['POST'])
def toggle_holiday():
    date = request.form.get('date')
    month = request.form.get('month')
    year = request.form.get('year')
    
    rows = safe_read_rows('holidays.csv', DATABASES['holidays.csv'])
    existing_dates = [r.get('Date') for r in rows]
    
    if str(date) in existing_dates:
        rows = [r for r in rows if r.get('Date') != str(date)]
    else:
        rows.append({'Date': str(date)})
        
    safe_write_rows(rows, 'holidays.csv', DATABASES['holidays.csv'])
    return redirect(url_for('index', month=month, year=year, active_tab='admin_students'))

@app.route('/student_login', methods=['POST'])
def student_login():
    roll_no = request.form.get('login_roll_no')
    password = request.form.get('login_password')
    
    rows = safe_read_rows('students.csv', DATABASES['students.csv'])
    student_data = None
    login_error = None

    now = datetime.now()
    num_days = calendar.monthrange(now.year, now.month)[1]
    days_list = [f"{now.year}-{now.month:02d}-{day:02d}" for day in range(1, num_days + 1)]

    target_student = None
    for r in rows:
        if r.get('Roll_No') == str(roll_no):
            target_student = r
            break

    if target_student:
        if str(target_student.get('Password')) == str(password):
            percentage, attended, total = calculate_student_percentage(roll_no, days_list)
            student_data = {
                'Roll_No': target_student.get('Roll_No'), 'Name': target_student.get('Name'), 'Course': target_student.get('Course'),
                'Profile_Pic': target_student.get('Profile_Pic'), 'Attendance_Percent': percentage, 'Attended': attended, 'Total_Classes': total
            }
        else:
            login_error = "Incorrect Password. Please try again."
    else:
        login_error = "Student Roll Number not registered."

    students = safe_read_rows('students.csv', DATABASES['students.csv'])
    staff = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    timetable = safe_read_rows('timetable.csv', DATABASES['timetable.csv'])
    assignments = safe_read_rows('assignments.csv', DATABASES['assignments.csv'])
    
    for s in students:
        pct, att, tot = calculate_student_percentage(s.get('Roll_No'), days_list)
        s['Attendance_Percent'] = pct
        s['Attended'] = att
        s['Total_Classes'] = tot
        
    return render_template(
        'index.html', students=students, staff=staff, timetable=timetable, assignments=assignments, 
        current_student=student_data, active_tab='student_portal', login_error=login_error,
        days_list=days_list, selected_month=now.month, selected_year=now.year, 
        attendance_map={}, month_name=calendar.month_name[now.month], holidays_list=[]
    )

@app.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    roll_no = request.form.get('roll_no')
    file = request.files.get('profile_image')
    
    now = datetime.now()
    num_days = calendar.monthrange(now.year, now.month)[1]
    days_list = [f"{now.year}-{now.month:02d}-{day:02d}" for day in range(1, num_days + 1)]

    if file and allowed_file(file.filename):
        filename = secure_filename(f"avatar_{roll_no}_{int(time.time())}.{file.filename.rsplit('.', 1)[1].lower()}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        rows = safe_read_rows('students.csv', DATABASES['students.csv'])
        for r in rows:
            if r.get('Roll_No') == str(roll_no):
                r['Profile_Pic'] = filename
        safe_write_rows(rows, 'students.csv', DATABASES['students.csv'])
        
    rows = safe_read_rows('students.csv', DATABASES['students.csv'])
    target_row = next((r for r in rows if r.get('Roll_No') == str(roll_no)), {'Roll_No':roll_no, 'Name':'', 'Course':'', 'Profile_Pic':''})
    percentage, attended, total = calculate_student_percentage(roll_no, days_list)
    
    student_data = {
        'Roll_No': target_row.get('Roll_No'), 'Name': target_row.get('Name'), 'Course': target_row.get('Course'),
        'Profile_Pic': target_row.get('Profile_Pic'), 'Attendance_Percent': percentage, 'Attended': attended, 'Total_Classes': total
    }
    
    students = safe_read_rows('students.csv', DATABASES['students.csv'])
    staff = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    timetable = safe_read_rows('timetable.csv', DATABASES['timetable.csv'])
    assignments = safe_read_rows('assignments.csv', DATABASES['assignments.csv'])
    
    return render_template(
        'index.html', students=students, staff=staff, timetable=timetable, assignments=assignments, 
        current_student=student_data, active_tab='student_portal', login_error=None,
        days_list=days_list, selected_month=now.month, selected_year=now.year, attendance_map={}, month_name="", holidays_list=[]
    )

@app.route('/edit_student', methods=['POST'])
def edit_student():
    rows = safe_read_rows('students.csv', DATABASES['students.csv'])
    for r in rows:
        if r.get('Roll_No') == str(request.form.get('roll_no')):
            r['Name'] = request.form.get('name')
            r['Course'] = request.form.get('course')
            r['Password'] = request.form.get('password')
    safe_write_rows(rows, 'students.csv', DATABASES['students.csv'])
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/add_student', methods=['POST'])
def add_student():
    roll_no = request.form.get('roll_no')
    rows = safe_read_rows('students.csv', DATABASES['students.csv'])
    if not any(r.get('Roll_No') == str(roll_no) for r in rows):
        rows.append({
            'Roll_No': str(roll_no), 'Name': request.form.get('name'), 'Course': request.form.get('course'),
            'Password': str(request.form.get('password', '12345')), 'Profile_Pic': ''
        })
        safe_write_rows(rows, 'students.csv', DATABASES['students.csv'])
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/delete_student/<roll_no>')
def delete_student(roll_no):
    rows = safe_read_rows('students.csv', DATABASES['students.csv'])
    rows = [r for r in rows if r.get('Roll_No') != str(roll_no)]
    safe_write_rows(rows, 'students.csv', DATABASES['students.csv'])
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/edit_staff', methods=['POST'])
def edit_staff():
    rows = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    for r in rows:
        if r.get('Emp_ID') == str(request.form.get('emp_id')):
            r['Name'] = request.form.get('name')
            r['Department'] = request.form.get('department')
    safe_write_rows(rows, 'staff.csv', DATABASES['staff.csv'])
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/add_staff', methods=['POST'])
def add_staff():
    rows = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    if not any(r.get('Emp_ID') == str(request.form.get('emp_id')) for r in rows):
        rows.append({'Emp_ID': str(request.form.get('emp_id')), 'Name': request.form.get('name'), 'Department': request.form.get('department')})
        safe_write_rows(rows, 'staff.csv', DATABASES['staff.csv'])
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/delete_staff/<emp_id>')
def delete_staff(emp_id):
    rows = safe_read_rows('staff.csv', DATABASES['staff.csv'])
    rows = [r for r in rows if r.get('Emp_ID') != str(emp_id)]
    safe_write_rows(rows, 'staff.csv', DATABASES['staff.csv'])
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/edit_timetable', methods=['POST'])
def edit_timetable():
    rows = safe_read_rows('timetable.csv', DATABASES['timetable.csv'])
    for r in rows:
        if r.get('ID') == str(request.form.get('id')):
            r['Day'] = request.form.get('day')
            r['Time'] = request.form.get('time')
            r['Subject'] = request.form.get('subject')
            r['Teacher'] = request.form.get('teacher')
    safe_write_rows(rows, 'timetable.csv', DATABASES['timetable.csv'])
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/add_timetable', methods=['POST'])
def add_timetable():
    rows = safe_read_rows('timetable.csv', DATABASES['timetable.csv'])
    rows.append({'ID': str(int(time.time())), 'Day': request.form.get('day'), 'Time': request.form.get('time'), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher')})
    safe_write_rows(rows, 'timetable.csv', DATABASES['timetable.csv'])
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/delete_timetable/<entry_id>')
def delete_timetable(entry_id):
    rows = safe_read_rows('timetable.csv', DATABASES['timetable.csv'])
    rows = [r for r in rows if r.get('ID') != str(entry_id)]
    safe_write_rows(rows, 'timetable.csv', DATABASES['timetable.csv'])
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/edit_assignment', methods=['POST'])
def edit_assignment():
    rows = safe_read_rows('assignments.csv', DATABASES['assignments.csv'])
    for r in rows:
        if r.get('ID') == str(request.form.get('id')):
            r['Subject'] = request.form.get('subject')
            r['Teacher'] = request.form.get('teacher')
            r['Deadline'] = request.form.get('deadline')
            r['Question'] = request.form.get('question')
    safe_write_rows(rows, 'assignments.csv', DATABASES['assignments.csv'])
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/add_assignment', methods=['POST'])
def add_assignment():
    rows = safe_read_rows('assignments.csv', DATABASES['assignments.csv'])
    rows.append({'ID': str(int(time.time())), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher'), 'Deadline': request.form.get('deadline'), 'Question': request.form.get('question')})
    safe_write_rows(rows, 'assignments.csv', DATABASES['assignments.csv'])
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/delete_assignment/<entry_id>')
def delete_assignment(entry_id):
    rows = safe_read_rows('assignments.csv', DATABASES['assignments.csv'])
    rows = [r for r in rows if r.get('ID') != str(entry_id)]
    safe_write_rows(rows, 'assignments.csv', DATABASES['assignments.csv'])
    return redirect(url_for('index', active_tab='admin_assignments'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)