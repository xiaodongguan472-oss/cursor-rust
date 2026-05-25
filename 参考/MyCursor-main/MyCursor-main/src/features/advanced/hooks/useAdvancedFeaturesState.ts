import { useState } from "react";
import type { TelemetryPatchStatus } from "@/features/settings/types/telemetryPatchStatus";
import type { WindowsUserInfo } from "@/features/identity/hooks/useIdentityPageState";

export function useAdvancedFeaturesState() {
  const [telemetryStatus, setTelemetryStatus] = useState<TelemetryPatchStatus | null>(null);
  const [telemetryLoading, setTelemetryLoading] = useState(false);
  const [customCursorPath, setCustomCursorPath] = useState("");
  const [currentCustomPath, setCurrentCustomPath] = useState<string | null>(null);
  const [autoUpdateDisabled, setAutoUpdateDisabled] = useState<boolean | null>(null);
  const [isWindows, setIsWindows] = useState(false);
  const [windowsUsers, setWindowsUsers] = useState<WindowsUserInfo[]>([]);
  const [syncingUser, setSyncingUser] = useState<string | null>(null);

  return {
    telemetryStatus,
    setTelemetryStatus,
    telemetryLoading,
    setTelemetryLoading,
    customCursorPath,
    setCustomCursorPath,
    currentCustomPath,
    setCurrentCustomPath,
    autoUpdateDisabled,
    setAutoUpdateDisabled,
    isWindows,
    setIsWindows,
    windowsUsers,
    setWindowsUsers,
    syncingUser,
    setSyncingUser,
  };
}
