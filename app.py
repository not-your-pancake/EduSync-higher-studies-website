import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash

app = Flask(__name__)
app.secret_key = 'edusync_secret_key'

# --- DB CONFIG ---
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='root', # <--- PUT YOUR MYSQL PASSWORD HERE
        database='edusync'
    )

# --- AUTH ROUTES ---
@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email=%s AND password=%s AND role=%s", 
                      (request.form['email'], request.form['password'], role))
        user = cursor.fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['first_name']
            return redirect(url_for('feed'))
        else:
            flash('Invalid credentials')
    return render_template('auth.html', mode='login', role=role)

@app.route('/signup/<role>', methods=['GET', 'POST'])
def signup(role):
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (first_name, email, password, role) VALUES (%s, %s, %s, %s)",
                          (request.form['first_name'], request.form['email'], request.form['password'], role))
            conn.commit()
            uid = cursor.lastrowid
            cursor.execute("INSERT INTO personal_info (user_id) VALUES (%s)", (uid,))
            conn.commit()
            flash('Account created! Please login.')
            return redirect(url_for('login', role=role))
        except Exception as e:
            flash(str(e))
        finally:
            conn.close()
    return render_template('auth.html', mode='signup', role=role)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

# --- UNIVERSAL FEED (Pages 2, 6, 14, 20) ---
@app.route('/feed')
def feed():
    role = session.get('role', 'guest')
    # Mock posts for the feed
    posts = [
        {'author': 'Admin Team', 'time': '2h ago', 'content': 'University applications closing soon!', 'color': 'bg-red-100'},
        {'author': 'System', 'time': '5h ago', 'content': 'New top-ranked universities added.', 'color': 'bg-blue-100'}
    ]
    return render_template('feed.html', role=role, posts=posts)

# --- CONNECTIONS (Pages 10, 16, 23) ---
@app.route('/connections')
def connections():
    if 'user_id' not in session: return redirect(url_for('landing'))
    uid = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Logic: Get Followers, Following, and Suggestions
    cursor.execute("SELECT u.id, u.first_name, u.role FROM connections c JOIN users u ON c.follower_id=u.id WHERE c.following_id=%s", (uid,))
    followers = cursor.fetchall()
    cursor.execute("SELECT u.id, u.first_name, u.role FROM connections c JOIN users u ON c.following_id=u.id WHERE c.follower_id=%s", (uid,))
    following = cursor.fetchall()
    cursor.execute("SELECT id, first_name, role FROM users WHERE id!=%s LIMIT 5", (uid,))
    suggestions = cursor.fetchall()
    conn.close()
    return render_template('connections.html', followers=followers, following=following, suggestions=suggestions)

