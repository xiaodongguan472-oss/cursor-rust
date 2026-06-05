// ============================================================================
// 日志缓冲区：进程内存最近 200 条 + 写到 ~/.cursor-renewal/run.log
//
// 用途：调试用户问题时，让用户在 UI 里直接看到关键事件 ——
//   - 重置机器码每个步骤
//   - ExtHost 补丁注入/移除 + 检测
//   - override 文件写入路径 + 内容大小
//   - 自动换号关键节点
//
// 调用方式：log!("[Reset] step 4 ok");  会同时进内存 + 追加到磁盘
// ============================================================================

use std::sync::{Mutex, OnceLock};
use std::collections::VecDeque;
use std::path::PathBuf;
use std::io::Write;

const MAX_LINES: usize = 200;

static BUFFER: OnceLock<Mutex<VecDeque<String>>> = OnceLock::new();

fn buf() -> &'static Mutex<VecDeque<String>> {
    BUFFER.get_or_init(|| Mutex::new(VecDeque::with_capacity(MAX_LINES)))
}

fn log_file_path() -> PathBuf {
    let home = dirs::home_dir().unwrap_or_default();
    let dir = home.join(".cursor-renewal");
    let _ = std::fs::create_dir_all(&dir);
    dir.join("run.log")
}

/// 写一条日志 —— 自动加时间戳；进内存环形缓冲 + 追加到 run.log
pub fn log_line(line: impl Into<String>) {
    let line = line.into();
    let stamped = format!(
        "[{}] {}",
        chrono::Local::now().format("%H:%M:%S%.3f"),
        line
    );

    // 1. 进内存缓冲
    if let Ok(mut q) = buf().lock() {
        if q.len() >= MAX_LINES {
            q.pop_front();
        }
        q.push_back(stamped.clone());
    }

    // 2. 追加到磁盘
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_file_path())
    {
        let _ = writeln!(f, "{}", stamped);
    }
}

/// 取所有缓冲行（拷贝出来，避免持锁过久）
pub fn snapshot() -> Vec<String> {
    buf().lock().ok().map(|q| q.iter().cloned().collect()).unwrap_or_default()
}

/// 清空内存缓冲（磁盘文件保留）
#[allow(dead_code)]
pub fn clear_memory() {
    if let Ok(mut q) = buf().lock() {
        q.clear();
    }
}

#[macro_export]
macro_rules! ulog {
    ($($arg:tt)*) => {
        $crate::commands::log_buffer::log_line(format!($($arg)*));
    };
}

// ============================================================================
// Tauri commands
// ============================================================================

/// 拿当前内存缓冲的所有日志行
#[tauri::command]
pub async fn get_log_entries() -> Vec<String> {
    snapshot()
}

/// 拿磁盘上的完整 run.log（最近一次启动以来 / 含历史；返回最后 ~500KB）
#[tauri::command]
pub async fn read_log_file() -> String {
    let path = log_file_path();
    if !path.exists() {
        return String::new();
    }
    match std::fs::read_to_string(&path) {
        Ok(s) => {
            // 太大 → 截断到末尾 500KB
            if s.len() > 500_000 {
                let start = s.len() - 500_000;
                let safe_start = s
                    .char_indices()
                    .find(|(i, _)| *i >= start)
                    .map(|(i, _)| i)
                    .unwrap_or(start);
                format!("...[已截断早期内容]\n{}", &s[safe_start..])
            } else {
                s
            }
        }
        Err(e) => format!("读取日志文件失败: {}", e),
    }
}

/// 清空磁盘日志文件
#[tauri::command]
pub async fn clear_log_file() -> bool {
    let path = log_file_path();
    if path.exists() {
        std::fs::write(&path, "").is_ok()
    } else {
        true
    }
}

/// 让前端打开 run.log 所在的文件夹（用户也能用文件管理器看）
#[tauri::command]
pub async fn open_log_folder() -> Result<(), String> {
    let path = log_file_path();
    let folder = path.parent().ok_or("无效的日志目录")?;
    open::that(folder).map_err(|e| format!("无法打开文件夹: {}", e))
}

/// 读取 ExtHost 补丁自己写的 exthost.log（每次拦截 cursor.sh 请求都会追加一行）
/// 用于诊断「补丁是否在 Cursor 里跑了」+「替换有没有触发」。
/// 返回末尾 ~300KB 内容；不存在返回空字符串。
#[tauri::command]
pub async fn read_exthost_log() -> String {
    let path = log_file_path()
        .parent()
        .map(|p| p.join("exthost.log"))
        .unwrap_or_else(|| PathBuf::from("exthost.log"));
    if !path.exists() {
        return String::new();
    }
    match std::fs::read_to_string(&path) {
        Ok(s) => {
            if s.len() > 300_000 {
                let start = s.len() - 300_000;
                let safe_start = s
                    .char_indices()
                    .find(|(i, _)| *i >= start)
                    .map(|(i, _)| i)
                    .unwrap_or(start);
                format!("...[已截断早期内容]\n{}", &s[safe_start..])
            } else {
                s
            }
        }
        Err(e) => format!("读取 exthost.log 失败: {}", e),
    }
}
