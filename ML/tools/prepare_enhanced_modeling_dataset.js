const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const INPUT_PATH = path.join(ROOT, "data", "jedi_master_prepared.csv");
const OUTPUT_PATH = path.join(ROOT, "jedi_modeling_enhanced_dataset.csv");
const CORR_PATH = path.join(ROOT, "data", "jedi_enhanced_feature_correlation_report.csv");
const DROP_PATH = path.join(ROOT, "data", "jedi_enhanced_low_correlation_drop_candidates.csv");
const EXP_AUDIT_PATH = path.join(ROOT, "data", "jedi_experience_fit_fix_audit.csv");
const SUMMARY_PATH = path.join(ROOT, "docs", "enhanced_dataset_preparation_report.md");
const ERROR_PRED_PATH = path.join(ROOT, "data", "jedi_xgboost_stacked_oof_predictions.csv");
const ERROR_AUDIT_PATH = path.join(ROOT, "data", "jedi_xgboost_error_audit.csv");
const ERROR_REPORT_PATH = path.join(ROOT, "docs", "xgboost_error_audit_report.md");

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
    if (ch === '"') inQuotes = true;
    else if (ch === ",") {
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
  return "\ufeff" + [
    headers.map(csvEscape).join(","),
    ...rows.map((row) => headers.map((h) => csvEscape(row[h])).join(",")),
  ].join("\r\n") + "\r\n";
}

function lower(value) {
  return String(value || "").trim().toLowerCase();
}