@app.route('/api/connection/<action>', methods=['POST'])
def manage_conn(action):
    data = request.json
    me = session['user_id']
    target = data['target_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    if action == 'add':
        cursor.execute("INSERT IGNORE INTO connections (follower_id, following_id) VALUES (%s, %s)", (me, target))
    else:
        cursor.execute("DELETE FROM connections WHERE follower_id=%s AND following_id=%s", (me, target))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

# --- CHAT (Pages 11, 15, 22) ---
@app.route('/chat')
def chat():
    return render_template('chat.html')

@app.route('/api/contacts')
def contacts():
    # Chat shows people you are connected with
    uid = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT DISTINCT u.id, u.first_name, u.role FROM users u 
        JOIN connections c ON (c.follower_id=u.id AND c.following_id=%s) 
                           OR (c.following_id=u.id AND c.follower_id=%s)
    """, (uid, uid))
    res = cursor.fetchall()
    conn.close()
    return jsonify(res)

@app.route('/api/messages/<int:pid>')
def get_msgs(pid):
    uid = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM messages WHERE (sender_id=%s AND receiver_id=%s) OR (sender_id=%s AND receiver_id=%s) ORDER BY timestamp ASC", (uid, pid, pid, uid))
    res = cursor.fetchall()
    conn.close()
    return jsonify(res)

@app.route('/api/messages/send', methods=['POST'])
def send_msg():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (sender_id, receiver_id, content) VALUES (%s, %s, %s)", (session['user_id'], data['rid'], data['content']))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

# --- STUDENT FEATURES ---
@app.route('/student/swipe')
def swipe():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if 'user_id' in session:
        # Don't show already swiped
        cursor.execute("SELECT * FROM universities WHERE id NOT IN (SELECT university_id FROM swiped_universities WHERE student_id=%s)", (session['user_id'],))
    else:
        cursor.execute("SELECT * FROM universities LIMIT 10")
    unis = cursor.fetchall()
    conn.close()
    return render_template('swipe.html', universities=unis)

@app.route('/api/swipe', methods=['POST'])
def api_swipe():
    data = request.json
    if 'user_id' not in session and data['status'] == 'liked':
        return jsonify({'result': 'guest_blocked'})
    
    if 'user_id' in session:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Auto-set status to 'requested' so it appears in Admin dashboard immediately
        cursor.execute("INSERT IGNORE INTO swiped_universities (student_id, university_id, status, application_status) VALUES (%s, %s, %s, 'requested')", 
                      (session['user_id'], data['uni_id'], data['status']))
        conn.commit()
        conn.close()
    return jsonify({'result': 'saved'})

@app.route('/student/dashboard')
def student_dash():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT u.name, s.status, s.application_status, s.progress FROM swiped_universities s JOIN universities u ON s.university_id = u.id WHERE s.student_id=%s AND s.status='liked'", (session['user_id'],))
    apps = cursor.fetchall()
    conn.close()
    return render_template('student_dashboard.html', applications=apps)

@app.route('/student/profile', methods=['GET', 'POST'])
def profile():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        cursor.execute("UPDATE personal_info SET passport_number=%s, school_name=%s, ielts_score=%s, sat_score=%s WHERE user_id=%s",
                      (request.form['passport'], request.form['school'], request.form['ielts'], request.form['sat'], session['user_id']))
        conn.commit()
    cursor.execute("SELECT * FROM personal_info WHERE user_id=%s", (session['user_id'],))
    info = cursor.fetchone()
    conn.close()
    return render_template('personal_info.html', info=info)

# --- EMPLOYEE FEATURES ---
@app.route('/employee/dashboard')
def employee_dash():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT u.id, u.first_name, u.email FROM allocations a JOIN users u ON a.student_id=u.id WHERE a.employee_id=%s", (session['user_id'],))
    students = cursor.fetchall()
    conn.close()
    return render_template('employee_dashboard.html', students=students)

@app.route('/employee/student/<int:sid>')
def work_student(sid):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM personal_info WHERE user_id=%s", (sid,))
    info = cursor.fetchone()
    cursor.execute("SELECT u.name, s.progress, s.id as swipe_id FROM swiped_universities s JOIN universities u ON s.university_id=u.id WHERE s.student_id=%s", (sid,))
    unis = cursor.fetchall()
    conn.close()
    return render_template('student_package.html', info=info, unis=unis)

@app.route('/api/update_progress', methods=['POST'])
def update_prog():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE swiped_universities SET progress=%s WHERE id=%s", (data['progress'], data['swipe_id']))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

# --- ADMIN FEATURES ---
@app.route('/admin/dashboard')
def admin_dash():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Get unallocated requests
    cursor.execute("SELECT DISTINCT u.id, u.first_name FROM users u JOIN swiped_universities s ON u.id=s.student_id LEFT JOIN allocations a ON u.id=a.student_id WHERE s.application_status='requested' AND a.id IS NULL")
    reqs = cursor.fetchall()
    cursor.execute("SELECT id, first_name FROM users WHERE role='employee'")
    emps = cursor.fetchall()
    conn.close()
    return render_template('admin_dashboard.html', students=reqs, employees=emps)

@app.route('/admin/allocate', methods=['POST'])
def allocate():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO allocations (student_id, employee_id) VALUES (%s, %s)", (request.form['sid'], request.form['eid']))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dash'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)