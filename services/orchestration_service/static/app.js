const state = {
  uploadedDocument: null,
  doclingResult: null,
};

function pickFields(source, fields) {
  if (!source) return null;
  return Object.fromEntries(
    fields
      .filter((field) => source[field] !== undefined)
      .map((field) => [field, source[field]])
  );
}

function resetWorkflowState() {
  state.uploadedDocument = null;
  state.doclingResult = null;

  const fileInput = document.getElementById("uploadFile");
  const filePath = document.getElementById("filePath");
  const languageHint = document.getElementById("languageHint");
  const label = document.getElementById("dropZoneLabel");

  fileInput.value = "";
  filePath.value = "";
  languageHint.value = "auto";
  label.textContent = "Drop a file here or click to choose one.";

  setText("uploadResult", "No upload yet.", true);
  setText("documentResult", "Nothing uploaded yet.", true);
  setText("processResult", "No orchestration run yet.", true);
  setText("doclingInfo", "No Docling run yet.", true);
  setText("doclingMarkdown", "No Docling markdown yet.", true);
  setText("latestProcessingResult", "No processing row loaded yet.", true);
  setText("finalMarkdown", "No final markdown yet.", true);
  setText("finalMessage", "No final message yet.", true);

  document.getElementById("confidenceSource").textContent = "—";
  document.getElementById("confidenceValue").textContent = "—";
  document.getElementById("vlmTriggered").textContent = "No";
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function setText(id, text, muted = false) {
  const node = document.getElementById(id);
  node.textContent = typeof text === "string" ? text : pretty(text);
  node.classList.toggle("muted", muted);
}

function serviceCard(title, details) {
  const tone = !details.configured ? "off" : details.reachable ? "ok" : "fail";
  const label = !details.configured ? "Not configured" : details.reachable ? "Reachable" : "Unavailable";
  return `
    <article class="status-card">
      <h3>${title}</h3>
      <div class="status-pill ${tone}">${label}</div>
      <div class="status-url">${details.url || "No URL configured."}</div>
    </article>
  `;
}

async function refreshStatus() {
  const response = await fetch("/orchestration/status");
  const data = await response.json();
  const grid = document.getElementById("statusGrid");
  grid.innerHTML = [
    serviceCard("Postgres", data.postgres),
    serviceCard("Upload", data.upload),
    serviceCard("Docling", data.docling),
    serviceCard("VLM", data.vlm),
    serviceCard("LightRAG", data.lightrag),
  ].join("");
}

async function initTables() {
  setText("initDbResult", "Initializing tables...", true);
  const response = await fetch("/orchestration/postgres/init", { method: "POST" });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : pretty(data));
  }
  setText("initDbResult", data);
}

async function uploadFile(event) {
  event.preventDefault();
  const fileInput = document.getElementById("uploadFile");
  if (!fileInput.files.length) {
    setText("uploadResult", "Choose a file first.", true);
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  setText("uploadResult", "Uploading file...", true);
  const response = await fetch("/orchestration/upload", {
    method: "POST",
    body: formData,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : pretty(data));
  }

  state.uploadedDocument = data;
  document.getElementById("filePath").value = data.file_path || "";
  document.getElementById("lightragIndexFilePath").value = data.file_path || "";
  setText("uploadResult", data);
  setText("documentResult", data);
}

async function runProcess(event) {
  event.preventDefault();
  const filePath = document.getElementById("filePath").value.trim();
  const languageHint = document.getElementById("languageHint").value;
  if (!filePath) {
    setText("processResult", "We need a file path first.", true);
    return;
  }

  setText("processResult", "Running orchestration...", true);
  const response = await fetch("/orchestration/process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_path: filePath, language_hint: languageHint }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : pretty(data));
  }

  state.doclingResult = data.docling_result;
  const doclingSummary = pickFields(data.docling_result, [
    "document_id",
    "processing_id",
    "file_path",
    "ocr_engine",
    "easyocr_confidence",
    "docling_duration_seconds",
    "status",
  ]);
  const latestProcessingSummary = pickFields(data.latest_processing, [
    "processing_id",
    "document_id",
    "processing_status",
    "parsed_at",
    "parser_name",
    "used_ocr",
    "ocr_engine",
    "ocr_confidence",
    "mean_confidence",
    "low_confidence",
    "used_vlm",
    "vlm_model",
  ]);

  setText("processResult", data.final_message || "Orchestration finished.");
  setText("doclingInfo", doclingSummary || "No Docling result.", !doclingSummary);
  setText(
    "doclingMarkdown",
    data.docling_result?.markdown_text || data.latest_processing?.markdown_text || "No Docling markdown returned.",
    !(data.docling_result?.markdown_text || data.latest_processing?.markdown_text)
  );
  setText(
    "latestProcessingResult",
    latestProcessingSummary || "No processing row returned.",
    !latestProcessingSummary
  );
  setText("finalMarkdown", data.final_markdown || "No markdown returned.", !data.final_markdown);
  setText("finalMessage", data.final_message || "No final message.", !data.final_message);

  document.getElementById("confidenceSource").textContent = data.confidence_source || "-";
  document.getElementById("confidenceValue").textContent =
    data.confidence_value === null || data.confidence_value === undefined ? "-" : String(data.confidence_value);
  document.getElementById("vlmTriggered").textContent = data.vlm_triggered ? "Yes" : "No";
}

async function runLightragIndexing(event) {
  event.preventDefault();
  const filePath = document.getElementById("lightragIndexFilePath").value.trim();
  if (!filePath) {
    setText("lightragIndexResult", "File path is required.", true);
    return;
  }

  setText(
    "lightragIndexResult",
    "Running LightRAG indexing...\n- Resolve document by file path\n- Send indexing request\n- Wait for indexing completion",
    true
  );
  const response = await fetch("/orchestration/lightrag/index-by-path", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_path: filePath }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : pretty(data));
  }
  const indexSummary = [
    "LightRAG indexing completed.",
    "",
    `document_id: ${data.document_id || "-"}`,
    `status: ${data.indexing_result?.status || "-"}`,
    `run_id: ${data.indexing_result?.run_id || "-"}`,
    `file_path: ${data.file_path || "-"}`,
  ].join("\n");
  setText("lightragIndexResult", indexSummary);
}

