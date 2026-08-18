// iHiring.org — shared prototype behavior

document.addEventListener('DOMContentLoaded', () => {
  // Единый выпадающий список SpinHire вместо системного меню браузера.
  const customSelects = [];
  const closeSelect = (item, restoreFocus = false) => {
    if (!item || !item.wrapper.classList.contains('is-open')) return;
    item.wrapper.classList.remove('is-open');
    item.trigger.setAttribute('aria-expanded', 'false');
    if (restoreFocus) item.trigger.focus();
  };
  const closeAllSelects = except => customSelects.forEach(item => { if (item !== except) closeSelect(item); });

  document.querySelectorAll('select:not([multiple]):not([data-native-select])').forEach((select, selectIndex) => {
    const measuredWidth = Math.ceil(select.getBoundingClientRect().width);
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select' + (select.disabled ? ' is-disabled' : '');
    if (measuredWidth) wrapper.style.setProperty('--select-width', measuredWidth + 'px');
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);
    select.classList.add('custom-select__native');

    const trigger = document.createElement('button');
    trigger.type = 'button'; trigger.className = 'custom-select__trigger';
    trigger.setAttribute('aria-haspopup', 'listbox'); trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-label', select.getAttribute('aria-label') || select.name || 'Выберите значение');
    trigger.disabled = select.disabled;
    wrapper.appendChild(trigger);

    const menu = document.createElement('div'); menu.className = 'custom-select__menu';
    const list = document.createElement('div'); list.className = 'custom-select__options';
    list.id = 'custom-select-' + selectIndex; list.setAttribute('role', 'listbox');
    trigger.setAttribute('aria-controls', list.id);
    const empty = document.createElement('div'); empty.className = 'custom-select__empty'; empty.textContent = 'Ничего не найдено';
    let search = null;
    if (select.options.length > 10) {
      search = document.createElement('input'); search.type = 'search'; search.className = 'custom-select__search';
      search.placeholder = 'Найти в списке…'; search.setAttribute('aria-label', 'Поиск по вариантам'); menu.appendChild(search);
    }
    menu.appendChild(list); menu.appendChild(empty); wrapper.appendChild(menu);

    const optionButtons = Array.from(select.options).map((option, optionIndex) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'custom-select__option'; button.setAttribute('role', 'option');
      button.dataset.index = optionIndex; button.textContent = option.textContent; button.disabled = option.disabled;
      button.addEventListener('click', () => {
        select.selectedIndex = optionIndex;
        select.dispatchEvent(new Event('input', { bubbles: true }));
        select.dispatchEvent(new Event('change', { bubbles: true }));
        closeSelect(item, true);
      });
      list.appendChild(button); return button;
    });
    const sync = () => {
      const selected = select.options[select.selectedIndex] || select.options[0];
      trigger.textContent = selected ? selected.textContent : 'Выберите значение';
      optionButtons.forEach((button, i) => button.setAttribute('aria-selected', String(i === select.selectedIndex)));
    };
    const item = { select, wrapper, trigger, menu, search, optionButtons, sync };
    customSelects.push(item); sync();

    const open = () => {
      if (select.disabled) return;
      const willOpen = !wrapper.classList.contains('is-open'); closeAllSelects(item);
      wrapper.classList.toggle('is-open', willOpen); trigger.setAttribute('aria-expanded', String(willOpen));
      if (willOpen) {
        if (search) { search.value = ''; optionButtons.forEach(b => { b.hidden = false; }); empty.classList.remove('is-visible'); search.focus(); }
        else (optionButtons[select.selectedIndex] || optionButtons[0])?.focus();
      }
    };
    trigger.addEventListener('click', open);
    trigger.addEventListener('keydown', e => { if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    select.addEventListener('change', sync);
    if (select.form) select.form.addEventListener('reset', () => setTimeout(sync));
    if (search) search.addEventListener('input', () => {
      const query = search.value.trim().toLocaleLowerCase(); let visible = 0;
      optionButtons.forEach(button => { button.hidden = !button.textContent.toLocaleLowerCase().includes(query); if (!button.hidden) visible++; });
      empty.classList.toggle('is-visible', visible === 0);
    });
    list.addEventListener('keydown', e => {
      const visible = optionButtons.filter(button => !button.hidden && !button.disabled);
      const at = visible.indexOf(document.activeElement);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); visible[(at + (e.key === 'ArrowDown' ? 1 : -1) + visible.length) % visible.length]?.focus(); }
      if (e.key === 'Home') { e.preventDefault(); visible[0]?.focus(); }
      if (e.key === 'End') { e.preventDefault(); visible.at(-1)?.focus(); }
      if (e.key === 'Escape') { e.preventDefault(); closeSelect(item, true); }
    });
  });
  document.addEventListener('click', e => { customSelects.forEach(item => { if (!item.wrapper.contains(e.target)) closeSelect(item); }); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') customSelects.forEach(item => closeSelect(item, true)); });

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
