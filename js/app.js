// iHiring.org — shared prototype behavior

document.addEventListener('DOMContentLoaded', () => {
  // CV marketplace entry points for legacy static pages that share this script.
  const sharedNav = document.querySelector('.main-nav');
  if (sharedNav && !sharedNav.querySelector('a[href="/resumes"], a[href="resumes"]')) {
    const jobsLink = sharedNav.querySelector('a[href$="jobs.html"], a[href="/jobs"]');
    const resumesLink = document.createElement('a');
    resumesLink.href = '/resumes';
    resumesLink.textContent = 'Резюме';
    if (window.location.pathname === '/resumes') resumesLink.classList.add('active');
    if (jobsLink) jobsLink.insertAdjacentElement('afterend', resumesLink);
    else sharedNav.prepend(resumesLink);
  }
  const sharedActions = document.querySelector('.header-actions');
  if (sharedActions && !sharedActions.querySelector('a[href*="profile#cv"]')) {
    const cvLink = document.createElement('a');
    cvLink.href = '/profile#cv';
    cvLink.className = 'btn btn-acid btn-sm';
    cvLink.textContent = 'Добавить CV';
    const vacancyLink = sharedActions.querySelector('a[href*="post-job"]');
    if (vacancyLink) sharedActions.insertBefore(cvLink, vacancyLink);
    else sharedActions.prepend(cvLink);
  }

  // mobile nav
  const burger = document.querySelector('.nav-burger');
  const nav = document.querySelector('.main-nav');
  if (burger && nav) {
    burger.setAttribute('aria-expanded', 'false');
    burger.setAttribute('aria-controls', 'main-nav');
    nav.id = nav.id || 'main-nav';
    const setNav = open => {
      nav.classList.toggle('open', open);
      document.body.classList.toggle('nav-open', open);
      burger.setAttribute('aria-expanded', String(open));
      burger.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
      const icon = burger.querySelector('span');
      if (icon) icon.textContent = open ? '✕' : '☰';
    };
    burger.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      setNav(open);
    });
    nav.addEventListener('click', e => { if (e.target.closest('a')) setNav(false); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') setNav(false); });
    document.addEventListener('click', e => {
      if (nav.classList.contains('open') && !nav.contains(e.target) && !burger.contains(e.target)) setNav(false);
    });
    window.addEventListener('resize', () => { if (window.innerWidth > 900) setNav(false); });
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

// (переключатель палитры удалён — фиксированная зелёная гамма)
