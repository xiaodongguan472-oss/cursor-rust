import { useCallback } from "react";
import { AccountService } from "@/services/accountService";
import type { AccountInfo } from "@/types/account";
import type { AccountsPageActionsContext } from "./accountsPageActionTypes.ts";

export function useAccountsPageSessionActions({
  switchModal,
  setToast,
  setConfirmDialog,
  setSwitchModal,
  loadAccounts,
}: AccountsPageActionsContext) {
  const handleSwitchAccount = useCallback(
    (account: AccountInfo) => {
      setSwitchModal({
        show: true,
        account,
        resetMachineId: true,
        machineIdOption: account.machine_ids ? "bound" : "new",
      });
    },
    [setSwitchModal]
  );

  const handleSwitchConfirm = useCallback(async () => {
    const { account, resetMachineId, machineIdOption } = switchModal;
    if (!account) return;

    setSwitchModal((prev) => ({ ...prev, show: false }));

    try {
      const { CursorService } = await import("@/services/cursorService");
      const isAdmin = await CursorService.checkAdminPrivileges();

      if (!isAdmin) {
        setConfirmDialog({
          show: true,
          title: "需要管理员权限",
          message: "切换账户需要管理员权限才能修改 Cursor 配置文件。\n\n请以管理员身份运行本程序后重试。",
          onConfirm: () => setConfirmDialog((prev) => ({ ...prev, show: false })),
        });
        return;
      }

      const useBoundMachineId = resetMachineId && machineIdOption === "bound";
      const resetMachineIdFlag = resetMachineId && machineIdOption === "new";
      const { invoke } = await import("@tauri-apps/api/core");
      const result = await invoke<{ success: boolean; message: string }>("switch_account_with_options", {
        email: account.email,
        resetMachineId: resetMachineIdFlag,
        useBoundMachineId,
      });

      if (result.success) {
        await loadAccounts();
        try {
          await invoke<{ success: boolean; message: string }>("launch_cursor");
          setToast({ message: "账户切换成功，Cursor 已启动", type: "success" });
        } catch (launchErr) {
          setToast({ message: `账户切换成功，但启动 Cursor 失败: ${launchErr}`, type: "error" });
        }
      } else {
        setToast({ message: result.message, type: "error" });
      }
    } catch (error) {
      console.error("Failed to switch account:", error);
      setToast({ message: "切换账户失败", type: "error" });
    }
  }, [loadAccounts, setConfirmDialog, setSwitchModal, setToast, switchModal]);

  const handleViewDashboard = useCallback(
    async (account: AccountInfo) => {
      if (!account.workos_cursor_session_token) {
        setToast({ message: "该账户没有WorkOS Session Token，无法查看主页", type: "error" });
        return;
      }

      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("open_cursor_dashboard", {
          workosCursorSessionToken: account.workos_cursor_session_token,
        });
        setToast({ message: "Cursor主页已打开", type: "success" });
      } catch (error) {
        console.error("Failed to open dashboard:", error);
        setToast({ message: "打开主页失败", type: "error" });
      }
    },
    [setToast]
  );

  const handleViewBindCard = useCallback(
    async (account: AccountInfo) => {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        const result = await invoke<{ success: boolean; message: string }>("open_bind_card_info", {
          accessToken: account.token,
          workosCursorSessionToken: account.workos_cursor_session_token || null,
        });
        setToast({ message: result.message, type: result.success ? "success" : "error" });
      } catch (error) {
        console.error("Failed to open bind card info:", error);
        setToast({ message: "打开绑卡信息失败", type: "error" });
      }
    },
    [setToast]
  );

  const handleDeleteCursorAccount = useCallback(
    (account: AccountInfo) => {
      setConfirmDialog({
        show: true,
        title: "注销 Cursor 账户",
        message: `确定要注销 Cursor 账户 ${account.email} 吗？\n\n此操作将从 Cursor 服务器永久删除该账户，不可恢复！`,
        type: "danger",
        confirmText: "确认注销",
        onConfirm: async () => {
          setConfirmDialog((prev) => ({ ...prev, show: false }));
          try {
            const result = await AccountService.deleteCursorAccount(
              account.token,
              account.workos_cursor_session_token || undefined
            );
            setToast({ message: result.message, type: result.success ? "success" : "error" });
          } catch (error) {
            console.error("Failed to delete cursor account:", error);
            setToast({ message: "注销账户失败", type: "error" });
          }
        },
      });
    },
    [setConfirmDialog, setToast]
  );

  const handleLogout = useCallback(() => {
    setConfirmDialog({
      show: true,
      title: "登出当前账号",
      message: "确定要登出吗？\n\n此操作将清除本地认证数据（storage.json 和 SQLite），下次使用需要重新登录。",
      type: "warning",
      confirmText: "确认登出",
      onConfirm: async () => {
        setConfirmDialog((prev) => ({ ...prev, show: false }));
        try {
          const result = await AccountService.logoutCurrentAccount();
          setToast({ message: result.message || "已登出", type: result.success ? "success" : "error" });
          if (result.success) {
            await loadAccounts();
          }
        } catch (error) {
          console.error("Failed to logout:", error);
          setToast({ message: "登出失败", type: "error" });
        }
      },
    });
  }, [loadAccounts, setConfirmDialog, setToast]);

  return {
    handleSwitchAccount,
    handleSwitchConfirm,
    handleViewDashboard,
    handleViewBindCard,
    handleDeleteCursorAccount,
    handleLogout,
  };
}
