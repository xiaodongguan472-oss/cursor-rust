// ============================================================================
// 反逆向 / 反调试
// 检测调试器（IDA/x64dbg/Cheat Engine 附加），检测到则延迟崩溃干扰逆向
// 设计原则：
//   1. 不在第一时间崩溃（避免攻击者快速定位检测点）
//   2. 多重 fallback 检测（任一命中即标记），降低单点绕过概率
//   3. macOS 用 PT_DENY_ATTACH 拒绝 ptrace 调试
// ============================================================================

use std::sync::atomic::{AtomicBool, Ordering};

static DEBUGGER_DETECTED: AtomicBool = AtomicBool::new(false);

// ----------------------------------------------------------------------------
// Windows: IsDebuggerPresent + CheckRemoteDebuggerPresent + PEB BeingDebugged
// ----------------------------------------------------------------------------
#[cfg(target_os = "windows")]
mod platform {
    use std::ffi::c_void;

    type BOOL = i32;
    type HANDLE = *mut c_void;

    #[link(name = "kernel32")]
    extern "system" {
        fn IsDebuggerPresent() -> BOOL;
        fn CheckRemoteDebuggerPresent(hProcess: HANDLE, pbDebuggerPresent: *mut BOOL) -> BOOL;
        fn GetCurrentProcess() -> HANDLE;
    }

    pub fn is_debugger_present() -> bool {
        unsafe {
            // 第一层：IsDebuggerPresent
            if IsDebuggerPresent() != 0 {
                return true;
            }
            // 第二层：CheckRemoteDebuggerPresent（防止 hook IsDebuggerPresent）
            let mut present: BOOL = 0;
            if CheckRemoteDebuggerPresent(GetCurrentProcess(), &mut present) != 0 && present != 0 {
                return true;
            }
            false
        }
    }

    pub fn deny_debugger() {
        // Windows 没有 PT_DENY_ATTACH 等价物，留空
    }
}

// ----------------------------------------------------------------------------
// macOS: ptrace(PT_DENY_ATTACH) - 拒绝调试器附加（金标准）
// 不做 sysctl/kinfo_proc 检测：PT_DENY_ATTACH 已让调试器无法附加，多此一举
// 而且 libc::kinfo_proc 在 arm64 编译失败（libc crate 跨架构兼容性差）
// ----------------------------------------------------------------------------
#[cfg(target_os = "macos")]
mod platform {
    const PT_DENY_ATTACH: i32 = 31;

    extern "C" {
        fn ptrace(request: i32, pid: i32, addr: *mut u8, data: i32) -> i32;
    }

    pub fn is_debugger_present() -> bool {
        // PT_DENY_ATTACH 已经在 init() 调用，调试器根本无法附加
        // 这里返回 false（不做无谓检测，保证跨架构编译干净）
        false
    }

    pub fn deny_debugger() {
        unsafe {
            // 拒绝任何 ptrace 附加请求 — macOS 防调试金标准
            ptrace(PT_DENY_ATTACH, 0, std::ptr::null_mut(), 0);
        }
    }
}

// ----------------------------------------------------------------------------
// Linux: 读 /proc/self/status 查找 TracerPid
// ----------------------------------------------------------------------------
#[cfg(target_os = "linux")]
mod platform {
    use std::fs;

    pub fn is_debugger_present() -> bool {
        if let Ok(content) = fs::read_to_string("/proc/self/status") {
            for line in content.lines() {
                if let Some(rest) = line.strip_prefix("TracerPid:") {
                    if let Ok(pid) = rest.trim().parse::<i32>() {
                        return pid != 0;
                    }
                }
            }
        }
        false
    }

    pub fn deny_debugger() {}
}

// ============================================================================
// 统一入口
// ============================================================================

/// 启动时调用：拒绝调试器附加 + 启动后台监控线程
pub fn init() {
    // 1. 拒绝调试器附加（macOS PT_DENY_ATTACH 立即生效）
    platform::deny_debugger();

    // 2. 启动时立即检测一次
    if platform::is_debugger_present() {
        DEBUGGER_DETECTED.store(true, Ordering::SeqCst);
        schedule_delayed_termination();
    }

    // 3. 后台轮询检测（每 5 秒一次），动态附加调试器也能捕获
    std::thread::spawn(|| {
        loop {
            std::thread::sleep(std::time::Duration::from_secs(5));
            if platform::is_debugger_present() && !DEBUGGER_DETECTED.load(Ordering::SeqCst) {
                DEBUGGER_DETECTED.store(true, Ordering::SeqCst);
                schedule_delayed_termination();
            }
        }
    });
}

/// 公开 API：业务逻辑可调用此函数判断是否被调试，决定是否返回假数据
#[allow(dead_code)]
pub fn is_debugger_attached() -> bool {
    DEBUGGER_DETECTED.load(Ordering::SeqCst) || platform::is_debugger_present()
}

/// 延迟 15-30 秒后崩溃，让攻击者难以定位检测点
fn schedule_delayed_termination() {
    use rand::Rng;
    let delay_secs = rand::thread_rng().gen_range(15..30);
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_secs(delay_secs));
        std::process::abort();
    });
}
