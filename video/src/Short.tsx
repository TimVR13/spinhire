import React from "react";
import { AbsoluteFill, Audio, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont as loadDisplay } from "@remotion/google-fonts/Unbounded";
import { loadFont as loadBody } from "@remotion/google-fonts/GolosText";

const display = loadDisplay("normal", { weights: ["700", "800"], subsets: ["latin", "cyrillic"] }).fontFamily;
const body = loadBody("normal", { weights: ["400", "600", "700"], subsets: ["latin", "cyrillic"] }).fontFamily;

export const FPS = 30;
const C = { bg: "#0a120e", bg2: "#0f1a14", ink: "#f2f7f4", dim: "#9fb3a8", acid: "#12e08e", pink: "#ff3fa4", gold: "#d4a94a", line: "rgba(18,224,142,.22)" };

type Scene = { id: string; type: string; start: number; end: number; [k: string]: any };
/* размер шрифта, чтобы строка влезла в ширину (Unbounded ≈ 0.68em на символ) */
const fit = (text: string, maxW: number, maxSize: number, k = 0.68) => Math.max(40, Math.min(maxSize, Math.floor(maxW / (Math.max(1, text.length) * k))));
type Caption = { text: string; start: number; end: number };
export type ShortProps = { id: string; format: string; bg: string; music: string; voice: string; duration: number; scenes: Scene[]; captions: Caption[] };

const Grain: React.FC = () => (
  <AbsoluteFill style={{ background: `radial-gradient(900px 700px at 80% 12%, rgba(212,169,74,.14), transparent 60%), radial-gradient(1000px 800px at 10% 100%, rgba(18,224,142,.12), transparent 60%), ${C.bg}` }} />
);

const Bg: React.FC<{ src: string; height?: number; zoom?: number; dim?: number }> = ({ src, height = 1100, zoom = 1, dim = 0 }) => (
  <div style={{ position: "absolute", top: 0, left: 0, right: 0, height, overflow: "hidden" }}>
    <Img src={staticFile(src)} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "50% 0%", transform: `scale(${zoom})`, transformOrigin: "50% 20%" }} />
    <div style={{ position: "absolute", inset: 0, background: `linear-gradient(180deg, rgba(10,18,14,${dim}) 30%, ${C.bg} 96%)` }} />
  </div>
);

const Logo: React.FC<{ size?: number }> = ({ size = 48 }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
    <Img src={staticFile("logo.svg")} style={{ width: size * 1.6, height: size }} />
    <div style={{ fontFamily: display, fontWeight: 800, fontSize: size * 0.9, color: C.ink, letterSpacing: -1 }}>spin<span style={{ color: C.acid }}>hire</span></div>
  </div>
);

const Kicker: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = C.acid }) => (
  <div style={{ display: "inline-block", fontFamily: body, fontWeight: 700, fontSize: 26, letterSpacing: 4, textTransform: "uppercase", color, border: `2px solid ${color}66`, borderRadius: 999, padding: "10px 22px" }}>● {children}</div>
);

