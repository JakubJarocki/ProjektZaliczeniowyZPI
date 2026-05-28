from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional, List
from datetime import datetime, date
import hashlib
import uuid
import os

app = FastAPI(title="MeetFit API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# MODELE PYDANTIC (z zagnieżdżeniami)
# ─────────────────────────────────────────────

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    email: str
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    gender: str
    experience_level: str
    fitness_goal: Optional[str] = None
    city: str

    @validator("gender")
    def validate_gender(cls, v):
        allowed = ["male", "female", "other"]
        if v not in allowed:
            raise ValueError(f"Płeć musi być jedną z: {allowed}")
        return v

    @validator("experience_level")
    def validate_level(cls, v):
        allowed = ["beginner", "intermediate", "advanced"]
        if v not in allowed:
            raise ValueError(f"Poziom musi być jednym z: {allowed}")
        return v

class UserRegister(UserBase):
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    username: str
    password: str

class UserPublic(BaseModel):
    id: str
    username: str
    first_name: str
    last_name: str
    city: str
    experience_level: str
    fitness_goal: Optional[str]
    gender: str
    user_type: str

class UserInDB(UserPublic):
    email: str
    password_hash: str

# Zagnieżdżony model — lokalizacja siłowni
class GymLocation(BaseModel):
    gym_name: str = Field(..., min_length=2)
    gym_address: Optional[str] = None
    city: str = Field(..., min_length=2)

# Zagnieżdżony model — szczegóły czasu
class TrainingSchedule(BaseModel):
    date: str
    start_time: str
    end_time: Optional[str] = None

    @validator("date")
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Data musi być w formacie YYYY-MM-DD")
        return v

# Główny model treningu — zagnieżdża GymLocation i TrainingSchedule
class TrainingCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    training_type: str
    difficulty_level: str = "medium"
    max_participants: int = Field(default=10, ge=2, le=50)
    location: GymLocation
    schedule: TrainingSchedule

    @validator("training_type")
    def validate_type(cls, v):
        allowed = ["strength", "cardio", "crossfit", "yoga", "other"]
        if v not in allowed:
            raise ValueError(f"Typ musi być jednym z: {allowed}")
        return v

    @validator("difficulty_level")
    def validate_difficulty(cls, v):
        allowed = ["easy", "medium", "hard"]
        if v not in allowed:
            raise ValueError(f"Trudność musi być jedną z: {allowed}")
        return v

class TrainingPublic(BaseModel):
    id: str
    title: str
    description: Optional[str]
    training_type: str
    difficulty_level: str
    max_participants: int
    current_participants: int
    location: GymLocation
    schedule: TrainingSchedule
    creator: UserPublic
    is_joined: bool = False
    created_at: str

class CommentCreate(BaseModel):
    training_id: str
    content: str = Field(..., min_length=1, max_length=500)

class CommentPublic(BaseModel):
    id: str
    training_id: str
    content: str
    author: UserPublic
    created_at: str

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    city: Optional[str] = None
    experience_level: Optional[str] = None
    fitness_goal: Optional[str] = None
    gender: Optional[str] = None

# ─────────────────────────────────────────────
# "BAZY DANYCH" — listy w pamięci
# ─────────────────────────────────────────────

users_db: List[dict] = []
trainings_db: List[dict] = []
participations_db: List[dict] = []  # {user_id, training_id}
comments_db: List[dict] = []
sessions_db: dict = {}  # session_token -> user_id

# ─────────────────────────────────────────────
# HELPERY
# ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_session_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session_token")
    if not token or token not in sessions_db:
        return None
    user_id = sessions_db[token]
    return next((u for u in users_db if u["id"] == user_id), None)

def require_auth(request: Request) -> dict:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Wymagane logowanie")
    return user

def user_to_public(u: dict) -> dict:
    return {
        "id": u["id"],
        "username": u["username"],
        "first_name": u["first_name"],
        "last_name": u["last_name"],
        "city": u["city"],
        "experience_level": u["experience_level"],
        "fitness_goal": u.get("fitness_goal"),
        "gender": u["gender"],
        "user_type": u.get("user_type", "user"),
    }

def training_to_public(t: dict, current_user_id: Optional[str] = None) -> dict:
    creator = next((u for u in users_db if u["id"] == t["creator_id"]), None)
    count = len([p for p in participations_db if p["training_id"] == t["id"]])
    is_joined = any(
        p for p in participations_db
        if p["training_id"] == t["id"] and p["user_id"] == current_user_id
    ) if current_user_id else False
    return {
        "id": t["id"],
        "title": t["title"],
        "description": t.get("description"),
        "training_type": t["training_type"],
        "difficulty_level": t["difficulty_level"],
        "max_participants": t["max_participants"],
        "current_participants": count,
        "location": t["location"],
        "schedule": t["schedule"],
        "creator": user_to_public(creator) if creator else {},
        "is_joined": is_joined,
        "created_at": t["created_at"],
    }

def seed_data():
    """Dodaj przykładowe dane startowe"""
    if users_db:
        return

    admin = {
        "id": str(uuid.uuid4()),
        "username": "admin",
        "email": "admin@meetfit.pl",
        "password_hash": hash_password("admin123"),
        "first_name": "Admin",
        "last_name": "MeetFit",
        "gender": "other",
        "experience_level": "advanced",
        "fitness_goal": "general_fitness",
        "city": "Warszawa",
        "user_type": "admin",
        "created_at": datetime.now().isoformat(),
    }
    users_db.append(admin)

    users_data = [
        ("jakub", "jakub@meetfit.pl", "Jakub", "Jarocki", "male", "intermediate", "muscle_gain", "Warszawa"),
        ("anna_k", "anna@meetfit.pl", "Anna", "Kowalska", "female", "beginner", "weight_loss", "Kraków"),
        ("piotr_w", "piotr@meetfit.pl", "Piotr", "Wiśniewski", "male", "advanced", "strength", "Wrocław"),
        ("marta_n", "marta@meetfit.pl", "Marta", "Nowak", "female", "intermediate", "endurance", "Warszawa"),
    ]

    user_ids = []
    for u in users_data:
        uid = str(uuid.uuid4())
        user_ids.append(uid)
        users_db.append({
            "id": uid,
            "username": u[0],
            "email": u[1],
            "password_hash": hash_password("test123"),
            "first_name": u[2],
            "last_name": u[3],
            "gender": u[4],
            "experience_level": u[5],
            "fitness_goal": u[6],
            "city": u[7],
            "user_type": "user",
            "created_at": datetime.now().isoformat(),
        })

    trainings_data = [
        {
            "title": "Poranny trening siłowy",
            "description": "Skupiamy się na klatce i tricepsach. Poziom średniozaawansowany.",
            "training_type": "strength",
            "difficulty_level": "medium",
            "max_participants": 4,
            "location": {"gym_name": "Fitness Platinium", "gym_address": "ul. Marszałkowska 10", "city": "Warszawa"},
            "schedule": {"date": "2026-06-01", "start_time": "07:00", "end_time": "08:30"},
            "creator_id": user_ids[0],
        },
        {
            "title": "Joga dla początkujących",
            "description": "Relaksacyjna sesja jogi. Przynieś matę!",
            "training_type": "yoga",
            "difficulty_level": "easy",
            "max_participants": 8,
            "location": {"gym_name": "Yoga Studio Zen", "gym_address": "ul. Floriańska 5", "city": "Kraków"},
            "schedule": {"date": "2026-06-02", "start_time": "09:00", "end_time": "10:00"},
            "creator_id": user_ids[1],
        },
        {
            "title": "CrossFit — WOD z przyjaciółmi",
            "description": "Intensywny trening crossfit. Tylko dla zaawansowanych!",
            "training_type": "crossfit",
            "difficulty_level": "hard",
            "max_participants": 6,
            "location": {"gym_name": "CrossFit Wrocław", "gym_address": "ul. Świdnicka 22", "city": "Wrocław"},
            "schedule": {"date": "2026-06-03", "start_time": "18:00", "end_time": "19:30"},
            "creator_id": user_ids[2],
        },
        {
            "title": "Cardio i bieżnia",
            "description": "Trening cardio na bieżni + rower stacjonarny.",
            "training_type": "cardio",
            "difficulty_level": "easy",
            "max_participants": 5,
            "location": {"gym_name": "McFit Warszawa", "gym_address": "ul. Puławska 45", "city": "Warszawa"},
            "schedule": {"date": "2026-06-04", "start_time": "17:00", "end_time": "18:00"},
            "creator_id": user_ids[3],
        },
        {
            "title": "Nogi i plecy — trening klasyczny",
            "description": "Przysiad, martwy ciąg, wiosłowanie. Klasyczny plan.",
            "training_type": "strength",
            "difficulty_level": "hard",
            "max_participants": 3,
            "location": {"gym_name": "Gym One", "gym_address": "ul. Nowy Świat 15", "city": "Warszawa"},
            "schedule": {"date": "2026-06-05", "start_time": "16:00", "end_time": "17:30"},
            "creator_id": user_ids[0],
        },
    ]

    for t in trainings_data:
        tid = str(uuid.uuid4())
        trainings_db.append({
            "id": tid,
            **t,
            "created_at": datetime.now().isoformat(),
        })
        # Dodaj twórcę jako uczestnika
        participations_db.append({"user_id": t["creator_id"], "training_id": tid})

    # Dodaj kilka komentarzy
    if trainings_db and user_ids:
        comments_db.append({
            "id": str(uuid.uuid4()),
            "training_id": trainings_db[0]["id"],
            "content": "Super trening, chętnie dołączę!",
            "author_id": user_ids[1],
            "created_at": datetime.now().isoformat(),
        })
        comments_db.append({
            "id": str(uuid.uuid4()),
            "training_id": trainings_db[0]["id"],
            "content": "Jaki mniej więcej ciężar używamy przy wyciskaniu?",
            "author_id": user_ids[2],
            "created_at": datetime.now().isoformat(),
        })

seed_data()

# ─────────────────────────────────────────────
# STATYCZNE PLIKI + STRONY HTML
# ─────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("templates/index.html")

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return FileResponse("templates/login.html")

@app.get("/register", response_class=HTMLResponse)
async def register_page():
    return FileResponse("templates/register.html")

@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page():
    return FileResponse("templates/calendar.html")

@app.get("/create-training", response_class=HTMLResponse)
async def create_training_page():
    return FileResponse("templates/create_training.html")

@app.get("/my-trainings", response_class=HTMLResponse)
async def my_trainings_page():
    return FileResponse("templates/my_trainings.html")

@app.get("/training/{training_id}", response_class=HTMLResponse)
async def training_detail_page(training_id: str):
    return FileResponse("templates/training_detail.html")

@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    return FileResponse("templates/settings.html")

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return FileResponse("templates/admin.html")

# ─────────────────────────────────────────────
# ENDPOINT 1 — Rejestracja
# ─────────────────────────────────────────────

@app.post("/api/register")
async def register(user: UserRegister):
    if any(u["username"] == user.username for u in users_db):
        raise HTTPException(status_code=400, detail="Nazwa użytkownika jest już zajęta")
    if any(u["email"] == user.email for u in users_db):
        raise HTTPException(status_code=400, detail="Email jest już zarejestrowany")

    new_user = {
        "id": str(uuid.uuid4()),
        "username": user.username,
        "email": user.email,
        "password_hash": hash_password(user.password),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "gender": user.gender,
        "experience_level": user.experience_level,
        "fitness_goal": user.fitness_goal,
        "city": user.city,
        "user_type": "user",
        "created_at": datetime.now().isoformat(),
    }
    users_db.append(new_user)
    return {"success": True, "message": "Konto utworzone pomyślnie"}

# ─────────────────────────────────────────────
# ENDPOINT 2 — Logowanie / Wylogowanie / Sesja
# ─────────────────────────────────────────────

@app.post("/api/login")
async def login(credentials: UserLogin, response: Response):
    user = next(
        (u for u in users_db if u["username"] == credentials.username or u["email"] == credentials.username),
        None
    )
    if not user or user["password_hash"] != hash_password(credentials.password):
        raise HTTPException(status_code=401, detail="Nieprawidłowe dane logowania")

    token = str(uuid.uuid4())
    sessions_db[token] = user["id"]
    response.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return {"success": True, "user": user_to_public(user)}

@app.post("/api/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token and token in sessions_db:
        del sessions_db[token]
    response.delete_cookie("session_token")
    return {"success": True}

@app.get("/api/me")
async def get_me(request: Request):
    user = get_session_user(request)
    if not user:
        return {"logged_in": False}
    return {"logged_in": True, "user": user_to_public(user)}

# ─────────────────────────────────────────────
# ENDPOINT 3 — Treningi (lista + tworzenie)
# ─────────────────────────────────────────────

@app.get("/api/trainings")
async def get_trainings(
    request: Request,
    city: Optional[str] = None,
    training_type: Optional[str] = None,
    difficulty: Optional[str] = None,
):
    user = get_session_user(request)
    uid = user["id"] if user else None
    result = []
    for t in trainings_db:
        if city and t["location"]["city"].lower() != city.lower():
            continue
        if training_type and t["training_type"] != training_type:
            continue
        if difficulty and t["difficulty_level"] != difficulty:
            continue
        result.append(training_to_public(t, uid))
    return {"success": True, "trainings": result}

@app.post("/api/trainings")
async def create_training(training: TrainingCreate, request: Request):
    user = require_auth(request)
    tid = str(uuid.uuid4())
    new_training = {
        "id": tid,
        "title": training.title,
        "description": training.description,
        "training_type": training.training_type,
        "difficulty_level": training.difficulty_level,
        "max_participants": training.max_participants,
        "location": training.location.dict(),
        "schedule": training.schedule.dict(),
        "creator_id": user["id"],
        "created_at": datetime.now().isoformat(),
    }
    trainings_db.append(new_training)
    participations_db.append({"user_id": user["id"], "training_id": tid})
    return {"success": True, "training_id": tid}

# ─────────────────────────────────────────────
# ENDPOINT 4 — Szczegóły / usuwanie treningu
# ─────────────────────────────────────────────

@app.get("/api/trainings/{training_id}")
async def get_training(training_id: str, request: Request):
    user = get_session_user(request)
    uid = user["id"] if user else None
    t = next((t for t in trainings_db if t["id"] == training_id), None)
    if not t:
        raise HTTPException(status_code=404, detail="Trening nie istnieje")
    return {"success": True, "training": training_to_public(t, uid)}

@app.delete("/api/trainings/{training_id}")
async def delete_training(training_id: str, request: Request):
    user = require_auth(request)
    t = next((t for t in trainings_db if t["id"] == training_id), None)
    if not t:
        raise HTTPException(status_code=404, detail="Trening nie istnieje")
    if t["creator_id"] != user["id"] and user.get("user_type") != "admin":
        raise HTTPException(status_code=403, detail="Brak uprawnień")
    trainings_db.remove(t)
    global participations_db
    participations_db = [p for p in participations_db if p["training_id"] != training_id]
    return {"success": True, "message": "Trening usunięty"}

# ─────────────────────────────────────────────
# ENDPOINT 5 — Dołączanie / opuszczanie treningu
# ─────────────────────────────────────────────

@app.post("/api/trainings/{training_id}/join")
async def join_training(training_id: str, request: Request):
    user = require_auth(request)
    t = next((t for t in trainings_db if t["id"] == training_id), None)
    if not t:
        raise HTTPException(status_code=404, detail="Trening nie istnieje")

    already = any(p for p in participations_db if p["training_id"] == training_id and p["user_id"] == user["id"])
    if already:
        raise HTTPException(status_code=400, detail="Już dołączyłeś do tego treningu")

    count = len([p for p in participations_db if p["training_id"] == training_id])
    if count >= t["max_participants"]:
        raise HTTPException(status_code=400, detail="Trening jest pełny")

    participations_db.append({"user_id": user["id"], "training_id": training_id})
    return {"success": True, "message": "Dołączono do treningu"}

@app.delete("/api/trainings/{training_id}/join")
async def leave_training(training_id: str, request: Request):
    user = require_auth(request)
    t = next((t for t in trainings_db if t["id"] == training_id), None)
    if not t:
        raise HTTPException(status_code=404, detail="Trening nie istnieje")
    if t["creator_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Twórca nie może opuścić własnego treningu")

    global participations_db
    before = len(participations_db)
    participations_db = [p for p in participations_db if not (p["training_id"] == training_id and p["user_id"] == user["id"])]
    if len(participations_db) == before:
        raise HTTPException(status_code=400, detail="Nie jesteś uczestnikiem tego treningu")
    return {"success": True, "message": "Opuszczono trening"}

# ─────────────────────────────────────────────
# ENDPOINT 6 — Użytkownicy i profil
# ─────────────────────────────────────────────

@app.get("/api/users")
async def get_users(request: Request, city: Optional[str] = None):
    user = require_auth(request)
    result = []
    for u in users_db:
        if city and u["city"].lower() != city.lower():
            continue
        result.append(user_to_public(u))
    return {"success": True, "users": result}

@app.put("/api/users/me")
async def update_profile(update: UserUpdate, request: Request):
    user = require_auth(request)
    idx = next((i for i, u in enumerate(users_db) if u["id"] == user["id"]), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Użytkownik nie istnieje")
    data = update.dict(exclude_none=True)
    users_db[idx].update(data)
    return {"success": True, "user": user_to_public(users_db[idx])}

# ─────────────────────────────────────────────
# ENDPOINT 7 — Komentarze
# ─────────────────────────────────────────────

@app.get("/api/trainings/{training_id}/comments")
async def get_comments(training_id: str):
    t = next((t for t in trainings_db if t["id"] == training_id), None)
    if not t:
        raise HTTPException(status_code=404, detail="Trening nie istnieje")
    result = []
    for c in comments_db:
        if c["training_id"] != training_id:
            continue
        author = next((u for u in users_db if u["id"] == c["author_id"]), None)
        result.append({
            "id": c["id"],
            "training_id": c["training_id"],
            "content": c["content"],
            "author": user_to_public(author) if author else {},
            "created_at": c["created_at"],
        })
    return {"success": True, "comments": result}

@app.post("/api/trainings/{training_id}/comments")
async def add_comment(training_id: str, comment: CommentCreate, request: Request):
    user = require_auth(request)
    t = next((t for t in trainings_db if t["id"] == training_id), None)
    if not t:
        raise HTTPException(status_code=404, detail="Trening nie istnieje")
    new_comment = {
        "id": str(uuid.uuid4()),
        "training_id": training_id,
        "content": comment.content,
        "author_id": user["id"],
        "created_at": datetime.now().isoformat(),
    }
    comments_db.append(new_comment)
    author = next((u for u in users_db if u["id"] == user["id"]), None)
    return {
        "success": True,
        "comment": {
            **new_comment,
            "author": user_to_public(author),
        }
    }

# ─────────────────────────────────────────────
# ENDPOINT 8 — Statystyki admina
# ─────────────────────────────────────────────

@app.get("/api/admin/stats")
async def get_admin_stats(request: Request):
    user = require_auth(request)
    if user.get("user_type") != "admin":
        raise HTTPException(status_code=403, detail="Brak uprawnień administratora")

    type_counts = {}
    for t in trainings_db:
        tt = t["training_type"]
        type_counts[tt] = type_counts.get(tt, 0) + 1

    city_counts = {}
    for u in users_db:
        c = u["city"]
        city_counts[c] = city_counts.get(c, 0) + 1

    top_cities = sorted(city_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "success": True,
        "stats": {
            "total_users": len(users_db),
            "total_trainings": len(trainings_db),
            "total_participations": len(participations_db),
            "total_comments": len(comments_db),
            "by_type": type_counts,
            "top_cities": [{"city": c, "count": n} for c, n in top_cities],
        }
    }

# ─────────────────────────────────────────────
# ENDPOINT 9 — Kalendarz (wydarzenia)
# ─────────────────────────────────────────────

@app.get("/api/calendar")
async def get_calendar_events(request: Request, city: Optional[str] = None):
    user = get_session_user(request)
    uid = user["id"] if user else None
    events = []
    type_colors = {
        "strength": "#4361ee",
        "cardio": "#dc3545",
        "yoga": "#6f42c1",
        "crossfit": "#fd7e14",
        "other": "#20c997",
    }
    for t in trainings_db:
        if city and t["location"]["city"].lower() != city.lower():
            continue
        is_mine = t["creator_id"] == uid if uid else False
        color = "#28a745" if is_mine else type_colors.get(t["training_type"], "#6c757d")
        is_joined = any(p for p in participations_db if p["training_id"] == t["id"] and p["user_id"] == uid) if uid else False
        events.append({
            "id": t["id"],
            "title": t["title"],
            "start": f"{t['schedule']['date']}T{t['schedule']['start_time']}",
            "end": f"{t['schedule']['date']}T{t['schedule']['end_time']}" if t["schedule"].get("end_time") else None,
            "color": color,
            "extendedProps": {
                "gym_name": t["location"]["gym_name"],
                "city": t["location"]["city"],
                "creator": next((u["first_name"] + " " + u["last_name"] for u in users_db if u["id"] == t["creator_id"]), ""),
                "is_joined": is_joined,
                "training_type": t["training_type"],
            }
        })
    return {"success": True, "events": events}

# ─────────────────────────────────────────────
# ENDPOINT 10 — Treningi użytkownika
# ─────────────────────────────────────────────

@app.get("/api/my-trainings")
async def get_my_trainings(request: Request):
    user = require_auth(request)
    uid = user["id"]

    created = [training_to_public(t, uid) for t in trainings_db if t["creator_id"] == uid]
    joined_ids = {p["training_id"] for p in participations_db if p["user_id"] == uid}
    joined = [training_to_public(t, uid) for t in trainings_db if t["id"] in joined_ids and t["creator_id"] != uid]

    return {"success": True, "created_trainings": created, "joined_trainings": joined}
