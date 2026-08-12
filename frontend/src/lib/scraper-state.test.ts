import assert from "node:assert/strict";
import test from "node:test";

import type { ScrapeRunSummary } from "./api";
import {
  canAdvanceScrape,
  canCancelScrape,
  canImportScrape,
  canSelectScrapeCandidate,
  experienceLabel,
  importedBatchHref,
  scrapeProgress,
  shouldWarnAboutPartialRun,
} from "./scraper-state";
import type { ScrapeCandidate } from "./api";

const run = {
  status: "RUNNING",
  targetJobCount: 100,
  validCount: 25,
  selectedCount: 25,
  sourceCount: 100,
  processedSourceCount: 25,
} as ScrapeRunSummary;

test("scraper progress is bounded and lifecycle-aware", () => {
  assert.equal(scrapeProgress(run), 25);
  assert.equal(scrapeProgress({ ...run, processedSourceCount: 125 }), 100);
  assert.equal(scrapeProgress({ ...run, status: "IMPORTED" }), 100);
  assert.equal(canAdvanceScrape(run), true);
  assert.equal(canAdvanceScrape({ ...run, status: "REVIEW_READY" }), false);
  assert.equal(canCancelScrape(run), true);
  assert.equal(canCancelScrape({ ...run, status: "REVIEW_READY" }), true);
  assert.equal(canCancelScrape({ ...run, status: "NORMALIZATION_FAILED" }), true);
  assert.equal(canCancelScrape({ ...run, status: "IMPORTING" }), false);
  assert.equal(canCancelScrape({ ...run, status: "IMPORTED" }), false);
});

test("only selected review-ready runs can import", () => {
  assert.equal(canImportScrape({ ...run, status: "REVIEW_READY" }), true);
  assert.equal(canImportScrape({ ...run, status: "REVIEW_READY", selectedCount: 0 }), false);
});

test("failed-source warnings and successful batch links follow persisted state", () => {
  assert.equal(
    shouldWarnAboutPartialRun({
      ...run,
      status: "REVIEW_READY",
      failedSourceCount: 1,
    }),
    true,
  );
  assert.equal(shouldWarnAboutPartialRun({ ...run, failedSourceCount: 1 }), false);
  assert.equal(
    shouldWarnAboutPartialRun({
      ...run,
      status: "REVIEW_READY",
      failedSourceCount: 0,
      sourceCount: 10,
      processedSourceCount: 4,
    }),
    true,
  );
  assert.equal(importedBatchHref({ ...run, importedBatchId: "batch-123" }), "/batches/batch-123");
  assert.equal(importedBatchHref({ ...run, importedBatchId: null }), null);
});

test("experience labels preserve unknown values", () => {
  assert.equal(experienceLabel(null, null), "Unknown");
  assert.equal(experienceLabel(1, 3), "1-3 yrs");
  assert.equal(experienceLabel(2, null), "2+ yrs");
});

test("candidate selection keeps review jobs explicit and rejects hard failures", () => {
  const candidate = {
    reviewGroup: "RECOMMENDED",
    schemaValid: true,
    sourceQualityValid: true,
    geographyEligibility: "ELIGIBLE",
  } as ScrapeCandidate;
  assert.equal(canSelectScrapeCandidate(candidate, "REVIEW_READY"), true);
  assert.equal(
    canSelectScrapeCandidate({ ...candidate, reviewGroup: "NEEDS_REVIEW" }, "REVIEW_READY"),
    true,
  );
  assert.equal(
    canSelectScrapeCandidate(
      { ...candidate, reviewGroup: "NEEDS_REVIEW", geographyEligibility: "INELIGIBLE" },
      "REVIEW_READY",
    ),
    true,
  );
  assert.equal(
    canSelectScrapeCandidate({ ...candidate, reviewGroup: "REJECTED" }, "REVIEW_READY"),
    false,
  );
  assert.equal(canSelectScrapeCandidate(candidate, "RUNNING"), false);
});
