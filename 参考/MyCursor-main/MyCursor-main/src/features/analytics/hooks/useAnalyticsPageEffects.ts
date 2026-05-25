import { useEffect } from "react";

interface UseAnalyticsPageEffectsParams {
  loadCurrentAccount: () => Promise<void>;
}

export function useAnalyticsPageEffects({ loadCurrentAccount }: UseAnalyticsPageEffectsParams) {
  useEffect(() => {
    void loadCurrentAccount();
  }, [loadCurrentAccount]);
}
