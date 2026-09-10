"use client";

import { useRef } from "react";

import DraggableWindow, { DraggableWindowGroup } from "./DraggableWindow";

export default function AboutProject() {
  const desktopRef = useRef<HTMLDivElement | null>(null);

  return (
    <section className="about-project" aria-labelledby="about-project-title">
      <div className="about-project-heading">
        <p className="product-kicker">05 · Behind the project</p>
        <h2 id="about-project-title">About the project.</h2>
      </div>

      <div className="about-desktop" ref={desktopRef}>
        <span className="about-desktop-label">MEMORYCUE / FIELD NOTES</span>
        <DraggableWindowGroup>
          <DraggableWindow
            id="origin"
            title="origin.txt"
            boundsRef={desktopRef}
            initialPosition={{ x: 38, y: 44 }}
            compactPosition={{ x: 16, y: 34 }}
            initialZIndex={2}
            className="about-window window-origin"
          >
            <p>
              I started MemoryCue with a small question: could a pair of glasses help someone recover the thread of an
              ordinary day?
            </p>
            <p>
              Today, it is a browser-based software prototype. A laptop camera stands in for a future smart-glasses
              experience, bringing saved context back through short, calm cues.
            </p>
            <p className="origin-signoff">Still early. Still curious.</p>
            <a className="about-github-link" href="https://github.com/tehsin-shaik/ai_dementia_glasses" target="_blank" rel="noreferrer">
              View the project on GitHub <span aria-hidden="true">↗</span>
            </a>
          </DraggableWindow>

          <DraggableWindow
            id="disclaimer"
            title="a gentle note.txt"
            boundsRef={desktopRef}
            initialPosition={{ x: 470, y: 38 }}
            compactPosition={{ x: 28, y: 330 }}
            initialZIndex={5}
            className="about-window window-disclaimer"
          >
            <h3>Prototype note</h3>
            <p>
              MemoryCue is experimental. It does not provide medical care and is not a medical device, diagnosis,
              treatment, or replacement for caregivers or medical professionals.
            </p>
            <p>Optional AI analysis can suggest details, but only reviewed information is saved as a MemoryCue record.</p>
          </DraggableWindow>

          <DraggableWindow
            id="capabilities"
            title="prototype.log"
            boundsRef={desktopRef}
            initialPosition={{ x: 635, y: 312 }}
            compactPosition={{ x: 18, y: 560 }}
            initialZIndex={4}
            className="about-window window-capabilities"
          >
            <p className="window-note-label">What it can do today</p>
            <p className="capability-lead">Capture moments. Find what was misplaced. Keep today close.</p>
            <ul>
              <li>Reviewed memories from camera or uploaded images</li>
              <li>Recent activity, last-seen, and schedule retrieval</li>
              <li>Approved-person recognition and optional context cues</li>
            </ul>
            <p className="creator-credit">A small research project by Tehsin Shaik.</p>
          </DraggableWindow>

          <DraggableWindow
            id="snapshot"
            title="memorycue.jpg"
            boundsRef={desktopRef}
            initialPosition={{ x: 1000, y: 78 }}
            compactPosition={{ x: 84, y: 810 }}
            initialZIndex={3}
            className="about-window window-snapshot"
          >
            <div className="about-photo-art" aria-label="An illustrated memory cue snapshot">
              <span className="photo-window-glow" />
              <span className="photo-sun" />
              <span className="photo-head" />
              <span className="photo-shoulders" />
              <span className="photo-glasses" />
              <span className="photo-caption">a moment worth keeping</span>
            </div>
            <p className="snapshot-credit">Built by Tehsin Shaik · 2026</p>
          </DraggableWindow>
        </DraggableWindowGroup>
        <span className="about-desktop-footer">Drag the notes around · explore at your own pace</span>
      </div>
    </section>
  );
}
