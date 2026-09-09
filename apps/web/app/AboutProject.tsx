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
            compactPosition={{ x: 16, y: 24 }}
            initialZIndex={2}
            className="about-window window-origin"
          >
            <p>
              I started MemoryCue with a small question: what if a pair of glasses could quietly give someone back the
              thread of an ordinary day?
            </p>
            <p>
              This project is my way of following that question into the messy, hopeful middle — one grounded moment,
              one calm cue, and a laptop camera standing in for the glasses.
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
            compactPosition={{ x: 102, y: 218 }}
            initialZIndex={5}
            className="about-window window-disclaimer"
          >
            <h3>Prototype note</h3>
            <p>
              MemoryCue is an experimental software prototype — not a medical device, diagnosis, treatment, or
              replacement for caregivers or medical professionals.
            </p>
            <p>AI suggestions are suggestions. Review them before they become part of someone&apos;s memory.</p>
          </DraggableWindow>

          <DraggableWindow
            id="capabilities"
            title="prototype.log"
            boundsRef={desktopRef}
            initialPosition={{ x: 635, y: 312 }}
            compactPosition={{ x: 28, y: 464 }}
            initialZIndex={4}
            className="about-window window-capabilities"
          >
            <p className="window-note-label">What it can do today</p>
            <p className="capability-lead">Capture moments. Find what was misplaced. Keep today close.</p>
            <ul>
              <li>Reviewable memories from images</li>
              <li>Last-seen objects and recent activity</li>
              <li>Schedules and caregiver-approved people</li>
            </ul>
            <p className="creator-credit">A small research project by Tehsin Shaik.</p>
          </DraggableWindow>

          <DraggableWindow
            id="snapshot"
            title="memorycue.jpg"
            boundsRef={desktopRef}
            initialPosition={{ x: 1000, y: 78 }}
            compactPosition={{ x: 178, y: 606 }}
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
        <span className="about-desktop-footer">Drag the notes around · they&apos;re still finding their place</span>
      </div>
    </section>
  );
}
