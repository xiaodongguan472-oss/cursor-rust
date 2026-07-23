#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

mod commands;

use commands::*;
use tauri::Manager;

/// 根据当前显示器的分辨率与 DPI 缩放因子，动态调整主窗口尺寸并居中。
///
/// 背景：窗口在 tauri.conf.json 中被写死为 920x680 逻辑像素。在“超宽屏 /
/// 非标准 DPI 缩放”的显示器上，固定尺寸会导致界面比例失衡（内容被压扁或
/// 留大片空白）。这里以 920:680 为设计基准宽高比，按屏幕可用空间等比选取
/// 一个合适的窗口尺寸，配合前端 --ui-scale 等比缩放，使任意显示器都能正常显示。
fn adjust_window_to_screen(window: &tauri::Window) {
    // 设计基准尺寸（逻辑像素），与前端 neededWidth/neededHeight 保持一致
    const BASE_W: f64 = 920.0;
    const BASE_H: f64 = 680.0;

    if let Ok(Some(monitor)) = window.current_monitor() {
        let scale = monitor.scale_factor();
        if scale <= 0.0 {
            return;
        }
        let phys = monitor.size();

        // 显示器逻辑可用尺寸（物理像素 / DPI 缩放因子）
        let logical_w = phys.width as f64 / scale;
        let logical_h = phys.height as f64 / scale;

        // 预留边距：宽度留 8%，高度留 10%（避开任务栏与视觉留白）
        let avail_w = logical_w * 0.92;
        let avail_h = logical_h * 0.90;

        // 在保持 920:680 宽高比的前提下，取能放进可用区域的等比系数。
        // 上限 1.0：正常/大屏保持设计尺寸，不放大；只有当屏幕装不下时才缩小。
        let mut k = (avail_w / BASE_W).min(avail_h / BASE_H);
        if !k.is_finite() || k <= 0.0 {
            k = 1.0;
        }
        // 下限 0.7：极小屏兜底；上限 1.0：不超过设计尺寸
        k = k.min(1.0).max(0.7);

        let target_w = BASE_W * k;
        let target_h = BASE_H * k;

        // conf 中设置了 minWidth/minHeight=920/680，缩小场景会被 clamp，
        // 先解除最小尺寸限制，再设置目标尺寸并居中。
        let _ = window.set_min_size(None::<tauri::Size>);
        let _ = window.set_size(tauri::Size::Logical(tauri::LogicalSize::new(
            target_w, target_h,
        )));
        let _ = window.center();
    }
}

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
        .setup(|app| {
            // 0. 根据显示器分辨率/DPI 动态调整窗口尺寸并居中，
            //    解决超宽屏、非标准缩放显示器上界面比例失衡的问题。
            if let Some(window) = app.get_window("main") {
                adjust_window_to_screen(&window);
                let _ = window.show();
            }

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
