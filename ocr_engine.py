import os
import re
import shutil

import pytesseract
from PIL import Image, ImageEnhance


class OCRError(Exception):
    """Ridicata atunci cand extragerea de text prin OCR nu poate fi realizata."""
    pass


def _configureaza_tesseract():
    """
    Determina calea catre executabilul Tesseract:
    1. Variabila de mediu TESSERACT_CMD, daca e setata (recomandat in productie).
    2. Detectare automata in PATH (functioneaza pe Linux/macOS/Windows daca
       Tesseract e instalat corect si adaugat in PATH).
    Nu mai hardcodam o cale fixa de Windows - ruleaza pe orice sistem pe care
    Tesseract e instalat corect.
    """
    cale_env = os.environ.get('TESSERACT_CMD')
    if cale_env and os.path.exists(cale_env):
        pytesseract.pytesseract.tesseract_cmd = cale_env
        return

    cale_auto = shutil.which('tesseract')
    if cale_auto:
        pytesseract.pytesseract.tesseract_cmd = cale_auto
    # Daca nu gasim nimic, lasam valoarea implicita din pytesseract si vom
    # obtine o eroare clara la prima utilizare (vezi extrage_text_din_poza),
    # in loc sa blocam pornirea aplicatiei.


_configureaza_tesseract()


def tesseract_disponibil():
    """Verifica daca Tesseract poate fi apelat efectiv (folosit de panoul admin)."""
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def preprocesare_imagine(cale_imagine):
    img = Image.open(cale_imagine)
    img = img.convert('L')
    latime, inaltime = img.size
    img = img.resize((latime * 2, inaltime * 2), Image.Resampling.LANCZOS)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    return img


def extrage_text_din_poza(cale_imagine):
    """
    Extrage text dintr-o imagine. Ridica OCRError (in loc sa returneze un
    text-sentinela) daca Tesseract nu e disponibil sau imaginea e invalida,
    astfel apelantul trateaza eroarea explicit, cu try/except.
    """
    try:
        img_procesata = preprocesare_imagine(cale_imagine)
    except Exception as e:
        raise OCRError(f"Imaginea nu a putut fi citita: {e}")

    try:
        config_custom = r'--oem 3 --psm 6'
        text_extras = pytesseract.image_to_string(img_procesata, config=config_custom)
        return text_extras.strip()
    except Exception as e:
        raise OCRError(f"Tesseract nu este instalat/configurat corect: {e}")


_PERECHE_INTREBARE_RASPUNS = re.compile(r'(\d+)\D{0,3}([a-jA-J])')


def _extrage_perechi(text):
    """
    Extrage perechile (numar_intrebare -> litera_raspuns) dintr-un text de
    forma '1a2b3c4b5a', '1. a, 2. b, 3. c', '1-a 2-b 3-c' etc. Accepta pana
    la 3 caractere non-cifra intre numar si litera (punct, spatiu, liniuta).
    Foloseste doar prima potrivire pentru fiecare numar de intrebare, ca sa
    ignore duplicate accidentale.
    """
    perechi = {}
    for numar, litera in _PERECHE_INTREBARE_RASPUNS.findall(str(text)):
        if numar not in perechi:
            perechi[numar] = litera.lower()
    return perechi


def evalueaza_grila_text(text_elev, barem_profesor):
    """
    Compara raspunsurile elevului cu baremul, intrebare cu intrebare - nu
    similaritate bruta de text pe tot blocul. Asta face comparatia imuna la
    ordinea in care OCR-ul a citit perechile si separa clar "litera de
    raspuns gresita" de "numar de intrebare citit gresit de OCR".
    """
    # Protecție imediată împotriva baremelor goale
    if not barem_profesor:
        return {"nota": 1, "status": "Eroare Barem", "justificare": "Baremul setat de profesor este gol sau invalid."}
    if not text_elev:
        return {"nota": 1, "status": "Eroare Imagine", "justificare": "Sistemul nu a putut extrage text din imagine."}

    perechi_barem = _extrage_perechi(barem_profesor)
    if not perechi_barem:
        return {"nota": 1, "status": "Eroare Configurare",
                "justificare": "Baremul nu are formatul așteptat (număr+literă, ex: '1a,2b,3c')."}

    perechi_elev = _extrage_perechi(text_elev)
    if not perechi_elev:
        return {"nota": 1, "status": "Eroare OCR",
                "justificare": f"Nu am putut identifica răspunsuri (format număr+literă) în textul citit din poză: '{text_elev}'."}

    total = len(perechi_barem)
    corecte = sum(1 for numar, litera in perechi_barem.items() if perechi_elev.get(numar) == litera)

    nota = round(1 + 9 * corecte / total, 2)  # scala românească 1-10

    detalii = ", ".join(
        f"{numar}: elev='{perechi_elev.get(numar, '-')}' barem='{litera}'"
        for numar, litera in sorted(perechi_barem.items(), key=lambda p: int(p[0]))
    )

    if nota >= 9.5:
        status = "Succes"
    elif nota >= 5:
        status = "Parțial"
    else:
        status = "Eșuat"

    justificare = f"{corecte} din {total} răspunsuri corecte. ({detalii})"

    return {"nota": nota, "status": status, "justificare": justificare}


if __name__ == '__main__':
    print("Tesseract disponibil:", tesseract_disponibil())
    print(evalueaza_grila_text("1a2b3c4b5a", "1a2b3c4b5a"))       # toate corecte -> Succes
    print(evalueaza_grila_text("1a2b3c4b5x", "1a2b3c4b5a"))       # litera gresita la q5 -> Partial
    print(evalueaza_grila_text("1a3c2b5a4b", "1a2b3c4b5a"))       # reordonate, toate corecte -> Succes
    print(evalueaza_grila_text("1a2b8c4b5a", "1a2b3c4b5a"))       # cifra de intrebare citita gresit (q3 lipseste)
    print(evalueaza_grila_text("1a2b3d4b5a", "1a2b3c4b5a"))       # litera chiar gresita la q3
