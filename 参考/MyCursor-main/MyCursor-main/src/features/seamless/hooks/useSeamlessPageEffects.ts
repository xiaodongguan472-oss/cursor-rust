import { useEffect } from "react";

interface UseSeamlessPageEffectsParams {
  loadStatus: () => Promise<void>;
}

export function useSeamlessPageEffects({ loadStatus }: UseSeamlessPageEffectsParams) {
  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);
}
