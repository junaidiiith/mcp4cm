import { API_URL } from "./config";

export async function postJson(path: string, payload: unknown) {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJsonResponse(response);
}

export async function postForm(path: string, formData: FormData) {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    body: formData,
  });
  return readJsonResponse(response);
}

export async function getJson(path: string) {
  const response = await fetch(`${API_URL}${path}`);
  return readJsonResponse(response);
}

export async function pollDuplicateJob(jobId: string) {
  for (;;) {
    await delay(700);
    const job = await getJson(`/api/duplicates/jobs/${jobId}`);
    if (job.status === "complete") return job;
    if (job.status === "error") throw new Error(job.error || job.message || "Duplicate detection failed");
  }
}

export async function pollUploadParseJob(
  uploadId: string,
  jobId: string,
  onUpdate?: (job: any) => void,
) {
  for (;;) {
    await delay(700);
    const job = await getJson(`/api/uploads/${uploadId}/jobs/${jobId}`);
    if (onUpdate) onUpdate(job);
    if (job.status === "complete") return job;
    if (job.status === "error") throw new Error(job.error || job.message || "Upload parsing failed");
  }
}

export async function getModelInspect(
  datasetId: string,
  modelId: string,
  options?: { nodeLimit?: number; edgeLimit?: number; includeAttrs?: boolean },
) {
  const query = new URLSearchParams();
  if (options?.nodeLimit) query.set("nodeLimit", String(options.nodeLimit));
  if (options?.edgeLimit) query.set("edgeLimit", String(options.edgeLimit));
  if (typeof options?.includeAttrs === "boolean") query.set("includeAttrs", String(options.includeAttrs));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return getJson(`/api/datasets/${encodeURIComponent(datasetId)}/models/${encodeURIComponent(modelId)}/inspect${suffix}`);
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function readJsonResponse(response: Response) {
  const contentType = response.headers.get("content-type") || "";
  const body = await response.text();
  let data: Record<string, any> = {};
  if (body && contentType.includes("application/json")) {
    data = JSON.parse(body);
  }
  if (!response.ok) {
    throw new Error(data.error || body || `Request failed with HTTP ${response.status}`);
  }
  if (!body) {
    throw new Error("The backend returned an empty response. Make sure Flask is running on 127.0.0.1:8765.");
  }
  if (!contentType.includes("application/json")) {
    throw new Error("The backend returned a non-JSON response. Make sure the Flask API is running and reachable.");
  }
  return data;
}
