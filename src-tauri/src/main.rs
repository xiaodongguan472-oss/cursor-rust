#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

mod commands;

use commands::*;

fn main() {
    // Release 模式：自定义 panic hook，隐藏源码文件路径
    #[cfg(not(debug_assertions))]
    std::panic::set_hook(Box::new(|_| {
        std::process::abort();
    }));

    // 反逆向：拒绝调试器附加 + 后台监控（必须在 tauri 启动前）
    commands::anti_debug::init();

    // 数据迁移：从旧版 Electron 目录 (cursor-renewal-client) 迁移到新版 (cursor-renewal)
    commands::utils::migrate_legacy_data();

    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            ipc::x0a, ipc::x0b, ipc::x0c,
            ipc::x1a, ipc::x1b,
            ipc::x2a, ipc::x2b, ipc::x2c,
            ipc::x3a, ipc::x3b, ipc::x3c, ipc::x3d, ipc::x3e, ipc::x3f,
            ipc::x4a, ipc::x4b, ipc::x4c, ipc::x4d, ipc::x4e,
            ipc::x5a, ipc::x5b, ipc::x5c, ipc::x5d,
            ipc::x6a, ipc::x6b, ipc::x6c, ipc::x6d, ipc::x6e,
            ipc::x7a, ipc::x7b, ipc::x7c, ipc::x7d, ipc::x7e, ipc::x7f, ipc::x7g,
            ipc::x8a, ipc::x8b, ipc::x8c, ipc::x8d, ipc::x8e,
            ipc::x9a, ipc::x9b,
            ipc::xa1,
            ipc::xb1, ipc::xb2,
            ipc::xc1, ipc::xc2, ipc::xc3, ipc::xc4, ipc::xc5, ipc::xc6,
            ipc::xc7, ipc::xc8, ipc::xc9, ipc::xca, ipc::xcb, ipc::xcc,
            ipc::xd1, ipc::xd2,
            ipc::xe1,
            ipc::xf1, ipc::xf2, ipc::xf3,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
