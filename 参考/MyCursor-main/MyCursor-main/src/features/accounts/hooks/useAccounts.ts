/** 账号列表查询 hook */
import { useQuery } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";

/** 获取账号列表 */
export function useAccounts() {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: () => invoke("get_account_list"),
    staleTime: 30_000,
  });
}

/** 获取当前账号 */
export function useCurrentAccount() {
  return useQuery({
    queryKey: ["current-account"],
    queryFn: () => invoke("get_current_account"),
  });
}
