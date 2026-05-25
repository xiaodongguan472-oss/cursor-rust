import { useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";

interface UseSettingsPageEffectsParams {
  setMinimizeToTray: (value: boolean) => void;
}

export function useSettingsPageEffects({ setMinimizeToTray }: UseSettingsPageEffectsParams) {
  useEffect(() => {
    invoke<{ minimize_to_tray: boolean }>("get_close_behavior")
      .then((result) => setMinimizeToTray(result.minimize_to_tray))
      .catch(() => {});
  }, [setMinimizeToTray]);
}
