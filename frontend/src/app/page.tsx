"use client";

import Link from "next/link";
import {
  ArrowDown,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleDot,
  LockKeyhole,
  Mail,
  MoveRight,
  Orbit,
  Route,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { PublicAuthActions } from "@/components/public-auth-actions";

const briefingJobs = [
  {
    rank: "01",
    score: "94.2",
    role: "Backend Engineer",
    company: "Fintech product team",
    location: "Bengaluru / Hybrid",
    note: "Strong role + stack alignment",
  },
  {
    rank: "02",
    score: "91.8",
    role: "ML Platform Engineer",
    company: "Enterprise software",
    location: "Remote / India",
    note: "High domain fit",
  },
  {
    rank: "03",
    score: "89.4",
    role: "Python Engineer",
    company: "Developer tools",
    location: "Gurugram / Hybrid",
    note: "Preferred stack",
  },
];

const signalSteps = [
  {
    number: "01",
    verb: "Curate",
    title: "A human-sized pool, not an infinite feed.",
    copy: "Relevant openings are gathered for one focused profile. JEDI is intentionally narrow: it is built to produce a useful daily read, not the largest database.",
  },
  {
    number: "02",
    verb: "Clean",
    title: "The noise loses before you arrive.",
    copy: "Malformed listings and duplicates are removed before ranking, so repeated posts do not manufacture importance and weak data does not become a confident score.",
  },
  {
    number: "03",
    verb: "Rank",
    title: "The strongest fit earns the first look.",
    copy: "One versioned model scores the surviving jobs against the shared profile. The result is a leaderboard designed for choosing what to review first.",
  },
];

const evidence = [
  { value: "96.8%", label: "Precision @ 25", note: "positive apply labels in the first 25" },
  { value: ".9752", label: "NDCG @ 25", note: "strong labels concentrated near the top" },
  { value: ".9321", label: "ROC AUC", note: "separation across apply thresholds" },
];

function DailyBriefing() {
  return (
    <div className="briefing-shell" aria-label="Illustrative JEDI daily leaderboard">
      <div className="briefing-topline">
        <span className="flex items-center gap-2">
          <CircleDot className="size-3.5 text-acid" aria-hidden="true" />
          DAILY BRIEF / RANKED
        </span>
        <span>INTERFACE SPECIMEN</span>
      </div>

      <div className="briefing-lead">
        <div>
          <span className="briefing-rank">01</span>
          <span className="briefing-rank-label">First look</span>
        </div>
        <div className="briefing-lead-copy">
          <span className="briefing-kicker">Highest preference fit today</span>
          <h2>{briefingJobs[0].role}</h2>
          <p>{briefingJobs[0].company} <span>/</span> {briefingJobs[0].location}</p>
          <div className="mt-7 flex flex-wrap gap-2">
            <span className="briefing-tag">Preferred role</span>
            <span className="briefing-tag">Stack match</span>
            <span className="briefing-tag">Fresh listing</span>
          </div>
        </div>
        <div className="briefing-score">
          <span>JEDI</span>
          <strong>{briefingJobs[0].score}</strong>
          <small>/ 100</small>
        </div>
      </div>

      <div className="briefing-table">
        {briefingJobs.slice(1).map((job) => (
          <div className="briefing-row" key={job.rank}>
            <span className="briefing-row-rank">{job.rank}</span>
            <div>
              <strong>{job.role}</strong>
              <span>{job.company} / {job.location}</span>
            </div>
            <span className="briefing-note">{job.note}</span>
            <strong className="briefing-row-score">{job.score}</strong>
          </div>
        ))}
      </div>

      <div className="briefing-footer">
        <span>One profile. One comparable ranking.</span>
        <span>Score = preference evidence, not outcome probability.</span>
      </div>
      <span className="briefing-stamp" aria-hidden="true">INVITE<br />ONLY</span>
    </div>
  );
}

function RouterDiagram() {
  return (
    <div className="router-diagram" aria-label="OpenJEDI routing concept">
      <div className="router-source">
        <span className="router-caption">Canonical market</span>
        <strong>JOB_0184</strong>
        <small>one source record</small>
      </div>
      <div className="router-track" aria-hidden="true"><MoveRight /></div>
      <div className="router-core">
        <Route aria-hidden="true" />
        <span>OPEN</span>
        <strong>ROUTER</strong>
        <small>v2</small>
      </div>
      <div className="router-branches" aria-hidden="true" />
      <div className="router-groups">
        <div><span>GROUP 01</span><strong>Backend / India</strong><small>model v3.2</small></div>
        <div><span>GROUP 02</span><strong>ML / Remote</strong><small>model v1.8</small></div>
        <div><span>GROUP 03</span><strong>Your profile</strong><small>creator-owned</small></div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const reduceMotion = useReducedMotion();

  return (
    <main className="jedi-landing overflow-hidden">
      <header className="landing-header">
        <div className="landing-header-inner">
          <Link href="/" className="landing-masthead" aria-label="JEDI home">
            <Orbit className="size-5" aria-hidden="true" />
            <span>JEDI</span>
          </Link>
          <div className="landing-edition hidden sm:block">
            <span>THE DAILY SIGNAL</span>
            <span>INVITED EDITION / V1</span>
          </div>
          <nav className="hidden items-center gap-6 xl:flex" aria-label="Public navigation">
            <a href="#brief">Today</a>
            <a href="#score">The score</a>
            <a href="#openjedi">OpenJEDI</a>
          </nav>
          <PublicAuthActions compact className="ml-auto shrink-0 justify-end" />
        </div>
      </header>

      <section className="landing-opening">
        <div className="landing-coordinate landing-coordinate-left" aria-hidden="true">01 / SIGNAL</div>
        <div className="landing-coordinate landing-coordinate-right" aria-hidden="true">ISSUE / DAILY</div>
        <div className="landing-opening-grid">
          <motion.div
            initial={reduceMotion ? false : { opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
            className="landing-opening-copy"
          >
            <p className="landing-eyebrow"><span /> Invite-only job intelligence</p>
            <h1>
              Stop<br />
              <span>searching.</span><br />
              Start choosing.
            </h1>
          </motion.div>

          <motion.aside
            initial={reduceMotion ? false : { opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.65, delay: 0.12, ease: [0.16, 1, 0.3, 1] }}
            className="landing-opening-aside"
          >
            <p className="landing-aside-number">THE PREMISE / 001</p>
            <p className="landing-aside-lead">
              The internet already has enough jobs. What it lacks is a good first page.
            </p>
            <p>
              JEDI curates, verifies, deduplicates, and ranks a focused set of openings every day—so invited members begin with the strongest fit instead of another empty search box.
            </p>
            <PublicAuthActions className="mt-8" />
            <a href="#brief" className="landing-text-link">
              Open the daily brief <ArrowDown className="size-4" aria-hidden="true" />
            </a>
          </motion.aside>
        </div>

        <motion.div
          initial={reduceMotion ? false : { opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.22, ease: [0.16, 1, 0.3, 1] }}
          className="landing-brief-wrap"
        >
          <DailyBriefing />
        </motion.div>
      </section>

      <div className="signal-ticker" aria-hidden="true">
        <div>
          <span>CURATED</span><i>✳</i><span>VERIFIED</span><i>✳</i><span>DEDUPLICATED</span><i>✳</i><span>RANKED</span><i>✳</i><span>SHARED</span><i>✳</i>
          <span>CURATED</span><i>✳</i><span>VERIFIED</span><i>✳</i><span>DEDUPLICATED</span><i>✳</i><span>RANKED</span><i>✳</i><span>SHARED</span><i>✳</i>
        </div>
      </div>

      <section id="brief" className="landing-story">
        <div className="landing-story-intro">
          <p className="landing-index">01 / THE DAILY BRIEF</p>
          <h2>Twenty tabs become one decision.</h2>
          <p>
            JEDI does not ask members to build a feed. The feed is the service: a controlled daily intake, narrowed for one shared job-seeker profile and ordered by one focused model.
          </p>
        </div>
        <div className="signal-steps">
          {signalSteps.map((step) => (
            <article className="signal-step" key={step.number}>
              <span className="signal-step-number">{step.number}</span>
              <p className="signal-step-verb">{step.verb}</p>
              <h3>{step.title}</h3>
              <p>{step.copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="score" className="score-section">
        <div className="score-heading">
          <p className="landing-index">02 / READ THE SCORE</p>
          <h2>A ranking,<br /><em>not a prophecy.</em></h2>
          <p>
            A 94.2 JEDI score does not mean a 94.2% chance of an interview. It means the job expresses stronger learned preference fit than the other jobs in that briefing.
          </p>
        </div>
        <dl className="score-ledger">
          {evidence.map((item, index) => (
            <div key={item.label}>
              <dt><span>0{index + 1}</span>{item.label}</dt>
              <dd>{item.value}</dd>
              <p>{item.note}</p>
            </div>
          ))}
        </dl>
        <div className="score-disclaimer">
          <strong>THE HONEST BOUNDARY</strong>
          <p>JEDI learns preference ranking. It does not predict recruiter replies, assessments, interviews, or offers. Those outcomes depend on people and systems the model cannot see.</p>
        </div>
      </section>

      <section className="member-section">
        <div className="member-marquee" aria-hidden="true">INVITED PEOPLE / SHARED SIGNAL / REAL FEEDBACK</div>
        <div className="member-layout">
          <div className="member-copy">
            <p className="landing-index">03 / USING JEDI TODAY</p>
            <h2>Read together.<br />Improve the signal.</h2>
            <p>
              V1 is a deliberately small room. Invited members review the same leaderboard, annotate the same jobs, and leave evidence that can sharpen the shared model.
            </p>
            <div className="member-boundary">
              <LockKeyhole aria-hidden="true" />
              <p><strong>Shared today, not private.</strong> Current job state and application events are attached to the job. Personal member-only logs and response analytics belong to v2.</p>
            </div>
          </div>
          <ol className="member-sequence">
            <li><span>01</span><div><strong>Enter by invite</strong><p>Registration stays controlled around one active group and profile.</p></div><ChevronRight aria-hidden="true" /></li>
            <li><span>02</span><div><strong>Read the ranked market</strong><p>Start at the top, inspect the evidence, and decide what deserves attention.</p></div><ChevronRight aria-hidden="true" /></li>
            <li><span>03</span><div><strong>Annotate what you learn</strong><p>Shared decisions become training evidence instead of disappearing in browser history.</p></div><ChevronRight aria-hidden="true" /></li>
            <li><span>04</span><div><strong>Take it to the inbox—or don&apos;t</strong><p>Email is an explicit member preference, not the price of using the feed.</p></div><Mail aria-hidden="true" /></li>
          </ol>
        </div>
      </section>

      <section id="openjedi" className="openjedi-field">
        <div className="openjedi-kicker">
          <span>THE NORTH STAR</span>
          <span>COMING SOON / V2</span>
        </div>
        <div className="openjedi-title" aria-label="OpenJEDI">
          <span>OPEN</span><span>JEDI</span>
        </div>
        <div className="openjedi-content">
          <div>
            <p className="openjedi-overline">The open router for job intelligence.</p>
            <h2>One job market.<br />Many ways to rank it.</h2>
            <p>
              OpenJEDI will let people discover profile-led groups—or create one—then route canonical jobs through the model and membership policy that fits them. The source market stays shared. The intelligence becomes selectable.
            </p>
            <div className="openjedi-points">
              <span><Check /> Join focused groups</span>
              <span><Check /> Create a ranking profile</span>
              <span><Check /> Route through versioned models</span>
              <span><Check /> Keep personal state personal</span>
            </div>
          </div>
          <RouterDiagram />
        </div>
      </section>

      <section className="landing-close">
        <div>
          <p className="landing-index text-acid">THE SIGNAL IS LIVE / INVITE REQUIRED</p>
          <h2>Your next job should not be hiding on page fourteen.</h2>
        </div>
        <div>
          <p>Start with the ranked market. Spend your attention where the evidence is strongest.</p>
          <PublicAuthActions className="mt-7" />
        </div>
      </section>

      <footer className="landing-footer">
        <Link href="/" className="flex items-center gap-2 font-black"><Orbit className="size-4 text-acid" /> JEDI</Link>
        <span>DAILY JOB INTELLIGENCE / INVITED EDITION</span>
        <a href="#openjedi" className="flex items-center gap-1">OPENJEDI <ArrowUpRight className="size-3.5" /></a>
      </footer>
    </main>
  );
}
