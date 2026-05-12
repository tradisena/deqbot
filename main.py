import os
import sqlite3
import random
import string
import requests
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

# --- Gemini SDK Setup ---
try:
    from google import genai
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False

# --- DATABASE SETUP ---
DB_NAME = "deqcore.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Tabel Clients
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_bot TEXT,
            nama_owner TEXT,
            email TEXT,
            no_wa TEXT,
            token TEXT UNIQUE,
            status TEXT DEFAULT 'Aktif',
            informasi_owner TEXT DEFAULT '',
            assigned_characters TEXT DEFAULT '',
            admin_instructions TEXT DEFAULT ''
        )
    ''')
    # Tabel Characters
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            instruction TEXT
        )
    ''')
    # Tabel Skills
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            content TEXT
        )
    ''')
    # Tabel Settings (Multi-engine & Gemini Config)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key_name TEXT PRIMARY KEY,
            key_value TEXT,
            model_type TEXT DEFAULT "gemini-3.1-flash"
        )
    ''')
    
    # Migrasi aman kolom model_type
    try:
        cursor.execute('ALTER TABLE settings ADD COLUMN model_type TEXT DEFAULT "gemini-3.1-flash"')
    except:
        pass

    # Default Data
    cursor.execute("INSERT OR IGNORE INTO settings (key_name, key_value) VALUES ('active_engine', 'llama3.2:1b')")
    cursor.execute("INSERT OR IGNORE INTO settings (key_name, key_value) VALUES ('hybrid_mode', 'true')")
    
    conn.commit()
    conn.close()

init_db()

# --- FASTAPI SETUP ---
app = FastAPI(title="DEQCore.ai")
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))

# --- MODELS ---
class Client(BaseModel):
    nama_bot: str
    nama_owner: str
    email: str
    no_wa: str
    informasi_owner: Optional[str] = ""
    assigned_characters: Optional[str] = ""
    admin_instructions: Optional[str] = ""

class Character(BaseModel):
    name: str
    instruction: str

class Skill(BaseModel):
    name: str
    description: str
    content: str

class ControlRequest(BaseModel):
    active_engine: str
    hybrid_mode: bool

class GeminiSaveRequest(BaseModel):
    api_key: str
    model_type: str

# --- ROUTES DASHBOARD ---
@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request):
    return templates.TemplateResponse(request=request, name="home.html", context={})

@app.get("/newdeq", response_class=HTMLResponse)
async def read_newdeq(request: Request):
    return templates.TemplateResponse(request=request, name="newdeq.html", context={})

@app.get("/deqbot", response_class=HTMLResponse)
async def read_deqbot(request: Request):
    return templates.TemplateResponse(request=request, name="deqbot.html", context={})

@app.get("/character", response_class=HTMLResponse)
async def read_character(request: Request):
    return templates.TemplateResponse(request=request, name="character.html", context={})

@app.get("/skill", response_class=HTMLResponse)
async def read_skill(request: Request):
    return templates.TemplateResponse(request=request, name="skill.html", context={})

@app.get("/configurasi", response_class=HTMLResponse)
async def read_config(request: Request):
    return templates.TemplateResponse(request=request, name="configurasi.html", context={})

# --- API SETTINGS & GEMINI ---
@app.get("/api/settings/load_control")
async def load_control():
    conn = get_db_connection()
    engine = conn.execute("SELECT key_value FROM settings WHERE key_name = 'active_engine'").fetchone()
    hybrid = conn.execute("SELECT key_value FROM settings WHERE key_name = 'hybrid_mode'").fetchone()
    conn.close()
    return {
        "active_engine": engine['key_value'] if engine else "llama3.2:1b",
        "hybrid_mode": (hybrid['key_value'] == 'true') if hybrid else True
    }

@app.post("/api/settings/save_control")
async def save_control(req: ControlRequest):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key_name, key_value) VALUES ('active_engine', ?)", (req.active_engine,))
    conn.execute("INSERT OR REPLACE INTO settings (key_name, key_value) VALUES ('hybrid_mode', ?)", (str(req.hybrid_mode).lower(),))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/settings/gemini/save")
async def save_gemini_config(req: GeminiSaveRequest):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key_name, key_value, model_type) VALUES ('gemini_api_key', ?, ?)", 
                 (req.api_key.strip(), req.model_type.strip()))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/settings/gemini/list")
async def list_gemini_keys():
    conn = get_db_connection()
    res = conn.execute("SELECT key_value, model_type FROM settings WHERE key_name = 'gemini_api_key'").fetchall()
    conn.close()
    return [dict(r) for r in res]

