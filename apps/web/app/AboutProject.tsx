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
              I started MemoryCue with a practical question: could saved everyday context help someone recover the
              thread of a moment when they need it?
            </p>
            <p>
              I am exploring that question through a browser prototype. A laptop camera stands in for future glasses,
              and each image can be reviewed before it becomes a saved record.
            </p>
            <p className="origin-signoff">An early prototype, built to learn.</p>
            <a className="about-github-link" href="https://github.com/tehsin-shaik/ai_dementia_glasses" target="_blank" rel="noreferrer">
              View the project on GitHub <span aria-hidden="true">↗</span>
            </a>
          </DraggableWindow>

          <DraggableWindow
            id="disclaimer"
            title="prototype-note.txt"
            boundsRef={desktopRef}
            initialPosition={{ x: 470, y: 38 }}
            compactPosition={{ x: 28, y: 330 }}
            initialZIndex={5}
            className="about-window window-disclaimer"
          >
            <h3>Prototype note</h3>
            <p>
              MemoryCue is an experimental software prototype — not a medical device, diagnosis, treatment, or
              replacement for caregivers or medical professionals.
            </p>
            <p>AI can suggest image details, but no MemoryCue record is saved until a person reviews the fields and chooses Save memory.</p>
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
            <p className="capability-lead">Save reviewed moments and retrieve short cues from them later.</p>
            <ul>
              <li>Image upload and browser-camera capture</li>
              <li>Recent activity and last-seen retrieval</li>
              <li>Saved schedules and opt-in person checks</li>
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
              <span className="photo-caption">example memory cue</span>
            </div>
            <p className="snapshot-credit">Built by Tehsin Shaik · 2026</p>
          </DraggableWindow>
        </DraggableWindowGroup>
        <span className="about-desktop-footer">Drag the windows to explore the project notes</span>
      </div>
    </section>
  );
}
