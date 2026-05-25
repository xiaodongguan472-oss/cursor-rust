import { useToast, ToastManager, useConfirmDialog, Icon } from "@/components";
import {
  StatusCard,
  InjectionControl,
  ServerControl,
  ResultCard,
  UsageGuide,
} from "./components";
import { useSeamlessPageState } from "./hooks/useSeamlessPageState";
import { useSeamlessPageActions } from "./hooks/useSeamlessPageActions";
import { useSeamlessPageEffects } from "./hooks/useSeamlessPageEffects";

const SeamlessPage = () => {
  const {
    status,
    setStatus,
    port,
    setPort,
    actionLoading,
    setActionLoading,
    lastResult,
    setLastResult,
  } = useSeamlessPageState();

  const { toasts, removeToast, showSuccess, showError, showWarning } = useToast();
  const { showConfirm, ConfirmDialog } = useConfirmDialog();

  const {
    loadStatus,
    handleInject,
    handleRestore,
    handleStartServer,
    handleStopServer,
  } = useSeamlessPageActions({
    port,
    setStatus,
    setActionLoading,
    setLastResult,
    setPort,
    showSuccess,
    showError,
    showWarning,
    showConfirm,
  });

  useSeamlessPageEffects({ loadStatus });

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <ToastManager toasts={toasts} removeToast={removeToast} />
      <ConfirmDialog />

      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3" style={{ color: "var(--text-primary)" }}>
          <Icon name="bolt" size={28} />
          无感换号
        </h1>
        <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          注入插件到 Cursor，在界面右下角添加 ⚡ 换号按钮，点击即可弹出账号选择（支持按类型/标签筛选），选择后无感切换。
        </p>
      </div>

      <StatusCard status={status} port={port} />

      <InjectionControl
        status={status}
        port={port}
        actionLoading={actionLoading}
        onPortChange={setPort}
        onInject={handleInject}
        onRestore={handleRestore}
      />

      <ServerControl
        status={status}
        actionLoading={actionLoading}
        onStart={handleStartServer}
        onStop={handleStopServer}
      />

      {lastResult && <ResultCard result={lastResult} />}

      <UsageGuide />
    </div>
  );
};

export default SeamlessPage;
