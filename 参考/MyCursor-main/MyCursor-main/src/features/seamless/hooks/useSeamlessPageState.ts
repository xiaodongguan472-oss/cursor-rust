import { useState } from "react";
import type { SeamlessStatus, SeamlessResult } from "@/types/account";

const DEFAULT_PORT = 36529;

export function useSeamlessPageState() {
  const [status, setStatus] = useState<SeamlessStatus | null>(null);
  const [port, setPort] = useState<number>(DEFAULT_PORT);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<SeamlessResult | null>(null);

  return {
    status,
    setStatus,
    port,
    setPort,
    actionLoading,
    setActionLoading,
    lastResult,
    setLastResult,
  };
}
