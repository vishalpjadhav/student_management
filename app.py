from flask import Flask, render_template, request, redirect, url_for, jsonify
import pandas as pd
import os
import time
from datetime import datetime
import calendar
from werkzeug.utils import secure_filename

app = Flask(__name__)

# --- SMART PATH CHECKER FOR WINDOWS vs RENDER ---
# If '/etc/secrets/' exists, we are running online on Render. Otherwise, we are running on local Windows.
IS_RENDER = os.path.exists('/etc/secrets/')

if IS_RENDER:
    UPLOAD_FOLDER = '/etc/secrets/uploads/'
    DATABASES = {
        '/etc/secrets/students.csv': ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'],
        '/etc/secrets/staff.csv': ['Emp_ID', 'Name', 'Department'],
        '/etc/secrets/timetable.csv': ['ID', 'Day', 'Time', 'Subject', 'Teacher'],
        '/etc/secrets/assignments.csv': ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'],
        '/etc/secrets/attendance.csv': ['Roll_No', 'Date', 'Status'],
        '/etc/secrets/holidays.csv': ['Date']
    }
else:
    # Local Windows Configuration Paths
    UPLOAD_FOLDER = 'static/uploads/'
    DATABASES = {
        'students.csv': ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'],
        'staff.csv': ['Emp_ID', 'Name', 'Department'],
        'timetable.csv': ['ID', 'Day', 'Time', 'Subject', 'Teacher'],
        'assignments.csv': ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'],
        'attendance.csv': ['Roll_No', 'Date', 'Status'],
        'holidays.csv': ['Date']
    }

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Safe Directory Creator: Cleans any conflicting regular files named "uploads" on Windows
if not os.path.isdir(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    except FileExistsError:
        if not IS_RENDER and os.path.exists(UPLOAD_FOLDER):
            os.remove(UPLOAD_FOLDER)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Generate database flat files if they don't exist (Only executed locally)
for file, columns in DATABASES.items():
    if not IS_RENDER and not os.path.exists(file):
        pd.DataFrame(columns=columns).to_csv(file, index=False)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_path(filename):
    """Helper utility to resolve paths dynamically whether local or production."""
    if IS_RENDER:
        return f'/etc/secrets/{filename}'
    return filename

def calculate_student_percentage(roll_no, current_month_days):
    """Calculates attendance based strictly on days the college was active."""
    holidays_set = set()
    h_path = get_db_path('holidays.csv')
    if os.path.exists(h_path):
        try:
            h_df = pd.read_csv(h_path, dtype=str)
            if not h_df.empty:
                holidays_set = set(h_df['Date'].tolist())
        except Exception:
            pass
            
    active_open_days = [d for d in current_month_days if d not in holidays_set]
    total_working_days = len(active_open_days)
    
    attended_count = 0
    att_path = get_db_path('attendance.csv')
    if os.path.exists(att_path) and total_working_days > 0:
        try:
            att_df = pd.read_csv(att_path, dtype=str)
            if not att_df.empty:
                s_logs = att_df[(att_df['Roll_No'] == str(roll_no)) & (att_df['Status'] == '1')]
                student_present_dates = s_logs['Date'].tolist()
                for d in student_present_dates:
                    if d in active_open_days:
                        attended_count += 1
        except Exception:
            pass
                    
    percentage = round((attended_count / total_working_days * 100), 2) if total_working_days > 0 else 0
    return percentage, attended_count, total_working_days

@app.route('/')
def index():
    students_df = pd.read_csv(get_db_path('students.csv'), dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str})
    students = students_df.fillna('').to_dict('records')
    staff = pd.read_csv(get_db_path('staff.csv'), dtype=str).fillna('').to_dict('records')
    timetable = pd.read_csv(get_db_path('timetable.csv'), dtype=str).fillna('').to_dict('records')
    assignments = pd.read_csv(get_db_path('assignments.csv'), dtype=str).fillna('').to_dict('records')
    
    now = datetime.now()
    selected_month = int(request.args.get('month', now.month))
    selected_year = int(request.args.get('year', now.year))
    active_tab = request.args.get('active_tab', 'admin_students')
    
    num_days = calendar.monthrange(selected_year, selected_month)[1]
    days_list = [f"{selected_year}-{selected_month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    
    try:
        holidays_df = pd.read_csv(get_db_path('holidays.csv'), dtype=str)
        holidays_list = holidays_df['Date'].tolist() if not holidays_df.empty else []
    except Exception:
        holidays_list = []
    
    attendance_map = {}
    att_path = get_db_path('attendance.csv')
    if os.path.exists(att_path):
        try:
            att_df = pd.read_csv(att_path, dtype=str)
            for _, row in att_df.iterrows():
                attendance_map[(str(row['Roll_No']), str(row['Date']))] = int(row['Status'])
        except Exception:
            pass
    
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

# ================= ASYNC FLICKER-FREE ATTENDANCE API ROUTE =================
@app.route('/toggle_attendance', methods=['POST'])
def toggle_attendance():
    roll_no = request.form.get('roll_no')
    date = request.form.get('date')
    status = int(request.form.get('status', 0))
    month = int(request.form.get('month', datetime.now().month))
    year = int(request.form.get('year', datetime.now().year))

    att_path = get_db_path('attendance.csv')
    df = pd.read_csv(att_path, dtype=str)
    df = df[~((df['Roll_No'] == str(roll_no)) & (df['Date'] == str(date)))]
    
    new_entry = pd.DataFrame([{'Roll_No': str(roll_no), 'Date': str(date), 'Status': str(status)}])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv(att_path, index=False)
    
    num_days = calendar.monthrange(year, month)[1]
    days_list = [f"{year}-{month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    
    pct, att, tot = calculate_student_percentage(roll_no, days_list)
    return jsonify({
        'success': True,
        'new_percent': pct,
        'new_attended': att,
        'new_total': tot
    })

# ================= HOLIDAY CONFIGURATION CONTROLLER ROUTE =================
@app.route('/toggle_holiday', methods=['POST'])
def toggle_holiday():
    date = request.form.get('date')
    month = request.form.get('month')
    year = request.form.get('year')
    
    h_path = get_db_path('holidays.csv')
    df = pd.read_csv(h_path, dtype=str)
    
    if date in df['Date'].values:
        df = df[df['Date'] != date]
    else:
        df = pd.concat([df, pd.DataFrame([{'Date': date}])], ignore_index=True)
        
    df.to_csv(h_path, index=False)
    return redirect(url_for('index', month=month, year=year, active_tab='admin_students'))

# ================= IDENTITY LOGIN STUDENT PORTAL DASHBOARD =================
@app.route('/student_login', methods=['POST'])
def student_login():
    roll_no = request.form.get('login_roll_no')
    password = request.form.get('login_password')
    
    df = pd.read_csv(get_db_path('students.csv'), dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('')
    student_data = None
    login_error = None

    now = datetime.now()
    num_days = calendar.monthrange(now.year, now.month)[1]
    days_list = [f"{now.year}-{now.month:02d}-{day:02d}" for day in range(1, num_days + 1)]

    if str(roll_no) in df['Roll_No'].values:
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

    students = pd.read_csv(get_db_path('students.csv'), dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('').to_dict('records')
    staff = pd.read_csv(get_db_path('staff.csv'), dtype=str).fillna('').to_dict('records')
    timetable = pd.read_csv(get_db_path('timetable.csv'), dtype=str).fillna('').to_dict('records')
    assignments = pd.read_csv(get_db_path('assignments.csv'), dtype=str).fillna('').to_dict('records')
    
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

# ================= STUDENT PROFILE PHOTO IMAGE UPLOADER ROUTE =================
@app.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    roll_no = request.form.get('roll_no')
    file = request.files.get('profile_image')
    
    now = datetime.now()
    num_days = calendar.monthrange(now.year, now.month)[1]
    days_list = [f"{now.year}-{now.month:02d}-{day:02d}" for day in range(1, num_days + 1)]

    if file and allowed_file(file.filename):
        filename = secure_filename(f"avatar_{roll_no}_{int(time.time())}.{file.filename.rsplit('.', 1)[1].lower()}")
        
        # Determine the physical destination target based on the running runtime
        if IS_RENDER:
            # Create a static subfolder inside the persistent network disk if running on Render
            render_uploads = '/opt/render/project/src/data/static/uploads/'
            os.makedirs(render_uploads, exist_ok=True)
            file.save(os.path.join(render_uploads, filename))
        else:
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        stu_path = get_db_path('students.csv')
        df = pd.read_csv(stu_path, dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str})
        df.loc[df['Roll_No'] == str(roll_no), 'Profile_Pic'] = filename
        df.to_csv(stu_path, index=False)
        
    df = pd.read_csv(get_db_path('students.csv'), dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('')
    student_row = df[df['Roll_No'] == str(roll_no)].iloc[0]
    percentage, attended, total = calculate_student_percentage(roll_no, days_list)
    
    student_data = {
        'Roll_No': student_row['Roll_No'], 'Name': student_row['Name'], 'Course': student_row['Course'],
        'Profile_Pic': student_row['Profile_Pic'], 'Attendance_Percent': percentage, 'Attended': attended, 'Total_Classes': total
    }
    
    students = pd.read_csv(get_db_path('students.csv'), dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('').to_dict('records')
    staff = pd.read_csv(get_db_path('staff.csv'), dtype=str).fillna('').to_dict('records')
    timetable = pd.read_csv(get_db_path('timetable.csv'), dtype=str).fillna('').to_dict('records')
    assignments = pd.read_csv(get_db_path('assignments.csv'), dtype=str).fillna('').to_dict('records')
    
    return render_template(
        'index.html', students=students, staff=staff, timetable=timetable, assignments=assignments, 
        current_student=student_data, active_tab='student_portal', login_error=None,
        days_list=days_list, selected_month=now.month, selected_year=now.year, attendance_map={}, month_name="", holidays_list=[]
    )

# ================= INLINE MANAGEMENT RECORD EDITORS & MODIFIERS =================
@app.route('/edit_student', methods=['POST'])
def edit_student():
    stu_path = get_db_path('students.csv')
    df = pd.read_csv(stu_path, dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str})
    df.loc[df['Roll_No'] == str(request.form.get('roll_no')), ['Name', 'Course', 'Password']] = [request.form.get('name'), request.form.get('course'), request.form.get('password')]
    df.to_csv(stu_path, index=False)
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/add_student', methods=['POST'])
def add_student():
    roll_no, name, course, password = request.form.get('roll_no'), request.form.get('name'), request.form.get('course'), request.form.get('password', '12345')
    stu_path = get_db_path('students.csv')
    df = pd.read_csv(stu_path, dtype={'Roll_No': str})
    if str(roll_no) not in df['Roll_No'].values:
        df = pd.concat([df, pd.DataFrame([{'Roll_No': str(roll_no), 'Name': name, 'Course': course, 'Password': str(password), 'Profile_Pic': ''}])], ignore_index=True)
        df.to_csv(stu_path, index=False)
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/delete_student/<roll_no>')
def delete_student(roll_no):
    stu_path = get_db_path('students.csv')
    df = pd.read_csv(stu_path, dtype={'Roll_No': str})
    df = df[df['Roll_No'] != str(roll_no)]
    df.to_csv(stu_path, index=False)
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/edit_staff', methods=['POST'])
def edit_staff():
    staff_path = get_db_path('staff.csv')
    df = pd.read_csv(staff_path, dtype=str)
    df.loc[df['Emp_ID'] == str(request.form.get('emp_id')), ['Name', 'Department']] = [request.form.get('name'), request.form.get('department')]
    df.to_csv(staff_path, index=False)
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/add_staff', methods=['POST'])
def add_staff():
    staff_path = get_db_path('staff.csv')
    df = pd.read_csv(staff_path, dtype=str)
    if str(request.form.get('emp_id')) not in df['Emp_ID'].values:
        df = pd.concat([df, pd.DataFrame([{'Emp_ID': str(request.form.get('emp_id')), 'Name': request.form.get('name'), 'Department': request.form.get('department')}])], ignore_index=True)
        df.to_csv(staff_path, index=False)
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/delete_staff/<emp_id>')
def delete_staff(emp_id):
    staff_path = get_db_path('staff.csv')
    df = pd.read_csv(staff_path, dtype=str)
    df = df[df['Emp_ID'] != str(emp_id)]
    df.to_csv(staff_path, index=False)
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/edit_timetable', methods=['POST'])
def edit_timetable():
    time_path = get_db_path('timetable.csv')
    df = pd.read_csv(time_path, dtype=str)
    df.loc[df['ID'] == str(request.form.get('id')), ['Day', 'Time', 'Subject', 'Teacher']] = [request.form.get('day'), request.form.get('time'), request.form.get('subject'), request.form.get('teacher')]
    df.to_csv(time_path, index=False)
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/add_timetable', methods=['POST'])
def add_timetable():
    time_path = get_db_path('timetable.csv')
    df = pd.read_csv(time_path, dtype=str)
    df = pd.concat([df, pd.DataFrame([{'ID': str(int(time.time())), 'Day': request.form.get('day'), 'Time': request.form.get('time'), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher')}])], ignore_index=True)
    df.to_csv(time_path, index=False)
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/delete_timetable/<entry_id>')
def delete_timetable(entry_id):
    time_path = get_db_path('timetable.csv')
    df = pd.read_csv(time_path, dtype=str)
    df = df[df['ID'] != str(entry_id)]
    df.to_csv(time_path, index=False)
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/edit_assignment', methods=['POST'])
def edit_assignment():
    assign_path = get_db_path('assignments.csv')
    df = pd.read_csv(assign_path, dtype=str)
    df.loc[df['ID'] == str(request.form.get('id')), ['Subject', 'Teacher', 'Deadline', 'Question']] = [request.form.get('subject'), request.form.get('teacher'), request.form.get('deadline'), request.form.get('question')]
    df.to_csv(assign_path, index=False)
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/add_assignment', methods=['POST'])
def add_assignment():
    assign_path = get_db_path('assignments.csv')
    df = pd.read_csv(assign_path, dtype=str)
    df = pd.concat([df, pd.DataFrame([{'ID': str(int(time.time())), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher'), 'Deadline': request.form.get('deadline'), 'Question': request.form.get('question')}])], ignore_index=True)
    df.to_csv(assign_path, index=False)
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/delete_assignment/<entry_id>')
def delete_assignment(entry_id):
    assign_path = get_db_path('assignments.csv')
    df = pd.read_csv(assign_path, dtype=str)
    df = df[df['ID'] != str(entry_id)]
    df.to_csv(assign_path, index=False)
    return redirect(url_for('index', active_tab='admin_assignments'))

if __name__ == '__main__':
    # Automatically binds to host server rules, default to 5000 on localhost
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)