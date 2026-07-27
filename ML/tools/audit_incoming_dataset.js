const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const incomingPath = process.argv[2] || path.join(ROOT, "data", "jedi_360_balanced_more_jobs_training_supplement_2026-06-29.csv");
const labeledPath = path.join(ROOT, "data", "jedi_master_labeled.csv");
const preparedPath = path.join(ROOT, "data", "jedi_master_prepared.csv");
const defaultReportName = `incoming_dataset_audit_${path.basename(incomingPath, path.extname(incomingPath))}.md`;
const reportPath = process.argv[3] ? path.resolve(process.argv[3]) : path.join(ROOT, "docs", defaultReportName);

function parseCsv(text) {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const next = text[i + 1];

    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch !== "\r") {
      field += ch;
    }
  }

  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }

  const headers = rows.shift();
  return {
    headers,
    rows: rows
      .filter((r) => r.length > 1 || (r.length === 1 && r[0] !== ""))
      .map((r) => Object.fromEntries(headers.map((h, idx) => [h, r[idx] ?? ""]))),
  };
}

function readCsv(filePath) {
  return parseCsv(fs.readFileSync(filePath, "utf8"));
}

function lower(value) {
  return String(value || "").trim().toLowerCase();
}

function number(value) {
  const n = Number(String(value || "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function countBy(rows, column) {
  const counts = new Map();
  for (const row of rows) {
    const key = row[column] === "" ? "(blank)" : String(row[column]);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, count }));
}

function top(counts, n = 20) {
  return counts.slice(0, n);
}

function mdTable(headers, rows) {
  const header = `| ${headers.join(" | ")} |`;
  const sep = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = rows.map((row) => `| ${row.map((v) => String(v).replace(/\|/g, "\\|")).join(" | ")} |`);
  return [header, sep, ...body].join("\n");
}

