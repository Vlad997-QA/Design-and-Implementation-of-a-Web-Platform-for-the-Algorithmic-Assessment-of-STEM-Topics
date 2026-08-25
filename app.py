from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os

# Importăm funcția ta magică de OCR!
from ocr_engine import extrage_text_din_poza

app = Flask(__name__)
app.secret_key = 'cheie_secreta_super_sigura'

def init_db():
    conn = sqlite3.connect('baza_date.db', timeout=10)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA foreign_keys = ON;') 
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS utilizatori (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    rol TEXT NOT NULL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sarcini_teme (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_profesor INTEGER NOT NULL,
                    titlu TEXT NOT NULL,
                    tip_evaluare TEXT NOT NULL,
                    output_asteptat TEXT,
                    FOREIGN KEY (id_profesor) REFERENCES utilizatori(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS trimiteri (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_student INTEGER NOT NULL,
                    id_sarcina INTEGER NOT NULL,
                    nota REAL,
                    status_executie TEXT,
                    justificare_nota TEXT,
                    FOREIGN KEY (id_student) REFERENCES utilizatori(id),
                    FOREIGN KEY (id_sarcina) REFERENCES sarcini_teme(id))''')
    
    c.execute("INSERT OR IGNORE INTO utilizatori (username, password, rol) VALUES ('admin', 'admin123', 'admin')")
    c.execute("INSERT OR IGNORE INTO utilizatori (username, password, rol) VALUES ('profesor1', '1234', 'profesor')")
    c.execute("INSERT OR IGNORE INTO utilizatori (username, password, rol) VALUES ('student1', '1234', 'student')")
    
    conn.commit()
    conn.close()

@app.route('/', methods=['GET', 'POST'])
def login():
    eroare = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('baza_date.db')
        c = conn.cursor()
        c.execute("SELECT * FROM utilizatori WHERE username = ? AND password = ?", (username, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['rol'] = user[3]
            
            if session['rol'] == 'admin':
                return redirect(url_for('dashboard_admin'))
            elif session['rol'] == 'profesor':
                return redirect(url_for('dashboard_profesor'))
            else:
                return redirect(url_for('dashboard_student'))
        else:
            eroare = "Date incorecte!"
            
    return render_template('login.html', eroare=eroare)

# RUTA PROFESOR ACTUALIZATĂ CU OCR
@app.route('/profesor', methods=['GET', 'POST'])
def dashboard_profesor():
    if 'rol' not in session or session['rol'] != 'profesor':
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        titlu = request.form['titlu']
        tip_evaluare = request.form['tip_evaluare']
        barem_tastat = request.form.get('output_asteptat', '')
        
        # Logica pentru preluarea pozei
        poza = request.files.get('barem_poza')
        barem_final = barem_tastat # Setăm implicit textul tastat
        
        if poza and poza.filename != '':
            # Creăm un folder temporar dacă nu există
            if not os.path.exists('uploads'):
                os.makedirs('uploads')
                
            cale_salvare = os.path.join('uploads', poza.filename)
            poza.save(cale_salvare)
            
            # MAGIA SE ÎNTÂMPLĂ AICI: Trecem poza prin OCR
            text_extras = extrage_text_din_poza(cale_salvare)
            barem_final = text_extras # Înlocuim baremul cu ce a citit AI-ul din poză!
            print(f"[Server] Barem extras automat din poză: {barem_final}")

        # Salvăm în baza de date rezultatul final (fie el tastat sau extras din poză)
        conn = sqlite3.connect('baza_date.db')
        c = conn.cursor()
        c.execute("INSERT INTO sarcini_teme (id_profesor, titlu, tip_evaluare, output_asteptat) VALUES (?, ?, ?, ?)", 
                  (session['user_id'], titlu, tip_evaluare, barem_final))
        conn.commit()
        conn.close()
        
    return render_template('dashboard_profesor.html')

# Sus de tot in app.py, asigura-te ca ai importat ambele functii din ocr_engine:
from ocr_engine import extrage_text_din_poza, evalueaza_rezolvarea

# --- CODUL NOU PENTRU RUTA STUDENT ---
@app.route('/student', methods=['GET', 'POST'])
def dashboard_student():
    if 'rol' not in session or session['rol'] != 'student':
        return redirect(url_for('login'))
        
    mesaj = None
    rezultat_evaluare = None # Aici vom stoca NOTA finală
    
    if request.method == 'POST':
        fisier = request.files.get('fisier_tema')
        if fisier and fisier.filename != '':
            if not os.path.exists('uploads'):
                os.makedirs('uploads')
            cale_salvare = os.path.join('uploads', fisier.filename)
            fisier.save(cale_salvare)
            
            # MAGIA EVALUĂRII AUTOMATE ÎNCEPE AICI:
            # 1. Extragem ce a scris elevul în poză
            text_elev = extrage_text_din_poza(cale_salvare)
            
            # 2. Luăm baremul profesorului din baza de date (pentru simplitate, preluăm ultima temă adăugată)
            conn = sqlite3.connect('baza_date.db')
            c = conn.cursor()
            c.execute("SELECT output_asteptat FROM sarcini_teme ORDER BY id DESC LIMIT 1")
            sarcina = c.fetchone()
            conn.close()
            
            # 3. Comparăm și obținem nota
            if sarcina:
                barem_profesor = sarcina[0]
                print(f"[Server] Barem din DB: {barem_profesor} | Text elev: {text_elev}")
                # Apelăm funcția din ocr_engine.py
                rezultat_evaluare = evalueaza_rezolvarea(text_elev, barem_profesor)
                mesaj = "Fișier procesat cu succes de Inteligența Artificială!"
            else:
                mesaj = "Eroare: Profesorul nu a setat încă niciun barem."
            
    return render_template('dashboard_student.html', mesaj=mesaj, rezultat_evaluare=rezultat_evaluare)

@app.route('/admin')
def dashboard_admin():
    # Verificăm dacă e logat și dacă e admin
    if 'rol' not in session or session['rol'] != 'admin':
        return redirect(url_for('login'))
    return render_template('dashboard_admin.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    if not os.path.exists('baza_date.db'):
        init_db()
    app.run(debug=True)