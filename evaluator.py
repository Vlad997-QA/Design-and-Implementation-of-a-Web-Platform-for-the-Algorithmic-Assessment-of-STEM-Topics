import ast
import subprocess
import tempfile
import os
import sympy

# ==========================================
# 1. EVALUATORUL DE INFORMATICĂ (Python)
# ==========================================

def sanitize_code(code_string):
    """
    AST Sanitization: Verifică codul înainte de a-l rula pentru a bloca 
    importurile periculoase (ex: stergerea de fișiere de pe server).
    """
    try:
        tree = ast.parse(code_string)
    except SyntaxError as e:
        return False, f"Eroare de sintaxă în codul Python: {str(e)}"
    
    # Parcurgem arborele de sintaxă pentru a detecta noduri malițioase
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in ['os', 'sys', 'subprocess', 'shutil']:
                    return False, f"Securitate: Import nepermis detectat ('{alias.name}')."
    return True, "Cod curat."


def evaluate_python_code(student_code, expected_output):
    """
    Rulează codul studentului într-un mediu izolat cu timeout.
    """
    # 1. Verificăm codul (AST Sanitization)
    is_safe, msg = sanitize_code(student_code)
    if not is_safe:
        return {"nota": 1, "status": "Eroare Securitate", "justificare": msg}
    
    # 2. Creăm un fișier temporar unde salvăm codul studentului
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(student_code)
        temp_filename = f.name
    
    try:
        # 3. Executăm fișierul într-un Subproces (limitat la max 2 secunde)
        result = subprocess.run(['python', temp_filename], capture_output=True, text=True, timeout=2)
        
        output = result.stdout.strip()
        errors = result.stderr.strip()
        
        # Analizăm rezultatele
        if errors:
             return {"nota": 2, "status": "Eroare Execuție", "justificare": f"Codul a dat eroare: {errors[:200]}"}
        
        if output == str(expected_output).strip():
             return {"nota": 10, "status": "Succes", "justificare": "Algoritmul a returnat output-ul corect."}
        else:
             return {"nota": 4, "status": "Eșuat", "justificare": f"Output incorect. Așteptat: '{expected_output}', Obținut: '{output}'"}
             
    except subprocess.TimeoutExpired:
        # Prindem buclele infinite (ex: while True)
        return {"nota": 1, "status": "Timeout", "justificare": "Limita de timp (2s) depășită. Posibilă buclă infinită!"}
    finally:
        # Curățăm mereu serverul stergând fișierul temporar
        os.remove(temp_filename)


# ==========================================
# 2. EVALUATORUL DE MATEMATICĂ (SymPy)
# ==========================================

def evaluate_math_expression(student_expr, teacher_expr):
    """
    Verifică dacă două expresii matematice sunt echivalente simbolic.
    Ex: x+x == 2*x
    """
    try:
        # Transformăm textul în obiecte matematice SymPy
        stu_sym = sympy.sympify(student_expr)
        tea_sym = sympy.sympify(teacher_expr)
        
        # Metoda științifică: dacă diferența lor simplificată e 0, sunt echivalente
        if sympy.simplify(stu_sym - tea_sym) == 0:
            return {"nota": 10, "status": "Succes", "justificare": "Expresiile sunt echivalente matematic."}
        else:
            return {"nota": 4, "status": "Eșuat", "justificare": f"Expresia '{student_expr}' nu este echivalentă cu '{teacher_expr}'."}
            
    except Exception as e:
        return {"nota": 1, "status": "Eroare Sintaxă", "justificare": f"Nu se poate citi expresia matematică: {str(e)}"}

# === ZONA DE TESTARE IZOLATĂ (Fără a porni site-ul) ===
if __name__ == '__main__':
    print("--- Testare Evaluator Informatică ---")
    cod_bun = "print(5 + 5)"
    rezultat = evaluate_python_code(cod_bun, "10")
    print(f"Test Cod Bun:\n{rezultat}\n")
    
    cod_malitios = "import os\nprint(os.name)"
    rezultat2 = evaluate_python_code(cod_malitios, "nt")
    print(f"Test Cod Malițios:\n{rezultat2}\n")
    
    print("--- Testare Evaluator Matematică ---")
    rezultat_mate = evaluate_math_expression("x + x + x", "3*x")
    print(f"Test (x+x+x) vs (3*x):\n{rezultat_mate}")