use std::fs;
use tauri::api::dialog::FileDialogBuilder;

#[tauri::command]
pub async fn read_file_content(file_path: String) -> Result<Option<String>, String> {
    match fs::read_to_string(&file_path) {
        Ok(content) => Ok(Some(content)),
        Err(_) => Ok(None),
    }
}

#[tauri::command]
pub async fn write_file_content(file_path: String, content: String) -> bool {
    fs::write(&file_path, &content).is_ok()
}

#[tauri::command]
pub async fn open_file_dialog(_window: tauri::Window) -> Option<String> {
    let (tx, rx) = std::sync::mpsc::channel();
    FileDialogBuilder::new()
        .add_filter("Cursor配置文件", &["json"])
        .pick_file(move |path| {
            let _ = tx.send(path.map(|p| p.to_string_lossy().to_string()));
        });
    rx.recv().ok().flatten()
}

#[tauri::command]
pub async fn open_folder_dialog(_window: tauri::Window) -> Option<String> {
    let (tx, rx) = std::sync::mpsc::channel();
    FileDialogBuilder::new()
        .set_title("选择Cursor安装目录")
        .pick_folder(move |path| {
            let _ = tx.send(path.map(|p| p.to_string_lossy().to_string()));
        });
    rx.recv().ok().flatten()
}

#[tauri::command]
pub async fn open_external_url(url: String) -> Result<serde_json::Value, String> {
    open::that(&url).map_err(|e| format!("打开外部链接失败: {}", e))?;
    Ok(serde_json::json!({"success": true}))
}
