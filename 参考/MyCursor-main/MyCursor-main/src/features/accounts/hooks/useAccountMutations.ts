/** 账号变更操作 hooks */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";

/** 切换账号 */
export function useSwitchAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (email: string) => invoke("switch_account", { email }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["current-account"] });
    },
  });
}

/** 带选项切换账号 */
export function useSwitchAccountWithOptions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { email: string; resetMachineId: boolean; useBoundMachineId: boolean }) =>
      invoke("switch_account_with_options", params),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** 添加账号 */
export function useAddAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: Record<string, unknown>) => invoke("add_account", params),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** 编辑账号 */
export function useEditAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: Record<string, unknown>) => invoke("edit_account", params),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** 删除账号 */
export function useRemoveAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (email: string) => invoke("remove_account", { email }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** 导入账号 */
export function useImportAccounts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (importFilePath: string) => invoke("import_accounts", { importFilePath }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** 导出账号 */
export function useExportAccounts() {
  return useMutation({
    mutationFn: (params: { exportPath: string; selectedEmails?: string[] }) =>
      invoke("export_accounts", params),
  });
}

/** 登出 */
export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => invoke("logout_current_account"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["current-account"] });
    },
  });
}
