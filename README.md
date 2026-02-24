# Calendar Știință

Aplicație web pentru publicarea și vizualizarea unui calendar de evenimente științifice.
Administratorul încarcă un poster JPG, aplicația extrage automat evenimentele prin OCR, iar publicul le poate vizualiza și descărca.

## Funcționalități

**Public**
- Calendar interactiv (vizualizare lunară / listă)
- Căutare după cuvânt cheie
- Detalii eveniment la click
- Export eveniment în format `.ics` (Google Calendar, Outlook etc.)

**Admin** (protejat cu parolă)
- Încărcare poster JPG → extragere automată evenimente prin OCR
- Suport pentru calendare anuale tip grilă 6×2 și postere simple
- Revizie și editare evenimente înainte de publicare
- Adăugare / editare / ștergere manuală evenimente

## Stack

- **Backend**: Python, FastAPI, Tesseract OCR, Pillow, NumPy
- **Frontend**: HTML + CSS + JavaScript, [FullCalendar.js](https://fullcalendar.io/)
- **Stocare**: `events.json` (fișier local)

## Instalare (Windows)

### Automat

1. Descarcă sau clonează repo-ul
2. Dublu-clic pe `install.bat`
3. Confirmă cererea UAC (administrator)
4. Urmează instrucțiunile din terminal (setează parola admin)

Installerul descarcă și configurează automat: Python 3.12, Tesseract OCR, modelul român de OCR (`ron.traineddata` best) și toate dependențele Python.

### Manual

**Cerințe prealabile**
- Python 3.10+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) instalat

```bash
pip install -r requirements.txt
cp .env.example .env
# Editează .env cu parola dorită și calea către tesseract.exe
```

**Model OCR român (recomandat pentru diacritice)**

```bash
mkdir %USERPROFILE%\.tessdata
# Descarcă ron.traineddata din tessdata_best și pune-l în %USERPROFILE%\.tessdata\
```

## Pornire

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Sau dublu-clic pe `start.bat` (generat de installer).

Deschide în browser: [http://localhost:8000](http://localhost:8000)

## Configurare `.env`

```env
ADMIN_PASSWORD=parola_ta
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Cum se folosește

1. Deschide aplicația în browser
2. Tab **Admin** → autentifică-te cu parola
3. Tab **Încarcă poster** → selectează imaginea JPG
4. Completează câmpul **An calendar** (ex: `2026`)
5. Apasă **Extrage evenimente**
6. Revizuiește lista extrasă, modifică dacă e nevoie
7. Apasă **Publică** pentru fiecare eveniment confirmat

## Structura proiectului

```
science-calendar/
├── main.py              # Backend FastAPI + logică OCR
├── static/
│   └── index.html       # Frontend complet (single-file)
├── requirements.txt
├── install.bat          # Installer Windows (entry point)
├── install.ps1          # Logică installer PowerShell
├── .env.example         # Template configurare
└── .gitignore
```
