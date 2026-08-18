(function () {
  'use strict';

  const supported = ['ru', 'uk', 'en'];
  let saved = '';
  try { saved = localStorage.getItem('uiLanguage') || ''; } catch (_) {}
  const browser = (navigator.languages || [navigator.language || 'ru'])
    .map(value => String(value).toLowerCase().split('-')[0])
    .map(value => value === 'ua' ? 'uk' : value)
    .find(value => supported.includes(value)) || 'ru';
  const language = supported.includes(saved) ? saved : browser;
  if (language === 'ru') return;

  const pages = {
    '/privacy.html': {
      uk: {
        title: 'Політика конфіденційності | SpinHire',
        description: 'Як SpinHire збирає, використовує та захищає персональні дані кандидатів і роботодавців: GDPR, cookie та права користувача.',
        html: `<nav class="crumbs" aria-label="Хлібні крихти"><a href="index.html">Головна</a> / Політика конфіденційності</nav>
          <h1>Політика конфіденційності</h1><p class="upd">Оновлено 14 серпня 2026 року</p>
          <p>SpinHire («ми», «сервіс») — рекрутингова платформа для iGaming-індустрії. Ми поважаємо вашу приватність і обробляємо персональні дані відповідно до GDPR для користувачів ЄС та застосовного місцевого законодавства.</p>
          <div class="note"><b>Коротко:</b> ми збираємо лише дані, потрібні для роботи сервісу (email, дані профілю або резюме, відгуки), не продаємо їх третім особам і даємо вам право видалити їх у будь-який момент.</div>
          <h2>Які дані ми збираємо</h2><ul><li><b>Обліковий запис:</b> email, пароль у зашифрованому вигляді, ім’я, роль кандидата або роботодавця, назва компанії.</li><li><b>Профіль кандидата:</b> посада, очікувана зарплата, мови, статус інкогніто та ваші відгуки.</li><li><b>Вакансії роботодавця:</b> дані опублікованих вакансій.</li><li><b>Технічні дані:</b> сесійні cookie для входу та базові серверні журнали (IP, тип браузера) для безпеки.</li></ul>
          <h2>Навіщо ми використовуємо дані</h2><ul><li>Надаємо сервіс: пошук вакансій, відгуки, особисті кабінети та модерацію.</li><li>Забезпечуємо безпеку та запобігаємо зловживанням.</li><li>Зв’язуємося з вами щодо ваших дій на сайті, наприклад надсилаємо сповіщення про відгуки.</li></ul><p>Правова підстава за статтею 6 GDPR: виконання договору про надання сервісу та ваша згода, надана під час реєстрації.</p>
          <h2>Cookie</h2><p>Ми використовуємо лише технічно необхідні сесійні cookie для входу. Аналітичні та маркетингові cookie не встановлюються без вашої згоди.</p>
          <h2>Аналітика та cookie</h2><p>За вашою згодою SpinHire використовує Google Analytics для вимірювання відвідуваності та покращення сайту. До натискання «Прийняти» аналітичне й рекламне сховища Google вимкнені, а аналітичні cookie не встановлюються. Ви можете відхилити аналітику або змінити вибір через «Налаштування cookie» у футері.</p><p>Після отримання згоди Google може обробляти технічні відомості про пристрій, відвідані сторінки та дії на сайті відповідно до своєї <a href="https://policies.google.com/privacy" target="_blank" rel="noopener" style="color: var(--acid);">політики конфіденційності</a>. SpinHire використовує ідентифікатор Google Analytics G-0W5XWDYPZ3.</p>
          <h2>Передавання третім особам</h2><p>Ми не продаємо ваші дані. Коли аналітика ввімкнена, Google обробляє дані про використання сайту. Зовнішні вакансії позначені символом «↗» і ведуть на сторонні ресурси з власними політиками.</p>
          <h2>Ваші права</h2><ul><li>Отримати доступ до даних, виправити або видалити їх.</li><li>Відкликати згоду та видалити обліковий запис.</li><li>Подати скаргу до наглядового органу із захисту даних.</li></ul><p>Щоб скористатися правами, напишіть на <a href="mailto:privacy@spinhire.io" style="color: var(--acid);">privacy@spinhire.io</a>.</p>
          <h2>Зберігання</h2><p>Ми зберігаємо дані, поки ваш обліковий запис активний. Після видалення облікового запису дані видаляються в розумний строк, крім випадків, коли закон вимагає іншого.</p><div class="note">Це шаблонна політика для прототипу. Перед публічним запуском її має перевірити юрист з урахуванням юридичної особи оператора та цільових юрисдикцій.</div>`
      },
      en: {
        title: 'Privacy Policy | SpinHire',
        description: 'How SpinHire collects, uses and protects candidate and employer personal data, including GDPR, cookies and user rights.',
        html: `<nav class="crumbs" aria-label="Breadcrumbs"><a href="index.html">Home</a> / Privacy Policy</nav>
          <h1>Privacy Policy</h1><p class="upd">Updated 14 August 2026</p>
          <p>SpinHire (“we”, “the service”) is a recruitment platform for the iGaming industry. We respect your privacy and process personal data under the GDPR for EU users and applicable local data-protection law.</p>
          <div class="note"><b>In brief:</b> we collect only the data needed to operate the service (email, profile or resume information and applications), do not sell it to third parties, and allow you to delete it at any time.</div>
          <h2>Data we collect</h2><ul><li><b>Account:</b> email, encrypted password, name, candidate or employer role, and company name.</li><li><b>Candidate profile:</b> role, salary expectations, languages, incognito status and applications.</li><li><b>Employer vacancies:</b> information contained in published vacancies.</li><li><b>Technical data:</b> session cookies for login and basic server logs (IP address and browser type) for security.</li></ul>
          <h2>How we use data</h2><ul><li>To provide job search, applications, dashboards and moderation.</li><li>To maintain security and prevent abuse.</li><li>To contact you about actions on the site, such as application notifications.</li></ul><p>Our legal basis under Article 6 GDPR is performance of the service contract and the consent you provide during registration.</p>
          <h2>Cookies</h2><p>We use only technically necessary session cookies for login. Analytics and marketing cookies are not set without your consent.</p>
          <h2>Analytics and cookies</h2><p>With your consent, SpinHire uses Google Analytics to measure traffic and improve the site. Until you select “Accept”, Google analytics and advertising storage remain disabled and analytics cookies are not set. You can reject analytics or change your choice at any time through “Cookie settings” in the footer.</p><p>After consent, Google may process technical information about your device, visited pages and activity under its <a href="https://policies.google.com/privacy" target="_blank" rel="noopener" style="color: var(--acid);">Privacy Policy</a>. SpinHire uses Google Analytics ID G-0W5XWDYPZ3.</p>
          <h2>Third-party sharing</h2><p>We do not sell your data. When analytics is enabled, Google processes site-usage data. External vacancies are marked “↗” and lead to third-party services governed by their own policies.</p>
          <h2>Your rights</h2><ul><li>Access, correct or erase your data.</li><li>Withdraw consent and delete your account.</li><li>Lodge a complaint with a data-protection authority.</li></ul><p>To exercise these rights, email <a href="mailto:privacy@spinhire.io" style="color: var(--acid);">privacy@spinhire.io</a>.</p>
          <h2>Retention</h2><p>We retain data while your account is active. After account deletion, we erase it within a reasonable period unless the law requires otherwise.</p><div class="note">This is a prototype policy template. Before public launch, legal counsel should adapt it to the operating legal entity and target jurisdictions.</div>`
      }
    },
    '/terms.html': {
      uk: {
        title: 'Умови використання | SpinHire',
        description: 'Умови використання SpinHire: статус платформи, правила публікації вакансій, відповідальність і застосовне право.',
        html: `<nav class="crumbs" aria-label="Хлібні крихти"><a href="index.html">Головна</a> / Умови використання</nav><h1>Умови використання</h1><p class="upd">Оновлено 14 серпня 2026 року</p>
          <p>Використовуючи SpinHire, ви погоджуєтеся з цими умовами. Якщо ви не погоджуєтеся, не використовуйте сервіс.</p><h2>Що таке SpinHire</h2><p>SpinHire — інформаційна платформа-посередник, яка допомагає кандидатам і роботодавцям iGaming-індустрії знайти одне одного. Частина вакансій агрегується з відкритих джерел і позначається «↗». <b>SpinHire не є роботодавцем, класичним кадровим агентством або оператором азартних ігор і не гарантує працевлаштування чи найм.</b></p>
          <h2>Відповідальність за контент</h2><ul><li>Роботодавці відповідають за достовірність і законність своїх вакансій.</li><li>Кандидати відповідають за достовірність своїх даних.</li><li>SpinHire модерує вакансії, але не гарантує їх точність і не відповідає за дії роботодавців або сторонніх сайтів.</li></ul>
          <h2>Правила публікації</h2><ul><li>Заборонені незаконні або оманливі вакансії та пропозиції від неліцензованих операторів там, де ліцензія обов’язкова.</li><li>Діапазон зарплати є обов’язковим.</li><li>Ми можемо відхилити, зняти або відредагувати будь-яку вакансію.</li></ul>
          <h2>Ігрова зона</h2><p>Мініігри та бали SpinCoins регулюються окремими <a href="game-rules.html" style="color: var(--acid);">Правилами ігрової зони</a>. Це безплатна гейміфікація, а не азартна гра на гроші.</p><h2>Обмеження відповідальності</h2><p>Сервіс надається «як є». У межах, дозволених законом, SpinHire не відповідає за непрямі збитки, втрачену вигоду або дії третіх осіб.</p><h2>Вік</h2><p>Сервіс призначений для осіб віком від 18 років. Реєструючись, ви підтверджуєте повноліття.</p><h2>Зміни та право</h2><p>Ми можемо оновлювати ці умови. Застосовне право та юрисдикція визначаються місцем реєстрації оператора сервісу й будуть уточнені до запуску.</p><div class="note">Це шаблон для прототипу. Остаточну редакцію має підготувати юрист.</div>`
      },
      en: {
        title: 'Terms of Use | SpinHire',
        description: 'SpinHire terms of use covering platform status, job-posting rules, liability and applicable law.',
        html: `<nav class="crumbs" aria-label="Breadcrumbs"><a href="index.html">Home</a> / Terms of Use</nav><h1>Terms of Use</h1><p class="upd">Updated 14 August 2026</p>
          <p>By using SpinHire, you agree to these terms. If you do not agree, do not use the service.</p><h2>What SpinHire is</h2><p>SpinHire is an information platform and intermediary that helps iGaming candidates and employers find one another. Some vacancies are aggregated from public sources and marked “↗”. <b>SpinHire is not an employer, a traditional recruitment agency or a gambling operator, and does not guarantee employment or hiring.</b></p>
          <h2>Responsibility for content</h2><ul><li>Employers are responsible for the accuracy and legality of their vacancies.</li><li>Candidates are responsible for the accuracy of their information.</li><li>SpinHire moderates vacancies but does not guarantee their accuracy and is not responsible for the actions of employers or third-party sites.</li></ul>
          <h2>Posting rules</h2><ul><li>Illegal or misleading vacancies and offers from unlicensed operators where a licence is required are prohibited.</li><li>A salary range is mandatory.</li><li>We may reject, remove or edit any vacancy.</li></ul>
          <h2>Game zone</h2><p>Mini-games and SpinCoins are governed by separate <a href="game-rules.html" style="color: var(--acid);">Game Zone Rules</a>. This is free gamification, not gambling for money.</p><h2>Limitation of liability</h2><p>The service is provided “as is”. To the extent permitted by law, SpinHire is not liable for indirect loss, lost profit or the actions of third parties.</p><h2>Age</h2><p>The service is intended for people aged 18 and over. By registering, you confirm that you are an adult.</p><h2>Changes and governing law</h2><p>We may update these terms. Governing law and jurisdiction are determined by the service operator’s place of registration and will be confirmed before launch.</p><div class="note">This is a prototype template. Legal counsel must prepare the final version.</div>`
      }
    }
  };

  const page = pages[window.location.pathname] || pages['/' + window.location.pathname.split('/').pop()];
  const copy = page && page[language];
  const legal = document.querySelector('.legal');
  if (!copy || !legal) return;
  legal.innerHTML = copy.html;
  document.title = copy.title;
  const description = document.querySelector('meta[name="description"]');
  if (description) description.setAttribute('content', copy.description);
  document.documentElement.lang = language;
}());
