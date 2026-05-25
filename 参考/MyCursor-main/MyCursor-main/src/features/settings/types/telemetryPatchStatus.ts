/** 与后端 `TelemetryPatchStatus`（Specta）对齐 */
export type TelemetryPatchStatus = {
  supported: boolean;
  applied: boolean;
  backup_exists: boolean;
  extension_main_path?: string | null;
  extension_host_path?: string | null;
  details: string[];
};
