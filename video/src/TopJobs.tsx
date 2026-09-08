import React from "react";
import { AbsoluteFill, Audio, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont as loadDisplay } from "@remotion/google-fonts/Unbounded";
import { loadFont as loadBody } from "@remotion/google-fonts/GolosText";

const display = loadDisplay("normal", { weights: ["700", "800"], subsets: ["latin", "cyrillic"] }).fontFamily;
const body = loadBody("normal", { weights: ["400", "600", "700"], subsets: ["latin", "cyrillic"] }).fontFamily;

export const FPS = 30;
const HOOK = 78, CARD = 120, CTA = 84;
export const DURATION = HOOK + CARD * 5 + CTA; // 450 = 15 s

const C = { bg: "#0a120e", bg2: "#0f1a14", ink: "#f2f7f4", dim: "#9fb3a8", acid: "#12e08e", pink: "#ff3fa4", line: "rgba(18,224,142,.22)" };

type Job = { title: string; company: string; where: string; salary: string; tag: string };
type Props = { week: string; cta: string; total: string; promo: string; promo2: string; jobs: Job[] };

const Grain: React.FC = () => {
  const f = useCurrentFrame();
  const z = 1.08 + 0.06 * Math.sin(f / 140);
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Img src={staticFile("hero.jpg")} style={{ position: "absolute", width: "100%", height: "100%", objectFit: "cover", objectPosition: "72% 50%", transform: `scale(${z})`, opacity: 0.42, filter: "saturate(1.05) blur(1px)" }} />
      <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(10,18,14,.35) 0%, rgba(10,18,14,.78) 45%, rgba(10,18,14,.94) 100%)" }} />
    </AbsoluteFill>
  );
};

const HeroArt: React.FC<{ height: number; zoom?: number }> = ({ height, zoom = 1 }) => (
  <div style={{ position: "absolute", top: 0, left: 0, right: 0, height, overflow: "hidden" }}>
    <Img src={staticFile("hero.jpg")} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "74% 50%", transform: `scale(${zoom})` }} />
    <div style={{ position: "absolute", inset: 0, background: `linear-gradient(180deg, rgba(10,18,14,0) 55%, ${C.bg} 100%)` }} />
  </div>
);

const Slogan: React.FC<{ size?: number; progress: number }> = ({ size = 96, progress }) => (
  <div style={{ fontFamily: display, fontWeight: 800, fontSize: size, lineHeight: 1.0, textTransform: "uppercase", color: C.ink, letterSpacing: -1 }}>
    <div>Скучная карьера</div>
    <div style={{ position: "relative", display: "inline-block", color: "rgba(242,247,244,.85)" }}>
      закончилась
      <div style={{ position: "absolute", left: -6, right: -6, top: "52%", height: Math.max(8, size * 0.09), background: C.pink, borderRadius: 6, transform: `scaleX(${progress})`, transformOrigin: "left center", boxShadow: `0 0 24px ${C.pink}99` }} />
    </div>
    <div style={{ color: C.acid, textShadow: `0 0 40px ${C.acid}55` }}>Иди ва‑банк</div>
  </div>
);

const Logo: React.FC<{ size?: number }> = ({ size = 64 }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
    <Img src={staticFile("logo.svg")} style={{ width: size * 1.6, height: size }} />
    <div style={{ fontFamily: display, fontWeight: 800, fontSize: size * 0.9, color: C.ink, letterSpacing: -1 }}>
      spin<span style={{ color: C.acid }}>hire</span>
    </div>
  </div>
);

const Hook: React.FC<{ week: string }> = ({ week }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const s = spring({ frame: f, fps, config: { damping: 14, stiffness: 120 } });
  const s2 = spring({ frame: f - 8, fps, config: { damping: 16 } });
  const strike = interpolate(f, [22, 40], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const s3 = spring({ frame: f - 34, fps, config: { damping: 16 } });
  const out = interpolate(f, [HOOK - 10, HOOK], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const zoom = interpolate(f, [0, HOOK], [1.0, 1.08]);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <HeroArt height={1020} zoom={zoom} />
      <div style={{ position: "absolute", top: 96, left: 72, transform: `scale(${0.9 + 0.1 * s})`, transformOrigin: "left top", opacity: s }}><Logo size={56} /></div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 900, transform: `translateY(${(1 - s2) * 60}px)`, opacity: s2 }}>
        <div style={{ display: "inline-block", fontFamily: body, fontWeight: 700, fontSize: 26, letterSpacing: 4, textTransform: "uppercase", color: C.acid, border: `2px solid ${C.acid}66`, borderRadius: 999, padding: "10px 22px", marginBottom: 34 }}>● Джоб‑борд iGaming‑индустрии</div>
        <Slogan size={100} progress={strike} />
      </div>
      <div style={{ position: "absolute", left: 72, right: 72, bottom: 150, transform: `translateY(${(1 - s3) * 40}px)`, opacity: s3 }}>
        <div style={{ fontFamily: display, fontWeight: 800, fontSize: 60, color: C.ink }}>Топ‑5 вакансий недели</div>
        <div style={{ marginTop: 14, fontFamily: body, fontWeight: 600, fontSize: 36, color: C.dim, letterSpacing: 3, textTransform: "uppercase" }}>{week} · только с зарплатой</div>
      </div>
    </AbsoluteFill>
  );
};

