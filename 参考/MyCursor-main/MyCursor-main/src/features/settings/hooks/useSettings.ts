/** 设置项读写 hooks */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";

/** 获取自动更新状态 */
export function useAutoUpdateStatus() {
  return useQuery({
    queryKey: ["auto-update-status"],
    queryFn: () => invoke("get_auto_update_status"),
  });
}

/** 禁用自动更新 */
export function useDisableAutoUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => invoke("disable_auto_update"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auto-update-status"] });
    },
  });
}

/** 启用自动更新 */
export function useEnableAutoUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => invoke("enable_auto_update"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auto-update-status"] });
    },
  });
}

/** 清除用量缓存 */
export function useClearUsageCache() {
  return useMutation({
    mutationFn: () => invoke("clear_usage_data"),
  });
}

/** 清除账号缓存 */
export function useClearAccountCache() {
  return useMutation({
    mutationFn: () => invoke("clear_account_cache"),
  });
}

/** 清除事件缓存 */
export function useClearEventsCache() {
  return useMutation({
    mutationFn: () => invoke("clear_events_data"),
  });
}

/** 获取预设标签 */
export function usePresetTags() {
  return useQuery({
    queryKey: ["preset-tags"],
    queryFn: () => invoke("get_preset_tags"),
  });
}

/** 保存预设标签 */
export function useSavePresetTags() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tags: string[]) => invoke("save_preset_tags", { tags }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["preset-tags"] });
    },
  });
}
