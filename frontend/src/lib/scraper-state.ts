import type { ScrapeCandidate, ScrapeRunSummary } from "./api";

export const activeScrapeStatuses = new Set(["CREATED", "RUNNING"]);
export const cancellableScrapeStatuses = new Set([
  "CREATED",
  "RUNNING",
  "REVIEW_READY",
  "NORMALIZATION_FAILED",
]);

export function scrapeProgress(run: ScrapeRunSummary): number {
  if (run.status === "IMPORTED") return 100;
  if (!run.sourceCount) return 0;
  return Math.min(
    100,
    Math.round((run.processedSourceCount / run.sourceCount) * 100),
  );
}

export function canAdvanceScrape(run: ScrapeRunSummary): boolean {
  return activeScrapeStatuses.has(run.status);
}

export function canCancelScrape(run: ScrapeRunSummary): boolean {
  return cancellableScrapeStatuses.has(run.status);
}

export function canImportScrape(run: ScrapeRunSummary): boolean {
  return run.status === "REVIEW_READY" && run.selectedCount > 0;
}

export function shouldWarnAboutPartialRun(run: ScrapeRunSummary): boolean {
  return (
    run.status === "REVIEW_READY" &&
    (run.failedSourceCount > 0 || run.processedSourceCount < run.sourceCount)
  );
}

export function importedBatchHref(run: ScrapeRunSummary): string | null {
  return run.importedBatchId ? `/batches/${run.importedBatchId}` : null;
}

export function experienceLabel(
  minimum: number | null,
  maximum: number | null,
): string {
  if (minimum == null && maximum == null) return "Unknown";
  if (minimum != null && maximum != null) return `${minimum}-${maximum} yrs`;
  if (minimum != null) return `${minimum}+ yrs`;
  return `Up to ${maximum} yrs`;
}

export function canSelectScrapeCandidate(
  candidate: ScrapeCandidate,
  runStatus: string,
): boolean {
  return (
    runStatus === "REVIEW_READY" &&
    candidate.reviewGroup !== "REJECTED" &&
    candidate.schemaValid &&
    candidate.sourceQualityValid
  );
}
