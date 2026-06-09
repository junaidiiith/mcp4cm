import { Suspense, lazy, useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { errorMessage, getModelInspect } from "../../api";
import type { ModelInspectPayload, ParsedModelSummary, WarningEntry } from "../../types";

const LazyModelGraphPreview = lazy(() => import("../../components/model-graph-preview"));

export interface ModelInspectState {
  payload: ModelInspectPayload | null;
  loading: boolean;
  error: string;
}

export function useModelInspect(datasetId: string, modelId: string | null): ModelInspectState {
  const [payload, setPayload] = useState<ModelInspectPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!modelId) {
        setPayload(null);
        setError("");
        setLoading(false);
        return;
      }
      if (!datasetId) {
        setPayload(null);
        setError("Process selected models to inspect parsed graph details.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const response = await getModelInspect(datasetId, modelId, {
          includeAttrs: true,
        });
        if (!cancelled) {
          setPayload(response);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setPayload(null);
          setError(errorMessage(err, "Failed to load parsed model details."));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [datasetId, modelId]);

  return { payload, loading, error };
}

export function WarningInspectorDrawer({
  model,
  warnings,
  tab,
  onTabChange,
  onClose,
  inspectLoading,
  inspectError,
  inspectModel,
}: {
  model: ParsedModelSummary;
  warnings: WarningEntry[];
  tab: "warnings" | "model";
  onTabChange: (tab: "warnings" | "model") => void;
  onClose: () => void;
  inspectLoading: boolean;
  inspectError: string;
  inspectModel: ModelInspectPayload | null;
}) {
  return (
    <Sheet
      open
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <SheetContent side="right" className="inspectorDrawer">
        <SheetHeader>
          <SheetTitle>Model Details</SheetTitle>
          <SheetDescription>
            {model.modelId} · {model.path}
          </SheetDescription>
        </SheetHeader>
        <div className="inspectorTabs">
          <Button
            type="button"
            variant={tab === "warnings" ? "default" : "secondary"}
            onClick={() => onTabChange("warnings")}
          >
            Warnings
          </Button>
          <Button
            type="button"
            variant={tab === "model" ? "default" : "secondary"}
            onClick={() => onTabChange("model")}
          >
            Parsed Model
          </Button>
        </div>
        {tab === "warnings" ? (
          <div className="inspectorBody">
            <div className="warningTypeChips">
              {Object.entries(model.types || {}).map(([type, count]) => (
                <span key={type} className="warningTypeChip">
                  {type} ({count})
                </span>
              ))}
            </div>
            <div className="warningList inspector">
              {warnings.length ? (
                warnings.map((warning, index) => (
                  <div className="warningListRow" key={`${warning.type}:${index}`}>
                    <span>{warning.type}</span>
                    <p>{warning.message}</p>
                  </div>
                ))
              ) : (
                <div className="warningListRow hint">
                  <p>No detailed warning entries were emitted for this file.</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="inspectorBody">
            <ModelInspectBody
              inspectLoading={inspectLoading}
              inspectError={inspectError}
              inspectModel={inspectModel}
            />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

export function ModelGraphDrawer({
  title,
  modelId,
  onClose,
  inspectLoading,
  inspectError,
  inspectModel,
}: {
  title: string;
  modelId: string;
  onClose: () => void;
  inspectLoading: boolean;
  inspectError: string;
  inspectModel: ModelInspectPayload | null;
}) {
  return (
    <Sheet
      open
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <SheetContent side="right" className="inspectorDrawer">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{modelId}</SheetDescription>
        </SheetHeader>
        <div className="inspectorBody">
          <ModelInspectBody
            inspectLoading={inspectLoading}
            inspectError={inspectError}
            inspectModel={inspectModel}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function PairCompareModal({
  leftId,
  rightId,
  onClose,
  leftInspectLoading,
  leftInspectError,
  leftInspectModel,
  rightInspectLoading,
  rightInspectError,
  rightInspectModel,
}: {
  leftId: string;
  rightId: string;
  onClose: () => void;
  leftInspectLoading: boolean;
  leftInspectError: string;
  leftInspectModel: ModelInspectPayload | null;
  rightInspectLoading: boolean;
  rightInspectError: string;
  rightInspectModel: ModelInspectPayload | null;
}) {
  return (
    <Dialog
      open
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogContent className="pairCompareModal">
        <DialogHeader>
          <DialogTitle>Duplicate Pair Compare</DialogTitle>
          <DialogDescription>
            {leftId} {"<->"} {rightId}
          </DialogDescription>
        </DialogHeader>
        <div className="pairCompareGrid">
          <div className="pairComparePane">
            <div className="pairComparePaneHeader">
              <h4>Left</h4>
              <p>{leftId}</p>
            </div>
            <ModelInspectBody
              inspectLoading={leftInspectLoading}
              inspectError={leftInspectError}
              inspectModel={leftInspectModel}
            />
          </div>
          <div className="pairComparePane">
            <div className="pairComparePaneHeader">
              <h4>Right</h4>
              <p>{rightId}</p>
            </div>
            <ModelInspectBody
              inspectLoading={rightInspectLoading}
              inspectError={rightInspectError}
              inspectModel={rightInspectModel}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ModelInspectBody({
  inspectLoading,
  inspectError,
  inspectModel,
}: {
  inspectLoading: boolean;
  inspectError: string;
  inspectModel: ModelInspectPayload | null;
}) {
  if (inspectLoading) {
    return (
      <div className="inspectState">
        <Loader2 className="spin" size={16} />
        Loading parsed model...
      </div>
    );
  }
  if (inspectError) {
    return (
      <div className="inspectState error">
        <AlertTriangle size={16} />
        {inspectError}
      </div>
    );
  }
  if (!inspectModel) {
    return <div className="inspectState">No parsed model data available.</div>;
  }

  return (
    <Suspense
      fallback={
        <div className="inspectState">
          <Loader2 className="spin" size={16} />
          Loading graph preview...
        </div>
      }
    >
      <LazyModelGraphPreview payload={inspectModel} />
    </Suspense>
  );
}
