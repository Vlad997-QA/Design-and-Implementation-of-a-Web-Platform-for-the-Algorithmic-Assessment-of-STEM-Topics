import ast
import os
import re
import subprocess
import sys
import tempfile

import sympy

# ==========================================
# 0. VALIDARE INPUT MATEMATIC (anti-injectie in sympify)
# ==========================================

# sympy.sympify() foloseste eval() intern pentru a interpreta textul primit.
# NU trebuie trimis niciodata text OCR / input de utilizator nefiltrat direct
# catre sympify - limitam strict caracterele permise inainte de a apela sympify.
# Includem '=' ca sa permitem ecuatii de forma 'x + 2 = 5', nu doar expresii.
_CARACTERE_PERMISE_MATE = re.compile(r'^[0-9a-zA-Z\s\+\-\*\/\^\.\(\)\,_=]+$')


def _valideaza_expresie_matematica(expr):
    if not expr or not _CARACTERE_PERMISE_MATE.match(expr):
        raise ValueError("Expresia contine caractere nepermise pentru evaluare matematica.")
    return expr


# ==========================================
# 1. EVALUATORUL DE INFORMATICA (Python)
# ==========================================

_APELURI_INTERZISE = {
    'eval', 'exec', '__import__', 'compile', 'open',
    'globals', 'locals', 'vars', 'getattr', 'setattr', 'delattr', 'input',
}
_MODULE_INTERZISE = {'os', 'sys', 'subprocess', 'shutil', 'socket', 'importlib', 'ctypes'}


class _VerificatorSecuritate(ast.NodeVisitor):
    """
    Verifica arborele de sintaxa al codului trimis de student pentru a bloca:
    - importuri periculoase (os, sys, subprocess, shutil, socket, ...)
    - apeluri de functii periculoase (eval, exec, open, __import__, ...)
    - acces la atribute "dunder" (__class__, __bases__, __subclasses__ etc.),
      tehnica standard de evadare dintr-un sandbox Python fara niciun import.

    Nota: e o lista neagra, nu o garantie absoluta de izolare - pentru foarte
    multi utilizatori necunoscuti, ruleaza codul intr-un container/VM izolat,
    nu doar intr-un subproces pe acelasi server.
    """

    def __init__(self):
        self.erori = []

    def visit_Import(self, node):
        for alias in node.names:
            radacina = alias.name.split('.')[0]
            if radacina in _MODULE_INTERZISE:
                self.erori.append(f"Import nepermis detectat ('{alias.name}').")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            radacina = node.module.split('.')[0]
            if radacina in _MODULE_INTERZISE:
                self.erori.append(f"Import nepermis detectat ('{node.module}').")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in _APELURI_INTERZISE:
            self.erori.append(f"Apel de functie nepermis detectat ('{node.func.id}').")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr.startswith('__') and node.attr.endswith('__'):
            self.erori.append(f"Acces la atribut special nepermis ('{node.attr}').")
        self.generic_visit(node)


def sanitize_code(code_string):
    """
    AST Sanitization: verifica codul inainte de a-l rula.
    """
    try:
        tree = ast.parse(code_string)
    except SyntaxError as e:
        return False, f"Eroare de sintaxa in codul Python: {str(e)}"

    verificator = _VerificatorSecuritate()
    verificator.visit(tree)
    if verificator.erori:
        return False, "Securitate: " + " ".join(verificator.erori)
    return True, "Cod curat."


def evaluate_python_code(student_code, expected_output):
    """
    Ruleaza codul studentului intr-un proces separat, izolat, cu timeout.
    """
    is_safe, msg = sanitize_code(student_code)
    if not is_safe:
        return {"nota": 1, "status": "Eroare Securitate", "justificare": msg}

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(student_code)
        temp_filename = f.name

    try:
        # sys.executable in loc de 'python' hardcodat: functioneaza indiferent
        # de cum e configurat PATH-ul pe server.
        # -I = mod izolat: ignora variabile de mediu PYTHON*, script-uri
        # locale de configurare si user site-packages.
        result = subprocess.run(
            [sys.executable, '-I', temp_filename],
            capture_output=True, text=True, timeout=2,
        )

        output = result.stdout.strip()
        errors = result.stderr.strip()

        if errors:
            return {"nota": 2, "status": "Eroare Executie", "justificare": f"Codul a dat eroare: {errors[:200]}"}

        if output == str(expected_output).strip():
            return {"nota": 10, "status": "Succes", "justificare": "Algoritmul a returnat output-ul corect."}
        else:
            return {"nota": 4, "status": "Esuat",
                    "justificare": f"Output incorect. Asteptat: '{expected_output}', Obtinut: '{output}'"}

    except subprocess.TimeoutExpired:
        return {"nota": 1, "status": "Timeout", "justificare": "Limita de timp (2s) depasita. Posibila bucla infinita!"}
    finally:
        os.remove(temp_filename)


