# Personal JEDI — architecture and rollout

Date: 7 November 2026. The original dashboard, catalog implementation, landing page,
and owner-model navigation were preserved in commit `43c9c8d` before this design was
implemented. No existing data is migrated into a new account or deleted.

## What the research supports

- Google's [YouTube recommendation paper](https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/)
  separates candidate generation from ranking. This is architectural evidence for
  separating retrieval costs from personal ordering, not evidence that a small
  application needs deep neural networks.
- Google's [candidate generation overview](https://developers.google.com/machine-learning/recommendation/overview/candidate-generation)
  distinguishes content-based and collaborative retrieval. The latter needs useful
  interaction data; shared membership alone does not establish similar preferences.
- LinkedIn's [hiring-preference engineering article](https://www.linkedin.com/blog/engineering/learning/learning-hiring-preferences-the-ai-behind-linkedin-jobs)
  describes preference features derived from different kinds of feedback. That
  article concerns recruiter-side recommendations, so its feedback architecture
  informs this design without establishing job-seeker performance claims.

**JEDI decision:** generate shared role pools daily, assign members to those pools
from explicit target roles, then score candidates using each member's current
preferences. This is a transparent starting point. It is not learned clustering,
collaborative filtering, or a reproduction of those companies' models.

## Implemented boundaries

- `/legacy/dashboard`, `/legacy/jobs`, `/legacy/landing` preserve earlier pages.
  Shared model/profile/training controls are in the Legacy navigation section.
  `/jobs` remains the compatible catalog, with explicitly legacy score labels.
- `/dashboard` uses private `MemberProfile` preferences. The owner-trained model
  never supplies this feed's scores. Preference edits preserve stored resume text
  and do not change email subscriptions or the group's active model/profile.
- Daily retrieval stores job IDs in versioned role pools. No member IDs, resume
  text, email addresses, or cohort member lists are in the snapshot or public UI.
  The catalog is still the existing shared catalog. This change does not establish
  separate employer inventories for multiple independent tenant organizations.
- Members targeting similar role families share candidates. Their ordering is
  personal. Unmapped roles use a general pool; users may belong to several pools.
  These are deterministic role buckets, not demographic or inferred identity groups.
- Eligibility excludes explicitly closed, expired, undated, future-dated, and
  over-30-day-old postings. Eligibility is checked again when serving the feed.
  Employer availability is not re-fetched on each page load.
- Retrieval samples the newest 5,000 eligible catalog jobs. Each role pool has a
  1,000-job limit, and the feed returns 25 results. The UI discloses these limits.
- Preference score weights are role 45, skills 30, location/work mode 15, and
  experience 10, normalized across configured dimensions. Missing job evidence
  earns no credit. Skill aliases use the existing canonical vocabulary. Role-family
  overlap gets partial credit; it is not a proven semantic match.
- Salary is a review signal only when annual currency is comparable; it does not
  contribute to the score. Locations and experience are soft preference signals.
  Remote does not prove worldwide work eligibility. Resume fit is a separate
  evidence comparison. Neither score estimates interview or offer probability.

## Server operation

`vercel.json` schedules `GET /svc/ml/internal/recommendations/run` daily at 01:00
UTC (06:30 India time). The route requires `Authorization: Bearer <CRON_SECRET>`.
It does not send mail, scrape employer sites, or depend on an open browser. It
prepares recommendations from jobs already ingested by the collection workflow.

Vercel's [cron operations documentation](https://vercel.com/docs/cron-jobs/manage-cron-jobs)
explains authentication, function duration limits, duplicate invocation, and
overlap. A schedule declaration needs a production deployment to actually run.
Vercel does not automatically retry failed cron invocations. Operators may safely
retry the same authenticated endpoint. For another host, schedule that same request.

Publication uses a PostgreSQL transaction advisory lock and one key per algorithm
version and UTC date. Overlapping workers return `BUSY`. Completed daily snapshots
replay without recomputation. Failure records a safe error code and leaves the
latest completed generation available. A process crash releases the lock and rolls
back publication. It cannot reliably record its own crash; freshness exposes that
gap. Collection has a 90-second deadline, within the configured function budget.

Feed states are `NEEDS_PREFERENCES`, `WAITING_FOR_BATCH`, `READY`, `EMPTY`, and
`STALE` (over 36 hours since publication). API errors have an explicit retry state.
The latest failed attempt is shown alongside any earlier results. An unapplied
recommendation migration returns a specific setup-required message.

## Release checklist

- [x] Preserve legacy UI and owner model, with compatible deep links.
- [x] Add private preference editing and deterministic personal ranking.
- [x] Add additive, RLS-enabled snapshot migration and daily cron declaration.
- [x] Test aliases, evidence gaps, expiry, repeatability, authentication, member
  isolation, replay, stale fallback, and real PostgreSQL worker overlap.
- [x] Apply the new migration to isolated local PostgreSQL only.
- [ ] Apply `20261107000000_daily_recommendations` to the intended deployed database.
- [ ] Deploy with a strong `CRON_SECRET`, invoke one batch, and verify the next
  scheduled run in production logs. Hosted scheduling remains unverified.
- [ ] Monitor empty-pool rate, retrieval coverage, time to publish, and stale feeds.

## Next evaluation gates

1. Generalize role vocabulary beyond the current technical/design/product buckets
   using reviewed examples. Evaluate recall for nontechnical and mixed-role users.
2. Add explicit work-authorization and location constraints, structured salary
   comparability, and exclusion controls. Keep unknown eligibility visible.
3. Collect consented, member-scoped save/dismiss/application feedback. Separate
   explicit dislike from missing feedback. Prevent the legacy owner's labels from
   becoming everyone else's training target.
4. Compare content retrieval and learned embeddings against this deterministic
   baseline. Evaluate recall@K, per-user NDCG, coverage, diversity, cold-start users,
   and geography before adding learned clusters.
5. Move retrieval to checkpointed queued shards when the 5,000-job bound or runtime
   budget becomes restrictive. Add retry scheduling, alerts, retention, and a
   deployment operations view before increasing workload.
6. Add optional personal daily digests using the same published generation. Existing
   email campaigns remain separate and must not silently adopt a new score meaning.
