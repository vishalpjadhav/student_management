from flask import Flask, render_template, request, redirect, url_for, jsonify
import pandas as pd
import os
import time
from datetime import datetime
import calendar
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATABASES = {
    'students.csv': ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'],
    'staff.csv': ['Emp_ID', 'Name', 'Department'],
    'timetable.csv': ['ID', 'Day', 'Time', 'Subject', 'Teacher'],
    'assignments.csv': ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'],
    'attendance.csv': ['Roll_No', 'Date', 'Status'],
    'holidays.csv': ['Date']  # Tracks calendar dates designated as holidays
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
for file, columns in DATABASES.items():
    if not os.path.exists(file):
        pd.DataFrame(columns=columns).to_csv(file, index=False)
    else:
        try:
            df = pd.read_csv(file)
        except Exception:
            df = pd.DataFrame(columns=columns)
        for col in columns:
            if col not in df.columns:
                df[col] = "" if col == 'Profile_Pic' else "12345"
        df.to_csv(file, index=False)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_student_percentage(roll_no, current_month_days):
    """Calculates attendance based strictly on days the college was active."""
    # 1. Determine which dates are active open days (Not Holidays)
    holidays_set = set()
    if os.path.exists('holidays.csv'):
        h_df = pd.read_csv('holidays.csv', dtype=str)
        if not h_df.empty:
            holidays_set = set(h_df['Date'].tolist())
            
    active_open_days = [d for d in current_month_days if d not in holidays_set]
    total_working_days = len(active_open_days)
    
    # 2. Count how many open days the student actually attended
    attended_count = 0
    if os.path.exists('attendance.csv') and total_working_days > 0:
        att_df = pd.read_csv('attendance.csv', dtype=str)
        if not att_df.empty:
            # Filter logs specifically for this student where status is Present ('1')
            s_logs = att_df[(att_df['Roll_No'] == str(roll_no)) & (att_df['Status'] == '1')]
            student_present_dates = s_logs['Date'].tolist()
            
            # Only count presence if the college was actually open that day
            for d in student_present_dates:
                if d in active_open_days:
                    attended_count += 1
                    
    percentage = round((attended_count / total_working_days * 100), 2) if total_working_days > 0 else 0
    return percentage, attended_count, total_working_days

@app.route('/')
def index():
    students_df = pd.read_csv('students.csv', dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str})
    students = students_df.fillna('').to_dict('records')
    staff = pd.read_csv('staff.csv', dtype=str).fillna('').to_dict('records')
    timetable = pd.read_csv('timetable.csv', dtype=str).fillna('').to_dict('records')
    assignments = pd.read_csv('assignments.csv', dtype=str).fillna('').to_dict('records')
    
    now = datetime.now()
    selected_month = int(request.args.get('month', now.month))
    selected_year = int(request.args.get('year', now.year))
    active_tab = request.args.get('active_tab', 'admin_students')
    
    num_days = calendar.monthrange(selected_year, selected_month)[1]
    days_list = [f"{selected_year}-{selected_month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    
    # Load designated holidays
    holidays_df = pd.read_csv('holidays.csv', dtype=str)
    holidays_list = holidays_df['Date'].tolist() if not holidays_df.empty else []
    
    attendance_map = {}
    if os.path.exists('attendance.csv'):
        att_df = pd.read_csv('attendance.csv', dtype=str)
        for _, row in att_df.iterrows():
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

# ================= ASYNC ATTENDANCE SHEET TOGGLE API =================
@app.route('/toggle_attendance', methods=['POST'])
def toggle_attendance():
    roll_no = request.form.get('roll_no')
    date = request.form.get('date')
    status = int(request.form.get('status', 0))
    month = int(request.form.get('month', datetime.now().month))
    year = int(request.form.get('year', datetime.now().year))

    df = pd.read_csv('attendance.csv', dtype=str)
    df = df[~((df['Roll_No'] == str(roll_no)) & (df['Date'] == str(date)))]
    
    new_entry = pd.DataFrame([{'Roll_No': str(roll_no), 'Date': str(date), 'Status': str(status)}])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_csv('attendance.csv', index=False)
    
    # Recalculate baseline dynamically based on current selected month structure
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
    
    df = pd.read_csv('holidays.csv', dtype=str)
    
    if date in df['Date'].values:
        # If it's already a holiday, remove it (make it a normal college day)
        df = df[df['Date'] != date]
    else:
        # Otherwise, save it as a closed college day holiday
        df = pd.concat([df, pd.DataFrame([{'Date': date}])], ignore_index=True)
        
    df.to_csv('holidays.csv', index=False)
    return redirect(url_for('index', month=month, year=year, active_tab='admin_students'))

# ================= IDENTITY LOGIN STUDENT PORTAL DASHBOARD =================
@app.route('/student_login', methods=['POST'])
def student_login():
    roll_no = request.form.get('login_roll_no')
    password = request.form.get('login_password')
    
    df = pd.read_csv('students.csv', dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('')
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

    students = pd.read_csv('students.csv', dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('').to_dict('records')
    staff = pd.read_csv('staff.csv', dtype=str).fillna('').to_dict('records')
    timetable = pd.read_csv('timetable.csv', dtype=str).fillna('').to_dict('records')
    assignments = pd.read_csv('assignments.csv', dtype=str).fillna('').to_dict('records')
    
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
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        df = pd.read_csv('students.csv', dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str})
        df.loc[df['Roll_No'] == str(roll_no), 'Profile_Pic'] = filename
        df.to_csv('students.csv', index=False)
        
    df = pd.read_csv('students.csv', dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('')
    student_row = df[df['Roll_No'] == str(roll_no)].iloc[0]
    percentage, attended, total = calculate_student_percentage(roll_no, days_list)
    
    student_data = {
        'Roll_No': student_row['Roll_No'], 'Name': student_row['Name'], 'Course': student_row['Course'],
        'Profile_Pic': student_row['Profile_Pic'], 'Attendance_Percent': percentage, 'Attended': attended, 'Total_Classes': total
    }
    
    students = pd.read_csv('students.csv', dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str}).fillna('').to_dict('records')
    staff = pd.read_csv('staff.csv', dtype=str).fillna('').to_dict('records')
    timetable = pd.read_csv('timetable.csv', dtype=str).fillna('').to_dict('records')
    assignments = pd.read_csv('assignments.csv', dtype=str).fillna('').to_dict('records')
    
    return render_template(
        'index.html', students=students, staff=staff, timetable=timetable, assignments=assignments, 
        current_student=student_data, active_tab='student_portal', login_error=None,
        days_list=days_list, selected_month=now.month, selected_year=now.year, attendance_map={}, month_name="", holidays_list=[]
    )

# ================= INLINE MANAGEMENT RECORD MODIFIERS =================
@app.route('/edit_student', methods=['POST'])
def edit_student():
    df = pd.read_csv('students.csv', dtype={'Roll_No': str, 'Password': str, 'Profile_Pic': str})
    df.loc[df['Roll_No'] == str(request.form.get('roll_no')), ['Name', 'Course', 'Password']] = [request.form.get('name'), request.form.get('course'), request.form.get('password')]
    df.to_csv('students.csv', index=False)
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/add_student', methods=['POST'])
def add_student():
    roll_no, name, course, password = request.form.get('roll_no'), request.form.get('name'), request.form.get('course'), request.form.get('password', '12345')
    df = pd.read_csv('students.csv', dtype={'Roll_No': str})
    if str(roll_no) not in df['Roll_No'].values:
        df = pd.concat([df, pd.DataFrame([{'Roll_No': str(roll_no), 'Name': name, 'Course': course, 'Password': str(password), 'Profile_Pic': ''}])], ignore_index=True)
        df.to_csv('students.csv', index=False)
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/delete_student/<roll_no>')
def delete_student(roll_no):
    df = pd.read_csv('students.csv', dtype={'Roll_No': str})
    df = df[df['Roll_No'] != str(roll_no)]
    df.to_csv('students.csv', index=False)
    return redirect(url_for('index', active_tab='admin_students'))

@app.route('/edit_staff', methods=['POST'])
def edit_staff():
    df = pd.read_csv('staff.csv', dtype=str)
    df.loc[df['Emp_ID'] == str(request.form.get('emp_id')), ['Name', 'Department']] = [request.form.get('name'), request.form.get('department')]
    df.to_csv('staff.csv', index=False)
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/add_staff', methods=['POST'])
def add_staff():
    df = pd.read_csv('staff.csv', dtype=str)
    if str(request.form.get('emp_id')) not in df['Emp_ID'].values:
        df = pd.concat([df, pd.DataFrame([{'Emp_ID': str(request.form.get('emp_id')), 'Name': request.form.get('name'), 'Department': request.form.get('department')}])], ignore_index=True)
        df.to_csv('staff.csv', index=False)
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/delete_staff/<emp_id>')
def delete_staff(emp_id):
    df = pd.read_csv('staff.csv', dtype=str)
    df = df[df['Emp_ID'] != str(emp_id)]
    df.to_csv('staff.csv', index=False)
    return redirect(url_for('index', active_tab='admin_staff'))

@app.route('/edit_timetable', methods=['POST'])
def edit_timetable():
    df = pd.read_csv('timetable.csv', dtype=str)
    df.loc[df['ID'] == str(request.form.get('id')), ['Day', 'Time', 'Subject', 'Teacher']] = [request.form.get('day'), request.form.get('time'), request.form.get('subject'), request.form.get('teacher')]
    df.to_csv('timetable.csv', index=False)
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/add_timetable', methods=['POST'])
def add_timetable():
    df = pd.read_csv('timetable.csv', dtype=str)
    df = pd.concat([df, pd.DataFrame([{'ID': str(int(time.time())), 'Day': request.form.get('day'), 'Time': request.form.get('time'), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher')}])], ignore_index=True)
    df.to_csv('timetable.csv', index=False)
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/delete_timetable/<entry_id>')
def delete_timetable(entry_id):
    df = pd.read_csv('timetable.csv', dtype=str)
    df = df[df['ID'] != str(entry_id)]
    df.to_csv('timetable.csv', index=False)
    return redirect(url_for('index', active_tab='admin_timetable'))

@app.route('/edit_assignment', methods=['POST'])
def edit_assignment():
    df = pd.read_csv('assignments.csv', dtype=str)
    df.loc[df['ID'] == str(request.form.get('id')), ['Subject', 'Teacher', 'Deadline', 'Question']] = [request.form.get('subject'), request.form.get('teacher'), request.form.get('deadline'), request.form.get('question')]
    df.to_csv('assignments.csv', index=False)
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/add_assignment', methods=['POST'])
def add_assignment():
    df = pd.read_csv('assignments.csv', dtype=str)
    df = pd.concat([df, pd.DataFrame([{'ID': str(int(time.time())), 'Subject': request.form.get('subject'), 'Teacher': request.form.get('teacher'), 'Deadline': request.form.get('deadline'), 'Question': request.form.get('question')}])], ignore_index=True)
    df.to_csv('assignments.csv', index=False)
    return redirect(url_for('index', active_tab='admin_assignments'))

@app.route('/delete_assignment/<entry_id>')
def delete_assignment(entry_id):
    df = pd.read_csv('assignments.csv', dtype=str)
    df = df[df['ID'] != str(entry_id)]
    df.to_csv('assignments.csv', index=False)
    return redirect(url_for('index', active_tab='admin_assignments'))

if __name__ == '__main__':
    app.run(debug=True)
if __name__ == '__main__':
    # Automatically binds to the port provided by the live server
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False) # debug must be False online
# Update your app.py file paths at the top to match Render's Secret Directory
DATABASES = {
    '/etc/secrets/students.csv': ['Roll_No', 'Name', 'Course', 'Password', 'Profile_Pic'],
    '/etc/secrets/staff.csv': ['Emp_ID', 'Name', 'Department'],
    '/etc/secrets/timetable.csv': ['ID', 'Day', 'Time', 'Subject', 'Teacher'],
    '/etc/secrets/assignments.csv': ['ID', 'Subject', 'Teacher', 'Deadline', 'Question'],
    '/etc/secrets/attendance.csv': ['Roll_No', 'Date', 'Status'],
    '/etc/secrets/holidays.csv': ['Date']
}