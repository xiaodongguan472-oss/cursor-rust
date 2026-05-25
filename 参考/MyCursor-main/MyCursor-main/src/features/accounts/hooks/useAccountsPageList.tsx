import { useCallback, useMemo, type Dispatch, type SetStateAction } from "react";
import type { AccountInfo, AccountListResult } from "@/types/account";
import type { AccountsPageToastState } from "./useAccountsPageState";
import { AccountCard } from "../components";

interface UseAccountsPageListParams {
  accountData: AccountListResult | null;
  filteredAccounts: AccountInfo[];
  selectedAccounts: Set<string>;
  expandedAccountEmail: string | null;
  closingAccountEmail: string | null;
  toggleAccountSelection: (email: string) => void;
  handleRefreshAccount: (account: AccountInfo, index: number) => Promise<void>;
  handleSwitchAccount: (account: AccountInfo) => void;
  handleViewUsage: (account: AccountInfo) => void;
  handleEditAccount: (account: AccountInfo) => void;
  handleRemoveAccount: (email: string) => Promise<void>;
  handleToggleExpand: (email: string) => void;
  handleCloseMenu: () => void;
  handleViewDashboard: (account: AccountInfo) => Promise<void>;
  handleViewBindCard: (account: AccountInfo) => Promise<void>;
  handleDeleteCursorAccount: (account: AccountInfo) => void;
  handleLogout: () => void;
  setToast: Dispatch<SetStateAction<AccountsPageToastState | null>>;
  virtualScrollThreshold?: number;
}

export function useAccountsPageList({
  accountData,
  filteredAccounts,
  selectedAccounts,
  expandedAccountEmail,
  closingAccountEmail,
  toggleAccountSelection,
  handleRefreshAccount,
  handleSwitchAccount,
  handleViewUsage,
  handleEditAccount,
  handleRemoveAccount,
  handleToggleExpand,
  handleCloseMenu,
  handleViewDashboard,
  handleViewBindCard,
  handleDeleteCursorAccount,
  handleLogout,
  setToast,
  virtualScrollThreshold = 15,
}: UseAccountsPageListParams) {
  const shouldUseVirtualScroll = useMemo(() => {
    return filteredAccounts.length > virtualScrollThreshold;
  }, [filteredAccounts.length, virtualScrollThreshold]);

  const isAllSelected = useMemo(() => {
    return filteredAccounts.length > 0 && filteredAccounts.every((acc) => selectedAccounts.has(acc.email));
  }, [filteredAccounts, selectedAccounts]);

  const renderAccountCard = useCallback(
    (account: AccountInfo, index: number) => {
      const isCurrent = Boolean(accountData?.current_account && account.email === accountData.current_account.email);

      return (
        <AccountCard
          key={account.email}
          account={account}
          index={index}
          isSelected={selectedAccounts.has(account.email)}
          isCurrent={isCurrent}
          isExpanded={expandedAccountEmail === account.email}
          isClosing={closingAccountEmail === account.email}
          onSelect={toggleAccountSelection}
          onRefresh={handleRefreshAccount}
          onSwitch={handleSwitchAccount}
          onViewUsage={handleViewUsage}
          onEdit={handleEditAccount}
          onRemove={handleRemoveAccount}
          onToggleExpand={handleToggleExpand}
          onCloseMenu={handleCloseMenu}
          onViewDashboard={handleViewDashboard}
          onViewBindCard={handleViewBindCard}
          onDeleteCursorAccount={handleDeleteCursorAccount}
          onLogout={handleLogout}
          onToast={(message, type) => setToast({ message, type })}
        />
      );
    },
    [
      accountData,
      selectedAccounts,
      expandedAccountEmail,
      closingAccountEmail,
      toggleAccountSelection,
      handleRefreshAccount,
      handleSwitchAccount,
      handleViewUsage,
      handleEditAccount,
      handleRemoveAccount,
      handleToggleExpand,
      handleCloseMenu,
      handleViewDashboard,
      handleViewBindCard,
      handleDeleteCursorAccount,
      handleLogout,
      setToast,
    ]
  );

  return {
    shouldUseVirtualScroll,
    isAllSelected,
    renderAccountCard,
  };
}
