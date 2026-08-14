// iHiring.org — shared prototype behavior

document.addEventListener('DOMContentLoaded', () => {
  // mobile nav
  const burger = document.querySelector('.nav-burger');
  const nav = document.querySelector('.main-nav');
  if (burger && nav) {
    burger.setAttribute('aria-expanded', 'false');
    burger.setAttribute('aria-controls', 'main-nav');
    nav.id = nav.id || 'main-nav';
    burger.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      burger.setAttribute('aria-expanded', String(open));
    });
  }

  // auth modal
  const modal = document.getElementById('auth-modal');
  let lastFocused = null;
  document.querySelectorAll('[data-auth]').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      if (modal) {
        lastFocused = btn;
        modal.classList.add('open');
        const first = modal.querySelector('input, button');
        if (first) first.focus();
      }
    });
  });
  if (modal) {
    const closeModal = () => {
      modal.classList.remove('open');
      if (lastFocused) lastFocused.focus();
    };
    modal.addEventListener('click', e => {
      if (e.target === modal || e.target.closest('.modal__close')) closeModal();
    });
    const roleBtns = modal.querySelectorAll('.role-switch button');
    roleBtns.forEach(b => b.addEventListener('click', () => {
      roleBtns.forEach(x => { x.classList.remove('active'); x.setAttribute('aria-pressed', 'false'); });
      b.classList.add('active');
      b.setAttribute('aria-pressed', 'true');
      const submit = modal.querySelector('[data-auth-submit]');
      if (submit) submit.textContent = b.dataset.role === 'employer' ? 'Начать нанимать' : 'Создать профиль';
    }));
    // подключаем модалку к настоящей регистрации/логину (была демо-заглушка)
    const authForm = modal.querySelector('form');
    if (authForm) {
      authForm.removeAttribute('data-demo');
      authForm.addEventListener('submit', ev => {
        ev.preventDefault(); ev.stopImmediatePropagation();
        const active = modal.querySelector('.role-switch button.active');
        const role = active ? active.dataset.role : 'talent';
        window.location.href = '/register?role=' + role;
      }, true);
      if (!modal.querySelector('.auth-login-link')) {
        const p = document.createElement('p');
        p.className = 'auth-login-link';
        p.style.cssText = 'margin-top:14px;font-size:0.85rem;color:var(--ink-dim);text-align:center';
        p.innerHTML = 'Уже есть аккаунт? <a href="/login" style="color:var(--acid);font-weight:800">Войти</a>';
        authForm.insertAdjacentElement('afterend', p);
      }
    }
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && modal.classList.contains('open')) closeModal();
      if (e.key === 'Tab' && modal.classList.contains('open')) {
        const f = modal.querySelectorAll('a[href], button, input, [tabindex]:not([tabindex="-1"])');
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
  }

  // save job toggle
  document.querySelectorAll('.save-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault(); e.stopPropagation();
      btn.classList.toggle('saved');
      btn.textContent = btn.classList.contains('saved') ? '♥' : '♡';
      toast(btn.classList.contains('saved') ? 'Сохранено в список' : 'Убрано из сохранённых');
    });
  });

  // generic demo actions -> toast
  document.querySelectorAll('[data-toast]').forEach(el => {
    el.addEventListener('click', e => {
      if (el.tagName === 'A' || el.type === 'submit') e.preventDefault();
      toast(el.dataset.toast);
    });
  });

  // fake form submits
  document.querySelectorAll('form[data-demo]').forEach(f => {
    f.addEventListener('submit', e => {
      e.preventDefault();
      toast(f.dataset.demo || 'Done — this is a prototype');
    });
  });
});

let toastTimer;
function toast(msg) {
  let el = document.querySelector('.toast');
  if (!el) {
    el = document.createElement('div');
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2400);
}


// 3D tilt (desktop only, respects reduced-motion)
if (window.matchMedia('(pointer: fine)').matches &&
    !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  document.querySelectorAll('.job-card, .co-card, .company-tile, .post-card').forEach(card => {
    card.addEventListener('pointermove', e => {
      const r = card.getBoundingClientRect();
      const rx = ((e.clientY - r.top) / r.height - 0.5) * -6;
      const ry = ((e.clientX - r.left) / r.width - 0.5) * 6;
      card.style.transform = `perspective(700px) rotateX(${rx}deg) rotateY(${ry}deg) translate(-3px, -3px)`;
    });
    card.addEventListener('pointerleave', () => { card.style.transform = ''; });
  });
}

// SpinCoins counter on fab (games live on games.html)
(function () {
  const counter = document.getElementById('coin-count');
  if (counter) counter.textContent = localStorage.getItem('spinCoins') || '0';
})();

