/// 无缝切号命令入口
///
/// 使用新架构 services::SeamlessService 处理业务逻辑。
use crate::services::seamless_service::{SeamlessService, SeamlessStatus};
use crate::{log_info, log_error};
use tauri::State;

/// 启动无缝切号 HTTP 服务器
#[tauri::command]
#[specta::specta]
pub async fn start_seamless_server(
    service: State<'_, SeamlessService>,
    port: u16,
) -> Result<serde_json::Value, String> {
    service.start_server(port)
        .map(|_| serde_json::json!({"success": true, "message": format!("服务器已启动 (端口 {})", port)}))
        .map_err(|e| e.to_string())
}

/// 停止无缝切号 HTTP 服务器
#[tauri::command]
#[specta::specta]
pub async fn stop_seamless_server(
    service: State<'_, SeamlessService>,
) -> Result<serde_json::Value, String> {
    service.stop_server()
        .map(|_| serde_json::json!({"success": true, "message": "服务器已停止"}))
        .map_err(|e| e.to_string())
}

/// 注入 workbench
#[tauri::command]
#[specta::specta]
pub async fn inject_seamless(
    service: State<'_, SeamlessService>,
    port: u16,
) -> Result<serde_json::Value, String> {
    service.inject(port)
        .map_err(|e| e.to_string())
}

/// 恢复 workbench
#[tauri::command]
#[specta::specta]
pub async fn restore_seamless(
    service: State<'_, SeamlessService>,
) -> Result<serde_json::Value, String> {
    service.restore()
        .map_err(|e| e.to_string())
}

/// 获取无缝切号状态
#[tauri::command]
#[specta::specta]
pub async fn get_seamless_status(
    service: State<'_, SeamlessService>,
) -> Result<SeamlessStatus, String> {
    service.get_status()
        .map_err(|e| e.to_string())
}
