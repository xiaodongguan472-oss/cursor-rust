import { useState } from "react";
import type { AccountInfo } from "@/types/account";
import type { AggregatedUsageData, UsageEvent } from "@/types/usage";

export interface AccountsPageToastState {
  message: string;
  type: "success" | "error";
}

export interface AccountsPageConfirmDialogState {
  show: boolean;
  title: string;
  message: string;
  onConfirm: (checkboxValue?: boolean) => void;
  checkboxLabel?: string;
  checkboxDefaultChecked?: boolean;
  type?: "danger" | "warning" | "info";
  confirmText?: string;
}

export interface AccountsPageSwitchModalState {
  show: boolean;
  account: AccountInfo | null;
  resetMachineId: boolean;
  machineIdOption: "bound" | "new";
}

export interface AccountsPageSelectedUsageState {
  account: AccountInfo;
  usageData: AggregatedUsageData | null;
  events: UsageEvent[] | null;
  totalEvents: number;
  loading: boolean;
  useEventBasedCalculation: boolean;
}

export function useAccountsPageState() {
  const [showAddForm, setShowAddForm] = useState(false);
  const [showEditForm, setShowEditForm] = useState(false);
  const [editingAccount, setEditingAccount] = useState<AccountInfo | null>(null);
  const [expandedAccountEmail, setExpandedAccountEmail] = useState<string | null>(null);
  const [closingAccountEmail, setClosingAccountEmail] = useState<string | null>(null);
  const [usageModalOpen, setUsageModalOpen] = useState(false);
  const [selectedAccountUsage, setSelectedAccountUsage] = useState<AccountsPageSelectedUsageState | null>(null);
  const [toast, setToast] = useState<AccountsPageToastState | null>(null);
  const [confirmDialog, setConfirmDialog] = useState<AccountsPageConfirmDialogState>({
    show: false,
    title: "",
    message: "",
    onConfirm: () => {},
  });
  const [switchModal, setSwitchModal] = useState<AccountsPageSwitchModalState>({
    show: false,
    account: null,
    resetMachineId: true,
    machineIdOption: "bound",
  });

  return {
    showAddForm,
    setShowAddForm,
    showEditForm,
    setShowEditForm,
    editingAccount,
    setEditingAccount,
    expandedAccountEmail,
    setExpandedAccountEmail,
    closingAccountEmail,
    setClosingAccountEmail,
    usageModalOpen,
    setUsageModalOpen,
    selectedAccountUsage,
    setSelectedAccountUsage,
    toast,
    setToast,
    confirmDialog,
    setConfirmDialog,
    switchModal,
    setSwitchModal,
  };
}
