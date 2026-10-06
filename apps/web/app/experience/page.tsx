import type { Metadata } from "next";

import SiteNav from "../SiteNav";
import ExperienceWalkthrough from "./ExperienceWalkthrough";

export const metadata: Metadata = {
  title: "Experience — MemoryCue",
};

export default function ExperienceRoute() {
  return (
    <main className="exp-page">
      <SiteNav tone="dark" />
      <ExperienceWalkthrough />
    </main>
  );
}
