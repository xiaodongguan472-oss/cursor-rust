import { useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";

interface UseSettingsPageActionsParams {
  setMinimizeToTray: (value: boolean) => void;
  showSuccess: (message: string) => void;
  showError: (message: string) => void;
}

export function useSettingsPageActions({
  setMinimizeToTray,
  showSuccess,
  showError,
}: UseSettingsPageActionsParams) {
  const handleSetCloseBehavior = useCallback(
    async (minimize: boolean) => {
      try {
        const result = await invoke<{ success: boolean; message: string }>(
          "set_close_behavior",
          { minimizeToTray: minimize }
        );
        if (result.success) {
          setMinimizeToTray(minimize);
          showSuccess(result.message);
        }
      } catch {
        showError("设置关闭行为失败");
      }
    },
    [setMinimizeToTray, showSuccess, showError]
  );

  const handleClearUsageData = useCallback(async () => {
    try {
      const result = await invoke<{ success: boolean; message: string }>("clear_usage_data");
      if (result.success) showSuccess("用量数据已清除");
      else showError(result.message);
    } catch {
      showError("清除数据失败");
    }
  }, [showSuccess, showError]);

  const handleClearAccountCache = useCallback(async () => {
    try {
      const result = await invoke<{ success: boolean; message: string }>("clear_account_cache");
      if (result.success) showSuccess("账户缓存已清除");
      else showError(result.message);
    } catch {
      showError("清除缓存失败");
    }
  }, [showSuccess, showError]);

  const handleClearEventsData = useCallback(async () => {
    try {
      const result = await invoke<{ success: boolean; message: string }>("clear_events_data");
      if (result.success) showSuccess("事件数据已清除");
      else showError(result.message);
    } catch {
      showError("清除数据失败");
    }
  }, [showSuccess, showError]);

  return {
    handleSetCloseBehavior,
    handleClearUsageData,
    handleClearAccountCache,
    handleClearEventsData,
  };
}
