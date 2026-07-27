const DB_NAME = "jedi-screener-db";
const DB_VERSION = 2;
const STORE_NAME = "workspace";
const WORKSPACE_KEY = "active";
const ROW_CHUNK_SIZE = 250;
const REQUIRED_COLUMNS = [];
const LONG_FIELD_HINTS = [
  "description",
  "requirements",
  "responsibilities",
  "skills",
  "tech_stack",
  "raw_payload",
];

const state = {
  columns: [],
  rows: [],
  uploads: [],
  page: 1,
  pageSize: 50,
  mode: "table",
  search: "",
  appliedFilter: "",
  selectedReviewIndex: 0,
  contextColumnIndex: null,
  saveTimer: null,
};

const els = {
  csvInput: document.querySelector("#csvInput"),
  table: document.querySelector("#jobTable"),
  rowCount: document.querySelector("#rowCount"),
  columnCount: document.querySelector("#columnCount"),
  fileCount: document.querySelector("#fileCount"),
  saveStatus: document.querySelector("#saveStatus"),
  modeToggle: document.querySelector("#modeToggle"),
  clearButton: document.querySelector("#clearButton"),
  downloadButton: document.querySelector("#downloadButton"),
  addColumnButton: document.querySelector("#addColumnButton"),
  searchInput: document.querySelector("#searchInput"),
  appliedFilter: document.querySelector("#appliedFilter"),
  pageSize: document.querySelector("#pageSize"),
  prevPage: document.querySelector("#prevPage"),
  nextPage: document.querySelector("#nextPage"),
  pageInfo: document.querySelector("#pageInfo"),
  tableView: document.querySelector("#tableView"),
  reviewView: document.querySelector("#reviewView"),
  reviewList: document.querySelector("#reviewList"),
  reviewDetail: document.querySelector("#reviewDetail"),
  columnMenu: document.querySelector("#columnMenu"),
  addColumnRight: document.querySelector("#addColumnRight"),
  renameColumn: document.querySelector("#renameColumn"),
  fillUnknown: document.querySelector("#fillUnknown"),
  fillZero: document.querySelector("#fillZero"),
  fillCustom: document.querySelector("#fillCustom"),
  deleteColumn: document.querySelector("#deleteColumn"),
};

let db;

init();

async function init() {
  try {
    db = await openDb();
    const saved = await loadWorkspace();
  if (saved) {
    state.columns = saved.columns || [];
    state.rows = saved.rows || [];
    state.uploads = saved.uploads || [];
  }
} catch (error) {
  console.error(error);
  setSaveStatus("Storage unavailable", "is-error");
}
  alignRowsToColumns();
  bindEvents();
  render();
}

function bindEvents() {
  els.csvInput.addEventListener("change", handleCsvUpload);
  els.downloadButton.addEventListener("click", downloadCsv);
  els.addColumnButton.addEventListener("click", () => addColumn(state.columns.length));
  els.clearButton.addEventListener("click", clearWorkspace);
  els.modeToggle.addEventListener("click", toggleMode);
  els.searchInput.addEventListener("input", () => {
    state.search = els.searchInput.value.trim().toLowerCase();
    state.page = 1;
    render();
  });
  els.appliedFilter.addEventListener("change", () => {
    state.appliedFilter = els.appliedFilter.value;
    state.page = 1;
    render();
  });
  els.pageSize.addEventListener("change", () => {
    state.pageSize = Number(els.pageSize.value);
    state.page = 1;
    render();
  });
  els.prevPage.addEventListener("click", () => {
    state.page = Math.max(1, state.page - 1);
    render();
  });
  els.nextPage.addEventListener("click", () => {
    const total = Math.max(1, Math.ceil(getFilteredRows().length / state.pageSize));
    state.page = Math.min(total, state.page + 1);
    render();
  });
  els.addColumnRight.addEventListener("click", () => addColumn((state.contextColumnIndex || 0) + 1));
  els.renameColumn.addEventListener("click", renameContextColumn);
  els.fillUnknown.addEventListener("click", () => fillMissingInContextColumn("unknown"));
  els.fillZero.addEventListener("click", () => fillMissingInContextColumn("0"));
  els.fillCustom.addEventListener("click", fillMissingWithCustomValue);
  els.deleteColumn.addEventListener("click", deleteContextColumn);
  document.addEventListener("click", closeColumnMenu);
}

