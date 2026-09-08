import React from "react";
import { AbsoluteFill, Audio, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont as loadDisplay } from "@remotion/google-fonts/Unbounded";
import { loadFont as loadBody } from "@remotion/google-fonts/GolosText";

const display = loadDisplay("normal", { weights: ["700", "800"], subsets: ["latin", "cyrillic"] }).fontFamily;
const body = loadBody("normal", { weights: ["400", "600", "700"], subsets: ["latin", "cyrillic"] }).fontFamily;

export const FPS = 30;
const HOOK = 60, CARD = 66, CTA = 60;
export const DURATION = HOOK + CARD * 5 + CTA; // 450 = 15 s

const C = { bg: "#0a120e", bg2: "#0f1a14", ink: "#f2f7f4", dim: "#9fb3a8", acid: "#12e08e", pink: "#ff3fa4", line: "rgba(18,224,142,.22)" };

type Job = { title: string; company: string; where: string; salary: string; tag: string };
type Props = { week: string; cta: string; total: string; jobs: Job[] };

const Grain: React.FC = () => (
  <AbsoluteFill style={{ background: `radial-gradient(1200px 900px at 20% 0%, rgba(18,224,142,.14), transparent 60%), radial-gradient(900px 700px at 100% 100%, rgba(255,63,164,.10), transparent 55%), ${C.bg}` }} />
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
  const s2 = spring({ frame: f - 10, fps, config: { damping: 16 } });
  const out = interpolate(f, [HOOK - 10, HOOK], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: 90, opacity: out }}>
      <div style={{ transform: `scale(${0.8 + 0.2 * s})`, opacity: s }}><Logo size={72} /></div>
      <div style={{ marginTop: 70, fontFamily: display, fontWeight: 800, fontSize: 118, lineHeight: 0.95, textTransform: "uppercase", color: C.ink, textAlign: "center", transform: `translateY(${(1 - s2) * 60}px)`, opacity: s2 }}>
        Топ‑5<br /><span style={{ color: C.acid }}>вакансий</span><br />недели
      </div>
      <div style={{ marginTop: 44, fontFamily: body, fontWeight: 600, fontSize: 40, color: C.dim, letterSpacing: 4, textTransform: "uppercase", opacity: s2 }}>iGaming · {week}</div>
    </AbsoluteFill>
  );
};

const Card: React.FC<{ job: Job; n: number }> = ({ job, n }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const s = spring({ frame: f, fps, config: { damping: 15, stiffness: 140 } });
  const sal = spring({ frame: f - 8, fps, config: { damping: 12, stiffness: 160 } });
  const out = interpolate(f, [CARD - 8, CARD], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const slide = interpolate(f, [CARD - 8, CARD], [0, -40], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
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

const Cta: React.FC<{ cta: string; total: string }> = ({ cta, total }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const s = spring({ frame: f, fps, config: { damping: 14 } });
  const pulse = 1 + 0.03 * Math.sin(f / 4);
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: 90 }}>
      <div style={{ opacity: s, transform: `translateY(${(1 - s) * 40}px)` }}><Logo size={80} /></div>
      <div style={{ marginTop: 60, fontFamily: body, fontWeight: 600, fontSize: 44, color: C.dim, opacity: s }}>{total} с зарплатами</div>
      <div style={{ marginTop: 40, transform: `scale(${pulse * s})`, fontFamily: display, fontWeight: 800, fontSize: 84, color: "#06130c", background: C.acid, padding: "28px 56px", borderRadius: 999, boxShadow: `0 0 80px ${C.acid}77` }}>{cta}</div>
      <div style={{ marginTop: 40, fontFamily: body, fontSize: 36, color: C.dim, opacity: s }}>Все вакансии — с вилкой. Отклик в один клик.</div>
    </AbsoluteFill>
  );
};

export const TopJobs: React.FC<Props> = ({ week, cta, total, jobs }) => {
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
      <Sequence from={HOOK + CARD * 5} durationInFrames={CTA} premountFor={10}><Cta cta={cta} total={total} /></Sequence>
    </AbsoluteFill>
  );
};
