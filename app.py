from flask import Flask, render_template, request, redirect, url_for, jsonify
import pandas as pd
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
    # Writable persistent disk directory on Render
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
    
    # Securely create storage folders on the persistent disk
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # COPY TEMPLATES FROM RENDER SECRETS TO WRITABLE STORAGE ONCE IF MISSING
    for file, columns in DATABASES.items():
        dest_path = os.path.join(DATA_DIR, file)
        source_path = os.path.join('/etc/secrets/', file)
        
        if not os.path.exists(dest_path):
            if os.path.exists(source_path) and os.path.getsize(source_path) > 0:
                shutil.copy(source_path, dest_path)
            else:
                # Fallback if secret files are empty
                pd.DataFrame(columns=columns).to_csv(dest_path, index=False)
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
    
    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    except FileExistsError:
        if os.path.exists(UPLOAD_FOLDER):
            os.remove(UPLOAD_FOLDER)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Generate baseline files locally if missing
    for file, columns in DATABASES.items():
        if not os.path.exists(file):
            pd.DataFrame(columns=columns).to_csv(file, index=False)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_path(filename):
    """Returns the absolute writable path on Render or local path on Windows."""
    if IS_RENDER:
        return os.path.join(DATA_DIR, filename)
    return filename

def safe_read_csv(filename, default_columns, dtype_dict=None):
    path = get_file_path(filename)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=default_columns)
    try:
        if dtype_dict:
            return pd.read_csv(path, dtype=dtype_dict)
        return pd.read_csv(path, dtype=str)
    except Exception:
        return pd.DataFrame(columns=default_columns)

def safe_write_csv(df, filename):
    path = get_file_path(filename)
    df.to_csv(path, index=False)

def calculate_student_percentage(roll_no, current_month_days):
    holidays_set = set()
    h_df = safe_read_csv('holidays.csv', ['Date'])
    if not h_df.empty:
        holidays_set = set(h_df['Date'].fillna('').astype(str).tolist())
            
    active_open_days = [d for d in current_month_days if d not in holidays_set]
    total_working_days = len(active_open_days)
    
    attended_count = 0
    att_df = safe_read_csv('attendance.csv', ['Roll_No', 'Date', 'Status'])
    if not att_df.empty and total_working_days > 0:
        try:
            s_logs = att_df[(att_df['Roll_No'].astype(str) == str(roll_no)) & (att_df['Status'].astype(str) == '1')]
            student_present_dates = s_logs['Date'].fillna('').astype(str).tolist()
            for d in student_present_dates:
                if d in active_open_days:
                    attended_count += 1
        except Exception:
            pass
                    
    percentage = round((attended_count / total_working_days * 100), 2) if total_working_days > 0 else 0
    return percentage, attended_count, total_working_days

