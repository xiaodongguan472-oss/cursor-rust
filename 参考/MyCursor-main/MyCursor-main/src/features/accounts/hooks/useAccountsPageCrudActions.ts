import { useCallback } from "react";
import type { AccountInfo } from "@/types/account";
import type { AccountsPageActionsContext } from "./accountsPageActionTypes.ts";

export function useAccountsPageCrudActions({
  expandedAccountEmail,
  setShowAddForm,
  setShowEditForm,
  setEditingAccount,
  setExpandedAccountEmail,
  setClosingAccountEmail,
  setUsageModalOpen,
  setSelectedAccountUsage,
  setToast,
  setConfirmDialog,
  loadAccounts,
  addAccountToList,
  refreshSingleAccount,
  removeAccount,
}: AccountsPageActionsContext) {
  const handleAddSuccess = useCallback(
    async (email: string) => {
      setShowAddForm(false);
      await addAccountToList(email);
    },
    [addAccountToList, setShowAddForm]
  );

  const handleEditSuccess = useCallback(async () => {
    setShowEditForm(false);
    setEditingAccount(null);
    await loadAccounts();
  }, [loadAccounts, setEditingAccount, setShowEditForm]);

  const handleRefreshAccount = useCallback(
    async (account: AccountInfo, index: number) => {
      const result = await refreshSingleAccount(account, index);
      if (result.success) {
        setToast({ message: `${account.email} 信息已刷新`, type: "success" });
      } else {
        setToast({ message: `${account.email} ${result.message || "刷新失败"}`, type: "error" });
      }
    },
    [refreshSingleAccount, setToast]
  );

  const handleViewUsage = useCallback(
    (account: AccountInfo) => {
      setSelectedAccountUsage({
        account,
        usageData: null,
        events: null,
        totalEvents: 0,
        loading: false,
        useEventBasedCalculation: false,
      });
      setUsageModalOpen(true);
    },
    [setSelectedAccountUsage, setUsageModalOpen]
  );

  const handleEditAccount = useCallback(
    (account: AccountInfo) => {
      setEditingAccount(account);
      setShowEditForm(true);
    },
    [setEditingAccount, setShowEditForm]
  );

  const handleRemoveAccount = useCallback(
    async (email: string) => {
      setConfirmDialog({
        show: true,
        title: "确认删除",
        message: `确定要删除账户 ${email} 吗？`,
        onConfirm: async () => {
          const result = await removeAccount(email);
          if (result.success) {
            setToast({ message: "账户已删除", type: "success" });
          } else {
            setToast({ message: result.message || "删除失败", type: "error" });
          }
          setConfirmDialog((prev) => ({ ...prev, show: false }));
        },
      });
    },
    [removeAccount, setConfirmDialog, setToast]
  );

  const handleToggleExpand = useCallback(
    (email: string) => {
      if (expandedAccountEmail === email) {
        setExpandedAccountEmail(null);
        setClosingAccountEmail(null);
      } else {
        setExpandedAccountEmail(email);
        setClosingAccountEmail(null);
      }
    },
    [expandedAccountEmail, setClosingAccountEmail, setExpandedAccountEmail]
  );

  const handleCloseMenu = useCallback(() => {
    setExpandedAccountEmail(null);
    setClosingAccountEmail(null);
  }, [setClosingAccountEmail, setExpandedAccountEmail]);

  return {
    handleAddSuccess,
    handleEditSuccess,
    handleRefreshAccount,
    handleViewUsage,
    handleEditAccount,
    handleRemoveAccount,
    handleToggleExpand,
    handleCloseMenu,
  };
}
