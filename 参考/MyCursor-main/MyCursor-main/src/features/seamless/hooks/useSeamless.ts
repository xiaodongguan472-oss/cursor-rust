/** 无缝切号状态与操作 hooks */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";

/** 查询无缝切号状态（每 5 秒自动轮询） */
export function useSeamlessStatus() {
  return useQuery({
    queryKey: ["seamless-status"],
    queryFn: () => invoke("get_seamless_status"),
    refetchInterval: 5000,
  });
}

/** 注入 workbench */
export function useInjectSeamless() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (port: number) => invoke("inject_seamless", { port }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["seamless-status"] });
    },
  });
}

/** 恢复 workbench */
export function useRestoreSeamless() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => invoke("restore_seamless"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["seamless-status"] });
    },
  });
}

/** 无缝切号服务器控制 */
export function useSeamlessServer() {
  const qc = useQueryClient();

  const start = useMutation({
    mutationFn: (port: number) => invoke("start_seamless_server", { port }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["seamless-status"] });
    },
  });

  const stop = useMutation({
    mutationFn: () => invoke("stop_seamless_server"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["seamless-status"] });
    },
  });

  return { start, stop };
}