@app.delete("/api/settings/gemini/delete")
async def delete_gemini_key():
    conn = get_db_connection()
    conn.execute("DELETE FROM settings WHERE key_name = 'gemini_api_key'")
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- API CLIENTS ---
@app.get("/api/clients")
async def get_clients():
    conn = get_db_connection()
    clients = conn.execute('SELECT * FROM clients ORDER BY id DESC').fetchall()
    conn.close()
    return [dict(c) for c in clients]

@app.post("/api/clients")
async def create_client(client: Client):
    conn = get_db_connection()
    token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=15))
    try:
        conn.execute('''
            INSERT INTO clients (nama_bot, nama_owner, email, no_wa, token, informasi_owner, assigned_characters, admin_instructions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (client.nama_bot, client.nama_owner, client.email, client.no_wa, token, client.informasi_owner, client.assigned_characters, client.admin_instructions))
        conn.commit()
    finally:
        conn.close()
    return {"status": "success", "token": token}

@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: int):
    conn = get_db_connection()
    conn.execute('DELETE FROM clients WHERE id = ?', (client_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- API CHARACTERS ---
@app.get("/api/characters")
async def get_characters():
    conn = get_db_connection()
    chars = conn.execute('SELECT * FROM characters').fetchall()
    conn.close()
    return [dict(c) for c in chars]

@app.post("/api/characters")
async def create_character(char: Character):
    conn = get_db_connection()
    conn.execute('INSERT INTO characters (name, instruction) VALUES (?, ?)', (char.name, char.instruction))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/characters/{char_id}")
async def delete_character(char_id: int):
    conn = get_db_connection()
    conn.execute('DELETE FROM characters WHERE id = ?', (char_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- API SKILLS ---
@app.get("/api/skills")
async def get_skills():
    conn = get_db_connection()
    skills = conn.execute('SELECT * FROM skills').fetchall()
    conn.close()
    return [dict(s) for s in skills]

@app.post("/api/skills")
async def create_skill(skill: Skill):
    conn = get_db_connection()
    conn.execute('INSERT INTO skills (name, description, content) VALUES (?, ?, ?)', (skill.name, skill.description, skill.content))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: int):
    conn = get_db_connection()
    conn.execute('DELETE FROM skills WHERE id = ?', (skill_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- CHAT ENGINE (FIXED x_deq_key & TIMEOUT 60s) ---
@app.post("/v1/chat")
async def chat_endpoint(request: dict, x_deq_key: str = Header(None)):
    conn = get_db_connection()
    engine_set = conn.execute("SELECT key_value FROM settings WHERE key_name = 'active_engine'").fetchone()
    hybrid_set = conn.execute("SELECT key_value FROM settings WHERE key_name = 'hybrid_mode'").fetchone()
    gemini_set = conn.execute("SELECT key_value, model_type FROM settings WHERE key_name = 'gemini_api_key'").fetchone()
    
    active_engine = engine_set['key_value'] if engine_set else "llama3.2:1b"
    hybrid_on = (hybrid_set['key_value'] == 'true') if hybrid_set else True
    
    if x_deq_key == "MASTER-ADMIN":
        prompt_final = request['prompt']
    else:
        # PERBAIKAN: Gunakan x_deq_key agar sinkron dengan client token
        client = conn.execute('SELECT * FROM clients WHERE token = ?', (x_deq_key,)).fetchone()
        if not client:
            conn.close()
            raise HTTPException(status_code=401, detail="Token Invalid")
        prompt_final = f"ROLE: {client['assigned_characters']}\nSOP: {client['admin_instructions']}\nINFO: {client['informasi_owner']}\nUSER: {request['prompt']}"
    conn.close()

    if active_engine == "gemini":
        if HAS_GENAI_SDK and gemini_set:
            try:
                client_gen = genai.Client(api_key=gemini_set['key_value'])
                resp = client_gen.models.generate_content(model=gemini_set['model_type'], contents=prompt_final)
                return {"response": resp.text}
            except Exception as e:
                return {"response": f"Gemini Error ({gemini_set['model_type']}): {str(e)}"}
        return {"response": "Config Gemini Error."}
    else:
        try:
            # Timeout dinaikkan ke 60s untuk load model berat
            res = requests.post("http://localhost:11434/api/generate", 
                                json={"model": active_engine, "prompt": prompt_final, "stream": False}, timeout=60)
            return {"response": res.json().get("response", "")}
        except:
            if hybrid_on and HAS_GENAI_SDK and gemini_set:
                try:
                    client_gen = genai.Client(api_key=gemini_set['key_value'])
                    resp = client_gen.models.generate_content(model=gemini_set['model_type'], contents="[HYBRID FAILOVER] " + prompt_final)
                    return {"response": "(Backup Cloud) " + resp.text}
                except: pass
            return {"response": "Ollama Offline & Hybrid Gagal."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
