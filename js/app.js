// iHiring.org — shared prototype behavior

document.addEventListener('DOMContentLoaded', () => {
  // mobile nav
  const burger = document.querySelector('.nav-burger');
  const nav = document.querySelector('.main-nav');
  if (burger && nav) {
    burger.addEventListener('click', () => nav.classList.toggle('open'));
  }

  // auth modal
  const modal = document.getElementById('auth-modal');
  document.querySelectorAll('[data-auth]').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      if (modal) modal.classList.add('open');
    });
  });
  if (modal) {
    modal.addEventListener('click', e => {
      if (e.target === modal || e.target.closest('.modal__close')) modal.classList.remove('open');
    });
    const roleBtns = modal.querySelectorAll('.role-switch button');
    roleBtns.forEach(b => b.addEventListener('click', () => {
      roleBtns.forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      const submit = modal.querySelector('[data-auth-submit]');
      if (submit) submit.textContent = b.dataset.role === 'employer' ? 'Start hiring' : 'Create profile';
    }));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') modal.classList.remove('open'); });
  }

  // save job toggle
  document.querySelectorAll('.save-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault(); e.stopPropagation();
      btn.classList.toggle('saved');
      btn.textContent = btn.classList.contains('saved') ? '♥' : '♡';
      toast(btn.classList.contains('saved') ? 'Saved to your list' : 'Removed from saved');
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


// 3D tilt (desktop only)
if (window.matchMedia('(pointer: fine)').matches) {
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

// SpinCoins wheel demo
(function () {
  const fab = document.getElementById('wheel-fab');
  if (!fab) return;
  const counter = document.getElementById('coin-count');
  const load = () => parseInt(localStorage.getItem('spinCoins') || '0', 10);
  const save = v => localStorage.setItem('spinCoins', String(v));
  counter.textContent = load();
  const prizes = [10, 20, 30, 50, 75, 100, 150, 250];
  let spinning = false;
  fab.addEventListener('click', () => {
    if (spinning) return;
    spinning = true;
    fab.style.transition = 'transform 2.2s cubic-bezier(0.12, 0.8, 0.2, 1)';
    fab.style.transform = `rotate(${1440 + Math.random() * 360}deg)`;
    setTimeout(() => {
      const win = prizes[Math.floor(Math.random() * prizes.length)];
      const total = load() + win;
      save(total);
      counter.textContent = total;
      toast(`🎡 +${win} SpinCoins! Баланс: ${total}. Обмен на мерч — скоро`);
      fab.style.transition = 'none';
      fab.style.transform = '';
      spinning = false;
    }, 2300);
  });
})();
