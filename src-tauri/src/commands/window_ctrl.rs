#[tauri::command]
pub async fn minimize_window(window: tauri::Window) {
    let _ = window.minimize();
}

#[tauri::command]
pub async fn close_window(window: tauri::Window) {
    let _ = window.close();
}

#[tauri::command]
pub async fn show_main_window(window: tauri::Window) {
    let _ = window.show();
    let _ = window.set_focus();
}
