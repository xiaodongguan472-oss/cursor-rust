#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

mod commands;

use commands::*;

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            // Settings
            settings::get_settings,
            settings::save_settings,
            settings::quit_app,
            // Cursor paths
            cursor_paths::get_cursor_paths,
            cursor_paths::get_user_data_path,
            // Machine ID
            machine_id::get_machine_id,
            machine_id::reset_cursor_machine_id,
            machine_id::reset_machine_ids_standalone,
            // Database
            database::find_all_cursor_databases,
            database::manual_search_cursor_database,
            database::update_cursor_sqlite_db,
            database::update_cursor_auth,
            database::logout_current_cursor_account,
            database::python_style_account_switch,
            // File operations
            file_ops::read_file_content,
            file_ops::write_file_content,
            file_ops::open_file_dialog,
            file_ops::open_folder_dialog,
            file_ops::open_external_url,
            // Cursor file modification
            cursor_modify::modify_cursor_main_js,
            cursor_modify::analyze_cursor_file,
            cursor_modify::restore_cursor_backup,
            cursor_modify::modify_cursor_workbench,
            // Cursor process management
            cursor_process::check_cursor_running,
            cursor_process::force_close_cursor,
            cursor_process::restart_cursor,
            cursor_process::restart_cursor_complete,
            cursor_process::launch_cursor,
            // Card verification
            card::verify_card,
            card::verify_card_only,
            card::get_card_info,
            card::save_card_info,
            card::load_card_info,
            card::clear_card_info,
            card::record_usage,
            // API calls
            api::get_latest_notice,
            api::get_latest_tool_version,
            api::get_latest_popup,
            api::get_qrcode_image,
            api::check_version_update,
            // Permissions
            permissions::get_current_permissions,
            permissions::disable_cursor_auto_update,
            // Model settings
            model::set_cursor_default_model,
            // Proxy settings
            proxy::check_cursor_settings_status,
            proxy::update_cursor_settings,
            // Seamless switch
            seamless_switch::patch_ext_host,
            seamless_switch::unpatch_ext_host,
            seamless_switch::check_ext_host_patched,
            seamless_switch::write_active_token,
            seamless_switch::read_active_token,
            seamless_switch::clear_active_token,
            seamless_switch::check_cursor_usage,
            seamless_switch::get_cursor_account_quota,
            seamless_switch::seamless_switch_cmd,
            seamless_switch::one_click_switch,
            seamless_switch::toggle_auto_switch,
            seamless_switch::get_auto_switch_status,
            // Workspace
            workspace::save_current_workspace,
            workspace::load_saved_workspace,
            // Updater
            updater::download_and_update,
            // Window control
            window_ctrl::minimize_window,
            window_ctrl::close_window,
            window_ctrl::show_main_window,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