const Card: React.FC<{ job: Job; n: number }> = ({ job, n }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const s = spring({ frame: f, fps, config: { damping: 15, stiffness: 140 } });
  const sal = spring({ frame: f - 8, fps, config: { damping: 12, stiffness: 160 } });
  const out = interpolate(f, [CARD - 12, CARD], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const slide = interpolate(f, [CARD - 12, CARD], [0, -40], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ justifyContent: "center", padding: "0 72px", opacity: out, transform: `translateY(${slide}px)` }}>
      <div style={{ position: "absolute", top: 120, left: 72, right: 72, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Logo size={44} />
        <div style={{ display: "flex", gap: 10 }}>{[0, 1, 2, 3, 4].map(i => <div key={i} style={{ width: i === n - 1 ? 44 : 14, height: 14, borderRadius: 7, background: i === n - 1 ? C.acid : "rgba(255,255,255,.18)" }} />)}</div>
      </div>
      <div style={{ transform: `translateY(${(1 - s) * 120}px) scale(${0.94 + 0.06 * s})`, opacity: s, border: `2px solid ${C.line}`, borderRadius: 36, padding: "56px 56px 60px", background: `linear-gradient(180deg, ${C.bg2}, rgba(15,26,20,.6))`, boxShadow: "0 40px 120px rgba(0,0,0,.45)" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
          <div style={{ fontFamily: display, fontWeight: 800, fontSize: 150, lineHeight: 1, color: C.acid, textShadow: `0 0 40px ${C.acid}66` }}>{n}</div>
          <div style={{ fontFamily: body, fontWeight: 700, fontSize: 30, color: C.pink, letterSpacing: 3, textTransform: "uppercase", border: `2px solid ${C.pink}55`, borderRadius: 999, padding: "10px 22px" }}>{job.tag}</div>
        </div>
        <div style={{ marginTop: 34, fontFamily: display, fontWeight: 800, fontSize: 74, lineHeight: 1.02, color: C.ink, letterSpacing: -1 }}>{job.title}</div>
        <div style={{ marginTop: 26, fontFamily: body, fontWeight: 600, fontSize: 40, color: C.dim }}>{job.company} <span style={{ color: "rgba(255,255,255,.35)" }}>·</span> {job.where}</div>
        <div style={{ marginTop: 54, transform: `scale(${0.7 + 0.3 * sal})`, transformOrigin: "left center", opacity: sal, fontFamily: display, fontWeight: 800, fontSize: job.salary.length > 11 ? 80 : 100, color: C.acid, letterSpacing: -2, whiteSpace: "nowrap" }}>{job.salary}<span style={{ fontFamily: body, fontWeight: 600, fontSize: 36, color: C.dim, marginLeft: 18, letterSpacing: 0 }}>/ мес</span></div>
      </div>
    </AbsoluteFill>
  );
};

const Cta: React.FC<{ cta: string; total: string; promo: string; promo2: string }> = ({ cta, total }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const s = spring({ frame: f, fps, config: { damping: 14 } });
  const s2 = spring({ frame: f - 12, fps, config: { damping: 14 } });
  const pulse = 1 + 0.03 * Math.sin(f / 4);
  const zoom = interpolate(f, [0, CTA], [1.04, 1.12]);
  return (
    <AbsoluteFill>
      <HeroArt height={980} zoom={zoom} />
      <div style={{ position: "absolute", top: 96, left: 72, opacity: s }}><Logo size={56} /></div>
      <div style={{ position: "absolute", left: 72, right: 72, top: 860, opacity: s, transform: `translateY(${(1 - s) * 50}px)` }}>
        <Slogan size={90} progress={1} />
        <div style={{ marginTop: 34, fontFamily: body, fontWeight: 600, fontSize: 36, color: C.dim }}>{total} · вилки · релокация · крипто‑оплата</div>
      </div>
      <div style={{ position: "absolute", left: 72, right: 72, bottom: 170, opacity: s2, transform: `translateY(${(1 - s2) * 40}px)` }}>
        <div style={{ fontFamily: body, fontWeight: 700, fontSize: 34, color: C.acid, letterSpacing: 3, textTransform: "uppercase", marginBottom: 18 }}>Найти вакансии →</div>
        <div style={{ display: "inline-block", transform: `scale(${pulse})`, transformOrigin: "left center", fontFamily: display, fontWeight: 800, fontSize: 76, color: "#06130c", background: C.acid, padding: "26px 54px", borderRadius: 999, boxShadow: `0 0 80px ${C.acid}77`, whiteSpace: "nowrap" }}>{cta}</div>
        <div style={{ marginTop: 30, fontFamily: body, fontSize: 32, color: "rgba(255,255,255,.55)" }}>Ссылка в описании · отклик в один клик</div>
      </div>
    </AbsoluteFill>
  );
};

export const TopJobs: React.FC<Props> = ({ week, cta, total, promo, promo2, jobs }) => {
  const f = useCurrentFrame();
  const musicVol = interpolate(f, [0, 20, DURATION - 40, DURATION], [0, 0.45, 0.45, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ fontFamily: body, color: C.ink }}>
      <Grain />
      <Audio src={staticFile("audio/music.mp3")} volume={musicVol} />
      <Sequence from={0} durationInFrames={HOOK} premountFor={15}><Hook week={week} /></Sequence>
      {jobs.slice(0, 5).map((j, i) => (
        <Sequence key={i} from={HOOK + i * CARD} durationInFrames={CARD} premountFor={10}>
          <Card job={j} n={i + 1} />
          <Audio src={staticFile("audio/pop.wav")} volume={0.35} />
        </Sequence>
      ))}
      <Sequence from={HOOK + CARD * 5} durationInFrames={CTA} premountFor={10}><Cta cta={cta} total={total} promo={promo} promo2={promo2} /></Sequence>
    </AbsoluteFill>
  );
};
