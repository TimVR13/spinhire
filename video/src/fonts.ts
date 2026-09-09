import { cancelRender, continueRender, delayRender, staticFile } from "remotion";
import { getInfo as displayInfo } from "@remotion/google-fonts/Unbounded";
import { getInfo as bodyInfo } from "@remotion/google-fonts/GolosText";

/* Шрифты берём из public/fonts (те же woff2, что отдаёт gstatic): в облаке у браузера
   рендера нет прямого доступа к fonts.gstatic.com, а @remotion/google-fonts валит рендер. */
type Meta = ReturnType<typeof displayInfo>;

const loadLocal = (meta: Meta, weights: string[], subsets: string[]) => {
  if (typeof FontFace === "undefined") return meta.fontFamily;
  const seen = new Set<string>();
  for (const weight of weights) {
    for (const subset of subsets) {
      const url = meta.fonts.normal?.[weight]?.[subset];
      if (!url) continue;
      const key = `${weight}-${subset}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const file = url.split("/").pop() as string;
      const handle = delayRender(`Шрифт ${meta.fontFamily} ${weight} ${subset}`, { timeoutInMilliseconds: 60000 });
      const face = new FontFace(meta.fontFamily, `url(${staticFile(`fonts/${file}`)}) format('woff2')`, {
        weight,
        style: "normal",
        unicodeRange: meta.unicodeRanges[subset],
      });
      face
        .load()
        .then(() => {
          document.fonts.add(face);
          continueRender(handle);
        })
        .catch((err) => cancelRender(new Error(`Не загрузился шрифт ${meta.fontFamily} ${weight} ${subset} (public/fonts/${file}): ${err}`)));
    }
  }
  return meta.fontFamily;
};

export const display = loadLocal(displayInfo(), ["700", "800"], ["latin", "cyrillic"]);
export const body = loadLocal(bodyInfo(), ["400", "600", "700"], ["latin", "cyrillic"]);