async function runLightragRetrieval(event) {
  event.preventDefault();
  const query = document.getElementById("lightragQuery").value.trim();
  if (!query) {
    setText("lightragRetrieveResult", "Query is required.", true);
    return;
  }

  const topK = Number(document.getElementById("lightragTopK").value || 5);
  const searchType = document.getElementById("lightragSearchType").value;
  const generateAnswer = document.getElementById("lightragGenerateAnswer").value === "true";

  setText(
    "lightragRetrieveResult",
    "Running LightRAG retrieval...\n- Build retrieval request\n- Query LightRAG\n- Generate answer",
    true
  );
  const response = await fetch("/orchestration/lightrag/retrieve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      top_k: topK,
      search_type: searchType,
      generate_answer: generateAnswer,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : pretty(data));
  }
  const hasAnswer = typeof data.generated_answer === "string" && data.generated_answer.trim();
  const answer = hasAnswer ? data.generated_answer.trim() : "No generated answer returned.";
  const generationError =
    typeof data.generation_error === "string" && data.generation_error.trim()
      ? data.generation_error.trim()
      : null;
  const evalInfo = data.evaluation || {};
  const retrievalSummary = [
    "Generated answer:",
    "",
    answer,
    ...(generationError ? ["", "generation_error:", generationError] : []),
    "",
    "---",
    `retrieval_id: ${data.retrieval_id || "-"}`,
    `latency_ms: ${data.latency_ms ?? "-"}`,
    `retrieved_chunks: ${evalInfo.retrieved_chunks_count ?? "-"}`,
    `insufficient_context: ${evalInfo.insufficient_context ?? "-"}`,
  ].join("\n");
  setText("lightragRetrieveResult", retrievalSummary);
}

function hookButton(id, handler, eventName = "click") {
  document.getElementById(id).addEventListener(eventName, async (event) => {
    try {
      await handler(event);
      await refreshStatus();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (id === "initDb") setText("initDbResult", message, true);
      if (id === "uploadForm") setText("uploadResult", message, true);
      if (id === "processForm") setText("processResult", message, true);
      if (id === "lightragIndexForm") setText("lightragIndexResult", message, true);
      if (id === "lightragRetrieveForm") setText("lightragRetrieveResult", message, true);
    }
  });
}

function setupDropZone() {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("uploadFile");
  const label = document.getElementById("dropZoneLabel");

  const syncLabel = () => {
    if (fileInput.files.length) {
      label.textContent = fileInput.files[0].name;
    } else {
      label.textContent = "Drop a file here or click to choose one.";
    }
  };

  fileInput.addEventListener("change", syncLabel);
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("dragging");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("dragging");
    });
  });
  dropZone.addEventListener("drop", (event) => {
    if (event.dataTransfer?.files?.length) {
      fileInput.files = event.dataTransfer.files;
      syncLabel();
    }
  });
}

hookButton("refreshStatus", async () => {
  resetWorkflowState();
  await refreshStatus();
});
hookButton("initDb", initTables);
hookButton("uploadForm", uploadFile, "submit");
hookButton("processForm", runProcess, "submit");
hookButton("lightragIndexForm", runLightragIndexing, "submit");
hookButton("lightragRetrieveForm", runLightragRetrieval, "submit");
setupDropZone();

refreshStatus().catch((error) => {
  setText("processResult", String(error), true);
});
