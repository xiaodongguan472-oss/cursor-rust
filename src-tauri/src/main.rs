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
        .setup(|_app| {
            // 1. 迁移清理：老版本用 MITM 代理解锁，会在 settings.json 留下
            //    http.proxy=127.0.0.1:8189 —— 这正是 Cursor 3.11+ 下 AI 报错的元凶。
            //    启动时静默清掉旧代理 / CA 遗留，让升级用户无需手动改 settings.json。
            //    幂等：无残留则各步骤 no-op。
            tauri::async_runtime::spawn_blocking(|| {
                commands::unlock_mitm::cleanup_legacy_mitm();
            });

            // 2. 模型解锁改为渲染进程 workbench 注入，由用户显式开关驱动，
            //    启动时不擅自注入（保留占位调用，当前为 no-op）。
            tauri::async_runtime::spawn(async {
                commands::unlock_workbench::auto_restore_on_startup();
            });

            // 3. 禁用 Cursor 自动更新：确保用户 settings.json 中 update.mode = none
            tauri::async_runtime::spawn_blocking(|| {
                commands::cursor_modify::ensure_auto_update_disabled();
            });
            Ok(())
        })
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
            ipc::xg1, ipc::xg2, ipc::xg3, ipc::xg4, ipc::xg5,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
