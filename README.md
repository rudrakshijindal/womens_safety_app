# Women's Safety & Emergency Response System

Academic prototype with a Verified Guardian Network. Not a substitute for emergency services.

## Windows setup (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
flask --app app init-db
flask --app app run
pytest -v
```

Open http://127.0.0.1:5000 in your browser. Edit `.env` and set a long random `SECRET_KEY`.
Generate one with: `python -c "import secrets; print(secrets.token_hex(32))"`