import type { Dispatch, SetStateAction } from "react";
import type { AccountInfo } from "@/types/account";
import type {
  AccountsPageConfirmDialogState,
  AccountsPageSelectedUsageState,
  AccountsPageSwitchModalState,
  AccountsPageToastState,
} from "./useAccountsPageState";

export interface RefreshSingleAccountResult {
  success: boolean;
  message?: string;
}

export interface CurrentAccountRefreshResult {
  success: boolean;
  currentAccount: AccountInfo | null;
}

export interface OperationResult {
  success: boolean;
  message?: string;
}

export interface AccountsPageActionsContext {
  selectedAccounts: Set<string>;
  expandedAccountEmail: string | null;
  switchModal: AccountsPageSwitchModalState;
  setShowAddForm: Dispatch<SetStateAction<boolean>>;
  setShowEditForm: Dispatch<SetStateAction<boolean>>;
  setEditingAccount: Dispatch<SetStateAction<AccountInfo | null>>;
  setExpandedAccountEmail: Dispatch<SetStateAction<string | null>>;
  setClosingAccountEmail: Dispatch<SetStateAction<string | null>>;
  setUsageModalOpen: Dispatch<SetStateAction<boolean>>;
  setSelectedAccountUsage: Dispatch<SetStateAction<AccountsPageSelectedUsageState | null>>;
  setToast: Dispatch<SetStateAction<AccountsPageToastState | null>>;
  setConfirmDialog: Dispatch<SetStateAction<AccountsPageConfirmDialogState>>;
  setSwitchModal: Dispatch<SetStateAction<AccountsPageSwitchModalState>>;
  loadAccounts: () => Promise<unknown>;
  addAccountToList: (email: string) => Promise<unknown>;
  refreshSingleAccount: (account: AccountInfo, index: number) => Promise<RefreshSingleAccountResult>;
  removeAccount: (email: string) => Promise<OperationResult>;
  refreshCurrentAccount: () => Promise<CurrentAccountRefreshResult>;
  refreshSelectedAccounts: () => Promise<OperationResult>;
  refreshAllAccounts: () => Promise<OperationResult>;
  removeSelectedAccounts: () => Promise<OperationResult>;
}
