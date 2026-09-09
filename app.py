import os
import secrets
import sqlite3

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from ocr_engine import extrage_text_din_poza, evalueaza_grila_text, tesseract_disponibil, OCRError
from evaluator import evaluate_python_code, evaluate_math_expression

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True  # <--- ADAUGĂ ACEASTĂ LINIE

# Cheia de sesiune trebuie sa vina dintr-o variabila de mediu in productie.
# Daca nu e setata, generam una temporara (valabila doar cat ruleaza procesul) -
# suficient pentru dezvoltare, dar SETATI SECRET_KEY in mediu pentru productie.
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

UPLOAD_FOLDER = 'uploads'
EXTENSII_PERMISE_TEMA = {'py', 'png', 'jpg', 'jpeg'}
EXTENSII_PERMISE_IMAGINE = {'png', 'jpg', 'jpeg'}


def extensie_permisa(filename, extensii_permise):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in extensii_permise


def _asigura_coloana(conn, tabel, coloana, definitie_sql):
    """
    Adauga o coloana la o tabela existenta daca aceasta nu exista deja.
    Necesar pentru baze de date create cu o versiune mai veche a schemei -
    'CREATE TABLE IF NOT EXISTS' nu modifica structura unei tabele existente.
    """
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({tabel})")
    coloane_existente = {rand[1] for rand in c.fetchall()}
    if coloana not in coloane_existente:
        c.execute(f"ALTER TABLE {tabel} ADD COLUMN {coloana} {definitie_sql}")
        conn.commit()


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
                    data_trimitere TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (id_student) REFERENCES utilizatori(id),
                    FOREIGN KEY (id_sarcina) REFERENCES sarcini_teme(id))''')

    # 'CREATE TABLE IF NOT EXISTS' nu modifica o tabela care exista deja.
    # Daca 'trimiteri' a fost creata cu o versiune mai veche a schemei
    # (fara coloana data_trimitere), o adaugam acum, ca sa nu pice query-urile
    # care o folosesc. SQLite nu permite DEFAULT CURRENT_TIMESTAMP la ALTER
    # TABLE ADD COLUMN (doar la CREATE TABLE), deci aici adaugam coloana fara
    # default - data se completeaza explicit la fiecare INSERT, mai jos.
    _asigura_coloana(conn, 'trimiteri', 'data_trimitere', "TEXT")

    # Utilizatori demo, cu parole hash-uite (NU in clar, ca inainte).
    utilizatori_demo = [
        ('admin', 'admin123', 'admin'),
        ('profesor1', '1234', 'profesor'),
        ('student1', '1234', 'student'),
    ]
    for username, parola, rol in utilizatori_demo:
        c.execute("SELECT id FROM utilizatori WHERE username = ?", (username,))
        if c.fetchone() is None:
            c.execute(
                "INSERT INTO utilizatori (username, password, rol) VALUES (?, ?, ?)",
                (username, generate_password_hash(parola), rol),
            )

    conn.commit()
    _migreaza_parole_in_clar(conn)
    conn.close()


def _migreaza_parole_in_clar(conn):
    """
    Upgrade automat pentru baze de date create cu o versiune veche a
    aplicatiei (parole salvate in clar). Fara asta, login-ul pica pentru
    conturile deja existente, pentru ca check_password_hash() nu poate
    compara cu text simplu - orice utilizator ramas cu parola veche in DB
    nu s-ar mai putea autentifica dupa actualizarea codului.
    Un hash Werkzeug are mereu forma "metoda:parametri$salt$hash"; daca nu
    gasim acest format, presupunem ca valoarea e inca text simplu si o
    hash-uim, pastrand username-ul, rolul si restul datelor neschimbate.
    """
    c = conn.cursor()
    c.execute("SELECT id, password FROM utilizatori")
    utilizatori = c.fetchall()

    for user_id, parola_stocata in utilizatori:
        e_deja_hash = parola_stocata and ':' in parola_stocata and '$' in parola_stocata
        if not e_deja_hash:
            c.execute(
                "UPDATE utilizatori SET password = ? WHERE id = ?",
                (generate_password_hash(parola_stocata), user_id),
            )
    conn.commit()


@app.route('/', methods=['GET', 'POST'])
def login():
    eroare = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('baza_date.db')
        c = conn.cursor()
        c.execute("SELECT id, username, password, rol FROM utilizatori WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
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


@app.route('/profesor', methods=['GET', 'POST'])
def dashboard_profesor():
    if 'rol' not in session or session['rol'] != 'profesor':
        return redirect(url_for('login'))

    if request.method == 'POST':
        titlu = request.form.get('titlu', 'Tema Noua')
        tip_evaluare = request.form.get('tip_evaluare', 'General')
        barem_tastat = request.form.get('output_asteptat', '').strip()

        barem_final = barem_tastat
        poza = request.files.get('barem_poza')

        if poza and poza.filename != '':
            if extensie_permisa(poza.filename, EXTENSII_PERMISE_IMAGINE):
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                nume_fisier = secure_filename(poza.filename)
                cale_salvare = os.path.join(UPLOAD_FOLDER, nume_fisier)
                poza.save(cale_salvare)
                try:
                    text_extras = extrage_text_din_poza(cale_salvare)
                    if text_extras:
                        barem_final = text_extras
                except OCRError as e:
                    print(f"[Server] OCR indisponibil pentru barem, folosim textul tastat. Detalii: {e}")

        if not barem_final:
            barem_final = "1a,2b,3c,4b,5a"
            print("[Server] Atentie: niciun barem tastat sau extras prin OCR - se foloseste un barem implicit.")

        conn = sqlite3.connect('baza_date.db')
        c = conn.cursor()
        c.execute(
            "INSERT INTO sarcini_teme (id_profesor, titlu, tip_evaluare, output_asteptat) VALUES (?, ?, ?, ?)",
            (session['user_id'], titlu, tip_evaluare, barem_final),
        )
        conn.commit()
        conn.close()

    conn = sqlite3.connect('baza_date.db')
    c = conn.cursor()
    c.execute(
        "SELECT titlu, tip_evaluare, output_asteptat FROM sarcini_teme WHERE id_profesor = ? ORDER BY id DESC",
        (session['user_id'],),
    )
    teme = c.fetchall()
    conn.close()

    return render_template('dashboard_profesor.html', teme=teme)


@app.route('/student', methods=['GET', 'POST'])
def dashboard_student():
    if 'rol' not in session or session['rol'] != 'student':
        return redirect(url_for('login'))

    mesaj = None
    rezultat_evaluare = None

    if request.method == 'POST':
        id_sarcina = request.form.get('id_sarcina')
        fisier = request.files.get('fisier_tema')

        if not id_sarcina:
            mesaj = "Eroare: selectează întâi o temă din listă."
        elif not fisier or fisier.filename == '':
            mesaj = "Eroare: niciun fișier selectat."
        elif not extensie_permisa(fisier.filename, EXTENSII_PERMISE_TEMA):
            mesaj = "Eroare: tip de fișier neacceptat. Folosește .py, .png, .jpg sau .jpeg."
        else:
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            nume_fisier = secure_filename(fisier.filename)
            cale_salvare = os.path.join(UPLOAD_FOLDER, nume_fisier)
            fisier.save(cale_salvare)

            conn = sqlite3.connect('baza_date.db')
            c = conn.cursor()
            c.execute("SELECT tip_evaluare, output_asteptat FROM sarcini_teme WHERE id = ?", (id_sarcina,))
            sarcina = c.fetchone()
            conn.close()

            if not sarcina:
                mesaj = "Eroare: tema selectată nu mai există."
            else:
                tip_evaluare, barem_profesor = sarcina
                
                # PROTECȚIE: Prevenim erorile dacă baremul vechi este NULL
                if barem_profesor is None:
                    barem_profesor = ""

                if fisier.filename.endswith('.py'):
                    with open(cale_salvare, 'r', encoding='utf-8') as f:
                        cod_sursa = f.read()
                    rezultat_evaluare = evaluate_python_code(cod_sursa, barem_profesor)
                    mesaj = "Cod Python evaluat de motorul de izolare."

                elif tip_evaluare == 'informatica':
                    mesaj = "Eroare: această temă este de tip Informatică și necesită un fișier .py."

                else:
                    text_elev = None
                    try:
                        text_elev = extrage_text_din_poza(cale_salvare)
                    except OCRError as e:
                        # Nu mai mascam eroarea cu date false - o raportam onest,
                        # ca elevul si profesorul sa stie ca poza n-a fost citita.
                        print(f"[Eroare] OCR indisponibil la procesarea fisierului: {e}")
                        rezultat_evaluare = {
                            "nota": 1,
                            "status": "Eroare OCR",
                            "justificare": (
                                "Nu am putut citi textul din imagine - serviciul OCR nu "
                                "este disponibil sau nu este configurat corect pe server. "
                                "Verifica starea Tesseract in panoul de admin sau "
                                "reincearca cu o poza mai clara."
                            ),
                        }
                        mesaj = "Eroare: imaginea nu a putut fi procesată (OCR indisponibil)."

                    if text_elev is not None:
                        if tip_evaluare == 'matematica':
                            rezultat_evaluare = evaluate_math_expression(text_elev, barem_profesor)
                        else:
                            rezultat_evaluare = evalueaza_grila_text(text_elev, barem_profesor)
                        mesaj = "Fișier procesat cu succes de Inteligența Artificială!"

                # PROTECȚIE: Salvăm folosind .get() pentru a nu crăpa serverul dacă funcția de corectare are alt format
                if rezultat_evaluare and isinstance(rezultat_evaluare, dict):
                    conn = sqlite3.connect('baza_date.db')
                    c = conn.cursor()
                    c.execute(
                        """INSERT INTO trimiteri (id_student, id_sarcina, nota, status_executie, justificare_nota, data_trimitere)
                           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        (session['user_id'], id_sarcina, 
                         rezultat_evaluare.get('nota', 1.0),
                         rezultat_evaluare.get('status', 'Eroare'), 
                         rezultat_evaluare.get('justificare', 'Fără justificare')),
                    )
                    conn.commit()
                    conn.close()

    conn = sqlite3.connect('baza_date.db')
    c = conn.cursor()
    c.execute("SELECT id, titlu, tip_evaluare FROM sarcini_teme ORDER BY id DESC")
    sarcini = c.fetchall()
    c.execute(
        """SELECT s.titlu, t.nota, t.status_executie, t.justificare_nota, t.data_trimitere
           FROM trimiteri t JOIN sarcini_teme s ON t.id_sarcina = s.id
           WHERE t.id_student = ? ORDER BY t.id DESC""",
        (session['user_id'],),
    )
    istoric = c.fetchall()
    conn.close()

    return render_template(
        'dashboard_student.html',
        mesaj=mesaj, rezultat_evaluare=rezultat_evaluare, sarcini=sarcini, istoric=istoric,
    )


@app.route('/admin')
def dashboard_admin():
    if 'rol' not in session or session['rol'] != 'admin':
        return redirect(url_for('login'))

    conn = sqlite3.connect('baza_date.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM utilizatori")
    numar_utilizatori = c.fetchone()[0]
    conn.close()

    return render_template(
        'dashboard_admin.html',
        numar_utilizatori=numar_utilizatori,
        tesseract_status=tesseract_disponibil(),
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    init_db()
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode)
