import { techniques } from "./config";
import type { Thresholds } from "./types";

export function techniqueLabel(id: string) {
  const labels: Record<string, string> = {
    hash_names: "Hash: names",
    hash_names_types: "Hash: names + types",
    tfidf_names: "TF-IDF: names",
    tfidf_names_types: "TF-IDF: names + types",
  };
  return techniques.find((technique) => technique.id === id)?.label || labels[id] || id;
}

export function backendTechniquesFor(id: string, thresholds: Thresholds) {
  if (id === "hash") return [thresholds.hashIncludeTypes ? "hash_names_types" : "hash_names"];
  if (id === "tfidf") return [thresholds.tfidfIncludeTypes ? "tfidf_names_types" : "tfidf_names"];
  return [id];
}

export function round(value: number) {
  return Number.isInteger(value) ? value : Number(value || 0).toFixed(1);
}

export function formatDuration(ms = 0) {
  if (!ms) return "0 ms";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}
