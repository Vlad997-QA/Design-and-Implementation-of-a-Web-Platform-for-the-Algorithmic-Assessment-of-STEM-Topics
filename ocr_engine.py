import pytesseract
from PIL import Image, ImageEnhance
import sympy
import re

# AM ACTIVAT CALEA CĂTRE TESSERACT! (Asigură-te că aceasta este calea unde s-a instalat la tine)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocesare_imagine(cale_imagine):
    img = Image.open(cale_imagine)
    img = img.convert('L')
    latime, inaltime = img.size
    img = img.resize((latime * 2, inaltime * 2), Image.Resampling.LANCZOS)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    return img

def extrage_text_din_poza(cale_imagine):
    try:
        img_procesata = preprocesare_imagine(cale_imagine)
        config_custom = r'--oem 3 --psm 6'
        text_extras = pytesseract.image_to_string(img_procesata, config=config_custom)
        return text_extras.strip()
    except Exception as e:
        return f"Eroare_OCR_Lipsește_Tesseract" # Un text clar ca să nu-l mai confunde

def evalueaza_rezolvarea(text_din_ocr, barem_profesor):
    # Protecție anti-eroare (dacă Tesseract a crăpat, oprim evaluarea)
    if "Eroare_OCR" in text_din_ocr or "Eroare_OCR" in barem_profesor:
        return "Eroare Critică: Tesseract nu este instalat corect sau calea este greșită!"

    try:
        # Încercare 1: Matematică (SymPy)
        stu_sym = sympy.sympify(text_din_ocr)
        tea_sym = sympy.sympify(barem_profesor)
        
        if sympy.simplify(stu_sym - tea_sym) == 0:
            return "NOTA 10: Rezolvarea matematică este Corectă!"
        else:
            return "NOTA 4: Rezolvarea matematică este Greșită."
            
    except Exception:
        # Încercare 2: Text / Grilă (AICI FACEM CALCULUL NOTEI PE PUNCTE)
        print("\n[Sistem] Trecem pe evaluare grilă/text...")
        
        text_elev = re.sub(r'\W+', '', text_din_ocr.lower())
        text_barem = re.sub(r'\W+', '', barem_profesor.lower())
        
        print(f"[Sistem] Barem curățat extras: '{text_barem}'")
        print(f"[Sistem] Elev curățat extras: '{text_elev}'")
        
        # Dacă textele sunt complet goale, nu putem nota
        if not text_barem:
            return "Eroare: Baremul este gol!"
            
        lungime_maxima = max(len(text_barem), 1)
        caractere_corecte = 0
        
        # Comparăm caracter cu caracter
        for i in range(min(len(text_barem), len(text_elev))):
            if text_barem[i] == text_elev[i]:
                caractere_corecte += 1
                
        # Calculăm nota din 10
        nota = (caractere_corecte / lungime_maxima) * 10
        nota_rotunjita = round(nota, 2)
        
        if nota_rotunjita == 10.0:
            return f"NOTA 10: Toate răspunsurile sunt corecte! ({text_elev})"
        else:
            return f"NOTA {nota_rotunjita}: Răspunsuri parțial greșite. (Elev: {text_elev} | Barem: {text_barem})"