function number(value, fallback = null) {
  const n = Number(String(value || "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : fallback;
}

function bool(value) {
  return value ? "1" : "0";
}

function includesAny(text, terms) {
  return terms.some((term) => text.includes(term));
}

function normalizeExperienceFit(row) {
  const original = String(row.experience_profile_fit_score || "").trim();
  const existing = number(original, null);
  if (existing !== null) {
    return {
      value: Math.max(0, Math.min(5, Math.round(existing))),
      imputed: false,
      reason: "existing_numeric",
    };
  }

  const text = lower(`${row.seniority} ${row.seniority_standard} ${row.role_title}`);
  const seniority = lower(row.seniority_standard);
  const expMin = number(row.experience_min_years, null);

  if (["principal", "staff", "lead"].includes(seniority) || includesAny(text, ["principal", "staff", "lead"])) {
    return { value: 0, imputed: true, reason: "lead_staff_principal" };
  }
  if (seniority === "senior" || includesAny(text, ["senior", "sr. ", "sr "])) {
    return { value: 1, imputed: true, reason: "senior" };
  }

  if (expMin !== null) {
    if (expMin <= 1) return { value: 5, imputed: true, reason: "exp_min_0_1" };
    if (expMin <= 2) return { value: 4, imputed: true, reason: "exp_min_2" };
    if (expMin <= 3) return { value: 3, imputed: true, reason: "exp_min_3" };
    if (expMin <= 4) return { value: 2, imputed: true, reason: "exp_min_4" };
    if (expMin <= 6) return { value: 1, imputed: true, reason: "exp_min_5_6" };
    return { value: 0, imputed: true, reason: "exp_min_7_plus" };
  }

  if (["intern", "new_grad", "entry_level"].includes(seniority) || includesAny(text, ["intern", "new grad", "graduate", "entry", "sde i", "software engineer i"])) {
    return { value: 5, imputed: true, reason: "early_career_seniority" };
  }
  if (seniority === "junior" || includesAny(text, ["junior", "jr. ", "jr "])) {
    return { value: 4, imputed: true, reason: "junior_seniority" };
  }
  if (seniority === "early_mid") {
    return { value: 3, imputed: true, reason: "early_mid_seniority" };
  }
  if (seniority === "mid" || includesAny(text, ["mid", "sde ii", "software engineer ii"])) {
    return { value: 2, imputed: true, reason: "mid_seniority" };
  }
  return { value: 2, imputed: true, reason: "unknown_experience" };
}

function explicitFeatures(row) {
  const text = lower([
    row.role_title,
    row.role_family,
    row.role_family_standard,
    row.seniority,
    row.seniority_standard,
    row.location,
    row.work_mode,
    row.skills_or_requirements,
    row.skills_array,
  ].join(" "));
  const role = lower(row.role_family_standard);
  const seniority = lower(row.seniority_standard);
  const locBucket = lower(row.location_bucket);
  const workMode = lower(row.work_mode_standard);
  const expFit = number(row.experience_profile_fit_score, 0);
  const seniorityFit = number(row.seniority_profile_fit_score, 0);
  const locationFit = number(row.location_profile_fit_score, 0);
  const salaryFit = number(row.salary_profile_fit_score, 0);
  const salaryMid = number(row.salary_midpoint, 0);

  const isSeniorOrAbove = ["senior", "lead", "staff", "principal"].includes(seniority);
  const isLeadOrAbove = ["lead", "staff", "principal"].includes(seniority);
  const isInternOrNewGrad = ["intern", "new_grad"].includes(seniority);
  const isEntryOrJunior = ["entry_level", "junior"].includes(seniority);
  const isEarlyCareer = isInternOrNewGrad || isEntryOrJunior;
  const isTargetIndia = row.is_india === "True" || row.is_india === "1" || ["bengaluru", "delhi_ncr", "hyderabad", "pune", "mumbai", "chennai", "india_remote", "india_other"].includes(locBucket);
  const isBengaluruOrNcr = row.is_bengaluru === "True" || row.is_bengaluru === "1" || row.is_gurgaon_ncr === "True" || row.is_gurgaon_ncr === "1";
  const isTier1City = isBengaluruOrNcr || ["hyderabad", "pune", "mumbai", "chennai"].includes(locBucket);
  const isSupportAnnotation = includesAny(text, ["annotation", "cvat", "support", "customer support", "operations", "content moderation", "manual labeling"]);
  const isDevopsHeavy = role === "devops_cloud" || includesAny(text, ["devops", "sre", "kubernetes", "terraform", "helm", "prometheus", "incident response"]);
  const isSecurity = includesAny(text, ["security", "iam", "threat", "secure coding", "cyber"]);
  const isPlatformInfra = includesAny(text, ["platform", "infra", "infrastructure", "distributed systems", "reliability", "core infra"]);
  const isLLM = role === "ml_ai" || includesAny(text, ["llm", "rag", "genai", "generative ai", "agentic", "prompt engineering", "vector"]);
  const isBackendFullstack = role === "backend" || role === "fullstack";
  const isDataRole = ["data_engineering", "data_science", "analytics"].includes(role) || includesAny(text, ["data engineer", "etl", "pipeline", "spark", "airflow", "analytics"]);
  const isQa = role === "qa_testing" || includesAny(text, ["qa", "manual testing", "test automation"]);
  const isRemoteGlobal = locBucket === "global_remote" || includesAny(text, ["global remote", "worldwide", "anywhere"]);
  const isIndiaRemote = locBucket === "india_remote";
  const isRemote = workMode === "remote";

  return {
    feat_is_experience_mismatch: bool(expFit <= 2 || seniorityFit <= 2 || isSeniorOrAbove),
    feat_is_senior_or_above: bool(isSeniorOrAbove),
    feat_is_lead_staff_principal: bool(isLeadOrAbove),
    feat_is_early_career: bool(isEarlyCareer),
    feat_is_intern_or_new_grad: bool(isInternOrNewGrad),
    feat_is_entry_or_junior: bool(isEntryOrJunior),
    feat_is_mid_level: bool(["early_mid", "mid"].includes(seniority)),
    feat_is_backend_or_fullstack: bool(isBackendFullstack),
    feat_is_ml_ai: bool(role === "ml_ai"),
    feat_is_data_role: bool(isDataRole),
    feat_is_devops_cloud: bool(role === "devops_cloud"),
    feat_is_qa_testing: bool(isQa),
    feat_is_support_or_annotation: bool(isSupportAnnotation),
    feat_is_security_role: bool(isSecurity),
    feat_is_platform_infra: bool(isPlatformInfra),
    feat_is_llm_or_rag_role: bool(isLLM),
    feat_is_remote: bool(isRemote),
    feat_is_remote_global: bool(isRemoteGlobal),
    feat_is_india_remote: bool(isIndiaRemote),
    feat_is_india_target_location: bool(isTargetIndia),
    feat_is_bengaluru_or_ncr: bool(isBengaluruOrNcr),
    feat_is_tier1_city: bool(isTier1City),
    feat_is_location_mismatch: bool(locationFit <= 2 || isRemoteGlobal),
    feat_is_low_salary: bool(salaryFit <= 2 || salaryMid <= 800000),
    feat_is_mid_salary: bool(salaryFit >= 3 && salaryFit <= 5),
    feat_is_high_salary: bool(salaryFit >= 6),
    feat_salary_good_but_role_bad: bool(salaryFit >= 5 && (isSeniorOrAbove || isSupportAnnotation || isQa || isDevopsHeavy)),
    feat_low_salary_but_good_role: bool(salaryFit <= 2 && isEarlyCareer && (isBackendFullstack || isLLM || isDataRole)),
    feat_good_role_good_location: bool((isBackendFullstack || isLLM || isDataRole) && isTargetIndia && !isRemoteGlobal),
    feat_good_title_bad_experience: bool((isBackendFullstack || isLLM || isDataRole) && (isSeniorOrAbove || expFit <= 2)),
    feat_remote_early_career: bool(isRemote && isEarlyCareer),
    feat_onsite_or_hybrid_early_career: bool(["onsite", "hybrid"].includes(workMode) && isEarlyCareer),
    feat_bad_fit_combo: bool((isSeniorOrAbove || isRemoteGlobal || isSupportAnnotation || isQa || isDevopsHeavy) && expFit <= 2),
    feat_strong_fit_combo: bool(isEarlyCareer && (isBackendFullstack || isLLM || isDataRole) && isTargetIndia && expFit >= 4),
  };
}

function pearson(xs, ys) {
  const pairs = xs.map((x, i) => [Number(x), Number(ys[i])]).filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  if (pairs.length < 3) return 0;
  const meanX = pairs.reduce((s, [x]) => s + x, 0) / pairs.length;
  const meanY = pairs.reduce((s, [, y]) => s + y, 0) / pairs.length;
  let num = 0;
  let denX = 0;
  let denY = 0;
  for (const [x, y] of pairs) {
    const dx = x - meanX;
    const dy = y - meanY;
    num += dx * dy;
    denX += dx * dx;
    denY += dy * dy;
  }
  const den = Math.sqrt(denX * denY);
  return den === 0 ? 0 : num / den;
}

function countBy(rows, column) {
  const counts = new Map();
  for (const row of rows) {
    const key = String(row[column] || "(blank)");
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function mdTable(headers, rows) {
  return [
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.map((v) => String(v).replace(/\|/g, "\\|")).join(" | ")} |`),
  ].join("\n");
}

const parsed = parseCsv(fs.readFileSync(INPUT_PATH, "utf8"));
const rows = parsed.rows;
const expAuditRows = [];

const enhancedRows = rows.map((row) => {
  const out = { ...row };
  const originalExpFit = out.experience_profile_fit_score;
  const fixed = normalizeExperienceFit(out);
  out.experience_profile_fit_score_original = originalExpFit;
  out.experience_profile_fit_score = String(fixed.value);
  out.experience_profile_fit_imputed = fixed.imputed ? "1" : "0";
  out.experience_profile_fit_imputation_reason = fixed.reason;
  if (fixed.imputed) {
    expAuditRows.push({
      row_id: out.row_id,
      company_name: out.company_name,
      role_title: out.role_title,
      seniority: out.seniority,
      seniority_standard: out.seniority_standard,
      experience_min_years: out.experience_min_years,
      old_experience_profile_fit_score: originalExpFit,
      new_experience_profile_fit_score: fixed.value,
      reason: fixed.reason,
      applied: out.applied,
    });
  }
  Object.assign(out, explicitFeatures(out));
  out.enhanced_title_skill_text = [
    out.role_title,
    out.role_family,
    out.role_family_standard,
    out.seniority_standard,
    out.skills_or_requirements,
    out.skills_array,
  ].filter(Boolean).join(" | ");
  out.enhanced_context_text = [
    out.role_title,
    out.role_family,
    out.seniority,
    out.location,
    out.work_mode,
    out.employment_type,
    out.skills_or_requirements,
  ].filter(Boolean).join(" | ");
  return out;
});

const featureColumns = Object.keys(explicitFeatures(enhancedRows[0]));
const y = enhancedRows.map((row) => lower(row.applied) === "yes" ? 1 : 0);
const corrRows = featureColumns.map((column) => {
  const values = enhancedRows.map((row) => number(row[column], 0));
  const corr = pearson(values, y);
  const positiveRateWhenOneRows = enhancedRows.filter((row) => row[column] === "1");
  const positiveRateWhenZeroRows = enhancedRows.filter((row) => row[column] !== "1");
  const mean = (subset) => subset.length ? subset.reduce((s, row) => s + (lower(row.applied) === "yes" ? 1 : 0), 0) / subset.length : 0;
  return {
    feature: column,
    correlation_with_applied: corr.toFixed(6),
    abs_correlation: Math.abs(corr).toFixed(6),
    rows_with_feature: positiveRateWhenOneRows.length,
    positive_rate_when_1: mean(positiveRateWhenOneRows).toFixed(6),
    positive_rate_when_0: mean(positiveRateWhenZeroRows).toFixed(6),
  };
}).sort((a, b) => Number(b.abs_correlation) - Number(a.abs_correlation));

const lowCorrRows = [...corrRows].sort((a, b) => Number(a.abs_correlation) - Number(b.abs_correlation)).slice(0, 20);

const originalHeaders = parsed.headers;
const enhancedHeaders = [
  ...originalHeaders,
  "experience_profile_fit_score_original",
  "experience_profile_fit_imputed",
  "experience_profile_fit_imputation_reason",
  ...featureColumns,
  "enhanced_title_skill_text",
  "enhanced_context_text",
];

fs.writeFileSync(OUTPUT_PATH, toCsv(enhancedRows, enhancedHeaders), "utf8");
fs.writeFileSync(EXP_AUDIT_PATH, toCsv(expAuditRows, [
  "row_id",
  "company_name",
  "role_title",
  "seniority",
  "seniority_standard",
  "experience_min_years",
  "old_experience_profile_fit_score",
  "new_experience_profile_fit_score",
  "reason",
  "applied",
]), "utf8");
fs.writeFileSync(CORR_PATH, toCsv(corrRows, [
  "feature",
  "correlation_with_applied",
  "abs_correlation",
  "rows_with_feature",
  "positive_rate_when_1",
  "positive_rate_when_0",
]), "utf8");
fs.writeFileSync(DROP_PATH, toCsv(lowCorrRows, [
  "feature",
  "correlation_with_applied",
  "abs_correlation",
  "rows_with_feature",
  "positive_rate_when_1",
  "positive_rate_when_0",
]), "utf8");

function buildErrorAudit() {
  if (!fs.existsSync(ERROR_PRED_PATH)) return null;
  const predictions = parseCsv(fs.readFileSync(ERROR_PRED_PATH, "utf8")).rows;
  const sourceRowsById = new Map(enhancedRows.map((row) => [String(row.row_id), row]));
  const audit = [];
  for (const pred of predictions) {
    const source = sourceRowsById.get(String(pred.row_id)) || {};
    const actual = number(pred.actual_applied, 0);
    const stackedPred = number(pred.stacked_ridge_scores_xgboost_prediction, 0);
    const oraclePred = number(pred.oracle_true_scores_xgboost_prediction, 0);
    const stackedProb = number(pred.stacked_ridge_scores_xgboost_probability, 0);
    const oracleProb = number(pred.oracle_true_scores_xgboost_probability, 0);
    const isStackedError = actual !== stackedPred;
    const isOracleError = actual !== oraclePred;
    if (!isStackedError && !isOracleError) continue;
    const flags = explicitFeatures(source);
    const issueFlags = [];
    if (flags.feat_is_experience_mismatch === "1") issueFlags.push("experience_mismatch");
    if (flags.feat_is_senior_or_above === "1") issueFlags.push("senior_or_above");
    if (flags.feat_is_support_or_annotation === "1") issueFlags.push("support_or_annotation");
    if (flags.feat_is_qa_testing === "1") issueFlags.push("qa_testing");
    if (flags.feat_is_devops_cloud === "1") issueFlags.push("devops_cloud");
    if (flags.feat_is_remote_global === "1") issueFlags.push("remote_global");
    if (flags.feat_is_low_salary === "1") issueFlags.push("low_salary");
    if (flags.feat_salary_good_but_role_bad === "1") issueFlags.push("salary_good_but_role_bad");
    if (flags.feat_good_role_good_location === "1") issueFlags.push("good_role_good_location");
    if (flags.feat_good_title_bad_experience === "1") issueFlags.push("good_title_bad_experience");
    if (flags.feat_strong_fit_combo === "1") issueFlags.push("strong_fit_combo");
    const errorType = actual === 0 && stackedPred === 1 ? "false_positive" : actual === 1 && stackedPred === 0 ? "false_negative" : "oracle_only_error";
    const confidence = Math.abs(stackedProb - 0.5);
    let likelyIssue = "ambiguous_or_model_boundary";
    if (errorType === "false_positive" && issueFlags.includes("strong_fit_combo")) likelyIssue = "label_may_be_stricter_than_visible_features";
    if (errorType === "false_negative" && issueFlags.some((x) => ["experience_mismatch", "senior_or_above", "remote_global", "low_salary"].includes(x))) likelyIssue = "accepted_despite_visible_penalty";
    if (isOracleError) likelyIssue = "oracle_error_label_or_feature_contradiction";
    if (confidence > 0.35) likelyIssue = `high_confidence_${likelyIssue}`;
    audit.push({
      row_id: pred.row_id,
      company_name: pred.company_name,
      role_title: pred.role_title,
      role_family: pred.role_family,
      seniority: pred.seniority,
      location: pred.location,
      source_type: source.source_type || pred.source_type || "",
      actual_applied: actual,
      stacked_prediction: stackedPred,
      stacked_probability: stackedProb,
      oracle_prediction: oraclePred,
      oracle_probability: oracleProb,
      error_type: errorType,
      high_confidence_error: confidence > 0.35 ? "1" : "0",
      likely_issue: likelyIssue,
      issue_flags: issueFlags.join(";"),
      experience_fit_score: source.experience_profile_fit_score,
      overall_preference_score: source.overall_preference_score,
      preference_reason: source.preference_reason,
    });
  }
  fs.writeFileSync(ERROR_AUDIT_PATH, toCsv(audit, [
    "row_id",
    "company_name",
    "role_title",
    "role_family",
    "seniority",
    "location",
    "source_type",
    "actual_applied",
    "stacked_prediction",
    "stacked_probability",
    "oracle_prediction",
    "oracle_probability",
    "error_type",
    "high_confidence_error",
    "likely_issue",
    "issue_flags",
    "experience_fit_score",
    "overall_preference_score",
    "preference_reason",
  ]), "utf8");
  return audit;
}

const errorAudit = buildErrorAudit();

const summary = [];
summary.push("# Enhanced Dataset Preparation Report");
summary.push("");
summary.push("Date: 2026-06-29");
summary.push("");
summary.push("## Output");
summary.push("");
summary.push(mdTable(["Artifact", "Path"], [
  ["Enhanced root dataset", "jedi_modeling_enhanced_dataset.csv"],
  ["Experience fix audit", "data/jedi_experience_fit_fix_audit.csv"],
  ["Feature correlation report", "data/jedi_enhanced_feature_correlation_report.csv"],
  ["Low-correlation drop candidates", "data/jedi_enhanced_low_correlation_drop_candidates.csv"],
  ["Error audit", fs.existsSync(ERROR_AUDIT_PATH) ? "data/jedi_xgboost_error_audit.csv" : "not generated"],
]));
summary.push("");
summary.push("## Experience Fit Repair");
summary.push("");
summary.push(mdTable(["Metric", "Rows"], [
  ["Total rows", enhancedRows.length],
  ["Experience profile fit values imputed", expAuditRows.length],
  ["Remaining NA experience profile fit", enhancedRows.filter((row) => String(row.experience_profile_fit_score).toUpperCase() === "NA").length],
]));
summary.push("");
summary.push("### Imputation Reasons");
summary.push("");
summary.push(mdTable(["Reason", "Rows"], countBy(expAuditRows, "reason")));
summary.push("");
summary.push("## Strongest Explicit Features");
summary.push("");
summary.push(mdTable(["Feature", "corr", "abs_corr", "rows_with_feature", "positive_rate_when_1"], corrRows.slice(0, 15).map((row) => [
  row.feature,
  row.correlation_with_applied,
  row.abs_correlation,
  row.rows_with_feature,
  row.positive_rate_when_1,
])));
summary.push("");
summary.push("## Lowest-Correlation Explicit Features");
summary.push("");
summary.push(mdTable(["Feature", "corr", "abs_corr", "rows_with_feature"], lowCorrRows.map((row) => [
  row.feature,
  row.correlation_with_applied,
  row.abs_correlation,
  row.rows_with_feature,
])));
summary.push("");
if (errorAudit) {
  summary.push("## Error Audit From Previous XGBoost Run");
  summary.push("");
  summary.push(mdTable(["Metric", "Rows"], [
    ["Error rows audited", errorAudit.length],
    ["Stacked false positives", errorAudit.filter((row) => row.error_type === "false_positive").length],
    ["Stacked false negatives", errorAudit.filter((row) => row.error_type === "false_negative").length],
    ["Oracle/label contradiction rows", errorAudit.filter((row) => row.oracle_prediction !== row.actual_applied).length],
    ["High-confidence error rows", errorAudit.filter((row) => row.high_confidence_error === "1").length],
  ]));
  summary.push("");
  summary.push("### Likely Issue Buckets");
  summary.push("");
  summary.push(mdTable(["Likely issue", "Rows"], countBy(errorAudit, "likely_issue")));
  summary.push("");
}
summary.push("## Modeling Decision");
summary.push("");
summary.push("The enhanced dataset keeps all rows, fixes the experience target, adds explicit rule features, and leaves low-correlation dropping to the notebook so the drop decision is made inside each fold.");
summary.push("");

fs.writeFileSync(SUMMARY_PATH, `${summary.join("\n")}\n`, "utf8");

console.log(JSON.stringify({
  input: path.relative(ROOT, INPUT_PATH),
  output: path.relative(ROOT, OUTPUT_PATH),
  rows: enhancedRows.length,
  experience_imputed_rows: expAuditRows.length,
  explicit_features: featureColumns.length,
  correlation_report: path.relative(ROOT, CORR_PATH),
  drop_candidates: path.relative(ROOT, DROP_PATH),
  error_audit_rows: errorAudit ? errorAudit.length : 0,
  summary: path.relative(ROOT, SUMMARY_PATH),
}, null, 2));
