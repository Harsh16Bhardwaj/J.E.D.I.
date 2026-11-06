export const applicationStages = [
  "NOT_STARTED", "PREPARING", "APPLIED", "SCREENING", "ASSESSMENT",
  "INTERVIEW", "OFFER", "ACCEPTED", "REJECTED", "WITHDRAWN",
];
const terminal = new Set(["ACCEPTED", "REJECTED", "WITHDRAWN"]);

export function needsApplicationCorrection(previous: string, next: string) {
  return previous !== next && (
    terminal.has(previous) || applicationStages.indexOf(next) < applicationStages.indexOf(previous)
  );
}

export type ApplicationMoveAttempt = { signature: string; requestId: string };

export function applicationMoveRequest(payload: object, previous?: ApplicationMoveAttempt) {
  const signature = JSON.stringify(payload);
  const attempt = previous?.signature === signature
    ? previous
    : { signature, requestId: crypto.randomUUID() };
  return { attempt, body: JSON.stringify({ ...payload, requestId: attempt.requestId }) };
}

export function prepareApplicationMove(
  snapshot: { status: string; updatedAt: string | null },
  nextStatus: string,
  notes: string,
  previous?: ApplicationMoveAttempt,
) {
  const payload = {
    applicationStatus: nextStatus,
    expectedStatus: snapshot.status,
    expectedUpdatedAt: snapshot.updatedAt,
    notes: notes.trim() || null,
    correction: needsApplicationCorrection(snapshot.status, nextStatus),
  };
  return applicationMoveRequest(payload, previous);
}
