import { API_URL } from "./config";
import type {
  AfterDummyStatisticsResponse,
  DummyProgressState,
  DuplicateProgressState,
  ModelInspectPayload,
  ParsedModelSummary,
  StatisticsPayload,
  UploadParseJob,
} from "./types";

type JsonObject = Record<string, unknown>;

export async function postJson<TResponse = JsonObject>(path: string, payload: unknown): Promise<TResponse> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJsonResponse<TResponse>(response);
}

export async function postForm<TResponse = JsonObject>(path: string, formData: FormData): Promise<TResponse> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    body: formData,
  });
  return readJsonResponse<TResponse>(response);
}

export async function getJson<TResponse = JsonObject>(path: string): Promise<TResponse> {
  const response = await fetch(`${API_URL}${path}`);
  return readJsonResponse<TResponse>(response);
}

export async function pollDuplicateJob(
  jobId: string,
  onUpdate?: (job: DuplicateProgressState) => void,
): Promise<DuplicateProgressState> {
  for (;;) {
    await delay(700);
    const job = await getJson<DuplicateProgressState>(`/api/duplicates/jobs/${jobId}`);
    if (onUpdate) onUpdate(job);
    if (job.status === "complete") return job;
    if (job.status === "error") throw new Error(job.error || job.message || "Duplicate detection failed");
  }
}

export async function pollDummyJob(
  jobId: string,
  onUpdate?: (job: DummyProgressState) => void,
): Promise<DummyProgressState> {
  for (;;) {
    await delay(700);
    const job = await getJson<DummyProgressState>(`/api/dummy/jobs/${jobId}`);
    if (onUpdate) onUpdate(job);
    if (job.status === "complete") return job;
    if (job.status === "error") throw new Error(job.error || job.message || "Dummy cleansing failed");
  }
}

export async function pollUploadParseJob(
  uploadId: string,
  jobId: string,
  onUpdate?: (job: UploadParseJob) => void,
): Promise<UploadParseJob> {
  for (;;) {
    await delay(700);
    const job = await getJson<UploadParseJob>(`/api/uploads/${uploadId}/jobs/${jobId}`);
    if (onUpdate) onUpdate(job);
    if (job.status === "complete") return job;
    if (job.status === "error") throw new Error(job.error || job.message || "Upload parsing failed");
  }
}

export async function getModelInspect(
  datasetId: string,
  modelId: string,
  options?: { includeAttrs?: boolean },
): Promise<ModelInspectPayload> {
  const query = new URLSearchParams();
  if (typeof options?.includeAttrs === "boolean") query.set("includeAttrs", String(options.includeAttrs));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return getJson<ModelInspectPayload>(
    `/api/datasets/${encodeURIComponent(datasetId)}/models/${encodeURIComponent(modelId)}/inspect${suffix}`,
  );
}

export interface DatasetModelsPage {
  datasetId: string;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  models: ParsedModelSummary[];
}

export async function getDatasetModels(
  datasetId: string,
  options?: {
    page?: number;
    pageSize?: number;
    query?: string;
    sort?: string;
    order?: "asc" | "desc";
    warningType?: string;
  },
): Promise<DatasetModelsPage> {
  const query = new URLSearchParams();
  if (options?.page) query.set("page", String(options.page));
  if (options?.pageSize) query.set("pageSize", String(options.pageSize));
  if (options?.query) query.set("query", options.query);
  if (options?.sort) query.set("sort", options.sort);
  if (options?.order) query.set("order", options.order);
  if (options?.warningType) query.set("warningType", options.warningType);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return getJson<DatasetModelsPage>(`/api/datasets/${encodeURIComponent(datasetId)}/models${suffix}`);
}

export async function getDatasetStatistics(datasetId: string): Promise<StatisticsPayload> {
  return getJson<StatisticsPayload>(`/api/datasets/${encodeURIComponent(datasetId)}/statistics`);
}

export async function getDatasetAfterDummyStatistics(datasetId: string): Promise<AfterDummyStatisticsResponse> {
  return getJson<AfterDummyStatisticsResponse>(`/api/datasets/${encodeURIComponent(datasetId)}/statistics/after-dummy`);
}

export function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function readJsonResponse<TResponse>(response: Response): Promise<TResponse> {
  const contentType = response.headers.get("content-type") || "";
  const body = await response.text();
  let data: unknown = {};
  if (body && contentType.includes("application/json")) {
    data = JSON.parse(body);
  }
  if (!response.ok) {
    throw new Error(responseErrorMessage(data, body, response.status));
  }
  if (!body) {
    throw new Error("The backend returned an empty response. Make sure Flask is running on 127.0.0.1:8765.");
  }
  if (!contentType.includes("application/json")) {
    throw new Error("The backend returned a non-JSON response. Make sure the Flask API is running and reachable.");
  }
  return data as TResponse;
}

function responseErrorMessage(data: unknown, body: string, status: number) {
  if (data && typeof data === "object") {
    const payload = data as { error?: unknown; message?: unknown };
    if (typeof payload.error === "string" && payload.error) return payload.error;
    if (typeof payload.message === "string" && payload.message) return payload.message;
  }
  return body || `Request failed with HTTP ${status}`;
}

export function errorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message;
  if (error && typeof error === "object") {
    const candidate = (error as { message?: unknown }).message;
    if (typeof candidate === "string" && candidate) return candidate;
  }
  return fallback;
}