@app.route('/')
def index():
    students_df = safe_read_csv('students.csv', ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'], {'Roll_No': str, 'Password': str, 'Profile_Pic': str})
    students = students_df.fillna('').to_dict('records')
    
    staff = safe_read_csv('staff.csv', ['Emp_ID', 'Name', 'Department']).fillna('').to_dict('records')
    timetable = safe_read_csv('timetable.csv', ['ID', 'Day', 'Time', 'Subject', 'Teacher']).fillna('').to_dict('records')
    assignments = safe_read_csv('assignments.csv', ['ID', 'Subject', 'Teacher', 'Deadline', 'Question']).fillna('').to_dict('records')
    
    now = datetime.now()
    selected_month = int(request.args.get('month', now.month))
    selected_year = int(request.args.get('year', now.year))
    active_tab = request.args.get('active_tab', 'admin_students')
    
    num_days = calendar.monthrange(selected_year, selected_month)[1]
    days_list = [f"{selected_year}-{selected_month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    
    holidays_df = safe_read_csv('holidays.csv', ['Date'])
    holidays_list = holidays_df['Date'].fillna('').astype(str).tolist() if not holidays_df.empty else []
    
    attendance_map = {}
    att_df = safe_read_csv('attendance.csv', ['Roll_No', 'Date', 'Status'])
    if not att_df.empty:
        for _, row in att_df.iterrows():
            if pd.notna(row['Roll_No']) and pd.notna(row['Date']):
                attendance_map[(str(row['Roll_No']), str(row['Date']))] = int(row['Status'])
    
    for student in students:
        pct, att, tot = calculate_student_percentage(student['Roll_No'], days_list)
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

    df = safe_read_csv('attendance.csv', ['Roll_No', 'Date', 'Status'])
    if not df.empty:
        df = df[~((df['Roll_No'].astype(str) == str(roll_no)) & (df['Date'].astype(str) == str(date)))]
    
    new_entry = pd.DataFrame([{'Roll_No': str(roll_no), 'Date': str(date), 'Status': str(status)}])
    df = pd.concat([df, new_entry], ignore_index=True)
    safe_write_csv(df, 'attendance.csv')
    
    num_days = calendar.monthrange(year, month)[1]
    days_list = [f"{year}-{month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    
    pct, att, tot = calculate_student_percentage(roll_no, days_list)
    return jsonify({
        'success': True,
        'new_percent': pct,
        'new_attended': att,
        'new_total': tot
    })

@app.route('/toggle_holiday', methods=['POST'])
def toggle_holiday():
    date = request.form.get('date')
    month = request.form.get('month')
    year = request.form.get('year')
    
    df = safe_read_csv('holidays.csv', ['Date'])
    
    if not df.empty and date in df['Date'].fillna('').astype(str).values:
        df = df[df['Date'].astype(str) != str(date)]
    else:
        df = pd.concat([df, pd.DataFrame([{'Date': str(date)}])], ignore_index=True)
        
    safe_write_csv(df, 'holidays.csv')
    return redirect(url_for('index', month=month, year=year, active_tab='admin_students'))

@app.route('/student_login', methods=['POST'])
def student_login():
    roll_no = request.form.get('login_roll_no')
    password = request.form.get('login_password')
    
    df = safe_read_csv('students.csv', ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'], {'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('')
    student_data = None
    login_error = None

    now = datetime.now()
    num_days = calendar.monthrange(now.year, now.month)[1]
    days_list = [f"{now.year}-{now.month:02d}-{day:02d}" for day in range(1, num_days + 1)]

    if not df.empty and str(roll_no) in df['Roll_No'].values:
        student_row = df[df['Roll_No'] == str(roll_no)].iloc[0]
        if str(student_row['Password']) == str(password):
            percentage, attended, total = calculate_student_percentage(roll_no, days_list)
            student_data = {
                'Roll_No': student_row['Roll_No'], 'Name': student_row['Name'], 'Course': student_row['Course'],
                'Profile_Pic': student_row['Profile_Pic'], 'Attendance_Percent': percentage, 'Attended': attended, 'Total_Classes': total
            }
        else:
            login_error = "Incorrect Password. Please try again."
    else:
        login_error = "Student Roll Number not registered."

    students = safe_read_csv('students.csv', ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'], {'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('').to_dict('records')
    staff = safe_read_csv('staff.csv', ['Emp_ID', 'Name', 'Department']).fillna('').to_dict('records')
    timetable = safe_read_csv('timetable.csv', ['ID', 'Day', 'Time', 'Subject', 'Teacher']).fillna('').to_dict('records')
    assignments = safe_read_csv('assignments.csv', ['ID', 'Subject', 'Teacher', 'Deadline', 'Question']).fillna('').to_dict('records')
    
    for s in students:
        pct, att, tot = calculate_student_percentage(s['Roll_No'], days_list)
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
        
        df = safe_read_csv('students.csv', ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'], {'Roll_No': str, 'Password': str, 'Profile_Pic': str})
        if not df.empty:
            df.loc[df['Roll_No'] == str(roll_no), 'Profile_Pic'] = filename
            safe_write_csv(df, 'students.csv')
        
    df = safe_read_csv('students.csv', ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'], {'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('')
    student_row = df[df['Roll_No'] == str(roll_no)].iloc[0]
    percentage, attended, total = calculate_student_percentage(roll_no, days_list)
    
    student_data = {
        'Roll_No': student_row['Roll_No'], 'Name': student_row['Name'], 'Course': student_row['Course'],
        'Profile_Pic': student_row['Profile_Pic'], 'Attendance_Percent': percentage, 'Attended': attended, 'Total_Classes': total
    }
    
    students = safe_read_csv('students.csv', ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'], {'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('').to_dict('records')
    staff = safe_read_csv('staff.csv', ['Emp_ID', 'Name', 'Department']).fillna('').to_dict('records')
    timetable = safe_read_csv('timetable.csv', ['ID', 'Day', 'Time', 'Subject', 'Teacher']).fillna('').to_dict('records')
    assignments = safe_read_csv('assignments.csv', ['ID', 'Subject', 'Teacher', 'Deadline', 'Question']).fillna('').to_dict('records')
    
    return render_template(
        'index.html', students=students, staff=staff, timetable=timetable, assignments=assignments, 
        current_student=student_data, active_tab='student_portal', login_error=None,
        days_list=days_list, selected_month=now.month, selected_year=now.year, attendance_map={}, month_name="", holidays_list=[]
    )

@app.route('/edit_student', methods=['POST'])
def edit_student():
    df = safe_read_csv('students.csv', ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'], {'Roll_No': str, 'Password': str, 'Profile_Pic': str})
    df.loc[df['Roll_No'] == str(request.form.get('roll_no')), ['Name', 'Course', 'Password']] = [request.form.get('name'), request.form.get('course'), request.form.get('password')]
    safe_write_csv(df, 'students.csv')
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/add_student', methods=['POST'])
def add_student():
    roll_no, name, course, password = request.form.get('roll_no'), request.form.get('name'), request.form.get('course'), request.form.get('password', '12345')
    df = safe_read_csv('students.csv', ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'], {'Roll_No': str})
    
    exists = False
    if not df.empty and str(roll_no) in df['Roll_No'].values:
        exists = True
        
    if not exists:
        df = pd.concat([df, pd.DataFrame([{'Roll_No': str(roll_no), 'Name': name, 'Course': course, 'Password': str(password), 'Profile_Pic': ''}])], ignore_index=True)
        safe_write_csv(df, 'students.csv')
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/delete_student/<roll_no>')
def delete_student(roll_no):
    df = safe_read_csv('students.csv', ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'], {'Roll_No': str})
    if not df.empty:
        df = df[df['Roll_No'] != str(roll_no)]
        safe_write_csv(df, 'students.csv')
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/edit_staff', methods=['POST'])
def edit_staff():
    df = safe_read_csv('staff.csv', ['Emp_ID', 'Name', 'Department'])
    df.loc[df['Emp_ID'] == str(request.form.get('emp_id')), ['Name', 'Department']] = [request.form.get('name'), request.form.get('department')]
    safe_write_csv(df, 'staff.csv')
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/add_staff', methods=['POST'])
def add_staff():
    df = safe_read_csv('staff.csv', ['Emp_ID', 'Name', 'Department'])
    if df.empty or str(request.form.get('emp_id')) not in df['Emp_ID'].values:
        df = pd.concat([df, pd.DataFrame([{'Emp_ID': str(request.form.get('emp_id')), 'Name': request.form.get('name'), 'Department': request.form.get('department')}])], ignore_index=True)
        safe_write_csv(df, 'staff.csv')
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/delete_staff/<emp_id>')
def delete_staff(emp_id):
    df = safe_read_csv('staff.csv', ['Emp_ID', 'Name', 'Department'])
    if not df.empty:
        df = df[df['Emp_ID'] != str(emp_id)]
        safe_write_csv(df, 'staff.csv')
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/edit_timetable', methods=['POST'])
def edit_timetable():
    df = safe_read_csv('timetable.csv', ['ID', 'Day', 'Time', 'Subject', 'Teacher'])
    df.loc[df['ID'] == str(request.form.get('id')), ['Day', 'Time', 'Subject', 'Teacher']] = [request.form.get('day'), request.form.get('time'), request.form.get('subject'), request.form.get('teacher')]
    safe_write_csv(df, 'timetable.csv')
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/add_timetable', methods=['POST'])
def add_timetable():
    df = safe_read_csv('timetable.csv', ['ID', 'Day', 'Time', 'Subject', 'Teacher'])
    df = pd.concat([df, pd.DataFrame([{'ID': str(int(time.time())), 'Day': request.form.get('day'), 'Time': request.form.get('time'), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher')}])], ignore_index=True)
    safe_write_csv(df, 'timetable.csv')
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/delete_timetable/<entry_id>')
def delete_timetable(entry_id):
    df = safe_read_csv('timetable.csv', ['ID', 'Day', 'Time', 'Subject', 'Teacher'])
    if not df.empty:
        df = df[df['ID'] != str(entry_id)]
        safe_write_csv(df, 'timetable.csv')
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/edit_assignment', methods=['POST'])
def edit_assignment():
    df = safe_read_csv('assignments.csv', ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'])
    df.loc[df['ID'] == str(request.form.get('id')), ['Subject', 'Teacher', 'Deadline', 'Question']] = [request.form.get('subject'), request.form.get('teacher'), request.form.get('deadline'), request.form.get('question')]
    safe_write_csv(df, 'assignments.csv')
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/add_assignment', methods=['POST'])
def add_assignment():
    df = safe_read_csv('assignments.csv', ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'])
    df = pd.concat([df, pd.DataFrame([{'ID': str(int(time.time())), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher'), 'Deadline': request.form.get('deadline'), 'Question': request.form.get('question')}])], ignore_index=True)
    safe_write_csv(df, 'assignments.csv')
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/delete_assignment/<entry_id>')
def delete_assignment(entry_id):
    df = safe_read_csv('assignments.csv', ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'])
    if not df.empty:
        df = df[df['ID'] != str(entry_id)]
        safe_write_csv(df, 'assignments.csv')
    return redirect(url_for('index', active_tab='admin_assignments'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)