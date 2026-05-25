import { useState } from "react";
import type { AccountInfo } from "@/types/account";

export function useAnalyticsPageState() {
  const [token, setToken] = useState("");
  const [currentAccount, setCurrentAccount] = useState<AccountInfo | null>(null);
  const [loading, setLoading] = useState(false);

  return {
    token,
    setToken,
    currentAccount,
    setCurrentAccount,
    loading,
    setLoading,
  };
}
