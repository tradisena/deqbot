import os
import sqlite3
import random
import string
import requests
import importlib.util
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi import Body
from fastapi.responses import HTMLResponse
from fastapi.responses import PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

# --- Gemini SDK Setup ---
HAS_GENAI_SDK = importlib.util.find_spec("google.genai") is not None
HAS_OLD_GENAI_SDK = importlib.util.find_spec("google.generativeai") is not None
genai = None
old_genai = None

if HAS_GENAI_SDK:
    from google import genai
elif HAS_OLD_GENAI_SDK:
    import google.generativeai as old_genai

# --- DATABASE SETUP ---
DB_NAME = "deqcore.db"
MEMORY_DB_NAME = "memory.db"
WORKFORCE_DB = "database/core/workforce.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn
def get_workforce_connection():

    conn = sqlite3.connect(WORKFORCE_DB)

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

def init_workforce_db():

    conn = get_workforce_connection()

    cursor = conn.cursor()

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS employees (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            employee_name TEXT,
            role TEXT,
            personality TEXT,
            primary_skill TEXT,
            ai_engine TEXT,
            authority_level TEXT,
            objective TEXT,

            status TEXT DEFAULT 'ACTIVE',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

    """)

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS workforce_skills (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            skill_name TEXT NOT NULL,
            skill_category TEXT NOT NULL,
            ai_engine TEXT NOT NULL,
            skill_description TEXT DEFAULT '',

            status TEXT DEFAULT 'ACTIVE',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

    """)

    conn.commit()

    conn.close()


init_db()
init_workforce_db()

def get_memory_connection():
    conn = sqlite3.connect(MEMORY_DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_memory_db():
    conn = get_memory_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS client_profiles (
            token TEXT PRIMARY KEY,
            email TEXT DEFAULT '',
            business_identity TEXT DEFAULT '',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT,
            role TEXT,
            message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prospect_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT,
            nama TEXT,
            nohp TEXT,
            keterangan TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_memory_db()

def get_gemini_config():
    conn = get_db_connection()
    gemini_set = conn.execute(
        "SELECT key_value, model_type FROM settings WHERE key_name = 'gemini_api_key'"
    ).fetchone()
    conn.close()

    db_key = gemini_set["key_value"].strip() if gemini_set and gemini_set["key_value"] else ""
    db_model = gemini_set["model_type"].strip() if gemini_set and gemini_set["model_type"] else ""

    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    env_model = os.getenv("GEMINI_MODEL", "").strip()

    api_key = db_key or env_key
    model = db_model or env_model or "gemini-2.5-flash"
    return api_key, model

def generate_gemini_response(prompt: str):
    api_key, model = get_gemini_config()
    if not api_key:
        return None, "Config Gemini Error: API key belum diset di menu Config atau env GEMINI_API_KEY."

    if HAS_GENAI_SDK:
        try:
            client_gen = genai.Client(api_key=api_key)
            resp = client_gen.models.generate_content(model=model, contents=prompt)
            return resp.text, None
        except Exception as e:
            return None, f"Gemini Error ({model}): {str(e)}"

    if HAS_OLD_GENAI_SDK:
        try:
            old_genai.configure(api_key=api_key)
            model_client = old_genai.GenerativeModel(model)
            resp = model_client.generate_content(prompt)
            return resp.text, None
        except Exception as e:
            return None, f"Gemini Error ({model}): {str(e)}"

    return None, "Config Gemini Error: library Google Gemini belum ter-install (google-genai / google-generativeai)."

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

class ClientProfileSaveRequest(BaseModel):
    email: str = ""
    business_identity: str = ""

class ClientHistoryRequest(BaseModel):
    role: str
    message: str

class ProspectContactRequest(BaseModel):
    nama: str
    nohp: str
    keterangan: str = ""

class WorkforceSkillCreateRequest(BaseModel):
    skill_name: str
    skill_category: str
    ai_engine: str
    skill_description: str = ""

class WorkforceAgentChatRequest(BaseModel):
    employee_id: int
    prompt: str

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

@app.get("/workforce/dashboard", response_class=HTMLResponse)
async def workforce_dashboard(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="workforce/dashboard.html",
        context={}
    )
@app.get("/workforce/create", response_class=HTMLResponse)
async def workforce_create(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="workforce/create.html",
        context={}
    )
@app.post("/api/workforce/create")
async def api_workforce_create(data: dict = Body(...)):

    print("\n=== NEW AI EMPLOYEE ===")

    print(data)

    return {

        "success": True,
        "message": "AI Employee Recruitment Success"

    }

@app.get("/workforce/library", response_class=HTMLResponse)
async def workforce_library(request: Request):

    conn = get_workforce_connection()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT * FROM employees
        ORDER BY id DESC

    """)

    employees = cursor.fetchall()

    conn.close()

    return templates.TemplateResponse(

        request=request,

        name="workforce/library.html",

        context={

            "employees": employees

        }

    )
@app.get("/workforce/skills", response_class=HTMLResponse)
async def workforce_skills(request: Request):

    conn = get_workforce_connection()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT * FROM workforce_skills
        ORDER BY id DESC

    """)

    skills = cursor.fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="workforce/skills.html",
        context={
            "skills": skills
        }
    )

