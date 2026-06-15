import { forwardRef, useCallback, useEffect, useImperativeHandle, useState, type Ref } from "react";
import { PairCompareModal, useDeferredEnable, useModelInspect } from "./Inspector";

const PAIR_COMPARE_CLOSE_MS = 200;

export interface PairCompareInspectorHandle {
  open: (leftId: string, rightId: string) => void;
  close: () => void;
}

export const PairCompareInspector = forwardRef(function PairCompareInspector(
  { datasetId }: { datasetId: string },
  ref: Ref<PairCompareInspectorHandle>,
) {
  const [pair, setPair] = useState<{ leftId: string; rightId: string } | null>(null);
  const [open, setOpen] = useState(false);
  const [showCompareGraph, setShowCompareGraph] = useState(false);

  const close = useCallback(() => {
    setShowCompareGraph(false);
    setOpen(false);
    window.setTimeout(() => {
      setPair(null);
    }, PAIR_COMPARE_CLOSE_MS);
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      open(leftId: string, rightId: string) {
        setShowCompareGraph(false);
        setPair({ leftId, rightId });
        setOpen(true);
      },
      close,
    }),
    [close],
  );

  const fetchReady = useDeferredEnable(open && Boolean(pair));
  const leftInspect = useModelInspect(datasetId, pair?.leftId ?? null, { enabled: fetchReady });
  const rightInspect = useModelInspect(datasetId, pair?.rightId ?? null, { enabled: fetchReady });

  const bothReady = Boolean(
    leftInspect.payload &&
      rightInspect.payload &&
      !leftInspect.loading &&
      !rightInspect.loading &&
      !leftInspect.error &&
      !rightInspect.error,
  );

  useEffect(() => {
    if (open && bothReady) {
      setShowCompareGraph(true);
    }
  }, [bothReady, open]);

  if (!pair) {
    return null;
  }

  return (
    <PairCompareModal
      open={open}
      leftId={pair.leftId}
      rightId={pair.rightId}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) close();
      }}
      leftInspectLoading={!fetchReady || leftInspect.loading}
      leftInspectError={leftInspect.error}
      leftInspectModel={leftInspect.payload}
      rightInspectLoading={!fetchReady || rightInspect.loading}
      rightInspectError={rightInspect.error}
      rightInspectModel={rightInspect.payload}
      showCompareGraph={showCompareGraph}
    />
  );
});
