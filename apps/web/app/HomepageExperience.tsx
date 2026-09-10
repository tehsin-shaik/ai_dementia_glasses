"use client";

import type { AnimationEvent, MouseEvent, ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

const INTRO_DURATION_MS = 9350;

const INTRO_WORDS = [
  { className: "home-intro-word-remember", exitDuration: 550, exitStart: 800, index: "001", text: "remember" },
  { className: "home-intro-word-recognize", exitDuration: 700, exitStart: 2700, index: "002", text: "recognize" },
  { className: "home-intro-word-reconnect", exitDuration: 900, exitStart: 5050, index: "003", text: "reconnect" },
] as const;

const LETTER_PULL_STAGGER_MS = 30;

export default function HomepageExperience({ children }: { children: ReactNode }) {
  const [isComplete, setIsComplete] = useState(false);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const completionTimerRef = useRef<number | null>(null);
  const previousBodyOverflowRef = useRef("");
  const pageIsLockedRef = useRef(false);
  const hasFinishedRef = useRef(false);

  const releasePage = useCallback(() => {
    const content = contentRef.current;
    if (content) {
      content.inert = false;
      content.removeAttribute("aria-hidden");
    }

    if (pageIsLockedRef.current) {
      document.body.style.overflow = previousBodyOverflowRef.current;
      pageIsLockedRef.current = false;
    }
  }, []);

  const finishIntro = useCallback(
    (moveFocus: boolean) => {
      if (hasFinishedRef.current) {
        return;
      }

      hasFinishedRef.current = true;
      if (completionTimerRef.current !== null) {
        window.clearTimeout(completionTimerRef.current);
        completionTimerRef.current = null;
      }

      releasePage();
      setIsComplete(true);

      if (moveFocus) {
        window.requestAnimationFrame(() => contentRef.current?.focus({ preventScroll: true }));
      }
    },
    [releasePage],
  );

  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reducedMotion.matches) {
      finishIntro(false);
      return;
    }

    const root = document.documentElement;
    const previousScrollBehavior = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";
    window.scrollTo(0, 0);
    root.style.scrollBehavior = previousScrollBehavior;

    const content = contentRef.current;
    if (content) {
      content.inert = true;
      content.setAttribute("aria-hidden", "true");
    }

    previousBodyOverflowRef.current = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    pageIsLockedRef.current = true;

    completionTimerRef.current = window.setTimeout(() => finishIntro(false), INTRO_DURATION_MS);

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        finishIntro(true);
      }
    }

    function handleMotionPreference(event: MediaQueryListEvent) {
      if (event.matches) {
        finishIntro(false);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    reducedMotion.addEventListener("change", handleMotionPreference);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      reducedMotion.removeEventListener("change", handleMotionPreference);
      if (completionTimerRef.current !== null) {
        window.clearTimeout(completionTimerRef.current);
        completionTimerRef.current = null;
      }
      releasePage();
    };
  }, [finishIntro, releasePage]);

  function handleSkip(event: MouseEvent<HTMLButtonElement>) {
    finishIntro(event.detail === 0);
  }

  function handleIntroAnimationEnd(event: AnimationEvent<HTMLElement>) {
    if (event.target === event.currentTarget && event.animationName === "home-intro-finish") {
      finishIntro(false);
    }
  }

  return (
    <div className={`homepage-experience ${isComplete ? "is-complete" : "is-sequencing"}`}>
      {!isComplete && (
        <section
          className="home-intro"
          role="dialog"
          aria-modal="true"
          aria-label="MemoryCue introduction"
          onAnimationEnd={handleIntroAnimationEnd}
        >
          <p className="sr-only">Remember. Recognize. Reconnect.</p>
          <div className="home-intro-curtain home-intro-curtain-top" aria-hidden="true" />
          <div className="home-intro-curtain home-intro-curtain-bottom" aria-hidden="true" />
          <div className="home-intro-stage" aria-hidden="true">
            {INTRO_WORDS.map((word) => (
              <div className={`home-intro-word ${word.className}`} key={word.index}>
                <span
                  className="home-intro-index"
                  style={{
                    animationDelay: `${word.exitStart + (word.text.length - 1) * LETTER_PULL_STAGGER_MS}ms`,
                    animationDuration: `${word.exitDuration}ms`,
                  }}
                >
                  {word.index}
                </span>
                <strong className="home-intro-letters" aria-label={word.text}>
                  {[...word.text].map((letter, letterIndex) => (
                    <span
                      className="home-intro-letter"
                      aria-hidden="true"
                      key={`${word.index}-${letterIndex}`}
                      style={{
                        animationDelay: `${word.exitStart + (word.text.length - 1 - letterIndex) * LETTER_PULL_STAGGER_MS}ms`,
                        animationDuration: `${word.exitDuration}ms`,
                      }}
                    >
                      {letter}
                    </span>
                  ))}
                </strong>
              </div>
            ))}
          </div>
          <button className="home-intro-skip" type="button" onClick={handleSkip}>
            Skip
          </button>
        </section>
      )}

      <div className="homepage-content" ref={contentRef} tabIndex={-1}>
        {children}
      </div>
    </div>
  );
}
