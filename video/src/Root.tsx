import { Composition } from "remotion";
import { TopJobs, FPS, DURATION } from "./TopJobs";
import data from "../data/top-jobs.json";
export const RemotionRoot: React.FC = () => (
  <Composition id="TopJobs" component={TopJobs} durationInFrames={DURATION} fps={FPS} width={1080} height={1920} defaultProps={data as any} />
);
