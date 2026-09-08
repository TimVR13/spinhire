import { Composition } from "remotion";
import { TopJobs, FPS, DURATION } from "./TopJobs";
import { Short, ShortProps } from "./Short";
import data from "../data/top-jobs.json";
import sample from "../data/short-sample.json";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="TopJobs" component={TopJobs} durationInFrames={DURATION} fps={FPS} width={1080} height={1920} defaultProps={data as any} />
    <Composition
      id="Short"
      component={Short}
      fps={FPS}
      width={1080}
      height={1920}
      durationInFrames={Math.round((sample as any).duration * FPS)}
      defaultProps={sample as unknown as ShortProps}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.round((props as ShortProps).duration * FPS) })}
    />
  </>
);
