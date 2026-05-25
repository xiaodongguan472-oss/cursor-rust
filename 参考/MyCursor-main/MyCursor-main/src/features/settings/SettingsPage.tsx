import { Card, useToast, ToastManager, Icon } from "@/components";
import { CloseBehaviorSettings, CacheManagement, DataInfo } from "./components";
import { useSettingsPageState } from "./hooks/useSettingsPageState";
import { useSettingsPageActions } from "./hooks/useSettingsPageActions";
import { useSettingsPageEffects } from "./hooks/useSettingsPageEffects";

const SettingsPage = () => {
  const { minimizeToTray, setMinimizeToTray } = useSettingsPageState();
  const { toasts, removeToast, showSuccess, showError } = useToast();

  const { handleSetCloseBehavior, handleClearUsageData, handleClearAccountCache, handleClearEventsData } =
    useSettingsPageActions({
      setMinimizeToTray,
      showSuccess,
      showError,
    });

  useSettingsPageEffects({ setMinimizeToTray });

  return (
    <div className="space-y-6">
      <ToastManager toasts={toasts} removeToast={removeToast} />

      <Card className="p-6">
        <h2 className="text-2xl font-bold mb-6 flex items-center gap-3" style={{ color: "var(--text-primary)" }}>
          <Icon name="settings" size={28} />
          应用设置
        </h2>

        <div className="space-y-6">
          <CloseBehaviorSettings minimizeToTray={minimizeToTray} onSetBehavior={handleSetCloseBehavior} />
        </div>

        <hr style={{ borderColor: "var(--border-primary)", margin: "24px 0" }} />

        <div className="space-y-6">
          <CacheManagement
            onClearUsageData={handleClearUsageData}
            onClearAccountCache={handleClearAccountCache}
            onClearEventsData={handleClearEventsData}
          />
        </div>
      </Card>

      <DataInfo />
    </div>
  );
};

export default SettingsPage;
