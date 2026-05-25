import { useCallback } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { AccountService } from "@/services/accountService";
import type { AccountsPageActionsContext } from "./accountsPageActionTypes.ts";

export function useAccountsPageImportExportActions({
  selectedAccounts,
  setToast,
  setConfirmDialog,
  addAccountToList,
}: AccountsPageActionsContext) {
  const handleExportSelectedAccounts = useCallback(async () => {
    if (selectedAccounts.size === 0) {
      setToast({ message: "请先选择要导出的账户", type: "error" });
      return;
    }

    try {
      const selectedPath = await open({
        directory: true,
        multiple: false,
        title: "选择导出目录",
      });

      if (!selectedPath) return;

      const selectedEmails = Array.from(selectedAccounts) as string[];
      const result = await AccountService.exportAccounts(selectedPath, selectedEmails);
      if (result.success) {
        setToast({
          message: `成功导出 ${selectedAccounts.size} 个账户到 ${result.exported_path}`,
          type: "success",
        });
      } else {
        setToast({ message: result.message, type: "error" });
      }
    } catch (error) {
      console.error("Failed to export accounts:", error);
      setToast({ message: "导出账户失败", type: "error" });
    }
  }, [selectedAccounts, setToast]);

  const handleImportAccounts = useCallback(async () => {
    try {
      const selectedFile = await open({
        multiple: false,
        directory: false,
        filters: [{ name: "JSON Files", extensions: ["json"] }],
        title: "选择要导入的JSON文件",
      });

      if (!selectedFile) return;

      const { readTextFile } = await import("@tauri-apps/plugin-fs");
      const fileContent = await readTextFile(selectedFile);
      const { workerManager } = await import("@/utils/workerManager");

      setToast({ message: "正在解析文件...", type: "success" });

      const parseResult = await workerManager.parseAccounts(fileContent);

      if (!parseResult.success || !parseResult.accounts) {
        setToast({ message: parseResult.error || "文件解析失败", type: "error" });
        return;
      }

      const accountCount = parseResult.accounts.length;

      const performImport = async (filePath: string, count: number) => {
        try {
          const result = await AccountService.importAccounts(filePath);
          if (result.success) {
            setToast({
              message: `${result.message} - 共 ${count} 个账号已添加到列表。💡 请点击"刷新"按钮获取订阅信息`,
              type: "success",
            });
            await addAccountToList("");
          } else {
            setToast({ message: result.message, type: "error" });
          }
        } catch (error) {
          console.error("Failed to import accounts:", error);
          setToast({ message: "导入账户失败", type: "error" });
        }
      };

      if (accountCount > 500) {
        setConfirmDialog({
          show: true,
          title: "⚠️ 大批量导入提示",
          message:
            `即将导入 ${accountCount} 个账号。\n\n` +
            `• 导入过程可能需要几秒钟\n` +
            `• 导入后账号会立即显示在列表中\n` +
            `• 订阅信息需要手动点击\"刷新\"按钮获取\n\n` +
            `是否继续导入？`,
          onConfirm: async () => {
            setConfirmDialog((prev) => ({ ...prev, show: false }));
            await performImport(selectedFile, accountCount);
          },
        });
      } else {
        await performImport(selectedFile, accountCount);
      }
    } catch (error) {
      console.error("Failed to import accounts:", error);
      setToast({ message: "导入账户失败", type: "error" });
    }
  }, [addAccountToList, setConfirmDialog, setToast]);

  return {
    handleExportSelectedAccounts,
    handleImportAccounts,
  };
}
