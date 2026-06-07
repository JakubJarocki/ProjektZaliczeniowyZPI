# MeetFit 

Platforma internetowa do organizacji wspólnych aktywności sportowych.

## Działająca aplikacja

**https://meetfit-gf12.onrender.com**

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
