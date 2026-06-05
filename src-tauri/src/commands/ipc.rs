// IPC 命令混淆层：所有对外暴露的 Tauri command 统一使用无意义短名
// 逆向二进制只能看到 x0a, x0b... 无法推断功能含义
// 内部实现保持原函数名，仅 IPC 接口层混淆

use super::*;

// === Settings ===
#[tauri::command]
pub async fn x0a() -> settings::AppSettings {
    settings::get_settings().await
}
#[tauri::command]
pub async fn x0b(settings: settings::AppSettings) -> Result<bool, String> {
    settings::save_settings(settings).await
}
#[tauri::command]
pub fn x0c(app_handle: tauri::AppHandle) {
    settings::quit_app(app_handle)
}

// === Cursor paths ===
#[tauri::command]
pub fn x1a() -> cursor_paths::CursorPaths {
    cursor_paths::get_cursor_paths()
}
#[tauri::command]
pub fn x1b() -> Result<String, String> {
    cursor_paths::get_user_data_path()
}

// === Machine ID ===
#[tauri::command]
pub async fn x2a() -> Result<String, String> {
    machine_id::get_machine_id().await
}
#[tauri::command]
pub async fn x2b() -> machine_id::ResetResult {
    machine_id::reset_cursor_machine_id().await
}
#[tauri::command]
pub async fn x2c() -> machine_id::ResetResult {
    machine_id::reset_machine_ids_standalone().await
}

// === Database ===
#[tauri::command]
pub async fn x3a() -> database::DatabaseSearchResult {
    database::find_all_cursor_databases().await
}
#[tauri::command]
pub async fn x3b(search_path: String) -> database::DatabaseSearchResult {
    database::manual_search_cursor_database(search_path).await
}
#[tauri::command]
pub async fn x3c(db_path: String) -> database::DbUpdateResult {
    database::update_cursor_sqlite_db(db_path).await
}
#[tauri::command]
pub async fn x3d(db_path: String, email: String, access_token: String, refresh_token: String, machine_id_reset: Option<bool>) -> database::DbUpdateResult {
    database::update_cursor_auth(db_path, email, access_token, refresh_token, machine_id_reset).await
}
#[tauri::command]
pub async fn x3e(db_path: String) -> database::DbUpdateResult {
    database::logout_current_cursor_account(db_path).await
}
#[tauri::command]
pub async fn x3f(db_path: String, email: String, access_token: String, refresh_token: String) -> database::DbUpdateResult {
    database::python_style_account_switch(db_path, email, access_token, refresh_token).await
}

// === File ops ===
#[tauri::command]
pub async fn x4a(file_path: String) -> Result<Option<String>, String> {
    file_ops::read_file_content(file_path).await
}
#[tauri::command]
pub async fn x4b(file_path: String, content: String) -> bool {
    file_ops::write_file_content(file_path, content).await
}
#[tauri::command]
pub async fn x4c(window: tauri::Window) -> Option<String> {
    file_ops::open_file_dialog(window).await
}
#[tauri::command]
pub async fn x4d(window: tauri::Window) -> Option<String> {
    file_ops::open_folder_dialog(window).await
}
#[tauri::command]
pub async fn x4e(url: String) -> Result<serde_json::Value, String> {
    file_ops::open_external_url(url).await
}

// === Cursor modify ===
#[tauri::command]
pub async fn x5a(main_path: String) -> cursor_modify::ModifyResult {
    cursor_modify::modify_cursor_main_js(main_path).await
}
#[tauri::command]
pub async fn x5b(file_path: String) -> cursor_modify::AnalysisResult {
    cursor_modify::analyze_cursor_file(file_path).await
}
#[tauri::command]
pub async fn x5c(file_path: String) -> cursor_modify::ModifyResult {
    cursor_modify::restore_cursor_backup(file_path).await
}
#[tauri::command]
pub async fn x5d(workbench_path: String, is_valid: bool, days: Option<u32>) -> cursor_modify::ModifyResult {
    cursor_modify::modify_cursor_workbench(workbench_path, is_valid, days).await
}

// === Cursor process ===
#[tauri::command]
pub async fn x6a() -> bool {
    cursor_process::check_cursor_running().await
}
#[tauri::command]
pub async fn x6b() -> cursor_process::ProcessResult {
    cursor_process::force_close_cursor().await
}
#[tauri::command]
pub async fn x6c(cursor_path: String) -> bool {
    cursor_process::restart_cursor(cursor_path).await
}
#[tauri::command]
pub async fn x6d() -> cursor_process::ProcessResult {
    cursor_process::restart_cursor_complete().await
}
#[tauri::command]
pub async fn x6e(workspace_path: Option<String>) -> cursor_process::ProcessResult {
    cursor_process::launch_cursor(workspace_path).await
}

