from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import os
import time

app = Flask(__name__)

# Updated databases: Added Total_Classes and Attended to students
DATABASES = {
    'students.csv': ['Roll_No', 'Name', 'Course', 'Total_Classes', 'Attended'],
    'staff.csv': ['Emp_ID', 'Name', 'Department'],
    'timetable.csv': ['ID', 'Day', 'Time', 'Subject', 'Teacher'],
    'assignments.csv': ['ID', 'Subject', 'Teacher', 'Deadline', 'Question']
}

for file, columns in DATABASES.items():
    if not os.path.exists(file):
        pd.DataFrame(columns=columns).to_csv(file, index=False)

@app.route('/')
def index():
    students = pd.read_csv('students.csv').to_dict('records')
    staff = pd.read_csv('staff.csv').to_dict('records')
    timetable = pd.read_csv('timetable.csv').to_dict('records')
    assignments = pd.read_csv('assignments.csv').to_dict('records')
    
    # default_tab helps the page stay on the right tab after refreshing
    return render_template('index.html', students=students, staff=staff, 
                           timetable=timetable, assignments=assignments, 
                           current_student=None, active_tab='admin_students')

# ================= ADMIN: STUDENTS & ATTENDANCE =================
@app.route('/add_student', methods=['POST'])
def add_student():
    roll_no = request.form.get('roll_no')
    name = request.form.get('name')
    course = request.form.get('course')
    df = pd.read_csv('students.csv')
    
    if str(roll_no) not in df['Roll_No'].astype(str).values:
        # New students start with 0 attendance
        new_data = pd.DataFrame([{'Roll_No': roll_no, 'Name': name, 'Course': course, 'Total_Classes': 0, 'Attended': 0}])
        df = pd.concat([df, new_data], ignore_index=True)
        df.to_csv('students.csv', index=False)
    return redirect(url_for('index'))

@app.route('/update_attendance', methods=['POST'])
def update_attendance():
    roll_no = request.form.get('roll_no')
    total = request.form.get('total_classes')
    attended = request.form.get('attended')
    
    df = pd.read_csv('students.csv')
    # Update the specific student's attendance
    df.loc[df['Roll_No'].astype(str) == str(roll_no), ['Total_Classes', 'Attended']] = [int(total), int(attended)]
    df.to_csv('students.csv', index=False)
    return redirect(url_for('index'))

@app.route('/delete_student/<roll_no>')
def delete_student(roll_no):
    df = pd.read_csv('students.csv')
    df = df[df['Roll_No'].astype(str) != str(roll_no)]
    df.to_csv('students.csv', index=False)
    return redirect(url_for('index'))

# ================= OTHER ADMIN ROUTES =================
# (Staff, Timetable, Assignments adding/deleting logic remains the same)
@app.route('/add_staff', methods=['POST'])
def add_staff():
    emp_id = request.form.get('emp_id')
    name = request.form.get('name')
    department = request.form.get('department')
    df = pd.read_csv('staff.csv')
    if str(emp_id) not in df['Emp_ID'].astype(str).values:
        new_data = pd.DataFrame([{'Emp_ID': emp_id, 'Name': name, 'Department': department}])
        df = pd.concat([df, new_data], ignore_index=True)
        df.to_csv('staff.csv', index=False)
    return redirect(url_for('index'))

@app.route('/delete_staff/<emp_id>')
def delete_staff(emp_id):
    df = pd.read_csv('staff.csv')
    df = df[df['Emp_ID'].astype(str) != str(emp_id)]
    df.to_csv('staff.csv', index=False)
    return redirect(url_for('index'))

@app.route('/add_timetable', methods=['POST'])
def add_timetable():
    day = request.form.get('day'); time_slot = request.form.get('time')
    subject = request.form.get('subject'); teacher = request.form.get('teacher')
    entry_id = str(int(time.time())) 
    df = pd.read_csv('timetable.csv')
    new_data = pd.DataFrame([{'ID': entry_id, 'Day': day, 'Time': time_slot, 'Subject': subject, 'Teacher': teacher}])
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv('timetable.csv', index=False)
    return redirect(url_for('index'))

@app.route('/delete_timetable/<entry_id>')
def delete_timetable(entry_id):
    df = pd.read_csv('timetable.csv')
    df = df[df['ID'].astype(str) != str(entry_id)]
    df.to_csv('timetable.csv', index=False)
    return redirect(url_for('index'))

@app.route('/add_assignment', methods=['POST'])
def add_assignment():
    subject = request.form.get('subject'); teacher = request.form.get('teacher')
    deadline = request.form.get('deadline'); question = request.form.get('question')
    entry_id = str(int(time.time())) 
    df = pd.read_csv('assignments.csv')
    new_data = pd.DataFrame([{'ID': entry_id, 'Subject': subject, 'Teacher': teacher, 'Deadline': deadline, 'Question': question}])
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv('assignments.csv', index=False)
    return redirect(url_for('index'))

@app.route('/delete_assignment/<entry_id>')
def delete_assignment(entry_id):
    df = pd.read_csv('assignments.csv')
    df = df[df['ID'].astype(str) != str(entry_id)]
    df.to_csv('assignments.csv', index=False)
    return redirect(url_for('index'))

# ================= STUDENT PORTAL ROUTE =================
@app.route('/student_login', methods=['POST'])
def student_login():
    roll_no = request.form.get('login_roll_no')
    df = pd.read_csv('students.csv')
    
    student_data = None
    # Check if student exists
    if str(roll_no) in df['Roll_No'].astype(str).values:
        student_row = df[df['Roll_No'].astype(str) == str(roll_no)].iloc[0]
        
        # Calculate percentage safely
        total = int(student_row['Total_Classes'])
        attended = int(student_row['Attended'])
        percentage = round((attended / total * 100), 2) if total > 0 else 0
        
        student_data = {
            'Roll_No': student_row['Roll_No'],
            'Name': student_row['Name'],
            'Course': student_row['Course'],
            'Attendance_Percent': percentage
        }

    # Fetch global data for the dashboard
    students = pd.read_csv('students.csv').to_dict('records')
    staff = pd.read_csv('staff.csv').to_dict('records')
    timetable = pd.read_csv('timetable.csv').to_dict('records')
    assignments = pd.read_csv('assignments.csv').to_dict('records')
    
    # Keep the view locked onto the student portal tab
    return render_template('index.html', students=students, staff=staff, 
                           timetable=timetable, assignments=assignments, 
                           current_student=student_data, active_tab='student_portal')

if __name__ == '__main__':
    app.run(debug=True)