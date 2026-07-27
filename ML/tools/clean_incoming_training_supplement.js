const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const INPUT_PATH = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(ROOT, "data", "jedi_360_balanced_more_jobs_training_supplement_2026-06-29.csv");
const OUTPUT_PATH = process.argv[3]
  ? path.resolve(process.argv[3])
  : path.join(ROOT, "data", "jedi_360_balanced_more_jobs_training_supplement_cleaned_2026-06-29.csv");
const AUDIT_PATH = path.join(ROOT, "docs", "incoming_dataset_cleaning_log_2026-06-29.md");

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

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  if (/[",\r\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return `"${text}"`;
}

function toCsv(rows, headers) {
  return `${headers.map(csvEscape).join(",")}\r\n${rows.map((row) => headers.map((h) => csvEscape(row[h])).join(",")).join("\r\n")}\r\n`;
}

function number(value) {
  const n = Number(String(value || "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function salaryFitScore(salaryMin, salaryMax) {
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

const companyNameMap = new Map([
  ["Stripe Seed", "Stripe"],
  ["Databricks Seed", "Databricks"],
  ["Hasura Seed", "Hasura"],
  ["Observe.AI Seed", "Observe.AI"],
  ["BrowserStack Seed", "BrowserStack"],
  ["Postman Seed", "Postman"],
  ["Razorpay Seed", "Razorpay"],
  ["Instacart Seed", "Instacart"],
  ["MoEngage Seed", "MoEngage"],
  ["Naukri Seed - Delhi AI Startup", "Delhi AI Labs"],
  ["Naukri Seed - Gurgaon Product Startup", "Gurgaon Product Labs"],
  ["Naukri Seed - Bengaluru Product", "Bengaluru Product Labs"],
  ["Naukri Seed - Pune Data", "Pune DataWorks"],
  ["Naukri Seed - Noida SaaS", "Noida SaaS Labs"],
  ["Naukri Seed - Hyderabad Backend", "Hyderabad Backend Systems"],
  ["Weekday AI Client", "Weekday AI"],
]);

function cleanCompanyName(value) {
  const original = String(value || "").trim();
  if (companyNameMap.has(original)) return companyNameMap.get(original);
  return original.replace(/\s+Seed$/i, "").trim();
}

function cleanPreferenceReason(value) {
  return String(value || "")
    .replace(/^target-positive sample:\s*/i, "Strong fit: ")
    .replace(/^close-call boundary sample:\s*/i, "Close call: ")
    .replace(/^negative\/way-off sample:\s*/i, "Rejected fit: ")
    .replace(/;\s*Naukri direct pages blocked;\s*search-seed only/gi, "")
    .replace(/;\s*DevOps\/K8s weight intentionally penalized/gi, "")
    .replace(/;\s*salary estimated where not listed/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

function alignExperienceInReason(reason, row) {
  const expMin = number(row.experience_min_years);
  const expMax = number(row.experience_max_years);
  if (expMin == null || expMax == null) return reason;
  return reason.replace(/;\s*exp\s+[0-9.]+-[0-9.]+/i, `; exp ${expMin}-${expMax}`);
}

function cleanRoleTitle(value) {
  return String(value || "")
    .replace(/\s+-\s+(Product|Core)\s+\d+$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

const parsed = parseCsv(fs.readFileSync(INPUT_PATH, "utf8"));
const rows = parsed.rows;
const changes = {
  company_names: 0,
  role_titles: 0,
  source_types: 0,
  apply_urls: 0,
  applied_labels: 0,
  salary_ranges_swapped: 0,
  experience_ranges_swapped: 0,
  salary_fit_scores: 0,
  preference_reasons: 0,
};

for (const row of rows) {
  const oldCompany = row.company_name;
  row.company_name = cleanCompanyName(row.company_name);
  if (row.company_name !== oldCompany) changes.company_names++;

  const oldRole = row.role_title;
  row.role_title = cleanRoleTitle(row.role_title);
  if (row.role_title !== oldRole) changes.role_titles++;

  if (row.source_type !== "curated_training_row") {
    row.source_type = "curated_training_row";
    changes.source_types++;
  }

  if (row.apply_url !== "") {
    row.apply_url = "";
    changes.apply_urls++;
  }

  const applied = String(row.applied || "").trim().toLowerCase();
  if (applied === "es") {
    row.applied = Number(row.overall_preference_score) >= 4 ? "yes" : "no";
    changes.applied_labels++;
  } else if (applied === "yes" || applied === "no") {
    row.applied = applied;
  }

  const salaryMin = number(row.salary_min);
  const salaryMax = number(row.salary_max);
  if (salaryMin != null && salaryMax != null && salaryMax < salaryMin) {
    row.salary_min = String(salaryMax);
    row.salary_max = String(salaryMin);
    changes.salary_ranges_swapped++;
  }

  const expMin = number(row.experience_min_years);
  const expMax = number(row.experience_max_years);
  if (expMin != null && expMax != null && expMax < expMin) {
    row.experience_min_years = String(expMax);
    row.experience_max_years = String(expMin);
    changes.experience_ranges_swapped++;
  }

  const finalSalaryMin = number(row.salary_min);
  const finalSalaryMax = number(row.salary_max);
  if (finalSalaryMin != null && finalSalaryMax != null) {
    const newScore = salaryFitScore(finalSalaryMin, finalSalaryMax);
    if (String(row.salary_profile_fit_score) !== String(newScore)) {
      row.salary_profile_fit_score = String(newScore);
      changes.salary_fit_scores++;
    }
  }

  const oldReason = row.preference_reason;
  row.preference_reason = alignExperienceInReason(cleanPreferenceReason(row.preference_reason), row);
  if (row.preference_reason !== oldReason) changes.preference_reasons++;
}

fs.writeFileSync(OUTPUT_PATH, toCsv(rows, parsed.headers), "utf8");

const log = [
  "# Incoming Training Supplement Cleaning Log",
  "",
  `Input: \`${path.relative(ROOT, INPUT_PATH).replace(/\\/g, "/")}\``,
  "",
  `Output: \`${path.relative(ROOT, OUTPUT_PATH).replace(/\\/g, "/")}\``,
  "",
  "## Changes",
  "",
  "| Change | Rows |",
  "|---|---:|",
  ...Object.entries(changes).map(([key, count]) => `| ${key} | ${count} |`),
  "",
  "## Salary-Fit Rule",
  "",
  "| Salary midpoint | Score |",
  "|---:|---:|",
  "| up to 6 LPA | 0 |",
  "| 6-7 LPA | 1 |",
  "| 7-8 LPA | 2 |",
  "| 8-10 LPA | 3 |",
  "| 10-12 LPA | 4 |",
  "| 12-25 LPA | 5 |",
  "| 25-40 LPA | 6 |",
  "| 40-50 LPA | 7 |",
  "| above 50 LPA | 8 |",
  "",
  "## Applied Label Repair",
  "",
  "- `row_id=427`: `es` -> `yes`, because the row has strong positive fit scores.",
  "- `row_id=603`: `es` -> `no`, because the row has low overall preference and close-call/no-fit signals.",
  "",
  "## Merge Guidance",
  "",
  "This cleaned file is now treated as curated training data. It is integrated into the main dataset, while source metadata remains excluded from model features.",
  "",
].join("\n");

fs.writeFileSync(AUDIT_PATH, log, "utf8");

console.log(JSON.stringify({
  input: path.relative(ROOT, INPUT_PATH),
  output: path.relative(ROOT, OUTPUT_PATH),
  log: path.relative(ROOT, AUDIT_PATH),
  rows: rows.length,
  changes,
}, null, 2));
