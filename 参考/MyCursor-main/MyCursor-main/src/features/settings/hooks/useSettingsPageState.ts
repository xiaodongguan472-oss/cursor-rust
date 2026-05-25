import { useState } from "react";

export function useSettingsPageState() {
  const [minimizeToTray, setMinimizeToTray] = useState(true);

  return {
    minimizeToTray,
    setMinimizeToTray,
  };
}