async function handleCsvUpload(event) {
  const files = [...event.target.files];
  if (!files.length) return;
  setSaveStatus("Reading files", "is-saving");

  for (const file of files) {
    try {
      const parsed = await parseInputFile(file);
      appendParsedRows(parsed, file.name);
    } catch (error) {
      console.error(error);
      alert(`Could not import ${file.name}: ${error.message}`);
    }
  }

  event.target.value = "";
  alignRowsToColumns();
  state.page = 1;
  scheduleSave();
  render();
}

async function parseInputFile(file) {
  const name = file.name.toLowerCase();
  if (name.endsWith(".xlsx")) {
    return parseXlsx(await file.arrayBuffer());
  }
  if (name.endsWith(".csv") || file.type.includes("csv") || file.type === "") {
    return parseCsv(await file.text());
  }
  throw new Error("Only .csv and .xlsx files are supported.");
}

function appendParsedRows(parsed, fileName) {
  if (!parsed.headers.length) return;
  const existingColumns = new Set(state.columns);
  for (const header of parsed.headers) {
    if (!existingColumns.has(header)) {
      state.columns.push(header);
      existingColumns.add(header);
    }
  }
  alignRowsToColumns();

  for (const parsedRow of parsed.rows) {
    const row = {};
    for (const column of state.columns) row[column] = "";
    for (const [key, value] of Object.entries(parsedRow)) row[key] = value;
    state.rows.push(row);
  }

  state.uploads.push({
    name: fileName,
    rows: parsed.rows.length,
    importedAt: new Date().toISOString(),
  });
}

function alignRowsToColumns() {
  for (const row of state.rows) {
    for (const column of state.columns) {
      if (!(column in row)) row[column] = "";
    }
  }
}

function render() {
  const filtered = getFilteredRows();
  const totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
  state.page = Math.min(state.page, totalPages);
  const start = (state.page - 1) * state.pageSize;
  const pageRows = filtered.slice(start, start + state.pageSize);

  els.rowCount.textContent = `${state.rows.length} rows`;
  els.columnCount.textContent = `${state.columns.length} columns`;
  els.fileCount.textContent = `${state.uploads.length} uploads`;
  els.pageInfo.textContent = `Page ${state.page} of ${totalPages}`;
  els.prevPage.disabled = state.page <= 1;
  els.nextPage.disabled = state.page >= totalPages;

  if (state.mode === "table") {
    els.tableView.classList.remove("is-hidden");
    els.reviewView.classList.add("is-hidden");
    els.modeToggle.textContent = "Review mode";
    renderTable(pageRows, start);
  } else {
    els.tableView.classList.add("is-hidden");
    els.reviewView.classList.remove("is-hidden");
    els.modeToggle.textContent = "Table mode";
    renderReview(filtered);
  }
}

