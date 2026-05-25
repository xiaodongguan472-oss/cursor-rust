import { useCallback } from "react";
import type { AccountsPageActionsContext } from "./accountsPageActionTypes.ts";

export function useAccountsPageBatchActions({
  selectedAccounts,
  setToast,
  setConfirmDialog,
  refreshCurrentAccount,
  refreshSelectedAccounts,
  refreshAllAccounts,
  removeSelectedAccounts,
}: AccountsPageActionsContext) {
  const handleRefreshCurrentAccount = useCallback(async () => {
    const result = await refreshCurrentAccount();
    if (result.success && result.currentAccount) {
      setToast({ message: `当前账号: ${result.currentAccount.email}`, type: "success" });
    } else {
      setToast({ message: "未检测到当前登录账号", type: "error" });
    }
  }, [refreshCurrentAccount, setToast]);

  const handleRefreshAll = useCallback(async () => {
    if (selectedAccounts.size > 0) {
      const result = await refreshSelectedAccounts();
      if (result.success) {
        setToast({ message: result.message || `已刷新 ${selectedAccounts.size} 个账户`, type: "success" });
      } else {
        setToast({ message: result.message || "刷新失败", type: "error" });
      }
      return;
    }

    const result = await refreshAllAccounts();
    if (result.success) {
      setToast({ message: "所有账户信息已刷新", type: "success" });
    } else {
      setToast({ message: result.message || "刷新失败", type: "error" });
    }
  }, [refreshAllAccounts, refreshSelectedAccounts, selectedAccounts, setToast]);

  const handleDeleteSelected = useCallback(async () => {
    if (selectedAccounts.size === 0) {
      setToast({ message: "请先选择要删除的账户", type: "error" });
      return;
    }

    setConfirmDialog({
      show: true,
      title: "确认删除",
      message: `确定要删除选中的 ${selectedAccounts.size} 个账户吗？此操作不可恢复。`,
      onConfirm: async () => {
        const result = await removeSelectedAccounts();
        if (result.success) {
          setToast({ message: result.message || `已删除 ${selectedAccounts.size} 个账户`, type: "success" });
        } else {
          setToast({ message: result.message || "删除失败", type: "error" });
        }
        setConfirmDialog((prev) => ({ ...prev, show: false }));
      },
    });
  }, [removeSelectedAccounts, selectedAccounts, setConfirmDialog, setToast]);

  return {
    handleRefreshCurrentAccount,
    handleRefreshAll,
    handleDeleteSelected,
  };
}