const Top: React.FC<{ n?: number; total?: number }> = ({ n, total }) => (
  <div style={{ position: "absolute", top: 110, left: 72, right: 72, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
    <Logo size={44} />
    {total ? <div style={{ display: "flex", gap: 10 }}>{Array.from({ length: total }).map((_, i) => <div key={i} style={{ width: i === (n ?? 0) - 1 ? 44 : 14, height: 14, borderRadius: 7, background: i === (n ?? 0) - 1 ? C.acid : "rgba(255,255,255,.18)" }} />)}</div> : null}
  </div>
);

/* прогресс сцены 0..1 и пружина входа — считаются от локального кадра */
const useScene = (sc: Scene) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const local = f - Math.round(sc.start * fps);
  const len = Math.round((sc.end - sc.start) * fps);
  const s = spring({ frame: local, fps, config: { damping: 15, stiffness: 130 } });
  const s2 = spring({ frame: local - 10, fps, config: { damping: 17, stiffness: 100 } });
  const out = interpolate(local, [len - 10, len], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return { local, len, s, s2, out, p: Math.min(1, Math.max(0, local / Math.max(1, len))) };
};

const Hook: React.FC<{ sc: Scene; bg: string }> = ({ sc, bg }) => {
  const { s, s2, out, p } = useScene(sc);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <Bg src={bg} zoom={1 + 0.1 * p} />
      <div style={{ position: "absolute", top: 96, left: 72, opacity: s }}><Logo size={56} /></div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 900, transform: `translateY(${(1 - s2) * 60}px)`, opacity: s2 }}>
        <Kicker>{sc.kicker}</Kicker>
        <div style={{ marginTop: 34, fontFamily: display, fontWeight: 800, fontSize: sc.title.length > 22 ? 78 : 104, lineHeight: 1.02, textTransform: "uppercase", color: C.ink, letterSpacing: -1 }}>{sc.title}</div>
        {sc.sub ? <div style={{ marginTop: 22, fontFamily: body, fontWeight: 600, fontSize: 36, color: C.dim }}>{sc.sub}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

const JobCard: React.FC<{ sc: Scene }> = ({ sc }) => {
  const { s, s2, out } = useScene(sc);
  return (
    <AbsoluteFill style={{ justifyContent: "center", padding: "0 72px", opacity: out }}>
      <Top n={sc.n} total={sc.total} />
      <div style={{ marginTop: -120, transform: `translateY(${(1 - s) * 120}px) scale(${0.94 + 0.06 * s})`, opacity: s, border: `2px solid ${C.line}`, borderRadius: 36, padding: "52px 56px 56px", background: `linear-gradient(180deg, ${C.bg2}, rgba(15,26,20,.6))`, boxShadow: "0 40px 120px rgba(0,0,0,.45)" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
          <div style={{ fontFamily: display, fontWeight: 800, fontSize: 140, lineHeight: 1, color: C.acid, textShadow: `0 0 40px ${C.acid}66` }}>{sc.n}</div>
          <div style={{ fontFamily: body, fontWeight: 700, fontSize: 28, color: C.pink, letterSpacing: 3, textTransform: "uppercase", border: `2px solid ${C.pink}55`, borderRadius: 999, padding: "10px 22px" }}>{sc.tag}</div>
        </div>
        <div style={{ marginTop: 30, fontFamily: display, fontWeight: 800, fontSize: sc.title.length > 34 ? 56 : 70, lineHeight: 1.05, color: C.ink, letterSpacing: -1 }}>{sc.title}</div>
        <div style={{ marginTop: 24, fontFamily: body, fontWeight: 600, fontSize: 38, color: C.dim }}>{sc.company} <span style={{ color: "rgba(255,255,255,.35)" }}>·</span> {sc.where}</div>
        {sc.note ? <div style={{ marginTop: 14, fontFamily: body, fontWeight: 600, fontSize: 30, color: "rgba(255,255,255,.5)" }}>{sc.note}</div> : null}
        <div style={{ marginTop: 44, transform: `scale(${0.7 + 0.3 * s2})`, transformOrigin: "left center", opacity: s2, fontFamily: display, fontWeight: 800, fontSize: fit(sc.salary + " /мес", 880, 96), color: C.acid, letterSpacing: -2, whiteSpace: "nowrap" }}>{sc.salary}<span style={{ fontFamily: body, fontWeight: 600, fontSize: 34, color: C.dim, marginLeft: 18, letterSpacing: 0 }}>/ мес</span></div>
      </div>
    </AbsoluteFill>
  );
};

const Bars: React.FC<{ sc: Scene; captions: Caption[] }> = ({ sc, captions }) => {
  const { s, out, local } = useScene(sc);
  const { fps } = useVideoConfig();
  // каждая полоса растёт, когда начинается её фраза (фразы сцены идут по порядку полос)
  const phr = captions.filter(c => c.start >= sc.start - 0.3 && c.start < sc.end);
  return (
    <AbsoluteFill style={{ opacity: out, padding: "0 72px" }}>
      <Top />
      <div style={{ position: "absolute", left: 72, right: 72, top: 300, opacity: s, transform: `translateY(${(1 - s) * 40}px)` }}>
        <Kicker>{sc.sub}</Kicker>
        <div style={{ marginTop: 26, fontFamily: display, fontWeight: 800, fontSize: sc.title.length > 22 ? 64 : 84, lineHeight: 1.02, color: C.ink, letterSpacing: -1 }}>{sc.title}</div>
      </div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 640, display: "flex", flexDirection: "column", gap: sc.bars.length > 3 ? 30 : 44 }}>
        {sc.bars.map((b: any, i: number) => {
          const at = phr[i] ? Math.round((phr[i].start - sc.start) * fps) : i * 20;
          const g = spring({ frame: local - at, fps, config: { damping: 16, stiffness: 90 } });
          return (
            <div key={i} style={{ opacity: Math.min(1, g * 3) }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 24, marginBottom: 14 }}>
                <div style={{ fontFamily: body, fontWeight: 600, fontSize: 34, lineHeight: 1.15, color: C.dim, flex: 1 }}>{b.label}</div>
                <div style={{ fontFamily: display, fontWeight: 800, fontSize: fit(b.text, 560, 52), color: C.acid, letterSpacing: -1, whiteSpace: "nowrap" }}>{b.text}</div>
              </div>
              <div style={{ height: 34, borderRadius: 17, background: "rgba(255,255,255,.08)", overflow: "hidden" }}>
                <div style={{ width: `${b.pct * 100 * g}%`, height: "100%", borderRadius: 17, background: `linear-gradient(90deg, ${C.acid}, ${C.acid}99)`, boxShadow: `0 0 30px ${C.acid}66` }} />
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const Big: React.FC<{ sc: Scene; bg: string }> = ({ sc, bg }) => {
  const { s, s2, out } = useScene(sc);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <Bg src={bg} height={900} dim={0.35} />
      <Top />
      <div style={{ position: "absolute", left: 72, right: 72, top: 760, opacity: s, transform: `translateY(${(1 - s) * 50}px)` }}>
        <Kicker color={C.gold}>{sc.kicker}</Kicker>
        <div style={{ marginTop: 30, transform: `scale(${0.8 + 0.2 * s2})`, transformOrigin: "left center", fontFamily: display, fontWeight: 800, fontSize: fit(sc.number, 936, 140), lineHeight: 1, color: C.acid, letterSpacing: -3, textShadow: `0 0 60px ${C.acid}55`, whiteSpace: "nowrap" }}>{sc.number}</div>
        <div style={{ marginTop: 24, fontFamily: body, fontWeight: 600, fontSize: 40, color: C.dim }}>{sc.label}</div>
      </div>
    </AbsoluteFill>
  );
};

const Bullets: React.FC<{ sc: Scene; captions: Caption[]; bg: string }> = ({ sc, captions, bg }) => {
  const { s, out, local } = useScene(sc);
  const { fps } = useVideoConfig();
  const phr = captions.filter(c => c.start >= sc.start - 0.3 && c.start < sc.end);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <Bg src={bg} height={1920} dim={0.72} />
      <Top />
      <div style={{ position: "absolute", left: 72, right: 72, top: 300, opacity: s }}>
        <Kicker>{sc.title}</Kicker>
      </div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 420, display: "flex", flexDirection: "column", gap: 30 }}>
        {sc.items.map((it: string, i: number) => {
          const at = phr[i] ? Math.round((phr[i].start - sc.start) * fps) : i * 25;
          const g = spring({ frame: local - at, fps, config: { damping: 15, stiffness: 120 } });
          return (
            <div key={i} style={{ display: "flex", gap: 26, alignItems: "flex-start", opacity: g, transform: `translateX(${(1 - g) * 60}px)` }}>
              <div style={{ flex: "none", width: 64, height: 64, borderRadius: 20, background: C.acid, color: "#06130c", fontFamily: display, fontWeight: 800, fontSize: 36, display: "flex", alignItems: "center", justifyContent: "center" }}>{i + 1}</div>
              <div style={{ fontFamily: display, fontWeight: 700, fontSize: 46, lineHeight: 1.18, color: C.ink }}>{it}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const Quote: React.FC<{ sc: Scene; bg: string }> = ({ sc, bg }) => {
  const { s, out } = useScene(sc);
  return (
    <AbsoluteFill style={{ opacity: out, justifyContent: "center", padding: "0 72px" }}>
      <Bg src={bg} height={1920} dim={0.72} />
      <Top />
      <div style={{ opacity: s, transform: `translateY(${(1 - s) * 40}px)`, marginTop: -160 }}>
        {sc.kicker ? <div style={{ marginBottom: 30 }}><Kicker color={C.pink}>{sc.kicker}</Kicker></div> : null}
        <div style={{ borderLeft: `10px solid ${C.acid}`, paddingLeft: 40, fontFamily: display, fontWeight: 700, fontSize: sc.text.length > 140 ? 44 : 54, lineHeight: 1.22, color: C.ink }}>{sc.text}</div>
      </div>
    </AbsoluteFill>
  );
};

const Cta: React.FC<{ sc: Scene }> = ({ sc }) => {
  const { s, s2, local, p } = useScene(sc);
  const pulse = 1 + 0.025 * Math.sin(local / 5);
  return (
    <AbsoluteFill>
      <Bg src="cta-v.jpg" height={1000} zoom={1.04 + 0.1 * p} />
      <div style={{ position: "absolute", top: 96, left: 72, opacity: s }}><Logo size={56} /></div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 880, opacity: s, transform: `translateY(${(1 - s) * 50}px)` }}>
        <div style={{ fontFamily: display, fontWeight: 800, fontSize: 84, lineHeight: 1.0, textTransform: "uppercase", color: C.ink, letterSpacing: -1 }}>
          <div>Скучная карьера</div><div style={{ color: "rgba(242,247,244,.85)" }}>закончилась</div><div style={{ color: C.acid, textShadow: `0 0 40px ${C.acid}55` }}>Иди ва‑банк</div>
        </div>
      </div>
      <div style={{ position: "absolute", left: 72, right: 72, bottom: 420, opacity: s2, transform: `translateY(${(1 - s2) * 40}px)` }}>
        <div style={{ fontFamily: body, fontWeight: 700, fontSize: 32, color: C.acid, letterSpacing: 3, textTransform: "uppercase", marginBottom: 18 }}>{sc.line} →</div>
        <div style={{ display: "inline-block", transform: `scale(${pulse})`, transformOrigin: "left center", fontFamily: display, fontWeight: 800, fontSize: sc.url.length > 22 ? 46 : 64, color: "#06130c", background: C.acid, padding: "22px 44px", borderRadius: 999, boxShadow: `0 0 80px ${C.acid}77`, whiteSpace: "nowrap" }}>{sc.url}</div>
      </div>
    </AbsoluteFill>
  );
};

/* субтитры: фраза целиком, крупно, над зоной кнопок Shorts */
const Captions: React.FC<{ captions: Caption[]; hideOn: Set<string>; scenes: Scene[] }> = ({ captions, hideOn, scenes }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const t = f / fps;
  const cur = captions.find(c => t >= c.start - 0.05 && t < c.end + 0.15);
  if (!cur) return null;
  const sc = scenes.find(s => t >= s.start && t < s.end);
  if (sc && hideOn.has(sc.type)) return null;
  const local = f - Math.round(cur.start * fps);
  const s = spring({ frame: local, fps, config: { damping: 14, stiffness: 180 } });
  return (
    <div style={{ position: "absolute", left: 60, right: 60, bottom: 310, display: "flex", justifyContent: "center", pointerEvents: "none" }}>
      <div style={{ transform: `scale(${0.92 + 0.08 * s})`, opacity: s, background: "rgba(6,12,9,.78)", border: `2px solid rgba(255,255,255,.08)`, borderRadius: 26, padding: "22px 34px", fontFamily: body, fontWeight: 700, fontSize: cur.text.length > 70 ? 36 : 42, lineHeight: 1.25, color: C.ink, textAlign: "center", maxWidth: 960 }}>
        {cur.text}
      </div>
    </div>
  );
};

export const Short: React.FC<ShortProps> = ({ bg, music, voice, duration, scenes, captions }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const t = f / fps;
  const total = Math.round(duration * fps);
  const musicVol = interpolate(f, [0, 20, total - 45, total], [0, 0.16, 0.16, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const hideCaptionsOn = new Set(["quote", "bullets"]); // там текст уже на экране
  return (
    <AbsoluteFill style={{ fontFamily: body, color: C.ink }}>
      <Grain />
      <Audio src={staticFile(music)} volume={musicVol} />
      <Audio src={staticFile(voice)} volume={1} />
      {scenes.map(sc => {
        const from = Math.round(sc.start * fps), to = Math.round(sc.end * fps);
        if (f < from - 2 || f >= to) return null;
        switch (sc.type) {
          case "hook": return <Hook key={sc.id} sc={sc} bg={bg} />;
          case "job": return <JobCard key={sc.id} sc={sc} />;
          case "bars": return <Bars key={sc.id} sc={sc} captions={captions} />;
          case "big": return <Big key={sc.id} sc={sc} bg={bg} />;
          case "bullets": return <Bullets key={sc.id} sc={sc} captions={captions} bg={bg} />;
          case "quote": return <Quote key={sc.id} sc={sc} bg={bg} />;
          case "cta": return <Cta key={sc.id} sc={sc} />;
          default: return null;
        }
      })}
      <Captions captions={captions} hideOn={hideCaptionsOn} scenes={scenes} />
      {/* тонкая полоска прогресса сверху */}
      <div style={{ position: "absolute", top: 0, left: 0, height: 8, width: `${(t / duration) * 100}%`, background: C.acid, opacity: 0.8 }} />
    </AbsoluteFill>
  );
};
