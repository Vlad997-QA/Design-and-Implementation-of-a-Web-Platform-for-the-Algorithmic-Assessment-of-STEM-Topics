import sqlite3

# Ne conectăm la baza ta de date
conn = sqlite3.connect('baza_date.db')
cursor = conn.cursor()

# 1. Creăm tabela nouă Roles
cursor.execute('''
CREATE TABLE IF NOT EXISTS Roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT NOT NULL UNIQUE
)
''')

# 2. Inserăm cele 3 roluri (folosim IGNORE ca să nu dea eroare dacă rulezi de 2 ori)
cursor.execute("INSERT OR IGNORE INTO Roles (role_name) VALUES ('Admin'), ('Profesor'), ('Student')")

# Salvăm modificările
conn.commit()
conn.close()

print("Tabela Roles a fost adaugata cu succes in baza de date!")