# ==========================================
# 2. EVALUATORUL DE MATEMATICA (SymPy)
# ==========================================

def _parseaza_expresie_matematica(expr_validata):
    """
    Transforma un string deja validat (vezi _valideaza_expresie_matematica)
    intr-un obiect SymPy: o ecuatie (sympy.Eq) daca textul contine exact un
    '=', altfel o expresie simpla.
    """
    parti = expr_validata.split('=')
    if len(parti) == 1:
        return sympy.sympify(parti[0])
    if len(parti) == 2:
        stanga, dreapta = parti
        return sympy.Eq(sympy.sympify(stanga), sympy.sympify(dreapta))
    raise ValueError("Expresia contine mai mult de un semn '=' - format nesuportat.")


def _rezolva_ecuatie(ecuatie):
    """
    Returneaza multimea de solutii ale ecuatiei (ca valori simplificate),
    pentru a putea compara doua ecuatii dupa multimea lor de solutii si nu
    dupa forma literala (ex: 'x+2=5' si '2*x=6' trebuie sa iasa echivalente).
    """
    variabile = sorted(ecuatie.free_symbols, key=lambda s: s.name)
    if not variabile:
        # Ecuatie fara necunoscute (ex: '5=5') - o evaluam direct ca adevarat/fals.
        return {bool(ecuatie)}
    solutii = sympy.solve(ecuatie, *variabile)
    if not isinstance(solutii, (list, tuple, set)):
        solutii = [solutii]
    return {sympy.simplify(s) for s in solutii}


def evaluate_math_expression(student_expr, teacher_expr):
    """
    Verifica daca doua expresii/ecuatii matematice sunt echivalente simbolic.
    Ex: 'x+x' vs '2*x' (expresii), sau 'x+2=5' vs '2*x=6' (ecuatii cu aceeasi
    solutie, desi nu sunt identice ca forma).
    """
    try:
        _valideaza_expresie_matematica(student_expr)
        _valideaza_expresie_matematica(teacher_expr)

        stu_sym = _parseaza_expresie_matematica(student_expr)
        tea_sym = _parseaza_expresie_matematica(teacher_expr)

        stu_e_ecuatie = isinstance(stu_sym, sympy.Eq)
        tea_e_ecuatie = isinstance(tea_sym, sympy.Eq)

        if stu_e_ecuatie != tea_e_ecuatie:
            return {"nota": 1, "status": "Eroare Format",
                    "justificare": "Nu pot compara o ecuatie (cu '=') cu o expresie simpla."}

        if stu_e_ecuatie:
            sunt_echivalente = _rezolva_ecuatie(stu_sym) == _rezolva_ecuatie(tea_sym)
        else:
            sunt_echivalente = sympy.simplify(stu_sym - tea_sym) == 0

        if sunt_echivalente:
            return {"nota": 10, "status": "Succes", "justificare": "Expresiile sunt echivalente matematic."}
        else:
            return {"nota": 4, "status": "Esuat",
                    "justificare": f"Expresia '{student_expr}' nu este echivalenta cu '{teacher_expr}'."}

    except ValueError as e:
        return {"nota": 1, "status": "Eroare Securitate", "justificare": str(e)}
    except Exception as e:
        return {"nota": 1, "status": "Eroare Sintaxa", "justificare": f"Nu se poate citi expresia matematica: {str(e)}"}


if __name__ == '__main__':
    print("--- Testare Evaluator Informatica ---")
    print(evaluate_python_code("print(5 + 5)", "10"))
    print(evaluate_python_code("import os\nprint(os.name)", "nt"))
    print(evaluate_python_code("().__class__.__bases__[0].__subclasses__()", "10"))

    print("--- Testare Evaluator Matematica ---")
    print(evaluate_math_expression("x + x + x", "3*x"))
    print(evaluate_math_expression("__import__('os').system('echo hacked')", "3*x"))

    print("--- Testare Ecuatii (fix pentru '=') ---")
    print(evaluate_math_expression("x + 2 = 5", "x = 3"))          # asteptat: Succes
    print(evaluate_math_expression("2*x = 6", "x = 3"))            # asteptat: Succes (aceeasi solutie)
    print(evaluate_math_expression("x + 2 = 6", "x = 3"))          # asteptat: Esuat
    print(evaluate_math_expression("x = 3", "3*x"))                # asteptat: Eroare Format (ecuatie vs expresie)