// === Card ===
#[tauri::command]
pub async fn x7a(card_code: String) -> card::CardVerifyResult {
    card::verify_card(card_code).await
}
#[tauri::command]
pub async fn x7b(card_code: String) -> card::CardVerifyResult {
    card::verify_card_only(card_code).await
}
#[tauri::command]
pub async fn x7c(card_code: String) -> card::CardInfoResult {
    card::get_card_info(card_code).await
}
#[tauri::command]
pub async fn x7d(card_info: serde_json::Value) -> bool {
    card::save_card_info(card_info).await
}
#[tauri::command]
pub async fn x7e() -> Option<serde_json::Value> {
    card::load_card_info().await
}
#[tauri::command]
pub async fn x7f() -> bool {
    card::clear_card_info().await
}
#[tauri::command]
pub async fn x7g(card_code: String) -> serde_json::Value {
    card::record_usage(card_code).await
}

// === API ===
#[tauri::command]
pub async fn x8a() -> serde_json::Value {
    api::get_latest_notice().await
}
#[tauri::command]
pub async fn x8b() -> serde_json::Value {
    api::get_latest_tool_version().await
}
#[tauri::command]
pub async fn x8c() -> serde_json::Value {
    api::get_latest_popup().await
}
#[tauri::command]
pub async fn x8d() -> serde_json::Value {
    api::get_qrcode_image().await
}
#[tauri::command]
pub async fn x8e() -> serde_json::Value {
    api::check_version_update().await
}

// === Permissions ===
#[tauri::command]
pub async fn x9a() -> serde_json::Value {
    permissions::get_current_permissions().await
}
#[tauri::command]
pub async fn x9b() -> serde_json::Value {
    permissions::disable_cursor_auto_update().await
}

// === Model ===
#[tauri::command]
pub async fn xa1(model: Option<String>) -> serde_json::Value {
    model::set_cursor_default_model(model).await
}

// === Proxy ===
#[tauri::command]
pub async fn xb1() -> serde_json::Value {
    proxy::check_cursor_settings_status().await
}
#[tauri::command]
pub async fn xb2(enabled: bool) -> serde_json::Value {
    proxy::update_cursor_settings(enabled).await
}

// === Seamless switch ===
#[tauri::command]
pub async fn xc1(app: tauri::AppHandle) -> serde_json::Value {
    seamless_switch::patch_ext_host(app).await
}
#[tauri::command]
pub async fn xc2() -> serde_json::Value {
    seamless_switch::unpatch_ext_host().await
}
#[tauri::command]
pub async fn xc3(app: tauri::AppHandle) -> bool {
    seamless_switch::check_ext_host_patched(app).await
}
#[tauri::command]
pub async fn xc4(token: String) -> bool {
    seamless_switch::write_active_token(token).await
}
#[tauri::command]
pub async fn xc5() -> Option<String> {
    seamless_switch::read_active_token().await
}
#[tauri::command]
pub async fn xc6() -> bool {
    seamless_switch::clear_active_token().await
}
#[tauri::command]
pub async fn xc7(access_token: String) -> serde_json::Value {
    seamless_switch::check_cursor_usage(access_token).await
}
#[tauri::command]
pub async fn xc8(access_token: String) -> serde_json::Value {
    seamless_switch::get_cursor_account_quota(access_token).await
}
#[tauri::command]
pub async fn xc9(db_path: String, email: String, access_token: String, refresh_token: String) -> serde_json::Value {
    seamless_switch::seamless_switch_cmd(db_path, email, access_token, refresh_token).await
}
#[tauri::command]
pub async fn xca(db_path: String, card_code: String) -> serde_json::Value {
    seamless_switch::one_click_switch(db_path, card_code).await
}
#[tauri::command]
pub async fn xcb(app: tauri::AppHandle, enabled: bool, card_code: Option<String>) -> serde_json::Value {
    seamless_switch::toggle_auto_switch(app, enabled, card_code).await
}
#[tauri::command]
pub async fn xcc() -> serde_json::Value {
    seamless_switch::get_auto_switch_status().await
}

// === Workspace ===
#[tauri::command]
pub async fn xd1(db_path: String) -> serde_json::Value {
    workspace::save_current_workspace(db_path).await
}
#[tauri::command]
pub async fn xd2(db_path: String) -> serde_json::Value {
    workspace::load_saved_workspace(db_path).await
}

// === Updater ===
#[tauri::command]
pub async fn xe1(url: String, file_name: String) -> serde_json::Value {
    updater::download_and_update(url, file_name).await
}

// === Window control ===
#[tauri::command]
pub async fn xf1(window: tauri::Window) {
    window_ctrl::minimize_window(window).await
}
#[tauri::command]
pub async fn xf2(window: tauri::Window) {
    window_ctrl::close_window(window).await
}
#[tauri::command]
pub async fn xf3(window: tauri::Window) {
    window_ctrl::show_main_window(window).await
}

// === Log buffer / diagnostics ===
#[tauri::command]
pub async fn xg1() -> Vec<String> {
    log_buffer::get_log_entries().await
}
#[tauri::command]
pub async fn xg2() -> String {
    log_buffer::read_log_file().await
}
#[tauri::command]
pub async fn xg3() -> bool {
    log_buffer::clear_log_file().await
}
#[tauri::command]
pub async fn xg4() -> Result<(), String> {
    log_buffer::open_log_folder().await
}
#[tauri::command]
pub async fn xg5() -> String {
    log_buffer::read_exthost_log().await
}
