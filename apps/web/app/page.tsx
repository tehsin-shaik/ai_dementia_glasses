import Link from "next/link";

import AboutProject from "./AboutProject";
import HomepageExperience from "./HomepageExperience";
import SiteNav from "./SiteNav";

function MemoryCueMockup() {
  return (
    <div className="hero-mockup" aria-label="Example of a future glasses-style MemoryCue reminder">
      <div className="hero-glasses" aria-hidden="true">
        <span className="hero-lens hero-lens-left" />
        <span className="hero-bridge" />
        <span className="hero-lens hero-lens-right" />
        <span className="hero-arm hero-arm-left" />
        <span className="hero-arm hero-arm-right" />
      </div>
      <div className="hero-cue">
        <span className="hero-cue-label">Example cue</span>
        <strong>Sarah</strong>
        <span>Your daughter</span>
      </div>
      <div className="hero-spark hero-spark-one" aria-hidden="true">✦</div>
      <div className="hero-spark hero-spark-two" aria-hidden="true">+</div>
      <div className="hero-time">10:18 AM · Kitchen counter</div>
    </div>
  );
}

function StoryVisual({ type }: { type: "remember" | "find" | "people" | "today" }) {
  if (type === "remember") {
    return (
      <div className="story-visual story-visual-remember" aria-label="Recent activity cue">
        <span className="visual-time">10:25 AM</span>
        <strong>Preparing to leave</strong>
        <span className="visual-line" />
        <span className="visual-caption">A moment worth keeping</span>
      </div>
    );
  }
  if (type === "find") {
    return (
      <div className="story-visual story-visual-find" aria-label="Last seen keys cue">
        <span className="visual-eyebrow">Keys last seen</span>
        <strong>Kitchen counter</strong>
        <span className="visual-time">10:18 AM</span>
      </div>
    );
  }
  if (type === "people") {
    return (
      <div className="story-visual story-visual-people" aria-label="Known person cue">
        <span className="person-orbit" aria-hidden="true">S</span>
        <div>
          <strong>Sarah</strong>
          <span>Your daughter</span>
        </div>
        <small>Example · reference enrolled</small>
      </div>
    );
  }
  return (
    <div className="story-visual story-visual-today" aria-label="Daily schedule cue">
      <div><span>3:30 PM</span><strong>Sarah visits</strong></div>
      <div><span>6:00 PM</span><strong>Dinner</strong></div>
    </div>
  );
}

export default function ProductPage() {
  return (
    <HomepageExperience>
      <main className="product-page">
        <SiteNav />

        <section className="product-hero">
          <div className="product-hero-copy">
            <p className="product-kicker">A quieter kind of assistive technology</p>
            <h1>
              <span className="home-hero-line"><span>Memory,</span></span>
              <span className="home-hero-line"><em>when you need it.</em></span>
            </h1>
            <p className="product-hero-intro">
              AI-assisted memory support that brings everyday context back into view.
            </p>
            <Link className="product-button" href="/app">
              Try MemoryCue <span aria-hidden="true">↗</span>
            </Link>
          </div>
          <MemoryCueMockup />
          <span className="hero-note">Everyday context, close at hand</span>
        </section>

        <section className="story-section story-section-remember" id="remember">
        <div className="story-copy">
          <p className="product-kicker">01 · Remember</p>
          <h2>Remember<br /><em>what just happened.</em></h2>
          <p>Capture a moment, review the details, and save it for later.</p>
        </div>
        <StoryVisual type="remember" />
        </section>

        <section className="story-section story-section-find" id="find">
        <div className="story-copy">
          <p className="product-kicker">02 · Find</p>
          <h2>Find what<br /><em>you misplaced.</em></h2>
          <p>See where your keys were last seen, with the saved time and place.</p>
        </div>
        <StoryVisual type="find" />
        </section>

        <section className="story-section story-section-people" id="people">
        <div className="story-copy">
          <p className="product-kicker">03 · People</p>
          <h2>Recognize the<br /><em>people you trust.</em></h2>
          <p>Bring a familiar name and relationship into view with “Who is this?” using approved reference faces.</p>
        </div>
        <StoryVisual type="people" />
        </section>

        <section className="story-section story-section-today" id="today">
        <div className="story-copy">
          <p className="product-kicker">04 · Today</p>
          <h2>Keep today<br /><em>close.</em></h2>
          <p>See what is coming up through saved schedules and optional reminders you can dismiss or turn off.</p>
        </div>
        <StoryVisual type="today" />
        </section>

        <section className="caregiver-story">
        <div>
          <p className="product-kicker">For the people who help</p>
          <h2>Personal context,<br /><em>set up with care.</em></h2>
        </div>
        <div className="caregiver-story-side">
          <p>Add familiar people, important objects, schedules, and notes for someone you support.</p>
          <Link className="outline-button" href="/caregiver">Open caregiver setup <span aria-hidden="true">↗</span></Link>
        </div>
        </section>

        <section className="product-final-cta">
        <p className="product-kicker">Start with a moment</p>
        <h2>See what MemoryCue<br /><em>remembers.</em></h2>
        <Link className="product-button product-button-dark" href="/app">Try MemoryCue <span aria-hidden="true">↗</span></Link>
        </section>

        <AboutProject />

        <footer className="product-footer">
          <span>MemoryCue · everyday memory support</span>
          <Link href="/demo">Development tools</Link>
        </footer>
      </main>
    </HomepageExperience>
  );
}