// Переключатель светлой/тёмной темы (на всех страницах)
(function () {
  const saved = localStorage.getItem('theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
  function apply(t) {
    if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
    else document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('theme', t);
    if (btn) btn.textContent = t === 'light' ? '🌙' : '☀️';
    if (btn) btn.setAttribute('aria-label', t === 'light' ? 'Тёмная тема' : 'Светлая тема');
  }
  const btn = document.createElement('button');
  btn.className = 'theme-toggle';
  btn.type = 'button';
  document.addEventListener('DOMContentLoaded', () => {
    const foot = document.querySelector('.footer-bottom');
    if (foot) {
      foot.appendChild(btn);
    } else {
      btn.classList.add('theme-toggle--float');
      document.body.appendChild(btn);
    }
    apply(localStorage.getItem('theme') || 'dark');
    btn.addEventListener('click', () => {
      const cur = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
      apply(cur === 'light' ? 'dark' : 'light');
    });
  });
})();

// Живой выбор акцентной гаммы (пробуем цвета из 8 палитр прямо на сайте)
(function () {
  const PRESETS = [
    { id: 'emerald', name: 'Изумруд',  dot: '#00e39a', acid: 'oklch(0.80 0.19 162)', deep: 'oklch(0.68 0.17 164)', on: 'oklch(0.14 0.05 162)' },
    { id: 'cyan',    name: 'Циан',     dot: '#22e0ff', acid: 'oklch(0.84 0.16 205)', deep: 'oklch(0.72 0.15 210)', on: 'oklch(0.14 0.04 220)' },
    { id: 'blue',    name: 'Электрик', dot: '#4d7bff', acid: 'oklch(0.70 0.19 250)', deep: 'oklch(0.60 0.18 255)', on: '#ffffff' },
    { id: 'violet',  name: 'Фиолет',   dot: '#a855ff', acid: 'oklch(0.68 0.22 300)', deep: 'oklch(0.58 0.20 302)', on: '#ffffff' },
    { id: 'magenta', name: 'Магента',  dot: '#ff2d9c', acid: 'oklch(0.70 0.25 350)', deep: 'oklch(0.60 0.23 352)', on: '#ffffff' },
    { id: 'gold',    name: 'Золото',   dot: '#ffb020', acid: 'oklch(0.84 0.16 90)',  deep: 'oklch(0.74 0.15 88)',  on: 'oklch(0.20 0.05 90)' },
    { id: 'aqua',    name: 'Аква',     dot: '#2af0d4', acid: 'oklch(0.85 0.15 178)', deep: 'oklch(0.74 0.14 180)', on: 'oklch(0.15 0.05 178)' },
    { id: 'ruby',    name: 'Рубин',    dot: '#ff3b5c', acid: 'oklch(0.63 0.24 20)',  deep: 'oklch(0.54 0.22 22)',  on: '#ffffff' },
  ];
  function apply(id) {
    const p = PRESETS.find(x => x.id === id) || PRESETS[0];
    const r = document.documentElement.style;
    r.setProperty('--acid', p.acid);
    r.setProperty('--acid-deep', p.deep);
    r.setProperty('--on-acid', p.on);
    r.setProperty('--emerald', p.acid);
    r.setProperty('--on-emerald', p.on);
    r.setProperty('--shadow-acid', '0 8px 30px ' + p.acid.replace(')', ' / 0.22)'));
    localStorage.setItem('accent', p.id);
  }
  const saved = localStorage.getItem('accent');
  if (saved) apply(saved);

  document.addEventListener('DOMContentLoaded', () => {
    const wrap = document.createElement('div'); wrap.className = 'accent-switch';
    const btn = document.createElement('button'); btn.className = 'accent-switch__btn'; btn.type = 'button';
    btn.textContent = '🎨'; btn.setAttribute('aria-label', 'Цветовая гамма');
    const menu = document.createElement('div'); menu.className = 'accent-switch__menu'; menu.hidden = true;
    menu.innerHTML = '<b>Цвет акцента</b>' + PRESETS.map(p =>
      '<button data-acc="' + p.id + '"><i style="background:' + p.dot + '"></i>' + p.name + '</button>').join('');
    wrap.append(menu, btn); document.body.appendChild(wrap);
    btn.addEventListener('click', () => { menu.hidden = !menu.hidden; });
    menu.addEventListener('click', (e) => { const b = e.target.closest('button'); if (!b) return; apply(b.dataset.acc); menu.hidden = true; });
    document.addEventListener('click', (e) => { if (!wrap.contains(e.target)) menu.hidden = true; });
  });
})();
