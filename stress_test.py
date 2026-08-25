import sqlite3
import concurrent.futures
import time

def student_trimite_tema(thread_id):
    try:
        conn = sqlite3.connect('baza_date.db', timeout=10)
        c = conn.cursor()
        c.execute('''INSERT INTO trimiteri (id_student, id_sarcina, nota, status_executie, justificare_nota)
                     VALUES (3, 1, 10, 'Succes', 'Test la stres OCR')''')
        conn.commit()
        conn.close()
        return f"Thread {thread_id} a reusit."
    except Exception as e:
        return f"Eroare: {e}"

if __name__ == '__main__':
    print("Incepem simularea Deadline Rush (50 de fire de executie paralele)...")
    start = time.time()
    
    rezultate = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(student_trimite_tema, i) for i in range(1, 51)]
        for f in concurrent.futures.as_completed(futures):
            rezultate.append(f.result())
            
    succese = sum(1 for r in rezultate if "reusit" in r)
    print(f"Trimiteri reușite: {succese}/50")
    
    # AICI AM ADAUGAT: Dacă tot avem 0 succese, să ne spună DE CE!
    if succese < 50:
        erori = [r for r in rezultate if "Eroare" in r]
        print(f"Motivul blocajului: {erori[0]}")
        
    print(f"Timp total: {round(time.time() - start, 2)} secunde")