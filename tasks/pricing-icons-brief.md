# ТЗ на новую серию иконок тарифов и перков (/post-job)

Дата: 8 сентября 2026. Итог дизайн-ревью: старые JPG — «наклейки» с разным фоном, разной массой объекта и разным светом; временно спасены CSS (иконка справа от цены, круглая маска, свечение). Чтобы стало хорошо, нужна новая серия.

## Общие правила (добавлять в начало каждого промпта)

```
Isometric 3D icon, single object centered, object fills ~70% of the frame, clean silhouette,
one key light from top-left with soft emerald rim light, matte gold metal (#d4a94a) +
polished emerald glass (#00e0a4) + cyan neon accents (#3ee0ff), dark background #0b1512
(or transparent PNG), no text, no frame, no floor shadow beyond a soft contact shadow,
no outer glow ring, consistent camera angle 30°, 1024×1024
```

Файлы: PNG с альфой (лучше) или на #0b1512, квадрат 1024, объект вписан в круг Ø 72 % кадра. Никаких колец, прицелов и рамок вокруг объекта (свечение делает CSS). Все 15 картинок генерировать одной сессией/сидом. Имена файлов прежние: `img/pricing/t-*.jpg` → `t-*.png`, `p-*.jpg` → `p-*.png`. Проверка: силуэт читается в круге Ø 64 px на тёмном фоне.

## Тарифы (7)

1. `t-single` — a single gold casino chip standing upright, emerald glass inlay in the center, tiny job-card icon engraved on it
2. `t-promo` — a gold casino chip with a bold emerald lightning bolt cast into its face, faint cyan energy sparks (no ring)
3. `t-unlimited` — a low gold crown set with emerald gems, resting on three neatly stacked chips (compact pyramid, not a scattered pile)
4. `t-pack3` — a neat stack of exactly three gold-and-emerald casino chips, slightly fanned so all three edges read clearly
5. `t-pack10` — a short cylinder stack of ten gold-and-emerald casino chips, height roughly equal to width, top chip showing an embossed numeral 10 (no font text)
6. `t-cv1` / `t-cv10` / `t-cv30` — a gold key unlocking a small emerald glass ID card; варианты: with one key / with three keys on a ring / with a fanned deck of ID cards
7. `t-hunt` — gold binoculars with emerald lenses resting on a gold crown, subtle magenta (#ff3fa4) highlight on the lens rims only

## Перки (8, объект проще, масса ~60 % кадра)

1. `p-ats` — a compact kanban board of four emerald glass columns with small gold cards, on a gold base
2. `p-google` — a gold magnifying glass over an emerald glass job card, no logos
3. `p-seo` — a folded emerald glass map with a gold location pin standing on it
4. `p-company` — a small gold storefront with an emerald shield emblem above the door
5. `p-stats` — three rising gold bars with an emerald glass arrow curving upward, no frame around them
6. `p-moderation` — a gold shield with a raised emerald glass checkmark
7. `p-salary` — a short stack of gold coins with an emerald glass banknote band wrapped around it
8. `p-telegram` — a gold paper plane in flight with a short cyan light trail

Когда картинки будут: положить в `img/pricing/`, поменять расширения в `server/templates/post_job.html` (или сказать мне), в CSS вернуть вариант «иконка по центру над заголовком» при желании.