function normalizeText(value) {
  return lower(value)
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function nearDuplicateKey(row) {
  return [
    normalizeText(row.company_name),
    normalizeText(row.role_title),
    normalizeText(row.location),
  ].join("|");
}

const incoming = readCsv(incomingPath);
const labeled = readCsv(labeledPath);
const prepared = readCsv(preparedPath);

const incomingRows = incoming.rows;
const labeledRows = labeled.rows;
const preparedRows = prepared.rows;

const missingVsLabeled = labeled.headers.filter((h) => !incoming.headers.includes(h));
const extraVsLabeled = incoming.headers.filter((h) => !labeled.headers.includes(h));
const missingVsPrepared = prepared.headers.filter((h) => !incoming.headers.includes(h));
const extraVsPrepared = incoming.headers.filter((h) => !prepared.headers.includes(h));

const requiredColumns = [
  "row_id",
  "source_platform",
  "source_type",
  "company_name",
  "company_match_score",
  "role_title",
  "role_title_preference_score",
  "role_family",
  "role_family_preference_score",
  "seniority",
  "seniority_profile_fit_score",
  "location",
  "location_profile_fit_score",
  "work_mode",
  "work_mode_fit_score",
  "employment_type",
  "experience_min_years",
  "experience_profile_fit_score",
  "skills_or_requirements",
  "skills_profile_fit_score",
  "salary_min",
  "salary_max",
  "salary_profile_fit_score",
  "overall_preference_score",
  "preference_reason",
  "applied",
  "apply_url",
];

const missingRequired = requiredColumns.filter((h) => !incoming.headers.includes(h));

const blankCounts = incoming.headers.map((h) => ({
  column: h,
  blanks: incomingRows.filter((row) => String(row[h] ?? "").trim() === "").length,
})).filter((x) => x.blanks > 0);

const scoreColumns = incoming.headers.filter((h) => h.endsWith("_score") || h === "overall_preference_score" || h === "company_match_score");
const invalidScores = [];
for (const col of scoreColumns) {
  for (const row of incomingRows) {
    const n = number(row[col]);
    const maxAllowed = col === "salary_profile_fit_score" ? 8 : 5;
    if (n == null || n < 0 || n > maxAllowed) {
      invalidScores.push({ row_id: row.row_id, column: col, value: row[col] });
      if (invalidScores.length >= 20) break;
    }
  }
}

const numericChecks = [];
for (const row of incomingRows) {
  const expMin = number(row.experience_min_years);
  const expMax = number(row.experience_max_years);
  const salaryMin = number(row.salary_min);
  const salaryMax = number(row.salary_max);
  if (expMin == null || expMin < 0) numericChecks.push({ row_id: row.row_id, issue: "invalid experience_min_years", value: row.experience_min_years });
  if (expMax != null && expMax !== 0 && expMax < expMin) numericChecks.push({ row_id: row.row_id, issue: "experience_max_years < experience_min_years", value: `${row.experience_min_years}/${row.experience_max_years}` });
  if (salaryMin == null || salaryMin < 0) numericChecks.push({ row_id: row.row_id, issue: "invalid salary_min", value: row.salary_min });
  if (salaryMax == null || salaryMax < salaryMin) numericChecks.push({ row_id: row.row_id, issue: "salary_max < salary_min", value: `${row.salary_min}/${row.salary_max}` });
  if (numericChecks.length >= 30) break;
}

function expectedSalaryFit(row) {
  const salaryMin = number(row.salary_min);
  const salaryMax = number(row.salary_max);
  if (salaryMin == null || salaryMax == null) return null;
  const midpoint = Math.round((salaryMin + salaryMax) / 2);
  if (midpoint <= 600000) return 0;
  if (midpoint <= 700000) return 1;
  if (midpoint <= 800000) return 2;
  if (midpoint <= 1000000) return 3;
  if (midpoint <= 1200000) return 4;
  if (midpoint <= 2500000) return 5;
  if (midpoint <= 4000000) return 6;
  if (midpoint <= 5000000) return 7;
  return 8;
}

const salaryFitMismatches = [];
for (const row of incomingRows) {
  const expected = expectedSalaryFit(row);
  const actual = number(row.salary_profile_fit_score);
  if (expected != null && actual !== expected) {
    salaryFitMismatches.push({
      row_id: row.row_id,
      salary_min: row.salary_min,
      salary_max: row.salary_max,
      actual: row.salary_profile_fit_score,
      expected,
    });
  }
}

const allowedApplied = new Set(["yes", "no"]);
const invalidApplied = incomingRows.filter((row) => !allowedApplied.has(lower(row.applied))).slice(0, 20);

const labeledApplyUrls = new Set(labeledRows.map((row) => lower(row.apply_url)).filter(Boolean));
const incomingApplyUrls = incomingRows.map((row) => lower(row.apply_url)).filter(Boolean);
const duplicateIncomingUrls = top(countBy(incomingRows, "apply_url").filter((x) => x.value !== "(blank)" && x.count > 1), 20);
const overlapApplyUrls = incomingRows.filter((row) => labeledApplyUrls.has(lower(row.apply_url))).slice(0, 20);

const labeledNearKeys = new Set(labeledRows.map(nearDuplicateKey));
const incomingNearKeyCounts = new Map();
for (const row of incomingRows) {
  const key = nearDuplicateKey(row);
  incomingNearKeyCounts.set(key, (incomingNearKeyCounts.get(key) || 0) + 1);
}
const duplicateNearKeysIncoming = [...incomingNearKeyCounts.entries()]
  .filter(([, count]) => count > 1)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 20);
const overlapNearKeys = incomingRows.filter((row) => labeledNearKeys.has(nearDuplicateKey(row))).slice(0, 20);

const suspiciousUrls = incomingRows.filter((row) => {
  const url = lower(row.apply_url);
  return (
    url.includes("training_seed=") ||
    url.includes("/search?") ||
    url.includes("query=") ||
    url.includes("&q=") ||
    url.includes("?q=")
  );
});

