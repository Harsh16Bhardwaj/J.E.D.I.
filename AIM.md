# JEDI Product Aim

## North star

OpenJEDI becomes the open router for job intelligence.

The long-term product does not impose one universal definition of a good job.
It lets people choose the profile, model, and community signal that should rank a
canonical job market for them. A person can join an existing group whose goals
match their own or, when the platform is ready, create a focused group and feed.

## V1: JEDI today

JEDI v1 is intentionally controlled:

- Registration requires an invitation to the maintainer-operated group.
- The group has one active ranking profile and one active model.
- A curated daily job pool is validated, deduplicated, scored, and presented as
  a shared leaderboard.
- Invited members can access the shared review and annotation workflow.
- Email delivery is optional for people who want the daily signal in their
  inbox.
- Model, profile, intake, and training operations remain maintainer-controlled.

This narrow starting point is a product constraint, not an accidental limit.
The current model is designed for a certain kind of job and should be judged on
that specific ranking decision.

## OpenJEDI v2

OpenJEDI expands the same foundation into a routing network:

1. People can discover and join groups organized around a job-seeker profile.
2. Approved creators can create a group, define its profile, and establish its
   membership policy.
3. Each group owns an active profile, model, feed configuration, annotations,
   and model-improvement loop.
4. Canonical jobs can be evaluated by multiple group models without duplicating
   the underlying source record.
5. Every model exposes a versioned inference contract, health state, timeout
   policy, and observable result history before it can receive routed work.

The router connects a canonical market to selectable intelligence. It does not
turn every model into one blended score.

## Personal state requirement

Application tracking must become private before JEDI supports multiple members
as independent job seekers.

V2 must:

- Replace the current job-level application state with a user-job junction.
- Store review status, application status, notes, and timestamps per member.
- Store application events under both the member and the canonical job.
- Calculate applications, replies, assessments, interviews, offers,
  rejections, withdrawals, and stage conversion rates per member.
- Prevent one member from reading or overwriting another member's private job
  state.

Current shared job state must not be presented as private personal history.

## Data boundaries

- **Canonical jobs** are reusable market records that may be visible to several
  eligible groups.
- **Group annotations** belong to the group's ranking and training process.
- **Personal application state** belongs only to the member who created it.
- **Group profiles and models** are group-owned, versioned configuration.
- **Email subscriptions** are explicit member preferences, separate from group
  membership.

UI visibility is not authorization. Every boundary must be enforced by the API
and database before broader access is enabled.

## V1 non-goals

V1 does not provide:

- Public group creation.
- Open registration without an invitation.
- Arbitrary third-party model hosting or execution.
- Automated heavy scraping.
- Multiple active ranking profiles inside one group.
- Private per-member application analytics.
- Routing one job through a marketplace of models.

## Transition principle

OpenJEDI must preserve existing users, canonical jobs, batches, annotations,
profile versions, model versions, predictions, and ranking provenance.

The migration should add explicit ownership and routing keys around durable
records instead of rewriting historical results. A ranking must always remain
traceable to the group, profile version, model version, processing run, and job
that produced it.

## Measures of success

JEDI v1 succeeds when invited members consistently receive a small, trustworthy
daily leaderboard and spend less time searching through irrelevant jobs.

OpenJEDI succeeds when different groups can safely rank the same market through
their chosen intelligence while group training data and personal application
history remain correctly isolated.
