import { useCallback } from "react";
import { AccountService } from "@/services/accountService";
import type { AccountInfo } from "@/types/account";

interface UseAnalyticsPageActionsParams {
  setToken: (token: string) => void;
  setCurrentAccount: (account: AccountInfo | null) => void;
  setLoading: (loading: boolean) => void;
}

export function useAnalyticsPageActions({
  setToken,
  setCurrentAccount,
  setLoading,
}: UseAnalyticsPageActionsParams) {
  const loadCurrentAccount = useCallback(async () => {
    setLoading(true);
    try {
      const result = await AccountService.getAccountList();
      if (result.success && result.current_account) {
        setCurrentAccount(result.current_account);
        setToken(result.current_account.token);
      }
    } catch (error) {
      console.error("Failed to load current account:", error);
    } finally {
      setLoading(false);
    }
  }, [setToken, setCurrentAccount, setLoading]);

  return { loadCurrentAccount };
}
