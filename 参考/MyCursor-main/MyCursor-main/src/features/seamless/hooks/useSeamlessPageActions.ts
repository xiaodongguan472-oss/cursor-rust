import { useCallback } from "react";
import { SeamlessService } from "@/services/seamlessService";
import type { SeamlessStatus, SeamlessResult } from "@/types/account";

interface UseSeamlessPageActionsParams {
  port: number;
  setStatus: (status: SeamlessStatus | null) => void;
  setActionLoading: (loading: string | null) => void;
  setLastResult: (result: SeamlessResult | null) => void;
  setPort: (port: number) => void;
  showSuccess: (message: string) => void;
  showError: (message: string) => void;
  showWarning: (message: string) => void;
  showConfirm: (options: {
    title: string;
    message: string;
    confirmText: string;
    cancelText: string;
    type: "danger" | "warning" | "info";
    onConfirm: () => void;
  }) => void;
}

export function useSeamlessPageActions({
  port,
  setStatus,
  setActionLoading,
  setLastResult,
  setPort,
  showSuccess,
  showError,
  showWarning,
  showConfirm,
}: UseSeamlessPageActionsParams) {
  const loadStatus = useCallback(async () => {
    try {
      const s = await SeamlessService.getStatus();
      setStatus(s);
      if (s.port) setPort(s.port);
    } catch {
      // 静默处理
    }
  }, [setStatus, setPort]);

  const handleInject = useCallback(() => {
    const doInject = async () => {
      try {
        setActionLoading("inject");
        const result = await SeamlessService.inject(port);
        setLastResult(result);
        if (result.success) showSuccess(result.message);
        else showError(result.message);
        await loadStatus();
      } catch (error: unknown) {
        showError(error instanceof Error ? error.message : "注入失败");
      } finally {
        setActionLoading(null);
      }
    };

    showConfirm({
      title: "注入无感换号",
      message:
        "将修改 Cursor 的 workbench.desktop.main.js 文件，启用无感换号。原始文件会自动备份。\n\n请确保 Cursor 已完全关闭。\n使用期间需保持 MyCursor 运行并启动 HTTP 服务器。",
      confirmText: "注入",
      cancelText: "取消",
      type: "warning",
      onConfirm: doInject,
    });
  }, [port, setActionLoading, setLastResult, showSuccess, showError, showConfirm, loadStatus]);

  const handleRestore = useCallback(() => {
    const doRestore = async () => {
      try {
        setActionLoading("restore");
        const result = await SeamlessService.restore();
        setLastResult(result);
        if (result.success) showSuccess(result.message);
        else showWarning(result.message);
        await loadStatus();
      } catch (error: unknown) {
        showError(error instanceof Error ? error.message : "恢复失败");
      } finally {
        setActionLoading(null);
      }
    };

    showConfirm({
      title: "恢复原始文件",
      message: "将恢复 Cursor 的 workbench.desktop.main.js，移除无感换号。\n\n恢复后请重启 Cursor。",
      confirmText: "恢复",
      cancelText: "取消",
      type: "danger",
      onConfirm: doRestore,
    });
  }, [setActionLoading, setLastResult, showSuccess, showError, showWarning, showConfirm, loadStatus]);

  const handleStartServer = useCallback(async () => {
    try {
      setActionLoading("start");
      await SeamlessService.startServer(port);
      showSuccess("HTTP 服务器已启动");
      await loadStatus();
    } catch (error: unknown) {
      showError(error instanceof Error ? error.message : "启动失败");
    } finally {
      setActionLoading(null);
    }
  }, [port, setActionLoading, showSuccess, showError, loadStatus]);

  const handleStopServer = useCallback(async () => {
    try {
      setActionLoading("stop");
      await SeamlessService.stopServer();
      showSuccess("HTTP 服务器已停止");
      await loadStatus();
    } catch (error: unknown) {
      showError(error instanceof Error ? error.message : "停止失败");
    } finally {
      setActionLoading(null);
    }
  }, [setActionLoading, showSuccess, showError, loadStatus]);

  return {
    loadStatus,
    handleInject,
    handleRestore,
    handleStartServer,
    handleStopServer,
  };
}
