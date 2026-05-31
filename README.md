# MeetFit 

Platforma internetowa do organizacji wspólnych aktywności sportowych.

<<<<<<< HEAD
## 🌐 Działająca aplikacja
=======
## Działająca aplikacja
>>>>>>> be5408e75bb7d7833f7882cb34b5348ca0a75d26

**https://meetfit-gf12.onrender.com**

## Uruchomienie lokalne

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Aplikacja dostępna pod: http://localhost:8000

## Dane demo

| Login   | Hasło      | Rola  |
|---------|------------|-------|
| jakub   | test123    | user  |
| anna_k  | test123    | user  |
| admin   | admin123   | admin |

## Endpointy API

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| POST | /api/register | Rejestracja użytkownika |
| POST | /api/login | Logowanie |
| POST | /api/logout | Wylogowanie |
| GET | /api/me | Dane zalogowanego użytkownika |
| GET | /api/trainings | Lista treningów (filtry: city, training_type, difficulty) |
| POST | /api/trainings | Utwórz trening (wymaga zagnieżdżonych modeli) |
| GET | /api/trainings/{id} | Szczegóły treningu |
| DELETE | /api/trainings/{id} | Usuń trening |
| POST | /api/trainings/{id}/join | Dołącz do treningu |
| DELETE | /api/trainings/{id}/join | Opuść trening |
| GET | /api/trainings/{id}/comments | Komentarze treningu |
| POST | /api/trainings/{id}/comments | Dodaj komentarz |
| GET | /api/users | Lista użytkowników |
| PUT | /api/users/me | Aktualizuj profil |
| GET | /api/my-trainings | Moje treningi (utworzone + dołączone) |
| GET | /api/calendar | Wydarzenia do kalendarza |
| GET | /api/admin/stats | Statystyki (tylko admin) |

## Deploy na Render.com

1. Wgraj kod na GitHub
2. Utwórz nowy Web Service na render.com
3. Połącz z repozytorium
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
