import { Card, useToast, ToastManager, Icon } from "@/components";
import { AdvancedFeatures } from "./components";
import { useAdvancedFeaturesState } from "./hooks/useAdvancedFeaturesState";
import { useAdvancedFeaturesActions } from "./hooks/useAdvancedFeaturesActions";
import { useAdvancedFeaturesEffects } from "./hooks/useAdvancedFeaturesEffects";

const AdvancedFeaturesPage = () => {
  const {
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
  } = useAdvancedFeaturesState();

  const { toasts, removeToast, showSuccess, showError } = useToast();

  const {
    handleRefreshTelemetryStatus,
    handleApplyTelemetryPatch,
    handleRestoreTelemetryPatch,
    handleToggleAutoUpdate,
    handleSetCustomPath,
    handleClearCustomPath,
    handleFillDetectedPath,
    handleBrowseCustomPath,
    handleGetLogPath,
    handleOpenLogDirectory,
    handleDetectWindowsUsers,
    handleSyncUser,
  } = useAdvancedFeaturesActions({
    setTelemetryStatus,
    setTelemetryLoading,
    customCursorPath,
    autoUpdateDisabled,
    setCurrentCustomPath,
    setCustomCursorPath,
    setAutoUpdateDisabled,
    setWindowsUsers,
    setSyncingUser,
    showSuccess,
    showError,
  });

  useAdvancedFeaturesEffects({
    setTelemetryStatus,
    setTelemetryLoading,
    setCurrentCustomPath,
    setCustomCursorPath,
    setAutoUpdateDisabled,
    setIsWindows,
  });

  return (
    <div className="space-y-6">
      <ToastManager toasts={toasts} removeToast={removeToast} />

      <Card className="p-6">
        <h2 className="text-2xl font-bold mb-6 flex items-center gap-3" style={{ color: "var(--text-primary)" }}>
          <Icon name="power" size={28} />
          高级功能
        </h2>

        <AdvancedFeatures
          telemetryStatus={telemetryStatus}
          telemetryLoading={telemetryLoading}
          onRefreshTelemetryStatus={handleRefreshTelemetryStatus}
          onApplyTelemetryPatch={handleApplyTelemetryPatch}
          onRestoreTelemetryPatch={handleRestoreTelemetryPatch}
          autoUpdateDisabled={autoUpdateDisabled}
          onToggleAutoUpdate={handleToggleAutoUpdate}
          isWindows={isWindows}
          customCursorPath={customCursorPath}
          currentCustomPath={currentCustomPath}
          onCustomPathChange={setCustomCursorPath}
          onSetCustomPath={handleSetCustomPath}
          onFillDetectedPath={handleFillDetectedPath}
          onClearCustomPath={handleClearCustomPath}
          onBrowseCustomPath={handleBrowseCustomPath}
          onGetLogPath={handleGetLogPath}
          onOpenLogDirectory={handleOpenLogDirectory}
          windowsUsers={windowsUsers}
          syncingUser={syncingUser}
          onDetectWindowsUsers={handleDetectWindowsUsers}
          onSyncUser={handleSyncUser}
        />
      </Card>
    </div>
  );
};

export default AdvancedFeaturesPage;
