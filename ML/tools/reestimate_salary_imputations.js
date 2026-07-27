const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const TARGET_MIN = 1200000;
const TARGET_MAX = 1500000;

const INPUT_FILES = [
  path.join(ROOT, "data", "jedi_master_labeled.csv"),
  path.join(ROOT, "data", "jedi_master_prepared.csv"),
];

const AUDIT_PATH = path.join(ROOT, "data", "jedi_salary_reestimate_audit_2026-06-29.csv");
const SCORE_AUDIT_PATH = path.join(ROOT, "data", "jedi_salary_score_rebucket_audit_2026-06-29.csv");

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
  return rows
    .filter((r) => r.length > 1 || (r.length === 1 && r[0] !== ""))
    .map((r) => Object.fromEntries(headers.map((h, idx) => [h, r[idx] ?? ""])));
}

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  if (/[",\r\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return `"${text}"`;
}

function toCsv(rows, headers) {
  return "\ufeff" + [
    headers.map(csvEscape).join(","),
    ...rows.map((row) => headers.map((h) => csvEscape(row[h])).join(",")),
  ].join("\r\n") + "\r\n";
}

function stableHash(text) {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function rand01(row, salt = "") {
  const key = `${row.row_id || ""}|${row.company_name || ""}|${row.role_title || ""}|${salt}`;
  return stableHash(key) / 0xffffffff;
}

function lower(value) {
  return String(value || "").toLowerCase();
}

function number(value, fallback = 0) {
  const n = Number(String(value || "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : fallback;
}

function includesAny(text, terms) {
  return terms.some((term) => text.includes(term));
}

function inferSeniority(row) {
  const direct = lower(row.seniority_standard || row.seniority);
  const title = lower(row.role_title);
  const text = `${direct} ${title}`;
  if (includesAny(text, ["principal"])) return "principal";
  if (includesAny(text, ["staff"])) return "staff";
  if (includesAny(text, ["lead", "manager"])) return "lead";
  if (includesAny(text, ["senior", "sr. ", "sr "])) return "senior";
  if (includesAny(text, ["sde ii", "software engineer ii", "mid", "2+", "3+"])) return "mid";
  if (includesAny(text, ["early_mid", "early-mid"])) return "early_mid";
  if (includesAny(text, ["sde i", "sde-1", "sde 1", "software engineer i", "new grad"])) return "entry_level";
  if (includesAny(text, ["junior", "jr. ", "jr "])) return "junior";
  if (includesAny(text, ["intern", "internship", "trainee"])) return "intern";
  if (includesAny(text, ["fresher", "entry"])) return "entry_level";
  return direct || "unknown";
}

function inferRoleFamily(row) {
  const direct = lower(row.role_family_standard || row.role_family);
  const text = `${direct} ${lower(row.role_title)} ${lower(row.skills_or_requirements)}`;
  if (includesAny(text, ["qa", "quality assurance", "testing", "test automation"])) return "qa_testing";
  if (includesAny(text, ["frontend", "front-end", "react", "angular", "vue"])) return "frontend";
  if (includesAny(text, ["backend", "back-end", "api", "node", "java", "python"])) return "backend";
  if (includesAny(text, ["fullstack", "full-stack", "full stack"])) return "fullstack";
  if (includesAny(text, ["machine learning", "ml", "ai", "llm", "genai", "data annotation"])) return "ml_ai";
  if (includesAny(text, ["data engineer", "etl", "data pipeline", "warehouse"])) return "data_engineering";
  if (includesAny(text, ["data scientist", "analytics"])) return "data_science";
  if (includesAny(text, ["devops", "cloud", "platform", "sre"])) return "devops_cloud";
  return direct || "other";
}

function inferWorkMode(row) {
  const text = `${lower(row.work_mode_standard || row.work_mode)} ${lower(row.location)}`;
  if (includesAny(text, ["onsite", "on-site", "in office", "office"])) return "onsite";
  if (includesAny(text, ["hybrid"])) return "hybrid";
  if (includesAny(text, ["remote"])) return "remote";
  return lower(row.work_mode_standard || row.work_mode) || "unknown";
}

function inferCity(row) {
  const text = `${lower(row.city_standard)} ${lower(row.location)}`;
  if (includesAny(text, ["bengaluru", "bangalore"])) return "bengaluru";
  if (includesAny(text, ["gurgaon", "gurugram", "noida", "delhi", "faridabad"])) return "delhi_ncr";
  if (includesAny(text, ["hyderabad"])) return "hyderabad";
  if (includesAny(text, ["pune"])) return "pune";
  if (includesAny(text, ["mumbai"])) return "mumbai";
  if (includesAny(text, ["chennai"])) return "chennai";
  return lower(row.city_standard) || "unknown";
}

function salaryFitScore(midpoint) {
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

function roundLpa(value) {
  return Math.max(180000, Math.round(value / 50000) * 50000);
}

function estimateSalary(row) {
  const seniority = inferSeniority(row);
  const family = inferRoleFamily(row);
  const workMode = inferWorkMode(row);
  const city = inferCity(row);
  const companyScore = number(row.company_match_score, 3);
  const expMin = number(row.experience_min_years, 0);
  const text = `${lower(row.role_title)} ${lower(row.role_family)} ${lower(row.skills_or_requirements)} ${lower(row.company_name)}`;

  const premiumStack = includesAny(text, [
    "llm", "genai", "generative ai", "agentic", "machine learning", "ai platform",
    "backend", "distributed", "microservices", "cloud", "data pipeline", "data engineering",
    "react", "node", "python", "java", "kubernetes", "platform",
  ]);
  const genericStack = includesAny(text, [
    "qa", "testing", "manual", "support", "operations", "program management", "cvat",
    "annotation", "wordpress", "html", "css", "basic", "customer", "content",
  ]);

  let minLpa;
  let maxLpa;
  let reason = `${seniority}/${family}`;
  const r = rand01(row, "salary");
  const jitter = (rand01(row, "jitter") - 0.5) * 1.2;

  if (["principal", "staff"].includes(seniority)) {
    minLpa = 35 + jitter;
    maxLpa = 50 + r * 12;
    reason += "|staff_principal";
  } else if (seniority === "lead") {
    minLpa = 28 + jitter;
    maxLpa = 42 + r * 8;
    reason += "|lead";
  } else if (seniority === "senior") {
    minLpa = 20 + jitter;
    maxLpa = 32 + r * 10;
    reason += "|senior_20ish";
  } else if (["mid", "early_mid"].includes(seniority) || expMin >= 2) {
    minLpa = 12 + jitter;
    maxLpa = 20 + r * 10;
    reason += "|mid";
  } else if (["entry_level", "new_grad", "sde_1", "junior"].includes(seniority)) {
    if (companyScore >= 5 && premiumStack) {
      minLpa = 12 + jitter;
      maxLpa = 20 + r * 5;
      reason += "|premium_entry";
    } else if (companyScore >= 4 || premiumStack) {
      minLpa = 8 + jitter;
      maxLpa = 14 + r * 5;
      reason += "|good_entry";
    } else {
      minLpa = 5 + jitter;
      maxLpa = 9 + r * 4;
      reason += "|generic_entry";
    }
  } else if (seniority === "intern") {
    if (companyScore >= 4 && premiumStack) {
      minLpa = 5 + jitter;
      maxLpa = 10 + r * 2;
      reason += "|premium_intern";
    } else {
      minLpa = 3 + jitter;
      maxLpa = 6 + r * 2;
      reason += "|generic_intern";
    }
  } else {
    if (premiumStack && companyScore >= 4) {
      minLpa = 10 + jitter;
      maxLpa = 18 + r * 5;
      reason += "|unknown_premium";
    } else {
      minLpa = 6 + jitter;
      maxLpa = 12 + r * 4;
      reason += "|unknown_generic";
    }
  }

  if (genericStack && !["senior", "lead", "staff", "principal"].includes(seniority)) {
    minLpa -= 2;
    maxLpa -= 3;
    reason += "|generic_stack_lowered";
  }

  if (workMode === "onsite") {
    minLpa += 1;
    maxLpa += 1.5;
    reason += "|onsite_bump";
  } else if (workMode === "hybrid") {
    minLpa += 0.5;
    maxLpa += 0.75;
    reason += "|hybrid_bump";
  } else if (workMode === "remote" && ["intern", "entry_level", "junior", "new_grad", "sde_1"].includes(seniority)) {
    minLpa -= 0.5;
    maxLpa -= 0.75;
    reason += "|remote_early_discount";
  }

  if (["bengaluru", "delhi_ncr", "hyderabad"].includes(city) && !["senior", "lead", "staff", "principal"].includes(seniority)) {
    minLpa += 0.5;
    maxLpa += 0.75;
    reason += "|tier1_bump";
  }

  // Force some realistic low-bracket samples among generic early-career rows.
  if (
    ["intern", "entry_level", "junior", "new_grad", "sde_1"].includes(seniority) &&
    (genericStack || companyScore <= 3) &&
    rand01(row, "low_bracket") < 0.28
  ) {
    minLpa = 4 + rand01(row, "low_min") * 0.8;
    maxLpa = 5.5 + rand01(row, "low_max") * 1.0;
    reason += "|forced_4_6_low_bracket";
  }

  minLpa = Math.max(1.8, minLpa);
  maxLpa = Math.max(minLpa + 1.5, maxLpa);

  const salaryMin = roundLpa(minLpa * 100000);
  const salaryMax = roundLpa(maxLpa * 100000);
  const midpoint = Math.round((salaryMin + salaryMax) / 2);

  return {
    salaryMin,
    salaryMax,
    midpoint,
    fitScore: salaryFitScore(midpoint),
    reason,
  };
}

function updateFile(filePath, auditRows, scoreAuditRows) {
  const originalText = fs.readFileSync(filePath, "utf8");
  const parsedRowsRaw = (() => {
    const text = originalText.charCodeAt(0) === 0xfeff ? originalText.slice(1) : originalText;
    return parseCsv(text);
  })();

  const headerLine = (originalText.charCodeAt(0) === 0xfeff ? originalText.slice(1) : originalText).split(/\r?\n/)[0];
  const headers = (() => {
    const parsedHeader = [];
    let field = "";
    let inQuotes = false;
    const line = headerLine;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      const next = line[i + 1];
      if (inQuotes) {
        if (ch === '"' && next === '"') {
          field += '"';
          i++;
        } else if (ch === '"') {
          inQuotes = false;
        } else {
          field += ch;
        }
      } else if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        parsedHeader.push(field);
        field = "";
      } else {
        field += ch;
      }
    }
    parsedHeader.push(field);
    return parsedHeader;
  })();

  let changed = 0;
  for (const row of parsedRowsRaw) {
    const oldMin = number(row.salary_min);
    const oldMax = number(row.salary_max);
    const wasMedianImputed = oldMin === TARGET_MIN && oldMax === TARGET_MAX;

    if (wasMedianImputed) {
      const estimate = estimateSalary(row);
      row.salary_min = String(estimate.salaryMin);
      row.salary_max = String(estimate.salaryMax);

      if ("salary_midpoint" in row) row.salary_midpoint = String(estimate.midpoint);
      if ("salary_available" in row) row.salary_available = "True";

      auditRows.push({
        file: path.relative(ROOT, filePath).replace(/\\/g, "/"),
        row_id: row.row_id,
        company_name: row.company_name,
        role_title: row.role_title,
        seniority: row.seniority_standard || row.seniority,
        role_family: row.role_family_standard || row.role_family,
        work_mode: row.work_mode_standard || row.work_mode,
        city: row.city_standard || row.location,
        old_salary_min: String(oldMin),
        old_salary_max: String(oldMax),
        old_salary_midpoint: String(Math.round((oldMin + oldMax) / 2)),
        new_salary_min: String(estimate.salaryMin),
        new_salary_max: String(estimate.salaryMax),
        new_salary_midpoint: String(estimate.midpoint),
        new_salary_profile_fit_score: String(estimate.fitScore),
        reason: estimate.reason,
      });
      changed++;
    }

    const finalMin = number(row.salary_min);
    const finalMax = number(row.salary_max);
    const midpoint = "salary_midpoint" in row
      ? number(row.salary_midpoint, Math.round((finalMin + finalMax) / 2))
      : Math.round((finalMin + finalMax) / 2);
    const newFitScore = salaryFitScore(midpoint);
    const oldFitScore = String(row.salary_profile_fit_score || "");

    if (oldFitScore !== String(newFitScore)) {
      scoreAuditRows.push({
        file: path.relative(ROOT, filePath).replace(/\\/g, "/"),
        row_id: row.row_id,
        company_name: row.company_name,
        role_title: row.role_title,
        salary_min: String(finalMin),
        salary_max: String(finalMax),
        salary_midpoint: String(midpoint),
        old_salary_profile_fit_score: oldFitScore,
        new_salary_profile_fit_score: String(newFitScore),
      });
      row.salary_profile_fit_score = String(newFitScore);
    }

    if ("salary_midpoint" in row) row.salary_midpoint = String(midpoint);
    if ("salary_available" in row) row.salary_available = finalMin > 0 || finalMax > 0 ? "True" : "False";
  }

  fs.writeFileSync(filePath, toCsv(parsedRowsRaw, headers), "utf8");
  return changed;
}

const auditRows = [];
const scoreAuditRows = [];
const changeCounts = [];
for (const file of INPUT_FILES) {
  const changed = updateFile(file, auditRows, scoreAuditRows);
  changeCounts.push({ file: path.relative(ROOT, file).replace(/\\/g, "/"), changed });
}

const auditHeaders = [
  "file",
  "row_id",
  "company_name",
  "role_title",
  "seniority",
  "role_family",
  "work_mode",
  "city",
  "old_salary_min",
  "old_salary_max",
  "old_salary_midpoint",
  "new_salary_min",
  "new_salary_max",
  "new_salary_midpoint",
  "new_salary_profile_fit_score",
  "reason",
];
if (auditRows.length > 0 || !fs.existsSync(AUDIT_PATH)) {
  fs.writeFileSync(AUDIT_PATH, toCsv(auditRows, auditHeaders), "utf8");
}

const scoreAuditHeaders = [
  "file",
  "row_id",
  "company_name",
  "role_title",
  "salary_min",
  "salary_max",
  "salary_midpoint",
  "old_salary_profile_fit_score",
  "new_salary_profile_fit_score",
];
if (scoreAuditRows.length > 0 || !fs.existsSync(SCORE_AUDIT_PATH)) {
  fs.writeFileSync(SCORE_AUDIT_PATH, toCsv(scoreAuditRows, scoreAuditHeaders), "utf8");
}

console.log(JSON.stringify({
  changeCounts,
  auditPath: path.relative(ROOT, AUDIT_PATH),
  auditRows: auditRows.length,
  scoreAuditPath: path.relative(ROOT, SCORE_AUDIT_PATH),
  scoreAuditRows: scoreAuditRows.length,
}, null, 2));
