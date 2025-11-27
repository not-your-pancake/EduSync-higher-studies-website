  import os
  from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
  import mysql.connector
  from datetime import datetime

  app = Flask(__name__)
  app.secret_key = os.urandom(24)

  # --- Database Connection ---
  def get_db_connection():
      # In Replit, use Secrets for these values
      return mysql.connector.connect(
          host=os.environ.get('DB_HOST', 'localhost'),
          user=os.environ.get('DB_USER', 'root'),
          password=os.environ.get('DB_PASSWORD', ''),
          database=os.environ.get('DB_NAME', 'edusync')
      )

  # --- Routes: Landing & Auth ---

  @app.route('/')
  def landing():
      return render_template('landing.html')

  @app.route('/login/<role>', methods=['GET', 'POST'])
  def login(role):
      if request.method == 'POST':
          email = request.form['email']
          password = request.form['password']

          conn = get_db_connection()
          cursor = conn.cursor(dictionary=True)
          # SQL Query: Check user credentials
          query = "SELECT * FROM users WHERE email = %s AND password = %s AND role = %s"
          cursor.execute(query, (email, password, role))
          user = cursor.fetchone()
          cursor.close()
          conn.close()

          if user:
              session['user_id'] = user['id']
              session['role'] = user['role']
              session['name'] = user['first_name']

              # Role-based redirection
              if role == 'student':
                  return redirect(url_for('student_dashboard'))
              elif role == 'employee':
                  return redirect(url_for('employee_dashboard'))
              elif role == 'admin':
                  return redirect(url_for('admin_dashboard'))
          else:
              flash('Invalid credentials')

      return render_template('auth.html', mode='login', role=role)

  @app.route('/signup/<role>', methods=['GET', 'POST'])
  def signup(role):
      if request.method == 'POST':
          first_name = request.form['first_name']
          email = request.form['email']
          password = request.form['password']

          conn = get_db_connection()
          cursor = conn.cursor()
          try:
              # SQL Query: Create User
              cursor.execute(
                  "INSERT INTO users (first_name, email, password, role) VALUES (%s, %s, %s, %s)",
                  (first_name, email, password, role)
              )
              conn.commit()

              # If student, handle swiped universities from Guest session if passed
              user_id = cursor.lastrowid

              # Initialize Personal Info row
              cursor.execute("INSERT INTO personal_info (user_id) VALUES (%s)", (user_id,))
              conn.commit()

              flash('Account created! Please login.')
              return redirect(url_for('login', role=role))
          except Exception as e:
              flash(f'Error: {str(e)}')
          finally:
              cursor.close()
              conn.close()

      return render_template('auth.html', mode='signup', role=role)

  @app.route('/logout')
  def logout():
      session.clear()
      return redirect(url_for('landing'))

  # --- Routes: Student Flow ---

  @app.route('/student/dashboard')
  def student_dashboard():
      if 'user_id' not in session or session['role'] != 'student':
          return redirect(url_for('landing'))

      conn = get_db_connection()
      cursor = conn.cursor(dictionary=True)

      # SQL Query: Get swiped universities with progress
      cursor.execute("""
          SELECT u.name, s.status, s.application_status, s.progress, u.id as uni_id
          FROM swiped_universities s
          JOIN universities u ON s.university_id = u.id
          WHERE s.student_id = %s AND s.status = 'liked'
      """, (session['user_id'],))
      applications = cursor.fetchall()

      cursor.close()
      conn.close()
      return render_template('student_dashboard.html', applications=applications)

  @app.route('/student/swipe')
  def swipe_university():
      # Logic: Fetch random universities not yet swiped
      conn = get_db_connection()
      cursor = conn.cursor(dictionary=True)
      cursor.execute("SELECT * FROM universities LIMIT 10") # Simplified for prototype
      universities = cursor.fetchall()
      cursor.close()
      conn.close()
      return render_template('swipe.html', universities=universities)

  @app.route('/api/swipe', methods=['POST'])
  def api_swipe():
      data = request.json
      status = data.get('status') # 'liked' or 'rejected'
      uni_id = data.get('uni_id')

      if 'user_id' in session:
          conn = get_db_connection()
          cursor = conn.cursor()
          cursor.execute(
              "INSERT INTO swiped_universities (student_id, university_id, status) VALUES (%s, %s, %s)",
              (session['user_id'], uni_id, status)
          )
          conn.commit()
          conn.close()
          return jsonify({'msg': 'Saved'})
      return jsonify({'msg': 'Guest swipe stored locally'})

  # --- Routes: Employee Flow ---

  @app.route('/employee/dashboard')
  def employee_dashboard():
      if 'user_id' not in session or session['role'] != 'employee':
          return redirect(url_for('landing'))

      conn = get_db_connection()
      cursor = conn.cursor(dictionary=True)

      # SQL Query: Get students allocated to this employee
      cursor.execute("""
          SELECT u.id, u.first_name, u.last_name, u.email
          FROM allocations a
          JOIN users u ON a.student_id = u.id
          WHERE a.employee_id = %s
      """, (session['user_id'],))
      my_students = cursor.fetchall()

      cursor.close()
      conn.close()
      return render_template('employee_dashboard.html', students=my_students)

  @app.route('/employee/student/<int:student_id>')
  def view_student_package(student_id):
      # The "Work" button view - Read Only Package
      conn = get_db_connection()
      cursor = conn.cursor(dictionary=True)

      # Get Personal Info
      cursor.execute("SELECT * FROM personal_info WHERE user_id = %s", (student_id,))
      info = cursor.fetchone()

      # Get Desired Universities
      cursor.execute("""
          SELECT u.name, s.application_status, s.progress, s.id as swipe_id
          FROM swiped_universities s
          JOIN universities u ON s.university_id = u.id
          WHERE s.student_id = %s AND s.status = 'liked'
      """, (student_id,))
      unis = cursor.fetchall()

      cursor.close()
      conn.close()
      return render_template('student_package.html', info=info, unis=unis, student_id=student_id)

  @app.route('/api/update_progress', methods=['POST'])
  def update_progress():
      # Employee updates progress bar
      data = request.json
      swipe_id = data.get('swipe_id')
      progress = data.get('progress') # 0-100

      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute("UPDATE swiped_universities SET progress = %s WHERE id = %s", (progress, swipe_id))
      conn.commit()
      conn.close()
      return jsonify({'msg': 'Progress Updated'})

  # --- Routes: Admin Flow ---

  @app.route('/admin/dashboard')
  def admin_dashboard():
      if session.get('role') != 'admin':
          return redirect(url_for('landing'))

      conn = get_db_connection()
      cursor = conn.cursor(dictionary=True)

      # Get unallocated students who have requested applications
      cursor.execute("""
          SELECT DISTINCT u.id, u.first_name, u.last_name 
          FROM users u
          JOIN swiped_universities s ON u.id = s.student_id
          LEFT JOIN allocations a ON u.id = a.student_id
          WHERE s.application_status = 'requested' AND a.id IS NULL
      """)
      unallocated_students = cursor.fetchall()

      # Get all employees
      cursor.execute("SELECT id, first_name FROM users WHERE role = 'employee'")
      employees = cursor.fetchall()

      cursor.close()
      conn.close()
      return render_template('admin_dashboard.html', students=unallocated_students, employees=employees)

  @app.route('/admin/allocate', methods=['POST'])
  def allocate_student():
      student_id = request.form['student_id']
      employee_id = request.form['employee_id']

      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute("INSERT INTO allocations (student_id, employee_id) VALUES (%s, %s)", (student_id, employee_id))
      conn.commit()
      conn.close()
      return redirect(url_for('admin_dashboard'))

  # --- Routes: Chat (Universal) ---
  @app.route('/chat')
  def chat_view():
      return render_template('chat.html')

  @app.route('/api/messages/<int:partner_id>')
  def get_messages(partner_id):
      user_id = session['user_id']
      conn = get_db_connection()
      cursor = conn.cursor(dictionary=True)
      cursor.execute("""
          SELECT * FROM messages 
          WHERE (sender_id = %s AND receiver_id = %s) 
             OR (sender_id = %s AND receiver_id = %s)
          ORDER BY timestamp ASC
      """, (user_id, partner_id, partner_id, user_id))
      msgs = cursor.fetchall()
      conn.close()
      return jsonify(msgs)

  if __name__ == '__main__':
      app.run(host='0.0.0.0', port=8080)