@app.post("/api/workforce/skills/create")
async def api_workforce_skill_create(data: WorkforceSkillCreateRequest):

    skill_name = data.skill_name.strip()
    skill_category = data.skill_category.strip()
    ai_engine = data.ai_engine.strip()
    skill_description = data.skill_description.strip()

    if not skill_name:
        raise HTTPException(status_code=400, detail="Skill name is required")

    conn = get_workforce_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
            INSERT INTO workforce_skills (
                skill_name,
                skill_category,
                ai_engine,
                skill_description
            ) VALUES (?, ?, ?, ?)
        """,
        (skill_name, skill_category, ai_engine, skill_description)
    )

    conn.commit()

    conn.close()

    return {
        "success": True,
        "message": "Skill created successfully"
    }

@app.post("/api/workforce/chat")
async def api_workforce_chat(req: WorkforceAgentChatRequest):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    wf_conn = get_workforce_connection()
    employee = wf_conn.execute(
        "SELECT * FROM employees WHERE id = ?",
        (req.employee_id,)
    ).fetchone()
    wf_conn.close()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    system_prompt = (
        f"YOU ARE WORKFORCE AGENT: {employee['employee_name']}\n"
        f"ROLE: {employee['role']}\n"
        f"PERSONALITY: {employee['personality']}\n"
        f"PRIMARY_SKILL: {employee['primary_skill']}\n"
        f"AUTHORITY_LEVEL: {employee['authority_level']}\n"
        f"OBJECTIVE: {employee['objective']}\n"
        "INSTRUCTION: Respond as this specific agent and focus on the assigned role/objective.\n"
        f"USER: {prompt}"
    )

    conn = get_db_connection()
    engine_set = conn.execute("SELECT key_value FROM settings WHERE key_name = 'active_engine'").fetchone()
    hybrid_set = conn.execute("SELECT key_value FROM settings WHERE key_name = 'hybrid_mode'").fetchone()
    conn.close()

    active_engine = engine_set['key_value'] if engine_set else "llama3.2:1b"
    hybrid_on = (hybrid_set['key_value'] == 'true') if hybrid_set else True

    if active_engine == "gemini":
        gemini_text, gemini_error = generate_gemini_response(system_prompt)
        if gemini_text:
            return {"response": gemini_text, "agent_name": employee["employee_name"]}
        return {"response": gemini_error, "agent_name": employee["employee_name"]}

    try:
        res = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": active_engine, "prompt": system_prompt, "stream": False},
            timeout=60
        )
        return {"response": res.json().get("response", ""), "agent_name": employee["employee_name"]}
    except:
        if hybrid_on:
            gemini_text, _ = generate_gemini_response("[HYBRID FAILOVER] " + system_prompt)
            if gemini_text:
                return {"response": "(Backup Cloud) " + gemini_text, "agent_name": employee["employee_name"]}
        return {"response": "Ollama Offline & Hybrid Gagal.", "agent_name": employee["employee_name"]}
@app.get("/workforce/memory", response_class=HTMLResponse)
async def workforce_memory(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="workforce/memory.html",
        context={}
    )
@app.get("/workforce/tasks", response_class=HTMLResponse)
async def workforce_tasks(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="workforce/tasks.html",
        context={}
    )
@app.get("/workforce/teams", response_class=HTMLResponse)
async def workforce_teams(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="workforce/teams.html",
        context={}
    )

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

@app.get("/api/client/profile")
async def get_client_profile(x_deq_key: str = Header(None)):
    if not x_deq_key:
        raise HTTPException(status_code=401, detail="Token Required")
    conn = get_memory_connection()
    row = conn.execute("SELECT email, business_identity FROM client_profiles WHERE token = ?", (x_deq_key,)).fetchone()
    conn.close()
    return dict(row) if row else {"email": "", "business_identity": ""}

@app.post("/api/client/profile")
async def save_client_profile(req: ClientProfileSaveRequest, x_deq_key: str = Header(None)):
    if not x_deq_key:
        raise HTTPException(status_code=401, detail="Token Required")
    conn = get_memory_connection()
    conn.execute('''
        INSERT INTO client_profiles (token, email, business_identity, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(token) DO UPDATE SET
            email = excluded.email,
            business_identity = excluded.business_identity,
            updated_at = CURRENT_TIMESTAMP
    ''', (x_deq_key, req.email.strip(), req.business_identity.strip()))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/client/history")
async def get_client_history(x_deq_key: str = Header(None)):
    if not x_deq_key:
        raise HTTPException(status_code=401, detail="Token Required")
    conn = get_memory_connection()
    rows = conn.execute('''
        SELECT role, message, created_at
        FROM chat_history
        WHERE token = ?
        ORDER BY id ASC
        LIMIT 100
    ''', (x_deq_key,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/client/prospects")
async def get_client_prospects(x_deq_key: str = Header(None)):
    if not x_deq_key:
        raise HTTPException(status_code=401, detail="Token Required")
    conn = get_memory_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS prospect_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT,
            nama TEXT,
            nohp TEXT,
            keterangan TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    rows = conn.execute('''
        SELECT id, nama, nohp, keterangan, created_at
        FROM prospect_contacts
        WHERE token = ?
        ORDER BY id DESC
        LIMIT 200
    ''', (x_deq_key,)).fetchall()
    conn.commit()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/client/prospects")
async def add_client_prospect(req: ProspectContactRequest, x_deq_key: str = Header(None)):
    if not x_deq_key:
        raise HTTPException(status_code=401, detail="Token Required")
    conn = get_memory_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS prospect_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT,
            nama TEXT,
            nohp TEXT,
            keterangan TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        INSERT INTO prospect_contacts (token, nama, nohp, keterangan)
        VALUES (?, ?, ?, ?)
    ''', (x_deq_key, req.nama.strip(), req.nohp.strip(), req.keterangan.strip()))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/client/history")
async def save_client_history(req: ClientHistoryRequest, x_deq_key: str = Header(None)):
    if not x_deq_key:
        raise HTTPException(status_code=401, detail="Token Required")
    conn = get_memory_connection()
    conn.execute("INSERT INTO chat_history (token, role, message) VALUES (?, ?, ?)", (x_deq_key, req.role.strip(), req.message.strip()))
    conn.execute('''
        DELETE FROM chat_history
        WHERE token = ?
          AND id NOT IN (
              SELECT id FROM chat_history WHERE token = ? ORDER BY id DESC LIMIT 200
          )
    ''', (x_deq_key, x_deq_key))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/client/history")
async def clear_client_history(x_deq_key: str = Header(None)):
    if not x_deq_key:
        raise HTTPException(status_code=401, detail="Token Required")
    conn = get_memory_connection()
    conn.execute("DELETE FROM chat_history WHERE token = ?", (x_deq_key,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/client/history/export", response_class=PlainTextResponse)
async def export_client_history(x_deq_key: str = Header(None)):
    if not x_deq_key:
        raise HTTPException(status_code=401, detail="Token Required")
    conn = get_memory_connection()
    rows = conn.execute('''
        SELECT role, message, created_at
        FROM chat_history
        WHERE token = ?
        ORDER BY id ASC
    ''', (x_deq_key,)).fetchall()
    conn.close()
    lines = ["DEQBOT CLIENT CHAT EXPORT", f"TOKEN: {x_deq_key}", "----------------------------"]
    for r in rows:
        lines.append(f"[{r['created_at']}] {r['role'].upper()}: {r['message']}")
    return "\n".join(lines)

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
        mem_conn = get_memory_connection()
        profile = mem_conn.execute(
            "SELECT business_identity FROM client_profiles WHERE token = ?",
            (x_deq_key,)
        ).fetchone()
        mem_conn.close()
        business_identity = profile["business_identity"] if profile and profile["business_identity"] else "N/A"
        prompt_final = (
            f"ROLE: {client['assigned_characters']}\n"
            f"SOP: {client['admin_instructions']}\n"
            f"INFO: {client['informasi_owner']}\n"
            f"BUSINESS_IDENTITY:\n{business_identity}\n"
            f"INSTRUKSI PENTING: Wajib gunakan data BUSINESS_IDENTITY jika user menanyakan profil bisnis (owner, alamat, jam, dll).\n"
            f"USER: {request['prompt']}"
        )
    conn.close()

    if active_engine == "gemini":
        gemini_text, gemini_error = generate_gemini_response(prompt_final)
        if gemini_text:
            return {"response": gemini_text}
        return {"response": gemini_error}
    else:
        try:
            # Timeout dinaikkan ke 60s untuk load model berat
            res = requests.post("http://localhost:11434/api/generate", 
                                json={"model": active_engine, "prompt": prompt_final, "stream": False}, timeout=60)
            return {"response": res.json().get("response", "")}
        except:
            if hybrid_on:
                gemini_text, _ = generate_gemini_response("[HYBRID FAILOVER] " + prompt_final)
                if gemini_text:
                    return {"response": "(Backup Cloud) " + gemini_text}
            return {"response": "Ollama Offline & Hybrid Gagal."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
