// ─── HELPERY ───────────────────────────────────────────

const TYPE_LABELS = { strength:'Siłowy', cardio:'Cardio', crossfit:'CrossFit', yoga:'Joga', other:'Inny' };
const DIFF_LABELS  = { easy:'Łatwy', medium:'Średni', hard:'Trudny' };
const GOAL_LABELS  = { weight_loss:'Redukcja wagi', muscle_gain:'Budowa masy', strength:'Siła', endurance:'Wytrzymałość', general_fitness:'Ogólna kondycja', competition:'Zawody' };
const GENDER_LABELS = { male:'Mężczyzna', female:'Kobieta', other:'Inne' };
const LEVEL_LABELS  = { beginner:'Początkujący', intermediate:'Średniozaawansowany', advanced:'Zaawansowany' };

function escHtml(t){ if(!t) return ''; const d=document.createElement('div'); d.textContent=t; return d.innerHTML; }

function typeBadge(type){
  return `<span class="badge badge-type-${type}">${TYPE_LABELS[type]||type}</span>`;
}
function diffBadge(d){
  return `<span class="badge badge-${d}">${DIFF_LABELS[d]||d}</span>`;
}
function fmtDate(dateStr){
  if(!dateStr) return '';
  const d = new Date(dateStr+'T00:00:00');
  return d.toLocaleDateString('pl-PL', {day:'2-digit', month:'short', year:'numeric'});
}
function fmtTime(t){ return t ? t.substring(0,5) : ''; }
function fmtDateTime(iso){
  const d = new Date(iso);
  return d.toLocaleString('pl-PL',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
}
function initials(u){ return ((u.first_name||'')[0]||(u.username||'')[0]||'?').toUpperCase() + ((u.last_name||'')[0]||'').toUpperCase(); }

function avatar(u, size=''){
  return `<div class="avatar ${size}">${initials(u)}</div>`;
}

async function api(path, opts={}){
  const r = await fetch(path, {credentials:'include', headers:{'Content-Type':'application/json'}, ...opts});
  const data = await r.json();
  if(!r.ok) throw new Error(data.detail || 'Błąd serwera');
  return data;
}

function showToast(msg, type='success'){
  let container = document.getElementById('toast-container');
  if(!container){
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;display:flex;flex-direction:column;gap:0.5rem;';
    document.body.appendChild(container);
  }
  const t = document.createElement('div');
  const colors = { success:'rgba(0,200,150,0.12)', danger:'rgba(255,87,87,0.12)', info:'rgba(14,165,233,0.12)' };
  const borders = { success:'rgba(0,200,150,0.4)', danger:'rgba(255,87,87,0.4)', info:'rgba(14,165,233,0.4)' };
  const icons = { success:'✓', danger:'✕', info:'i' };
  t.style.cssText = `background:${colors[type]||colors.info};border:1px solid ${borders[type]||borders.info};color:var(--text);border-radius:10px;padding:0.75rem 1.1rem;font-size:0.9rem;display:flex;align-items:center;gap:0.6rem;min-width:240px;max-width:340px;backdrop-filter:blur(8px);animation:slideIn 0.2s ease;`;
  t.innerHTML = `<span style="font-weight:700">${icons[type]||''}</span>${escHtml(msg)}`;
  container.appendChild(t);
  setTimeout(()=>{ t.style.opacity='0'; t.style.transition='opacity 0.3s'; setTimeout(()=>t.remove(),300); }, 3200);
}

const style = document.createElement('style');
style.textContent = '@keyframes slideIn{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}';
document.head.appendChild(style);

// ─── NAWIGACJA ──────────────────────────────────────────

let _currentUser = null;

async function loadNavbar(){
  try {
    const data = await api('/api/me');
    _currentUser = data.logged_in ? data.user : null;
    renderNavbar(_currentUser);
  } catch(e){
    renderNavbar(null);
  }
}

function renderNavbar(user){
  const nav = document.getElementById('app-navbar');
  if(!nav) return;
  const path = window.location.pathname;

  const links = user ? `
    <li class="nav-item"><a class="nav-link${path==='/calendar'?' active':''}" href="/calendar"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="currentColor" class="me-1" viewBox="0 0 16 16"><path d="M3.5 0a.5.5 0 0 1 .5.5V1h8V.5a.5.5 0 0 1 1 0V1h1a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h1V.5a.5.5 0 0 1 .5-.5zM1 4v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4H1z"/></svg>Kalendarz</a></li>
    <li class="nav-item"><a class="nav-link${path==='/create-training'?' active':''}" href="/create-training"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="currentColor" class="me-1" viewBox="0 0 16 16"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/><path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4z"/></svg>Utwórz trening</a></li>
    <li class="nav-item"><a class="nav-link${path==='/my-trainings'?' active':''}" href="/my-trainings"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="currentColor" class="me-1" viewBox="0 0 16 16"><path d="M1 2.828c.885-.37 2.154-.769 3.388-.893 1.33-.134 2.458.063 3.112.752v9.746c-.935-.53-2.12-.603-3.213-.493-1.18.12-2.37.461-3.287.811V2.828zm7.5-.141c.654-.689 1.782-.886 3.112-.752 1.234.124 2.503.523 3.388.893v9.923c-.918-.35-2.107-.692-3.287-.81-1.094-.111-2.278-.039-3.213.492V2.687zM8 1.783C7.015.936 5.587.81 4.287.94c-1.514.153-3.042.672-3.994 1.105A.5.5 0 0 0 0 2.5v11a.5.5 0 0 0 .707.455c.882-.4 2.303-.881 3.68-1.02 1.409-.142 2.59.087 3.223.877a.5.5 0 0 0 .78 0c.633-.79 1.814-1.019 3.222-.877 1.378.139 2.8.62 3.681 1.02A.5.5 0 0 0 16 13.5v-11a.5.5 0 0 0-.293-.455c-.952-.433-2.48-.952-3.994-1.105C10.413.809 8.985.936 8 1.783z"/></svg>Moje treningi</a></li>
    ${user.user_type==='admin'?`<li class="nav-item"><a class="nav-link${path==='/admin'?' active':''}" href="/admin">Panel admina</a></li>`:''}
  ` : '';

  const userMenu = user ? `
    <div class="nav-item dropdown">
      <a class="nav-link dropdown-toggle d-flex align-items-center gap-2" href="#" data-bs-toggle="dropdown">
        ${avatar(user)} <span>${escHtml(user.first_name)}</span>
      </a>
      <ul class="dropdown-menu dropdown-menu-end">
        <li><a class="dropdown-item" href="/settings">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="currentColor" viewBox="0 0 16 16"><path d="M8 4.754a3.246 3.246 0 1 0 0 6.492 3.246 3.246 0 0 0 0-6.492zM5.754 8a2.246 2.246 0 1 1 4.492 0 2.246 2.246 0 0 1-4.492 0z"/><path d="M9.796 1.343c-.527-1.79-3.065-1.79-3.592 0l-.094.319a.873.873 0 0 1-1.255.52l-.292-.16c-1.64-.892-3.433.902-2.54 2.541l.159.292a.873.873 0 0 1-.52 1.255l-.319.094c-1.79.527-1.79 3.065 0 3.592l.319.094a.873.873 0 0 1 .52 1.255l-.16.292c-.892 1.64.902 3.433 2.541 2.54l.292-.159a.873.873 0 0 1 1.255.52l.094.319c.527 1.79 3.065 1.79 3.592 0l.094-.319a.873.873 0 0 1 1.255-.52l.292.16c1.64.892 3.433-.902 2.54-2.541l-.159-.292a.873.873 0 0 1 .52-1.255l.319-.094c1.79-.527 1.79-3.065 0-3.592l-.319-.094a.873.873 0 0 1-.52-1.255l.16-.292c.892-1.64-.902-3.433-2.541-2.54l-.292.159a.873.873 0 0 1-1.255-.52l-.094-.319zm-2.633.283c.246-.835 1.428-.835 1.674 0l.094.319a1.873 1.873 0 0 0 2.693 1.115l.291-.16c.764-.415 1.6.42 1.184 1.185l-.159.292a1.873 1.873 0 0 0 1.116 2.692l.318.094c.835.246.835 1.428 0 1.674l-.319.094a1.873 1.873 0 0 0-1.115 2.693l.16.291c.415.764-.42 1.6-1.185 1.184l-.292-.159a1.873 1.873 0 0 0-2.692 1.116l-.094.318c-.246.835-1.428.835-1.674 0l-.094-.319a1.873 1.873 0 0 0-2.693-1.115l-.291.16c-.764.415-1.6-.42-1.184-1.185l.159-.292a1.873 1.873 0 0 0-1.116-2.692l-.318-.094c-.835-.246-.835-1.428 0-1.674l.319-.094a1.873 1.873 0 0 0 1.115-2.693l-.16-.291c-.415-.764.42-1.6 1.185-1.184l.292.159a1.873 1.873 0 0 0 2.692-1.116l.094-.318z"/></svg>
          Ustawienia
        </a></li>
        <li><hr class="dropdown-divider"></li>
        <li><a class="dropdown-item text-danger" href="#" onclick="logout(event)">
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="currentColor" viewBox="0 0 16 16"><path fill-rule="evenodd" d="M10 12.5a.5.5 0 0 1-.5.5h-8a.5.5 0 0 1-.5-.5v-9a.5.5 0 0 1 .5-.5h8a.5.5 0 0 1 .5.5v2a.5.5 0 0 0 1 0v-2A1.5 1.5 0 0 0 9.5 2h-8A1.5 1.5 0 0 0 0 3.5v9A1.5 1.5 0 0 0 1.5 14h8a1.5 1.5 0 0 0 1.5-1.5v-2a.5.5 0 0 0-1 0v2z"/><path fill-rule="evenodd" d="M15.854 8.354a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708.708L14.293 7.5H5.5a.5.5 0 0 0 0 1h8.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3z"/></svg>
          Wyloguj
        </a></li>
      </ul>
    </div>
  ` : `
    <li class="nav-item"><a class="nav-link" href="/login">Zaloguj</a></li>
    <li class="nav-item ms-1"><a class="btn btn-primary btn-sm" href="/register">Dołącz</a></li>
  `;

  nav.innerHTML = `
    <div class="container">
      <a class="navbar-brand" href="/"><span>Meet</span>Fit</a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navCollapse">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navCollapse">
        <ul class="navbar-nav me-auto gap-1">${links}</ul>
        <ul class="navbar-nav align-items-center gap-1">${userMenu}</ul>
      </div>
    </div>
  `;
}

async function logout(e){
  e.preventDefault();
  try {
    await api('/api/logout', {method:'POST'});
    window.location.href = '/';
  } catch(err) {
    window.location.href = '/';
  }
}

document.addEventListener('DOMContentLoaded', loadNavbar);
