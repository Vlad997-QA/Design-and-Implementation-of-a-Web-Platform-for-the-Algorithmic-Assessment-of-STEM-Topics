# Design-and-Implementation-of-a-Web-Platform-for-the-Algorithmic-Assessment-of-STEM-Topics
Automated assessment of STEM assignments is a key pillar in the modernisation of the educational process. Although there are established software solutions on the market, most focus exclusively on programming or require complex cloud infrastructures.

Web application (Flask) for the automated marking of assignments in computer science,
mathematics and multiple-choice tests. It has three user roles: **admin**, **teacher** and
**student**.

## Features

- **Computer Science** — the Python code submitted by the student runs in isolation (sandbox with
  AST checking + subprocess with timeout) and is compared with the expected output.
- **Multiple-choice** — handwritten or photographed answers are read via OCR and
  
compared with the teacher’s marking scheme (approximate match, with partial marks).
- **Mathematics** — handwritten or photographed expressions and equations are read
  via OCR and symbolically verified using SymPy (mathematical equivalence, not
  literal text matching).
- **Admin panel** — live status: database, users, availability
of the OCR engine.

## Technologies

Flask · SQLite · Tesseract OCR (`pytesseract`) · Pillow · SymPy

## Installation

### 1. Clone the repository and install the Python dependencies

```bash
git clone <url-repo>
cd <folder-repo>
python -m venv venv
venv\Scripts\activate # Windows
# source venv/bin/activate # macOS/Linux
pip install -r requirements.txt
```

### 2. Install the Tesseract OCR engine (separately from the Python package!)

`pytesseract` is just a Python wrapper — it requires the actual
Tesseract OCR engine to be installed on the system, otherwise image reading will fail.

- **Windows** — download the installer from
[UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and
  
install it (default path: `C:\Program Files\Tesseract-OCR\`).
- **macOS** — `brew install tesseract`
- **Linux (Debian/Ubuntu)** — `sudo apt install tesseract-ocr`

If `tesseract` is not recognised as a command after installation (common on
Windows, when the folder isn’t in the `PATH`), set the environment variable
`TESSERACT_CMD` to the full path to the executable, for example:

```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

### 3. Start the application

```bash
python app.py
```

On first launch, `baza_date.db` is automatically created with the required schema and
the demo accounts listed below.

The application starts at `http://127.0.0.1:5000`. In the **admin** panel
(`/admin`) you can check in real time whether the OCR engine is detected correctly
(“Tesseract Online” / status `True`).

## Demo accounts

| Username | Password | Role |
|-------------|---------|----------|
| `admin` | admin123 | admin |
| `teacher1` | 1234 | teacher |
| `student1` | 1234 | student |

> These accounts are for demonstration and local development purposes only — change the passwords
> before using them outside the local environment.

## Project structure

```
app.py # Flask routes, authentication, dashboard logic
evaluator.py # Python code evaluation (sandbox) + maths evaluation (SymPy)
ocr_engine.py # text extraction from images (Tesseract) + grid evaluation
templates/ # HTML pages (login, admin/teacher/student dashboards)
requirements.txt # Python dependencies
```
