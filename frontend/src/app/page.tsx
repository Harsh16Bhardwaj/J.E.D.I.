"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowUpRight,
  Check,
  Crosshair,
  FileSearch,
  Orbit,
  Pause,
  Play,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { JediSentinel } from "@/components/jedi-sentinel";
import { PublicAuthActions } from "@/components/public-auth-actions";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const paths = [
  {
    icon: Crosshair,
    n: "01",
    title: "Set your coordinates.",
    copy: "Your roles. Your skills. Your kind of place. Tell JEDI where you want to go and make the feed your own.",
    tag: "PERSONAL PREFERENCES",
  },
  {
    icon: FileSearch,
    n: "02",
    title: "See what aligns.",
    copy: "Bring a job link or description. Compare it with reviewed resume evidence and see the strengths, gaps, and details to verify.",
    tag: "EVIDENCE BEFORE CONFIDENCE",
  },
  {
    icon: Orbit,
    n: "03",
    title: "Make your next move.",
    copy: "Keep applications in one place. Turn missing skills into a learning plan. Come back with a little more clarity.",
    tag: "PROGRESS WITH DIRECTION",
  },
];

export default function LandingPage() {
  const reduced = useReducedMotion();
  const [paused, setPaused] = useState(false);
  const [briefing, setBriefing] = useState(false);
  const [example, setExample] = useState<"frontend" | "backend">("frontend");
  const hydrated = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
  const still = (hydrated && reduced) || paused;
  const reveal = {
    initial: still ? (false as const) : { opacity: 0, y: 25 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, amount: 0.15 },
    transition: { duration: still ? 0 : 0.65 },
  };

  return (
    <main className={`jedi-next ${still ? "motion-paused" : ""}`}>
      <noscript>
        <style>{`.jedi-next [style] { opacity: 1 !important; transform: none !important; }`}</style>
      </noscript>
      <a className="jedi-skip" href="#mission">
        Skip to content
      </a>
      <header className="jedi-nav">
        <Link href="/" aria-label="JEDI home" className="jedi-wordmark">
          <span className="jedi-mark" aria-hidden="true">
            ✳
          </span>{" "}
          JEDI<span className="jedi-wordmark-dot">.</span>
        </Link>
        <nav aria-label="Public navigation">
          <a href="#mission">The mission</a>
          <a href="#signal">Your signal</a>
          <button onClick={() => setBriefing(true)}>
            Field guide <ArrowUpRight size={12} />
          </button>
        </nav>
        <div className="jedi-nav-access">
          <Link href="/login">Sign in</Link>
          <Link className="jedi-join" href="/register">
            Enter JEDI <ArrowUpRight size={15} />
          </Link>
        </div>
      </header>

      <section className="jedi-hero" aria-labelledby="hero-title">
        <div className="jedi-hero-grid" aria-hidden="true" />
        <div className="jedi-hero-copy">
          <motion.p {...reveal} className="jedi-eyebrow">
            <span className="jedi-status-dot" /> JOB INTELLIGENCE. PERSONALIZED.
          </motion.p>
          <motion.h1 {...reveal} id="hero-title">
            A clearer path.
            <br />A stronger
            <br />
            <span>next move.</span>
          </motion.h1>
          <motion.p {...reveal} className="jedi-hero-description">
            The job search is a whole universe.
            <br />
            Find your place in it.
          </motion.p>
          <motion.div {...reveal} className="jedi-hero-actions">
            <Link href="/dashboard" className="jedi-primary">
              Find my direction <ArrowUpRight size={18} />
            </Link>
            <button onClick={() => setBriefing(true)} className="jedi-play">
              <span>
                <Play size={13} fill="currentColor" />
              </span>{" "}
              Get the briefing
            </button>
          </motion.div>
          <p className="jedi-hero-note">
            <ShieldCheck size={13} /> Private resume. Personal preferences.
            Invite access.
          </p>
        </div>
        <div className="jedi-hero-art">
          <div className="jedi-art-label">
            <span>JEDI INTELLIGENCE SYSTEM</span>
            <span>VOL. 02</span>
          </div>
          <JediSentinel />
          <div className="jedi-art-caption">
            <span>
              <i /> SEEK CLARITY
            </span>
            <span>KEEP MOVING ↗</span>
          </div>
        </div>
        <div className="jedi-hero-bottom">
          <a href="#mission">
            <ArrowDown size={14} /> Explore the mission
          </a>
          <button
            onClick={() => setPaused(!paused)}
            aria-pressed={Boolean(still)}
            disabled={Boolean(hydrated && reduced)}
          >
            {still ? <Play size={12} /> : <Pause size={12} />}
            {hydrated && reduced
              ? "Reduced motion"
              : paused
                ? "Resume motion"
                : "Pause motion"}
          </button>
          <span>BUILT FOR YOUR NEXT CHAPTER</span>
        </div>
      </section>

      <section id="mission" className="jedi-section jedi-mission">
        <motion.div {...reveal} className="jedi-section-heading">
          <p className="jedi-eyebrow">01 / THE MISSION</p>
          <h2>
            Less wandering.
            <br />
            <span>More becoming.</span>
          </h2>
          <p>
            A workspace for the person behind the resume.
            <br />
            Discover the right work. Understand your fit. Build what comes next.
          </p>
        </motion.div>
        <div className="jedi-paths">
          {paths.map(({ icon: Icon, n, title, copy, tag }) => (
            <motion.article {...reveal} key={n}>
              <div key="top" className="jedi-path-top">
                <Icon size={25} strokeWidth={1.2} />
                <span>{n}</span>
              </div>
              <h3 key="title">{title}</h3>
              <p key="copy">{copy}</p>
              <span key="tag" className="jedi-path-tag">
                {tag}
              </span>
            </motion.article>
          ))}
        </div>
      </section>

      <section id="signal" className="jedi-section jedi-signal">
        <motion.div {...reveal} className="jedi-signal-copy">
          <p className="jedi-eyebrow">02 / YOUR SIGNAL</p>
          <h2>
            One market.
            <br />
            <span>Your perspective.</span>
          </h2>
          <p>
            People heading in a similar direction share a daily pool of
            opportunities. Your preferences decide the order you see.
          </p>
          <p>
            Change your direction whenever you need to. Your resume stays yours,
            and your score comes with reasons.
          </p>
          <button
            className="jedi-inline-action"
            onClick={() => setBriefing(true)}
          >
            Understand the scores <ArrowUpRight size={16} />
          </button>
        </motion.div>
        <motion.div {...reveal} className="jedi-signal-console">
          <div className="jedi-console-top">
            <span>
              <i /> PERSONAL SIGNAL
            </span>
            <span>INTERACTIVE EXAMPLE</span>
          </div>
          <div className="jedi-console-tabs" aria-label="Example preference">
            <button
              aria-pressed={example === "frontend"}
              onClick={() => setExample("frontend")}
            >
              Frontend
            </button>
            <button
              aria-pressed={example === "backend"}
              onClick={() => setExample("backend")}
            >
              Backend
            </button>
          </div>
          <div className="jedi-example-body" aria-live="polite">
            <div className="jedi-example-monogram">
              {example === "frontend" ? "F" : "B"}
              <Sparkles size={14} />
            </div>
            <p>ILLUSTRATIVE OPPORTUNITY</p>
            <h3>
              {example === "frontend"
                ? "Frontend Engineer"
                : "Backend Engineer"}
            </h3>
            <span>
              {example === "frontend"
                ? "React · TypeScript · Design systems"
                : "Python · PostgreSQL · API design"}
            </span>
            <div className="jedi-example-evidence">
              <p>
                <Check size={14} /> Your target role
              </p>
              <p>
                <Check size={14} /> Skills you want to work with
              </p>
              <p>
                <Crosshair size={14} /> Salary and eligibility still need review
              </p>
            </div>
          </div>
          <div className="jedi-console-foot">
            <ShieldCheck size={13} /> Preference alignment and resume fit are
            separate.
          </div>
        </motion.div>
      </section>

      <section className="jedi-principles">
        <div className="jedi-section">
          <motion.div {...reveal}>
            <p className="jedi-eyebrow">03 / THE CODE</p>
            <h2>
              Clarity is
              <br />a superpower.
            </h2>
          </motion.div>
          <div className="jedi-principles-list">
            {[
              [
                "01",
                "Your evidence stays yours.",
                "Your resume, fit comparisons, and application progress belong to your private workspace.",
              ],
              [
                "02",
                "Every score has a boundary.",
                "Preference scores help you prioritize. Resume fit reflects documented evidence. Neither predicts an offer.",
              ],
              [
                "03",
                "You stay in command.",
                "Review extracted facts, update your preferences, and decide where to apply. JEDI helps you choose your next move.",
              ],
            ].map(([n, title, copy]) => (
              <motion.article {...reveal} key={n}>
                <span key="n">{n}</span>
                <div key="copy">
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </div>
                <ArrowUpRight key="arrow" size={17} />
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      <section className="jedi-section jedi-final">
        <motion.div {...reveal}>
          <Orbit className="jedi-final-orbit" size={54} strokeWidth={0.7} />
          <p className="jedi-eyebrow">YOUR NEXT CHAPTER IS OUT THERE</p>
          <h2>
            Go find
            <br />
            <span>your orbit.</span>
          </h2>
          <PublicAuthActions className="jedi-final-actions" />
          <p>Invite access is currently required to create an account.</p>
        </motion.div>
      </section>
      <footer className="jedi-footer">
        <Link href="/" className="jedi-wordmark">
          ✳ JEDI.
        </Link>
        <span>JOB EVALUATION & DELIVERY INTELLIGENCE</span>
        <button onClick={() => setBriefing(true)}>
          Read the field guide <ArrowUpRight size={13} />
        </button>
        <span>MADE FOR THE NEXT MOVE.</span>
      </footer>

      <Dialog open={briefing} onOpenChange={setBriefing}>
        <DialogContent className="sm:max-w-2xl jedi-briefing-dialog">
          <DialogHeader>
            <p className="jedi-eyebrow">JEDI / FIELD GUIDE / 02</p>
            <DialogTitle>Before you enter the orbit.</DialogTitle>
            <DialogDescription>
              A short briefing on your workspace and what its signals mean.
            </DialogDescription>
          </DialogHeader>
          <div className="jedi-guide-sections">
            <section>
              <span>01 / PERSONAL SIGNAL</span>
              <h3>Built around your direction.</h3>
              <p>
                Set target roles, skills, locations, and experience. Daily
                server batches prepare shared job pools. Your current
                preferences order the jobs you see.
              </p>
            </section>
            <section>
              <span>02 / EVIDENCE & PRIVACY</span>
              <h3>You review the facts.</h3>
              <p>
                Upload a resume and review its extracted evidence. Compare it
                with a job description to understand documented matches and
                gaps. Other members do not receive your resume or private
                comparisons.
              </p>
            </section>
            <section>
              <span>03 / WHAT A SCORE MEANS</span>
              <h3>A useful signal with clear limits.</h3>
              <p>
                Preference scores reflect your choices. Resume fit reflects the
                evidence available. Missing details remain uncertain. Verify job
                availability, compensation, and eligibility with the employer.
              </p>
            </section>
            <section>
              <span>04 / THE ORIGINAL WORKSPACE</span>
              <h3>History has a home.</h3>
              <p>
                The original shared leaderboard and owner model are retained in
                Legacy. Their scores belong to the original shared profile.
              </p>
            </section>
          </div>
          <div className="jedi-guide-footer">
            <span>Read at your pace. No consent is recorded here.</span>
            <button className="jedi-primary" onClick={() => setBriefing(false)}>
              Understood <Check size={16} />
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
