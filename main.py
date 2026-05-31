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

    # ── ADMIN ──
    admin_id = str(uuid.uuid4())
    users_db.append({
        "id": admin_id,
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
    })

    # ── UŻYTKOWNICY (15 osób, różne miasta) ──
    users_data = [
        ("jakub",     "jakub@meetfit.pl",     "Jakub",     "Jarocki",     "male",   "intermediate", "muscle_gain",    "Warszawa"),
        ("anna_k",    "anna@meetfit.pl",       "Anna",      "Kowalska",    "female", "beginner",     "weight_loss",    "Kraków"),
        ("piotr_w",   "piotr@meetfit.pl",      "Piotr",     "Wiśniewski",  "male",   "advanced",     "strength",       "Wrocław"),
        ("marta_n",   "marta@meetfit.pl",      "Marta",     "Nowak",       "female", "intermediate", "endurance",      "Warszawa"),
        ("tomek_g",   "tomek@meetfit.pl",      "Tomasz",    "Grabowski",   "male",   "advanced",     "competition",    "Gdańsk"),
        ("karol_m",   "karol@meetfit.pl",      "Karolina",  "Mazur",       "female", "beginner",     "general_fitness","Poznań"),
        ("michal_z",  "michal@meetfit.pl",     "Michał",    "Zając",       "male",   "intermediate", "muscle_gain",    "Gdańsk"),
        ("ola_b",     "ola@meetfit.pl",        "Aleksandra","Bąk",         "female", "advanced",     "strength",       "Wrocław"),
        ("radek_k",   "radek@meetfit.pl",      "Radosław",  "Kaczmarek",   "male",   "beginner",     "weight_loss",    "Łódź"),
        ("kasia_p",   "kasia@meetfit.pl",      "Katarzyna", "Pawlak",      "female", "intermediate", "endurance",      "Kraków"),
        ("bartek_s",  "bartek@meetfit.pl",     "Bartosz",   "Sikora",      "male",   "advanced",     "competition",    "Warszawa"),
        ("ewa_w",     "ewa@meetfit.pl",        "Ewa",       "Wróbel",      "female", "beginner",     "general_fitness","Poznań"),
        ("lukasz_d",  "lukasz@meetfit.pl",     "Łukasz",    "Dąbrowski",   "male",   "intermediate", "muscle_gain",    "Łódź"),
        ("magda_j",   "magda@meetfit.pl",      "Magdalena", "Jabłońska",   "female", "advanced",     "strength",       "Gdańsk"),
        ("robert_c",  "robert@meetfit.pl",     "Robert",    "Czajka",      "male",   "intermediate", "endurance",      "Wrocław"),
    ]

    uids = []
    for u in users_data:
        uid = str(uuid.uuid4())
        uids.append(uid)
        users_db.append({
            "id": uid,
            "username": u[0], "email": u[1],
            "password_hash": hash_password("test123"),
            "first_name": u[2], "last_name": u[3],
            "gender": u[4], "experience_level": u[5],
            "fitness_goal": u[6], "city": u[7],
            "user_type": "user",
            "created_at": datetime.now().isoformat(),
        })

    # skróty dla czytelności
    jakub, anna, piotr, marta, tomek = uids[0], uids[1], uids[2], uids[3], uids[4]
    karol, michal, ola, radek, kasia = uids[5], uids[6], uids[7], uids[8], uids[9]
    bartek, ewa, lukasz, magda, robert = uids[10], uids[11], uids[12], uids[13], uids[14]

    # ── TRENINGI — cały czerwiec 2026 ──
    # Dni bez treningu: 6, 9, 14, 18, 22, 25 → reszta ma 1-2 treningi
    trainings_data = [
        # 1 czerwca
        {"title": "Poranny trening siłowy — klatka i triceps", "description": "Skupiamy się na klatce piersiowej i tricepsach. Wyciskanie, rozpiętki, pompki na poręczach.", "training_type": "strength", "difficulty_level": "medium", "max_participants": 4, "location": {"gym_name": "Fitness Platinium", "gym_address": "ul. Marszałkowska 10", "city": "Warszawa"}, "schedule": {"date": "2026-06-01", "start_time": "07:00", "end_time": "08:30"}, "creator_id": jakub},
        # 2 czerwca
        {"title": "Joga dla początkujących", "description": "Relaksacyjna sesja jogi. Przynieś własną matę. Skupiamy się na oddechu i rozciąganiu.", "training_type": "yoga", "difficulty_level": "easy", "max_participants": 8, "location": {"gym_name": "Yoga Studio Zen", "gym_address": "ul. Floriańska 5", "city": "Kraków"}, "schedule": {"date": "2026-06-02", "start_time": "09:00", "end_time": "10:00"}, "creator_id": anna},
        # 3 czerwca
        {"title": "CrossFit WOD — siła i kondycja", "description": "Intensywny trening crossfit. Burpees, kettlebell swings, box jumps. Tylko dla zaawansowanych!", "training_type": "crossfit", "difficulty_level": "hard", "max_participants": 6, "location": {"gym_name": "CrossFit Wrocław", "gym_address": "ul. Świdnicka 22", "city": "Wrocław"}, "schedule": {"date": "2026-06-03", "start_time": "18:00", "end_time": "19:30"}, "creator_id": piotr},
        # 4 czerwca
        {"title": "Cardio — bieżnia i rower", "description": "45 minut cardio: 20 min bieżnia, 25 min rower stacjonarny. Tempo umiarkowane.", "training_type": "cardio", "difficulty_level": "easy", "max_participants": 5, "location": {"gym_name": "McFit Warszawa", "gym_address": "ul. Puławska 45", "city": "Warszawa"}, "schedule": {"date": "2026-06-04", "start_time": "17:00", "end_time": "18:00"}, "creator_id": marta},
        # 5 czerwca
        {"title": "Nogi i plecy — trening klasyczny", "description": "Przysiad ze sztangą, martwy ciąg, wiosłowanie. Solidna praca nad dużymi partiami mięśniowymi.", "training_type": "strength", "difficulty_level": "hard", "max_participants": 3, "location": {"gym_name": "Gym One", "gym_address": "ul. Nowy Świat 15", "city": "Warszawa"}, "schedule": {"date": "2026-06-05", "start_time": "16:00", "end_time": "17:30"}, "creator_id": jakub},
        # 5 czerwca — Gdańsk
        {"title": "Bieganie po plaży — interwały", "description": "Trening biegowy na plaży. Seria sprintów i truchtu. Spotykamy się przy wejściu nr 5.", "training_type": "cardio", "difficulty_level": "medium", "max_participants": 10, "location": {"gym_name": "Plaża Jelitkowo", "gym_address": "ul. Jelitkowska 1", "city": "Gdańsk"}, "schedule": {"date": "2026-06-05", "start_time": "07:30", "end_time": "09:00"}, "creator_id": tomek},
        # 7 czerwca
        {"title": "Pilates — core i stabilizacja", "description": "Godzina pilatesu skupionego na wzmacnianiu core. Poziom dla wszystkich.", "training_type": "yoga", "difficulty_level": "easy", "max_participants": 6, "location": {"gym_name": "Studio Forma", "gym_address": "ul. Długa 8", "city": "Poznań"}, "schedule": {"date": "2026-06-07", "start_time": "10:00", "end_time": "11:00"}, "creator_id": karol},
        # 8 czerwca
        {"title": "Siłownia — Push Day", "description": "Klasyczny push day: klatka, barki, triceps. Pytaj na czacie jeśli masz pytania do planu.", "training_type": "strength", "difficulty_level": "medium", "max_participants": 4, "location": {"gym_name": "BodyFit Gdańsk", "gym_address": "ul. Grunwaldzka 100", "city": "Gdańsk"}, "schedule": {"date": "2026-06-08", "start_time": "18:30", "end_time": "20:00"}, "creator_id": michal},
        # 8 czerwca — Wrocław
        {"title": "Crossfit dla początkujących", "description": "Wprowadzenie do crossfitu. Uczymy techniki podstawowych ruchów. Brak limitu stażu.", "training_type": "crossfit", "difficulty_level": "easy", "max_participants": 8, "location": {"gym_name": "CrossFit Wrocław", "gym_address": "ul. Świdnicka 22", "city": "Wrocław"}, "schedule": {"date": "2026-06-08", "start_time": "10:00", "end_time": "11:30"}, "creator_id": ola},
        # 10 czerwca
        {"title": "Trening funkcjonalny — TRX", "description": "Trening z taśmami TRX. Praca z własną masą ciała. Przynieś butelkę wody.", "training_type": "strength", "difficulty_level": "medium", "max_participants": 5, "location": {"gym_name": "FitZone Łódź", "gym_address": "ul. Piotrkowska 200", "city": "Łódź"}, "schedule": {"date": "2026-06-10", "start_time": "17:00", "end_time": "18:00"}, "creator_id": radek},
        # 11 czerwca
        {"title": "Joga — power flow", "description": "Dynamiczna joga dla średniozaawansowanych. Połączenie siły i elastyczności.", "training_type": "yoga", "difficulty_level": "medium", "max_participants": 7, "location": {"gym_name": "Yoga Studio Zen", "gym_address": "ul. Floriańska 5", "city": "Kraków"}, "schedule": {"date": "2026-06-11", "start_time": "08:00", "end_time": "09:30"}, "creator_id": kasia},
        # 12 czerwca
        {"title": "Maraton treningowy — Pull Day", "description": "Plecy i biceps: podciągania, wiosłowania, uginania. Przyjdź głodny treningu!", "training_type": "strength", "difficulty_level": "hard", "max_participants": 4, "location": {"gym_name": "Gym One", "gym_address": "ul. Nowy Świat 15", "city": "Warszawa"}, "schedule": {"date": "2026-06-12", "start_time": "19:00", "end_time": "20:30"}, "creator_id": bartek},
        # 13 czerwca
        {"title": "Bieganie — 5K razem", "description": "Wspólny bieg 5 km po parku. Tempo 5:30-6:00 min/km. Startujemy od fontanny.", "training_type": "cardio", "difficulty_level": "easy", "max_participants": 12, "location": {"gym_name": "Park Cytadela", "gym_address": "ul. Cytadela 1", "city": "Poznań"}, "schedule": {"date": "2026-06-13", "start_time": "07:00", "end_time": "08:00"}, "creator_id": ewa},
        # 15 czerwca
        {"title": "Siłownia — nogi i pośladki", "description": "Praca nad nogami: przysiady, wykroki, leg press. Obowiązkowe rozgrzewanie 10 min.", "training_type": "strength", "difficulty_level": "medium", "max_participants": 4, "location": {"gym_name": "FitZone Łódź", "gym_address": "ul. Piotrkowska 200", "city": "Łódź"}, "schedule": {"date": "2026-06-15", "start_time": "16:30", "end_time": "18:00"}, "creator_id": lukasz},
        # 16 czerwca
        {"title": "Poranny CrossFit — AMRAP 20", "description": "20 minut AMRAP: 10 burpees, 15 kettlebell swings, 20 sit-ups. Zaawansowani mile widziani.", "training_type": "crossfit", "difficulty_level": "hard", "max_participants": 6, "location": {"gym_name": "CrossBox Gdańsk", "gym_address": "ul. Wrzeszcz 5", "city": "Gdańsk"}, "schedule": {"date": "2026-06-16", "start_time": "06:30", "end_time": "07:30"}, "creator_id": magda},
        # 16 czerwca — Wrocław
        {"title": "Cardio + stretching", "description": "Godzina cardio na sprzęcie + 20 minut stretchingu. Dobry trening na środek tygodnia.", "training_type": "cardio", "difficulty_level": "easy", "max_participants": 6, "location": {"gym_name": "Fitness World Wrocław", "gym_address": "ul. Legnicka 55", "city": "Wrocław"}, "schedule": {"date": "2026-06-16", "start_time": "17:30", "end_time": "19:00"}, "creator_id": robert},
        # 17 czerwca
        {"title": "Trening siłowy — full body", "description": "Pełny trening całego ciała. Idealne na środek tygodnia. 3 serie po 10 powtórzeń na ćwiczenie.", "training_type": "strength", "difficulty_level": "medium", "max_participants": 5, "location": {"gym_name": "Fitness Platinium", "gym_address": "ul. Marszałkowska 10", "city": "Warszawa"}, "schedule": {"date": "2026-06-17", "start_time": "18:00", "end_time": "19:30"}, "creator_id": jakub},
        # 19 czerwca
        {"title": "Joga — relaks i medytacja", "description": "Yin yoga i medytacja. 90 minut głębokiego rozciągania i wyciszenia umysłu.", "training_type": "yoga", "difficulty_level": "easy", "max_participants": 10, "location": {"gym_name": "Yoga Studio Zen", "gym_address": "ul. Floriańska 5", "city": "Kraków"}, "schedule": {"date": "2026-06-19", "start_time": "18:00", "end_time": "19:30"}, "creator_id": anna},
        # 20 czerwca
        {"title": "Crossfit — Murph challenge", "description": "Legendarny WOD Murph: 1 mila biegu, 100 podciągnięć, 200 pompek, 300 przysiadów, 1 mila biegu.", "training_type": "crossfit", "difficulty_level": "hard", "max_participants": 8, "location": {"gym_name": "CrossFit Wrocław", "gym_address": "ul. Świdnicka 22", "city": "Wrocław"}, "schedule": {"date": "2026-06-20", "start_time": "09:00", "end_time": "11:00"}, "creator_id": piotr},
        # 20 czerwca — Gdańsk
        {"title": "Bieganie na czas — 10K", "description": "Próba na 10 km. Mierzymy czas. Trasa: wzdłuż brzegu morza i z powrotem.", "training_type": "cardio", "difficulty_level": "hard", "max_participants": 6, "location": {"gym_name": "Plaża Sopot", "gym_address": "ul. Bitwy pod Płowcami 1", "city": "Gdańsk"}, "schedule": {"date": "2026-06-20", "start_time": "07:00", "end_time": "09:00"}, "creator_id": tomek},
        # 21 czerwca
        {"title": "Siłownia — ramiona i barki", "description": "Dzień na barki i ramiona. OHP, lateral raise, face pull, uginania różne chwyty.", "training_type": "strength", "difficulty_level": "medium", "max_participants": 4, "location": {"gym_name": "BodyFit Gdańsk", "gym_address": "ul. Grunwaldzka 100", "city": "Gdańsk"}, "schedule": {"date": "2026-06-21", "start_time": "17:00", "end_time": "18:30"}, "creator_id": michal},
        # 23 czerwca
        {"title": "Tabata — spalanie kalorii", "description": "8 rund tabaty: 20 sek pracy, 10 sek odpoczynku. Gwarantowane spalanie kalorii!", "training_type": "cardio", "difficulty_level": "medium", "max_participants": 8, "location": {"gym_name": "FitZone Łódź", "gym_address": "ul. Piotrkowska 200", "city": "Łódź"}, "schedule": {"date": "2026-06-23", "start_time": "18:00", "end_time": "19:00"}, "creator_id": radek},
        # 24 czerwca
        {"title": "Power yoga — siła i balans", "description": "Intensywna joga łącząca elementy siłowe z pracą nad równowagą. Poziom średniozaawansowany.", "training_type": "yoga", "difficulty_level": "medium", "max_participants": 7, "location": {"gym_name": "Studio Forma", "gym_address": "ul. Długa 8", "city": "Poznań"}, "schedule": {"date": "2026-06-24", "start_time": "09:00", "end_time": "10:30"}, "creator_id": karol},
        # 24 czerwca — Warszawa
        {"title": "Trening z kettlebell", "description": "Praca z kettlebell: swings, clean & press, turkish get-up. Przyjdź z rękawiczkami.", "training_type": "strength", "difficulty_level": "medium", "max_participants": 5, "location": {"gym_name": "Gym One", "gym_address": "ul. Nowy Świat 15", "city": "Warszawa"}, "schedule": {"date": "2026-06-24", "start_time": "19:00", "end_time": "20:00"}, "creator_id": bartek},
        # 26 czerwca
        {"title": "Bieganie — fartlek w parku", "description": "Fartlek 45 minut w parku. Naprzemienne przyspieszenia i trucht. Dla każdego poziomu.", "training_type": "cardio", "difficulty_level": "easy", "max_participants": 10, "location": {"gym_name": "Park Sołacki", "gym_address": "ul. Sołacka 1", "city": "Poznań"}, "schedule": {"date": "2026-06-26", "start_time": "07:30", "end_time": "08:30"}, "creator_id": ewa},
        # 27 czerwca
        {"title": "Siłownia — nogi ciężkie", "description": "Ciężki dzień na nogi: przysiad z pauzą, RDL, hack squat, leg curl. Nie dla słabeuszy!", "training_type": "strength", "difficulty_level": "hard", "max_participants": 3, "location": {"gym_name": "FitZone Łódź", "gym_address": "ul. Piotrkowska 200", "city": "Łódź"}, "schedule": {"date": "2026-06-27", "start_time": "16:00", "end_time": "17:30"}, "creator_id": lukasz},
        # 27 czerwca — Gdańsk
        {"title": "CrossFit — Girls WODs", "description": "Legendarny benchmark Fran: 21-15-9 thrusters i podciągnięcia. Mierzymy czas.", "training_type": "crossfit", "difficulty_level": "hard", "max_participants": 6, "location": {"gym_name": "CrossBox Gdańsk", "gym_address": "ul. Wrzeszcz 5", "city": "Gdańsk"}, "schedule": {"date": "2026-06-27", "start_time": "09:00", "end_time": "10:30"}, "creator_id": magda},
        # 28 czerwca
        {"title": "Trening cardio — rower i elipsa", "description": "45 min rower + 30 min elipsa. Tempo tlenowe, rozmowa możliwa. Luz i dobre nawodnienie.", "training_type": "cardio", "difficulty_level": "easy", "max_participants": 6, "location": {"gym_name": "Fitness World Wrocław", "gym_address": "ul. Legnicka 55", "city": "Wrocław"}, "schedule": {"date": "2026-06-28", "start_time": "10:00", "end_time": "11:30"}, "creator_id": robert},
        # 29 czerwca
        {"title": "Siłownia — Push/Pull split", "description": "Połączony trening push i pull w jednej sesji. Oszczędzamy czas, maksimum efektów.", "training_type": "strength", "difficulty_level": "medium", "max_participants": 4, "location": {"gym_name": "Fitness Platinium", "gym_address": "ul. Marszałkowska 10", "city": "Warszawa"}, "schedule": {"date": "2026-06-29", "start_time": "17:30", "end_time": "19:00"}, "creator_id": jakub},
        # 30 czerwca
        {"title": "Joga końca miesiąca — reset", "description": "Ostatni dzień czerwca — czas na regenerację. Joga restoratywna i oddech. Zapraszamy wszystkich!", "training_type": "yoga", "difficulty_level": "easy", "max_participants": 12, "location": {"gym_name": "Yoga Studio Zen", "gym_address": "ul. Floriańska 5", "city": "Kraków"}, "schedule": {"date": "2026-06-30", "start_time": "18:00", "end_time": "19:00"}, "creator_id": kasia},
        # 30 czerwca — Warszawa
        {"title": "CrossFit — zamknięcie miesiąca", "description": "Ostatni crossfit czerwca. Zrobimy coś specjalnego — niespodzianka dla uczestników!", "training_type": "crossfit", "difficulty_level": "medium", "max_participants": 8, "location": {"gym_name": "CrossFit Mokotów", "gym_address": "ul. Puławska 90", "city": "Warszawa"}, "schedule": {"date": "2026-06-30", "start_time": "10:00", "end_time": "11:30"}, "creator_id": bartek},
    ]

    for t in trainings_data:
        tid = str(uuid.uuid4())
        trainings_db.append({"id": tid, **t, "created_at": datetime.now().isoformat()})
        participations_db.append({"user_id": t["creator_id"], "training_id": tid})

    # ── Dodaj kilku uczestników do wybranych treningów ──
    def join(uid, tidx):
        tid = trainings_db[tidx]["id"]
        if not any(p for p in participations_db if p["user_id"]==uid and p["training_id"]==tid):
            participations_db.append({"user_id": uid, "training_id": tid})

    join(marta, 0); join(bartek, 0); join(anna, 2)
    join(jakub, 1); join(kasia, 1); join(ewa, 1)
    join(ola, 2);   join(robert, 2)
    join(tomek, 3); join(michal, 3)
    join(anna, 4);  join(kasia, 10); join(radek, 10)
    join(lukasz, 5); join(magda, 5); join(michal, 5)
    join(piotr, 11); join(robert, 11)
    join(jakub, 16); join(marta, 16); join(bartek, 16)
    join(anna, 18);  join(kasia, 18); join(ewa, 18)

    # ── Komentarze ──
    comments = [
        (0, anna,   "Super, dołączam! Czy używamy sztangi olimpijskiej?"),
        (0, bartek, "Jakub, jakie mniej więcej ciężary na wyciskaniu?"),
        (0, jakub,  "Zależy od poziomu — dla mnie ~100kg, dla początkujących ~60kg. Dogadamy na miejscu 💪"),
        (1, jakub,  "Nigdy nie próbowałem jogi, myślę że czas najwyższy!"),
        (1, kasia,  "Świetny wybór, joga to game changer dla regeneracji po siłowni"),
        (2, marta,  "Crossfit mnie przeraża ale spróbuję 😅"),
        (2, ola,    "Nie bój się, na początku wszyscy się boją. Po jednym treningu wciągasz się totalnie!"),
        (5, lukasz, "Bieganie po plaży brzmi genialnie, dołączam!"),
        (5, radek,  "Ile km planujecie łącznie?"),
        (5, tomek,  "Około 6-8 km zależy od tempa grupy, zobaczymy na miejscu"),
        (16, anna,  "Full body to mój ulubiony styl treningów!"),
        (18, jakub, "Yin yoga? Słyszałem że to najcięższa joga psychicznie 😂"),
        (18, anna,  "I masz rację! Leżysz spokojnie ale umysł szaleje haha"),
    ]
    for tidx, uid, content in comments:
        comments_db.append({
            "id": str(uuid.uuid4()),
            "training_id": trainings_db[tidx]["id"],
            "content": content,
            "author_id": uid,
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
