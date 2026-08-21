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
    // Язык страницы решает сервер (мета sh-lang / <html lang>). Старый выбор
    // в localStorage не должен показывать украинский баннер на русской странице.
    const meta = document.querySelector('meta[name="sh-lang"]');
    let language = (meta && meta.getAttribute('content')) || document.documentElement.lang || '';
    if (!language) {
      try { language = localStorage.getItem('uiLanguage') || ''; } catch (_) {}
    }
    language = (language || navigator.language || 'ru').toLowerCase().split('-')[0];
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
      },
      de: {
        title: 'Datenschutz-Einstellungen',
        text: 'Wir nutzen Google Analytics nur mit Ihrer Einwilligung, um SpinHire zu verbessern.',
        accept: 'Akzeptieren', reject: 'Ablehnen', settings: 'Cookie-Einstellungen', privacy: 'Datenschutz'
      },
      fr: {
        title: 'Paramètres de confidentialité',
        text: 'Nous utilisons Google Analytics uniquement avec votre consentement, pour améliorer SpinHire.',
        accept: 'Accepter', reject: 'Refuser', settings: 'Paramètres des cookies', privacy: 'Confidentialité'
      },
      pl: {
        title: 'Ustawienia prywatności',
        text: 'Google Analytics używamy wyłącznie za Twoją zgodą, aby ulepszać SpinHire.',
        accept: 'Akceptuję', reject: 'Odrzucam', settings: 'Ustawienia plików cookie', privacy: 'Prywatność'
      },
      es: {
        title: 'Configuración de privacidad',
        text: 'Usamos Google Analytics solo con tu consentimiento para mejorar SpinHire.',
        accept: 'Aceptar', reject: 'Rechazar', settings: 'Configuración de cookies', privacy: 'Privacidad'
      },
      pt: {
        title: 'Definições de privacidade',
        text: 'Usamos o Google Analytics apenas com o seu consentimento, para melhorar o SpinHire.',
        accept: 'Aceitar', reject: 'Recusar', settings: 'Definições de cookies', privacy: 'Privacidade'
      },
      it: {
        title: 'Impostazioni privacy',
        text: 'Usiamo Google Analytics solo con il tuo consenso, per migliorare SpinHire.',
        accept: 'Accetta', reject: 'Rifiuta', settings: 'Impostazioni cookie', privacy: 'Privacy'
      },
      el: {
        title: 'Ρυθμίσεις απορρήτου',
        text: 'Χρησιμοποιούμε το Google Analytics μόνο με τη συγκατάθεσή σας, για να βελτιώνουμε το SpinHire.',
        accept: 'Αποδοχή', reject: 'Απόρριψη', settings: 'Ρυθμίσεις cookies', privacy: 'Απόρρητο'
      },
      ro: {
        title: 'Setări de confidențialitate',
        text: 'Folosim Google Analytics doar cu acordul tău, ca să îmbunătățim SpinHire.',
        accept: 'Accept', reject: 'Refuz', settings: 'Setări cookie', privacy: 'Confidențialitate'
      },
      bg: {
        title: 'Настройки за поверителност',
        text: 'Използваме Google Analytics само с вашето съгласие, за да подобряваме SpinHire.',
        accept: 'Приемам', reject: 'Отказвам', settings: 'Настройки за бисквитки', privacy: 'Поверителност'
      }
    }[language] || {
      title: 'Privacy settings',
      text: 'We use Google Analytics only with your consent to understand how to improve SpinHire.',
      accept: 'Accept', reject: 'Reject', settings: 'Cookie settings', privacy: 'Privacy policy'
    };
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