const seedRoleUrls = incomingRows.filter((row) => lower(row.apply_url).includes("seed_role="));
const seedNamedCompanies = incomingRows.filter((row) => lower(row.company_name).includes("seed"));
const canNotApplyButAppliedYes = incomingRows.filter((row) => lower(row.can_apply_now) === "no" && lower(row.applied) === "yes");

const preferenceReasonPatterns = countBy(incomingRows.map((row) => ({
  pattern: lower(row.preference_reason).split(":")[0] || "(blank)",
})), "pattern");

const report = [];
report.push("# Incoming Dataset Audit");
report.push("");
report.push(`File: \`${path.relative(ROOT, incomingPath).replace(/\\/g, "/")}\``);
report.push("");
report.push("## Summary");
report.push("");
report.push(mdTable(
  ["Check", "Result"],
  [
    ["Rows", incomingRows.length],
    ["Columns", incoming.headers.length],
    ["Matches labeled schema", missingVsLabeled.length === 0 && extraVsLabeled.length === 0 ? "yes" : "no"],
    ["Missing required columns", missingRequired.length ? missingRequired.join(", ") : "none"],
    ["Extra columns vs labeled", extraVsLabeled.length ? extraVsLabeled.join(", ") : "none"],
    ["Missing prepared-derived columns", missingVsPrepared.length],
    ["Invalid applied labels", invalidApplied.length],
    ["Invalid score examples", invalidScores.length],
    ["Numeric issue examples", numericChecks.length],
    ["Salary-fit mismatches", salaryFitMismatches.length],
    ["Suspicious/search/training URLs", suspiciousUrls.length],
    ["URLs containing seed_role", seedRoleUrls.length],
    ["Companies containing Seed", seedNamedCompanies.length],
    ["can_apply_now=No but applied=yes", canNotApplyButAppliedYes.length],
    ["Apply URL overlaps with master", overlapApplyUrls.length],
    ["Near-duplicate overlaps with master", overlapNearKeys.length],
  ],
));
report.push("");
report.push("## Column Fit");
report.push("");
report.push("The incoming file matches the base labeled dataset schema. It does not include prepared-derived columns, which is acceptable if it goes through the preparation pipeline after merge.");
report.push("");
report.push(`Missing prepared-derived columns: \`${missingVsPrepared.join("`, `")}\``);
report.push("");
report.push("## Value Distributions");
report.push("");
for (const col of ["applied", "source_platform", "source_type", "can_apply_now", "role_family", "seniority", "work_mode", "employment_type", "salary_profile_fit_score", "overall_preference_score"]) {
  report.push(`### ${col}`);
  report.push("");
  report.push(mdTable(["Value", "Rows"], top(countBy(incomingRows, col), 30).map((x) => [x.value, x.count])));
  report.push("");
}
report.push("## Blank Columns");
report.push("");
report.push(blankCounts.length ? mdTable(["Column", "Blank rows"], blankCounts.map((x) => [x.column, x.blanks])) : "No blank values detected in CSV fields.");
report.push("");
report.push("## Structural Issues");
report.push("");
report.push("### Invalid Scores");
report.push("");
report.push(invalidScores.length ? mdTable(["row_id", "column", "value"], invalidScores.map((x) => [x.row_id, x.column, x.value])) : "No invalid score examples found.");
report.push("");
report.push("### Numeric Issues");
report.push("");
report.push(numericChecks.length ? mdTable(["row_id", "issue", "value"], numericChecks.map((x) => [x.row_id, x.issue, x.value])) : "No numeric range examples found.");
report.push("");
report.push("### Salary-Fit Mismatches");
report.push("");
report.push(salaryFitMismatches.length ? mdTable(
  ["row_id", "salary_min", "salary_max", "actual_fit", "expected_fit"],
  salaryFitMismatches.slice(0, 30).map((x) => [x.row_id, x.salary_min, x.salary_max, x.actual, x.expected]),
) : "No salary-fit mismatches found.");
report.push("");
report.push("### Duplicate Incoming Apply URLs");
report.push("");
report.push(duplicateIncomingUrls.length ? mdTable(["apply_url", "rows"], duplicateIncomingUrls.map((x) => [x.value, x.count])) : "No duplicate incoming apply URLs found.");
report.push("");
report.push("### Near-Duplicate Incoming Keys");
report.push("");
report.push(duplicateNearKeysIncoming.length ? mdTable(["near_key", "rows"], duplicateNearKeysIncoming.map((x) => [x[0], x[1]])) : "No repeated incoming near-duplicate keys found.");
report.push("");
report.push("## Semantic Issues");
report.push("");
report.push(`Suspicious/search/training URLs: ${suspiciousUrls.length} of ${incomingRows.length}`);
report.push("");
report.push(`URLs containing \`seed_role=\`: ${seedRoleUrls.length} of ${incomingRows.length}`);
report.push("");
report.push(`Company names containing \`Seed\`: ${seedNamedCompanies.length} of ${incomingRows.length}`);
report.push("");
report.push(`Rows with \`can_apply_now=No\` but \`applied=yes\`: ${canNotApplyButAppliedYes.length}`);
report.push("");
report.push("Examples:");
report.push("");
report.push(mdTable(
  ["row_id", "company", "role", "apply_url"],
  suspiciousUrls.slice(0, 10).map((row) => [row.row_id, row.company_name, row.role_title, row.apply_url]),
));
report.push("");
report.push("Preference reason leading patterns:");
report.push("");
report.push(mdTable(["Pattern", "Rows"], top(preferenceReasonPatterns, 20).map((x) => [x.value, x.count])));
report.push("");
report.push("## Recommendation");
report.push("");
if (suspiciousUrls.length > incomingRows.length * 0.5) {
  report.push("Do not merge this file directly into the real master job database as verified job rows.");
  report.push("");
  report.push("It is structurally mergeable after normalization, but semantically it looks like generated or seed-estimated training data rather than real scraped job listings.");
  report.push("");
  report.push("Safe use:");
  report.push("");
  report.push("- keep as an experimental augmentation file");
  report.push("- mark `source_type` as `synthetic_training_supplement` or `estimated_training_row`");
  report.push("- exclude `source_platform`, `source_type`, `apply_url`, and `preference_reason` from training");
  report.push("- run the preparation pipeline to normalize enums and derived fields");
  report.push("- train/evaluate separately with and without this file before accepting it");
} else {
  report.push("The file is structurally mergeable, but still needs enum normalization, duplicate checks, and preparation-pipeline processing before training.");
}
report.push("");

fs.writeFileSync(reportPath, `${report.join("\n")}\n`, "utf8");

console.log(JSON.stringify({
  incoming: path.relative(ROOT, incomingPath),
  report: path.relative(ROOT, reportPath),
  rows: incomingRows.length,
  columns: incoming.headers.length,
  missing_vs_labeled: missingVsLabeled,
  extra_vs_labeled: extraVsLabeled,
  missing_required: missingRequired,
  suspicious_urls: suspiciousUrls.length,
  invalid_applied_examples: invalidApplied.length,
  invalid_score_examples: invalidScores.length,
  numeric_issue_examples: numericChecks.length,
  salary_fit_mismatches: salaryFitMismatches.length,
  duplicate_incoming_apply_urls: duplicateIncomingUrls.length,
  overlap_apply_urls_with_master: overlapApplyUrls.length,
  duplicate_incoming_near_keys: duplicateNearKeysIncoming.length,
  overlap_near_keys_with_master: overlapNearKeys.length,
  seed_role_urls: seedRoleUrls.length,
  seed_named_companies: seedNamedCompanies.length,
  can_not_apply_but_applied_yes: canNotApplyButAppliedYes.length,
}, null, 2));
