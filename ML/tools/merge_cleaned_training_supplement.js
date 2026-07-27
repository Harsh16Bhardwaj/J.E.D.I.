const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const MASTER_PATH = path.join(ROOT, "data", "jedi_master_labeled.csv");
const PREPARED_PATH = path.join(ROOT, "data", "jedi_master_prepared.csv");
const SUPPLEMENT_PATH = path.join(ROOT, "data", "jedi_360_balanced_more_jobs_training_supplement_cleaned_2026-06-29.csv");
const BACKUP_DIR = path.join(ROOT, "data", "backups", "2026-06-29_before_360_merge");
const REPORT_PATH = path.join(ROOT, "docs", "merged_dataset_snapshot_2026-06-29.md");

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
  return "\ufeff" + [
    headers.map(csvEscape).join(","),
    ...rows.map((row) => headers.map((h) => csvEscape(row[h])).join(",")),
  ].join("\r\n") + "\r\n";
}

function readCsv(filePath) {
  return parseCsv(fs.readFileSync(filePath, "utf8"));
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

const master = readCsv(MASTER_PATH);
const supplement = readCsv(SUPPLEMENT_PATH);

const masterHeader = master.headers.join("\u0001");
const supplementHeader = supplement.headers.join("\u0001");
if (masterHeader !== supplementHeader) {
  throw new Error("Supplement schema does not exactly match master labeled schema.");
}

const masterIds = new Set(master.rows.map((row) => String(row.row_id)));
const duplicateIds = supplement.rows.filter((row) => masterIds.has(String(row.row_id)));
if (duplicateIds.length) {
  throw new Error(`Duplicate row_id values found: ${duplicateIds.slice(0, 10).map((row) => row.row_id).join(", ")}`);
}

const beforeRows = master.rows.length;
const supplementRows = supplement.rows.map((row) => ({
  ...row,
  source_type: "curated_training_row",
}));

const mergedRows = [...master.rows, ...supplementRows].sort((a, b) => Number(a.row_id) - Number(b.row_id));

fs.mkdirSync(BACKUP_DIR, { recursive: true });
fs.copyFileSync(MASTER_PATH, path.join(BACKUP_DIR, "jedi_master_labeled.csv"));
if (fs.existsSync(PREPARED_PATH)) {
  fs.copyFileSync(PREPARED_PATH, path.join(BACKUP_DIR, "jedi_master_prepared.csv"));
}

fs.writeFileSync(MASTER_PATH, toCsv(mergedRows, master.headers), "utf8");

const report = [];
report.push("# Merged Dataset Snapshot");
report.push("");
report.push("Date: 2026-06-29");
report.push("");
report.push("## Merge");
report.push("");
report.push(mdTable(
  ["Item", "Value"],
  [
    ["Master rows before", beforeRows],
    ["Supplement rows added", supplement.rows.length],
    ["Master rows after", mergedRows.length],
    ["Supplement source_type after merge", "curated_training_row"],
    ["Backup directory", path.relative(ROOT, BACKUP_DIR).replace(/\\/g, "/")],
  ],
));
report.push("");
report.push("## Applied Distribution");
report.push("");
report.push(mdTable(["applied", "rows"], countBy(mergedRows, "applied")));
report.push("");
report.push("## Source Type Distribution");
report.push("");
report.push(mdTable(["source_type", "rows"], countBy(mergedRows, "source_type")));
report.push("");
report.push("## Salary Fit Distribution");
report.push("");
report.push(mdTable(["salary_profile_fit_score", "rows"], countBy(mergedRows, "salary_profile_fit_score")));
report.push("");
report.push("## Seniority Distribution");
report.push("");
report.push(mdTable(["seniority", "rows"], countBy(mergedRows, "seniority").slice(0, 20)));
report.push("");
report.push("## Role Family Distribution");
report.push("");
report.push(mdTable(["role_family", "rows"], countBy(mergedRows, "role_family").slice(0, 20)));
report.push("");
fs.writeFileSync(REPORT_PATH, `${report.join("\n")}\n`, "utf8");

console.log(JSON.stringify({
  master: path.relative(ROOT, MASTER_PATH),
  supplement: path.relative(ROOT, SUPPLEMENT_PATH),
  report: path.relative(ROOT, REPORT_PATH),
  backup_dir: path.relative(ROOT, BACKUP_DIR),
  before_rows: beforeRows,
  added_rows: supplement.rows.length,
  after_rows: mergedRows.length,
}, null, 2));
