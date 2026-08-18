// iHiring.org — shared prototype behavior

document.addEventListener('DOMContentLoaded', () => {
  // Язык автоматически следует за браузером; ручной выбор доступен в футере.
  const UI_LANGS = ['ru', 'uk', 'en'];
  const savedUiLang = localStorage.getItem('uiLanguage');
  const browserUiLang = (navigator.languages || [navigator.language || 'ru'])
    .map(lang => String(lang).toLowerCase().split('-')[0])
    .map(lang => lang === 'ua' ? 'uk' : lang)
    .find(lang => UI_LANGS.includes(lang)) || 'ru';
  const uiLang = UI_LANGS.includes(savedUiLang) ? savedUiLang : browserUiLang;
  const UI_COPY = {
    uk: {
      'Вакансии':'Вакансії','Резюме':'Резюме','Компании':'Компанії','Блог':'Блог','Работодателям':'Роботодавцям',
      'Войти':'Увійти','Выйти':'Вийти','Добавить CV':'Додати CV','+ Добавить CV':'+ Додати CV','Мой профиль':'Мій профіль',
      'Кандидатам':'Кандидатам','Анонимные резюме':'Анонімні резюме','Гид по зарплатам':'Гід із зарплат','Игровая зона':'Ігрова зона','🎡 Игровая зона':'🎡 Ігрова зона','Карьерный блог':'Кар’єрний блог',
      'Разместить вакансию':'Розмістити вакансію','Кабинет работодателя':'Кабінет роботодавця','Тарифы':'Тарифи','База резюме':'База резюме','О проекте':'Про проєкт','О нас':'Про нас','Методология':'Методологія','Контакты':'Контакти','Конфиденциальность':'Конфіденційність','Условия':'Умови','Правила игр':'Правила ігор',
      'Главная':'Головна','Живая база':'Жива база','Онлайн / офис — любой':'Онлайн / офіс — будь-який','Любая страна / город':'Будь-яка країна / місто','Все направления':'Усі напрями','Любой язык':'Будь-яка мова','с вилкой':'із зарплатною вилкою','Найти':'Знайти','Сбросить':'Скинути',
      'по запросу':'за запитом','Пусто по этим фильтрам':'За цими фільтрами порожньо','Назад':'Назад','Вперёд':'Далі','Описание':'Опис','Похожие вакансии':'Схожі вакансії','О вакансии':'Про вакансію','Компания':'Компанія','Направление':'Напрям','Формат':'Формат','Локация':'Локація','Зарплата':'Зарплата','Размещена':'Розміщена','Дедлайн':'Дедлайн','Статус':'Статус','Откликнуться':'Відгукнутися','Язык работы':'Мова роботи','Выберите язык':'Оберіть мову','Не указан':'Не вказано',
      '▮ Описание':'▮ Опис','▮ Похожие вакансии':'▮ Схожі вакансії','Отклик на вакансию':'Відгук на вакансію','Откликнуться →':'Відгукнутися →','Войти и откликнуться →':'Увійти та відгукнутися →','Откликнуться через SpinHire →':'Відгукнутися через SpinHire →','Откликнуться у работодателя ↗':'Відгукнутися у роботодавця ↗','Войти как соискатель':'Увійти як кандидат','Смотреть актуальные вакансии →':'Дивитися актуальні вакансії →','Должность, компания, тег…':'Посада, компанія, тег…','Поиск вакансий':'Пошук вакансій','Страна и город':'Країна та місто',
      'удалёнка':'віддалено','удалёнка ЕС':'віддалено в ЄС','гибрид':'гібрид','офис':'офіс','Топ-менеджмент':'Топменеджмент','Разработка игр':'Розробка ігор','Маркетинг и CRM':'Маркетинг і CRM','Саппорт (языки)':'Підтримка (мови)'
    },
    en: {
      'Вакансии':'Jobs','Резюме':'Resumes','Компании':'Companies','Блог':'Blog','Работодателям':'For employers',
      'Войти':'Log in','Выйти':'Log out','Добавить CV':'Add CV','+ Добавить CV':'+ Add CV','Мой профиль':'My profile',
      'Кандидатам':'For candidates','Анонимные резюме':'Anonymous resumes','Гид по зарплатам':'Salary guide','Игровая зона':'Game zone','🎡 Игровая зона':'🎡 Game zone','Карьерный блог':'Career blog',
      'Разместить вакансию':'Post a job','Кабинет работодателя':'Employer dashboard','Тарифы':'Pricing','База резюме':'Resume database','О проекте':'About','О нас':'About us','Методология':'Methodology','Контакты':'Contacts','Конфиденциальность':'Privacy','Условия':'Terms','Правила игр':'Game rules',
      'Главная':'Home','Живая база':'Live database','Онлайн / офис — любой':'Remote / office — any','Любая страна / город':'Any country / city','Все направления':'All categories','Любой язык':'Any language','с вилкой':'salary shown','Найти':'Search','Сбросить':'Reset',
      'по запросу':'on request','Пусто по этим фильтрам':'No jobs match these filters','Назад':'Back','Вперёд':'Next','Описание':'Description','Похожие вакансии':'Similar jobs','О вакансии':'About this job','Компания':'Company','Направление':'Category','Формат':'Work format','Локация':'Location','Зарплата':'Salary','Размещена':'Posted','Дедлайн':'Deadline','Статус':'Status','Откликнуться':'Apply','Язык работы':'Working language','Выберите язык':'Select a language','Не указан':'Not specified',
      '▮ Описание':'▮ Description','▮ Похожие вакансии':'▮ Similar jobs','Отклик на вакансию':'Apply for this job','Откликнуться →':'Apply →','Войти и откликнуться →':'Log in and apply →','Откликнуться через SpinHire →':'Apply via SpinHire →','Откликнуться у работодателя ↗':'Apply on employer site ↗','Войти как соискатель':'Log in as candidate','Смотреть актуальные вакансии →':'View open jobs →','Должность, компания, тег…':'Job title, company, tag…','Поиск вакансий':'Search jobs','Страна и город':'Country and city',
      'удалёнка':'remote','удалёнка ЕС':'remote in EU','гибрид':'hybrid','офис':'office','Топ-менеджмент':'Executive','Разработка игр':'Game development','Маркетинг и CRM':'Marketing & CRM','Саппорт (языки)':'Customer support (languages)'
    }
  };
  const translateInterface = lang => {
    document.documentElement.lang = lang;
    if (lang === 'ru') return;
    const dict = UI_COPY[lang];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) {
      const parent = walker.currentNode.parentElement;
      if (parent && !parent.closest('script, style, textarea')) nodes.push(walker.currentNode);
    }
    nodes.forEach(node => {
      const raw = node.nodeValue, key = raw.trim();
      if (dict[key]) node.nodeValue = raw.replace(key, dict[key]);
    });
    document.querySelectorAll('[placeholder],[aria-label],[title]').forEach(el => {
      ['placeholder','aria-label','title'].forEach(attr => {
        const value = el.getAttribute(attr); if (value && dict[value]) el.setAttribute(attr, dict[value]);
      });
    });
    document.querySelectorAll('[data-i18n-prefix="jobsCount"]').forEach(el => {
      const count = (el.textContent.match(/\d+/) || ['0'])[0];
      el.textContent = lang === 'uk' ? `Вакансії iGaming — ${count}` : `iGaming jobs — ${count}`;
    });
  };
  const languageHost = document.querySelector('.footer-bottom');
  if (languageHost && !languageHost.querySelector('.footer-language')) {
    const label = document.createElement('label'); label.className = 'footer-language';
    const caption = document.createElement('span'); caption.textContent = 'Язык';
    const select = document.createElement('select');
    select.setAttribute('data-native-select', ''); select.setAttribute('aria-label', 'Язык сайта');
    select.innerHTML = '<option value="ru">Русский</option><option value="uk">Українська</option><option value="en">English</option>';
    select.value = uiLang;
    select.addEventListener('change', () => {
      localStorage.setItem('uiLanguage', select.value); location.reload();
    });
    label.append(caption, select); languageHost.appendChild(label);
  }
  setTimeout(() => translateInterface(uiLang), 0);

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
