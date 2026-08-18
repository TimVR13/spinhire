(function () {
  'use strict';

  const CONSENT_KEY = 'spinhireConsent';
  const COOKIE_NAME = 'spinhire_consent';
  const CONSENT_FIELDS = {
    analytics_storage: 'denied',
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied'
  };

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window.gtag('consent', 'default', Object.assign({
    functionality_storage: 'granted',
    security_storage: 'granted',
    wait_for_update: 500
  }, CONSENT_FIELDS));

  const readConsent = () => {
    try {
      const saved = localStorage.getItem(CONSENT_KEY);
      if (saved === 'granted' || saved === 'denied') return saved;
    } catch (_) {}
    const match = document.cookie.match(new RegExp('(?:^|; )' + COOKIE_NAME + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  };

  const savedConsent = readConsent();
  if (savedConsent === 'granted') {
    window.gtag('consent', 'update', {
      analytics_storage: 'granted',
      ad_storage: 'granted',
      ad_user_data: 'granted',
      ad_personalization: 'granted'
    });
  }

  const copyFor = () => {
    let language = '';
    try { language = localStorage.getItem('uiLanguage') || ''; } catch (_) {}
    language = language || document.documentElement.lang || navigator.language || 'ru';
    language = language.toLowerCase().split('-')[0];
    if (language === 'ua') language = 'uk';
    return {
      uk: {
        title: 'Налаштування приватності',
        text: 'Ми використовуємо Google Analytics лише за вашою згодою, щоб розуміти, як покращувати SpinHire.',
        accept: 'Прийняти', reject: 'Відхилити', settings: 'Налаштування cookie', privacy: 'Конфіденційність'
      },
      en: {
        title: 'Privacy settings',
        text: 'We use Google Analytics only with your consent to understand how to improve SpinHire.',
        accept: 'Accept', reject: 'Reject', settings: 'Cookie settings', privacy: 'Privacy policy'
      },
      ru: {
        title: 'Настройки приватности',
        text: 'Мы используем Google Analytics только с вашего согласия, чтобы понимать, как улучшать SpinHire.',
        accept: 'Принять', reject: 'Отклонить', settings: 'Настройки cookie', privacy: 'Конфиденциальность'
      }
    }[language] || null;
  };

  const remember = value => {
    try { localStorage.setItem(CONSENT_KEY, value); } catch (_) {}
    document.cookie = COOKIE_NAME + '=' + encodeURIComponent(value) + '; Max-Age=31536000; Path=/; SameSite=Lax; Secure';
  };

  const updateConsent = value => {
    const granted = value === 'granted';
    window.gtag('consent', 'update', {
      analytics_storage: granted ? 'granted' : 'denied',
      ad_storage: granted ? 'granted' : 'denied',
      ad_user_data: granted ? 'granted' : 'denied',
      ad_personalization: granted ? 'granted' : 'denied'
    });
    window.gtag('set', 'allow_google_signals', granted);
    remember(value);
    document.querySelector('.consent-banner')?.remove();
  };

  const showBanner = () => {
    document.querySelector('.consent-banner')?.remove();
    const copy = copyFor();
    const banner = document.createElement('section');
    banner.className = 'consent-banner';
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-modal', 'true');
    banner.setAttribute('aria-label', copy.title);
    banner.innerHTML = '<div class="consent-banner__copy"><b></b><p></p><a href="/privacy.html"></a></div>' +
      '<div class="consent-banner__actions"><button type="button" class="btn btn-ghost consent-reject"></button>' +
      '<button type="button" class="btn btn-acid consent-accept"></button></div>';
    banner.querySelector('b').textContent = copy.title;
    banner.querySelector('p').textContent = copy.text;
    banner.querySelector('a').textContent = copy.privacy;
    banner.querySelector('.consent-reject').textContent = copy.reject;
    banner.querySelector('.consent-accept').textContent = copy.accept;
    banner.querySelector('.consent-reject').addEventListener('click', () => updateConsent('denied'));
    banner.querySelector('.consent-accept').addEventListener('click', () => updateConsent('granted'));
    document.body.appendChild(banner);
  };

  document.addEventListener('DOMContentLoaded', () => {
    if (!savedConsent) showBanner();
    const footer = document.querySelector('.footer-bottom');
    if (footer && !footer.querySelector('.consent-settings')) {
      const copy = copyFor();
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'consent-settings';
      button.textContent = copy.settings;
      button.addEventListener('click', showBanner);
      footer.appendChild(button);
    }
  });

  window.SpinHireConsent = { show: showBanner };
})();
