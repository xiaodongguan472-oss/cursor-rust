import { invoke } from "@tauri-apps/api/core";
import { SeamlessStatus, SeamlessResult } from "../types/account";

/** 无感换号服务 */
export class SeamlessService {
  static async getStatus(): Promise<SeamlessStatus> {
    return await invoke<SeamlessStatus>("get_seamless_status");
  }

  static async inject(port: number): Promise<SeamlessResult> {
    return await invoke<SeamlessResult>("inject_seamless", { port });
  }

  static async restore(): Promise<SeamlessResult> {
    return await invoke<SeamlessResult>("restore_seamless");
  }

  static async startServer(
    port: number
  ): Promise<{ success: boolean; message: string }> {
    return await invoke<{ success: boolean; message: string }>(
      "start_seamless_server",
      { port }
    );
  }

  static async stopServer(): Promise<{ success: boolean; message: string }> {
    return await invoke<{ success: boolean; message: string }>(
      "stop_seamless_server"
    );
  }
}