function renderTable(pageRows, start) {
  els.table.innerHTML = "";
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headerRow.appendChild(makeHeader("#", -1, "row-number"));
  state.columns.forEach((column, index) => {
    headerRow.appendChild(makeHeader(column, index, columnClass(column)));
  });
  thead.appendChild(headerRow);

  const tbody = document.createElement("tbody");
  pageRows.forEach(({ row, originalIndex }, visibleIndex) => {
    const tr = document.createElement("tr");
    const rowNumber = document.createElement("td");
    rowNumber.className = "row-number";
    rowNumber.innerHTML = `<div class="cell">${start + visibleIndex + 1}</div>`;
    tr.appendChild(rowNumber);

    state.columns.forEach((column) => {
      const td = document.createElement("td");
      td.className = columnClass(column);
      if (isAppliedColumn(column)) {
        const select = document.createElement("select");
        select.className = "applied-select";
        ["no", "yes", ""].forEach((value) => {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = value ? value.toUpperCase() : "BLANK";
          select.appendChild(option);
        });
        select.value = normalizeAppliedValue(row[column]);
        select.addEventListener("change", () => updateCell(originalIndex, column, select.value));
        td.appendChild(select);
      } else {
        const cell = document.createElement("div");
        cell.className = "cell";
        cell.contentEditable = "true";
        cell.textContent = row[column] || "";
        td.addEventListener("click", (event) => {
          if (event.target === cell) return;
          focusEditableCell(cell);
        });
        cell.addEventListener("click", () => focusEditableCell(cell));
        cell.addEventListener("blur", () => updateCell(originalIndex, column, cell.textContent));
        td.appendChild(cell);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  els.table.append(thead, tbody);
}

function makeHeader(label, index, className) {
  const th = document.createElement("th");
  th.className = className;
  th.textContent = label;
  if (index >= 0) {
    th.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      state.contextColumnIndex = index;
      openColumnMenu(event.clientX, event.clientY);
    });
  }
  return th;
}

function renderReview(filtered) {
  els.reviewList.innerHTML = "";
  if (!filtered.length) {
    els.reviewDetail.innerHTML = `<p class="empty-state">No rows match the current filters.</p>`;
    return;
  }

  state.selectedReviewIndex = Math.min(state.selectedReviewIndex, filtered.length - 1);
  filtered.forEach(({ row }, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = index === state.selectedReviewIndex ? "is-active" : "";
    button.innerHTML = `
      <span class="review-title">${escapeHtml(pick(row, ["title_normalized", "title_raw", "Title", "title"]) || "Untitled role")}</span>
      <span class="review-meta">${escapeHtml(pick(row, ["company_name", "Company", "company"]) || "Unknown company")}</span>
      ${getAppliedColumn() ? `<span class="review-meta">Applied: ${escapeHtml(row[getAppliedColumn()] || "")}</span>` : ""}
    `;
    button.addEventListener("click", () => {
      state.selectedReviewIndex = index;
      renderReview(filtered);
    });
    els.reviewList.appendChild(button);
  });

  const { row, originalIndex } = filtered[state.selectedReviewIndex];
  const fields = state.columns
    .map((column) => {
      const isWide = LONG_FIELD_HINTS.some((hint) => column.toLowerCase().includes(hint));
      return `
        <div class="detail-field ${isWide ? "is-wide" : ""}">
          <label>${escapeHtml(column)}</label>
          <textarea data-column="${escapeHtml(column)}">${escapeHtml(row[column] || "")}</textarea>
        </div>
      `;
    })
    .join("");

  els.reviewDetail.innerHTML = `
    <h2>${escapeHtml(pick(row, ["title_normalized", "title_raw", "Title", "title"]) || "Untitled role")}</h2>
    <p class="review-meta">${escapeHtml(pick(row, ["company_name", "Company", "company"]) || "Unknown company")}</p>
    <div class="detail-grid">${fields}</div>
  `;

  els.reviewDetail.querySelectorAll("textarea").forEach((textarea) => {
    textarea.addEventListener("blur", () => {
      updateCell(originalIndex, textarea.dataset.column, textarea.value);
    });
  });
}

function getFilteredRows() {
  return state.rows
    .map((row, originalIndex) => ({ row, originalIndex }))
    .filter(({ row }) => {
      if (state.appliedFilter) {
        const appliedColumn = getAppliedColumn();
        if (!appliedColumn) return state.appliedFilter === "blank";
        const applied = normalizeAppliedValue(row[appliedColumn]);
        if (state.appliedFilter === "blank" && applied) return false;
        if (state.appliedFilter !== "blank" && applied !== state.appliedFilter) return false;
      }
      if (!state.search) return true;
      return state.columns.some((column) => String(row[column] || "").toLowerCase().includes(state.search));
    });
}

function updateCell(rowIndex, column, value) {
  if (state.rows[rowIndex][column] === value) return;
  state.rows[rowIndex][column] = value;
  scheduleSave();
}

function isAppliedColumn(column) {
  return column.toLowerCase() === "applied";
}

function getAppliedColumn() {
  return state.columns.find(isAppliedColumn);
}

function normalizeAppliedValue(value) {
  return String(value || "").trim().toLowerCase();
}

function focusEditableCell(cell) {
  cell.focus();
  const range = document.createRange();
  range.selectNodeContents(cell);
  range.collapse(false);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

function addColumn(index) {
  closeColumnMenu();
  const name = prompt("Column name");
  if (!name) return;
  const cleanName = uniqueColumnName(name.trim());
  state.columns.splice(index, 0, cleanName);
  for (const row of state.rows) row[cleanName] = "";
  scheduleSave();
  render();
}

function renameContextColumn() {
  closeColumnMenu();
  const oldName = state.columns[state.contextColumnIndex];
  if (!oldName) return;
  const name = prompt("Rename column", oldName);
  if (!name || name === oldName) return;
  const cleanName = uniqueColumnName(name.trim());
  state.columns[state.contextColumnIndex] = cleanName;
  for (const row of state.rows) {
    row[cleanName] = row[oldName] || "";
    delete row[oldName];
  }
  scheduleSave();
  render();
}

function deleteContextColumn() {
  closeColumnMenu();
  const column = state.columns[state.contextColumnIndex];
  if (!column || REQUIRED_COLUMNS.includes(column)) return;
  if (!confirm(`Delete column "${column}"?`)) return;
  state.columns.splice(state.contextColumnIndex, 1);
  for (const row of state.rows) delete row[column];
  scheduleSave();
  render();
}

function fillMissingWithCustomValue() {
  const value = prompt("Set missing values to");
  if (value === null) {
    closeColumnMenu();
    return;
  }
  fillMissingInContextColumn(value);
}

function fillMissingInContextColumn(value) {
  closeColumnMenu();
  const column = state.columns[state.contextColumnIndex];
  if (!column) return;
  let changed = 0;
  for (const row of state.rows) {
    if (isMissingValue(row[column])) {
      row[column] = value;
      changed += 1;
    }
  }
  if (changed > 0) {
    scheduleSave();
    render();
    setSaveStatus(`Filled ${changed}`, "is-saving");
    return;
  }
  setSaveStatus("No missing", "");
}

function isMissingValue(value) {
  return value === null || value === undefined || String(value).trim() === "";
}

function uniqueColumnName(name) {
  let candidate = name || "New Column";
  let suffix = 2;
  while (state.columns.includes(candidate)) {
    candidate = `${name} ${suffix}`;
    suffix += 1;
  }
  return candidate;
}

function openColumnMenu(x, y) {
  els.columnMenu.style.left = `${x}px`;
  els.columnMenu.style.top = `${y}px`;
  els.columnMenu.classList.add("is-open");
}

function closeColumnMenu() {
  els.columnMenu.classList.remove("is-open");
}

function toggleMode() {
  state.mode = state.mode === "table" ? "review" : "table";
  render();
}

function downloadCsv() {
  const csv = stringifyCsv(state.columns, state.rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `jedi-annotated-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

async function clearWorkspace() {
  if (!confirm("Clear all cached CSV rows and annotations?")) return;
  state.columns = [];
  state.rows = [];
  state.uploads = [];
  state.page = 1;
  alignRowsToColumns();
  await saveWorkspaceNow();
  render();
}

function scheduleSave() {
  setSaveStatus("Saving", "is-saving");
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveWorkspaceNow, 350);
}

async function saveWorkspaceNow() {
  if (!db) {
    setSaveStatus("Storage unavailable", "is-error");
    return;
  }
  try {
    await saveWorkspace({
      columns: state.columns,
      rows: state.rows,
      uploads: state.uploads,
      savedAt: new Date().toISOString(),
    });
    setSaveStatus("Saved", "");
  } catch (error) {
    console.error(error);
    setSaveStatus(`Save failed: ${error.name || "storage"}`, "is-error");
  }
}

function setSaveStatus(text, className) {
  els.saveStatus.textContent = text;
  els.saveStatus.className = `save-status ${className || ""}`.trim();
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (char === '"' && inQuotes && next === '"') {
      field += '"';
      index += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      row.push(field);
      field = "";
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") index += 1;
      row.push(field);
      if (row.some((value) => value.length)) rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }

  row.push(field);
  if (row.some((value) => value.length)) rows.push(row);
  const headers = (rows.shift() || []).map((header, index) => header.trim() || `Column ${index + 1}`);
  const records = rows.map((values) => {
    const record = {};
    headers.forEach((header, index) => {
      record[header] = values[index] || "";
    });
    return record;
  });
  return { headers, rows: records };
}

async function parseXlsx(arrayBuffer) {
  const files = await unzipXlsx(arrayBuffer);
  const workbookXml = decodeXmlFile(files, "xl/workbook.xml");
  const workbookRelsXml = decodeXmlFile(files, "xl/_rels/workbook.xml.rels");
  const sharedStringsXml = files.has("xl/sharedStrings.xml")
    ? decodeXmlFile(files, "xl/sharedStrings.xml")
    : "";
  const sheetPath = getFirstWorksheetPath(workbookXml, workbookRelsXml);
  const sheetXml = decodeXmlFile(files, sheetPath);
  const sharedStrings = parseSharedStrings(sharedStringsXml);
  const matrix = parseWorksheet(sheetXml, sharedStrings);
  return matrixToRecords(matrix);
}

async function unzipXlsx(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const directoryOffset = findCentralDirectoryOffset(bytes);
  const files = new Map();
  let offset = directoryOffset;

  while (readUint32(bytes, offset) === 0x02014b50) {
    const compression = readUint16(bytes, offset + 10);
    const compressedSize = readUint32(bytes, offset + 20);
    const uncompressedSize = readUint32(bytes, offset + 24);
    const nameLength = readUint16(bytes, offset + 28);
    const extraLength = readUint16(bytes, offset + 30);
    const commentLength = readUint16(bytes, offset + 32);
    const localHeaderOffset = readUint32(bytes, offset + 42);
    const name = decodeBytes(bytes.slice(offset + 46, offset + 46 + nameLength));
    const localNameLength = readUint16(bytes, localHeaderOffset + 26);
    const localExtraLength = readUint16(bytes, localHeaderOffset + 28);
    const dataStart = localHeaderOffset + 30 + localNameLength + localExtraLength;
    const compressed = bytes.slice(dataStart, dataStart + compressedSize);
    files.set(name, await inflateZipEntry(compressed, compression, uncompressedSize));
    offset += 46 + nameLength + extraLength + commentLength;
  }

  return files;
}

function findCentralDirectoryOffset(bytes) {
  for (let offset = bytes.length - 22; offset >= 0; offset -= 1) {
    if (readUint32(bytes, offset) === 0x06054b50) {
      return readUint32(bytes, offset + 16);
    }
  }
  throw new Error("Invalid .xlsx file: ZIP directory not found.");
}

async function inflateZipEntry(bytes, compression, expectedSize) {
  if (compression === 0) return bytes;
  if (compression !== 8) {
    throw new Error(`Unsupported .xlsx compression method: ${compression}`);
  }
  if (!("DecompressionStream" in window)) {
    throw new Error("This browser cannot decompress .xlsx files. Use Chrome/Edge or upload CSV.");
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  const decompressed = new Uint8Array(await new Response(stream).arrayBuffer());
  if (expectedSize && decompressed.length !== expectedSize) {
    return decompressed;
  }
  return decompressed;
}

function getFirstWorksheetPath(workbookXml, relsXml) {
  const workbook = parseXml(workbookXml);
  const rels = parseXml(relsXml);
  const firstSheet = getXmlElements(workbook, "sheet")[0];
  if (!firstSheet) throw new Error("No worksheet found in .xlsx file.");
  const relId = firstSheet.getAttribute("r:id");
  const relationship = getXmlElements(rels, "Relationship").find(
    (rel) => rel.getAttribute("Id") === relId,
  );
  if (!relationship) throw new Error("Worksheet relationship missing in .xlsx file.");
  const target = relationship.getAttribute("Target").replace(/^\/+/, "");
  return target.startsWith("xl/") ? target : `xl/${target}`;
}

function parseSharedStrings(xmlText) {
  if (!xmlText) return [];
  const xml = parseXml(xmlText);
  return getXmlElements(xml, "si").map((item) =>
    getXmlElements(item, "t").map((textNode) => textNode.textContent || "").join(""),
  );
}

function parseWorksheet(xmlText, sharedStrings) {
  const xml = parseXml(xmlText);
  const matrix = [];
  getXmlElements(xml, "row").forEach((rowNode) => {
    const rowIndex = Number(rowNode.getAttribute("r") || matrix.length + 1) - 1;
    matrix[rowIndex] = matrix[rowIndex] || [];
    getXmlElements(rowNode, "c").forEach((cellNode) => {
      const ref = cellNode.getAttribute("r") || "";
      const colIndex = columnRefToIndex(ref.replace(/[0-9]/g, ""));
      matrix[rowIndex][colIndex] = readCellValue(cellNode, sharedStrings);
    });
  });
  return matrix.filter((row) => row && row.some((value) => String(value || "").length));
}

function readCellValue(cellNode, sharedStrings) {
  const type = cellNode.getAttribute("t");
  if (type === "inlineStr") {
    return getXmlElements(cellNode, "t").map((node) => node.textContent || "").join("");
  }
  const value = getXmlElements(cellNode, "v")[0]?.textContent || "";
  if (type === "s") return sharedStrings[Number(value)] || "";
  if (type === "b") return value === "1" ? "TRUE" : "FALSE";
  return value;
}

function matrixToRecords(matrix) {
  const rawHeaders = matrix.shift() || [];
  const headers = rawHeaders.map((header, index) => String(header || "").trim() || `Column ${index + 1}`);
  const rows = matrix.map((values) => {
    const record = {};
    headers.forEach((header, index) => {
      record[header] = values[index] || "";
    });
    return record;
  });
  return { headers, rows };
}

function parseXml(xmlText) {
  const xml = new DOMParser().parseFromString(xmlText, "application/xml");
  const error = getXmlElements(xml, "parsererror")[0];
  if (error) throw new Error("Invalid XML inside .xlsx file.");
  return xml;
}

function getXmlElements(root, localName) {
  return [...root.getElementsByTagName("*")].filter((node) => node.localName === localName);
}

function columnRefToIndex(ref) {
  let index = 0;
  for (const char of ref) {
    index = index * 26 + char.toUpperCase().charCodeAt(0) - 64;
  }
  return Math.max(0, index - 1);
}

function decodeXmlFile(files, path) {
  const file = files.get(path);
  if (!file) throw new Error(`Missing ${path} in .xlsx file.`);
  return decodeBytes(file);
}

function decodeBytes(bytes) {
  return new TextDecoder("utf-8").decode(bytes);
}

function readUint16(bytes, offset) {
  return bytes[offset] | (bytes[offset + 1] << 8);
}

function readUint32(bytes, offset) {
  return (
    bytes[offset] |
    (bytes[offset + 1] << 8) |
    (bytes[offset + 2] << 16) |
    (bytes[offset + 3] << 24)
  ) >>> 0;
}

function stringifyCsv(headers, rows) {
  const lines = [headers.map(escapeCsv).join(",")];
  for (const row of rows) {
    lines.push(headers.map((header) => escapeCsv(row[header] || "")).join(","));
  }
  return `${lines.join("\r\n")}\r\n`;
}

function escapeCsv(value) {
  const text = String(value);
  if (/[",\r\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

function columnClass(column) {
  const slug = column.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  return `col-${slug}`;
}

function pick(row, keys) {
  for (const key of keys) {
    if (row[key]) return row[key];
  }
  return "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function loadWorkspace() {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const chunks = [];
    let meta;

    const request = store.get(WORKSPACE_KEY);
    request.onsuccess = () => {
      meta = request.result;
      if (!meta || !meta.chunked) return;
      for (let index = 0; index < meta.chunkCount; index += 1) {
        const chunkRequest = store.get(rowChunkKey(index));
        chunkRequest.onsuccess = () => {
          chunks[index] = chunkRequest.result || [];
        };
      }
    };
    tx.oncomplete = () => {
      if (!meta) {
        resolve(null);
      } else if (meta.chunked) {
        resolve({
          columns: meta.columns || [],
          uploads: meta.uploads || [],
          rows: chunks.flat(),
        });
      } else {
        resolve(meta);
      }
    };
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

function saveWorkspace(workspace) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const chunkCount = Math.ceil(workspace.rows.length / ROW_CHUNK_SIZE);
    const previousRequest = store.get(WORKSPACE_KEY);

    previousRequest.onsuccess = () => {
      const previousChunkCount = previousRequest.result?.chunkCount || 0;
      store.put(
        {
          chunked: true,
          columns: workspace.columns,
          uploads: workspace.uploads,
          savedAt: workspace.savedAt,
          rowCount: workspace.rows.length,
          chunkSize: ROW_CHUNK_SIZE,
          chunkCount,
        },
        WORKSPACE_KEY,
      );

      for (let index = 0; index < chunkCount; index += 1) {
        const start = index * ROW_CHUNK_SIZE;
        store.put(workspace.rows.slice(start, start + ROW_CHUNK_SIZE), rowChunkKey(index));
      }

      for (let index = chunkCount; index < previousChunkCount; index += 1) {
        store.delete(rowChunkKey(index));
      }
    };

    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

function rowChunkKey(index) {
  return `rows:${index}`;
}
