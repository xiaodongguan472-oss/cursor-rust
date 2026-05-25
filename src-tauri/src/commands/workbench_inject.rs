use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use sha2::{Sha256, Sha512, Digest};
use uuid::Uuid;
use rand::Rng;
use super::utils;
#[allow(unused_imports)]
use super::cursor_paths;

// ========== 常量 ==========

const WB_PATCH_START: &str = "/* MC_WB_PATCH_START */";
const WB_PATCH_END: &str = "/* MC_WB_PATCH_END */";
const LOCAL_SERVER_PORT: u16 = 14521; // 本地HTTP服务端口

// ========== 全局状态 ==========

static SERVER_RUNNING: AtomicBool = AtomicBool::new(false);
static MACHINE_STATE: Mutex<Option<MachineResetState>> = Mutex::new(None);
static INJECT_STATUS: Mutex<InjectStatus> = Mutex::new(InjectStatus {
    js_connected: false,
    store_captured: false,
    last_heartbeat: 0,
    last_reset_ack: 0,
    reset_count: 0,
});

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct InjectStatus {
    pub js_connected: bool,
    pub store_captured: bool,
    pub last_heartbeat: u64,
    pub last_reset_ack: u64,
    pub reset_count: u32,
}

fn now_ts() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct MachineIds {
    pub dev_device_id: String,
    pub mac_machine_id: String,
    pub machine_id: String,
    pub sqm_id: String,
    pub service_machine_id: String,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
struct MachineResetState {
    is_new: bool,
    machine_ids: MachineIds,
}

// ========== 机器码生成（与AI助手文档一致的算法） ==========

/// 生成全套新机器码（5个随机字段）
/// - devDeviceId: UUID4
/// - macMachineId: SHA512(random 64 bytes) = 128 hex chars
/// - machineId: SHA256(random 32 bytes) = 64 hex chars
/// - sqmId: {UUID4-UPPERCASE}
/// - serviceMachineId: UUID4
pub fn generate_machine_ids() -> MachineIds {
    let dev_device_id = Uuid::new_v4().to_string();

    let mac_machine_id = {
        let mut rng = rand::thread_rng();
        let mut buf = [0u8; 64];
        rng.fill(&mut buf);
        let mut hasher = Sha512::new();
        hasher.update(&buf);
        hex::encode(hasher.finalize())
    };

    let machine_id = {
        let mut hasher = Sha256::new();
        hasher.update(rand::random::<[u8; 32]>());
        hex::encode(hasher.finalize())
    };

    let sqm_id = format!("{{{}}}", Uuid::new_v4().to_string().to_uppercase());

    let service_machine_id = Uuid::new_v4().to_string();

    MachineIds {
        dev_device_id,
        mac_machine_id,
        machine_id,
        sqm_id,
        service_machine_id,
    }
}

// ========== 磁盘文件更新 ==========

/// 更新磁盘上的机器码文件（machineId文件 + storage.json）
pub fn update_disk_files(ids: &MachineIds) -> Result<(), String> {
    let cursor_dir = utils::get_cursor_data_dir()
        .ok_or_else(|| "无法确定Cursor数据目录".to_string())?;

    if !cursor_dir.exists() {
        return Err(format!("Cursor数据目录不存在: {}", cursor_dir.display()));
    }

    // 1. 写入 machineId 文件
    let machine_id_file = cursor_dir.join("machineId");
    utils::clear_macos_immutable_flag(&machine_id_file);
    fs::write(&machine_id_file, &ids.machine_id)
        .map_err(|e| format!("写入machineId文件失败: {}", e))?;

    // 2. 更新 storage.json
    let storage_path = cursor_dir.join("User").join("globalStorage").join("storage.json");
    if storage_path.exists() {
        utils::clear_macos_immutable_flag(&storage_path);
        let content = fs::read_to_string(&storage_path)
            .map_err(|e| format!("读取storage.json失败: {}", e))?;
        let mut config: serde_json::Value = serde_json::from_str(&content)
            .map_err(|e| format!("解析storage.json失败: {}", e))?;

        if let Some(obj) = config.as_object_mut() {
            obj.insert(utils::keys::telem_machine(), serde_json::json!(ids.machine_id));
            obj.insert(utils::keys::telem_mac(), serde_json::json!(ids.mac_machine_id));
            obj.insert(utils::keys::telem_dev(), serde_json::json!(ids.dev_device_id));
            obj.insert(utils::keys::telem_sqm(), serde_json::json!(ids.sqm_id));
            // serviceMachineId
            let svc_key = obfstr::obfstr!("storage.serviceMachineId").to_string();
            obj.insert(svc_key, serde_json::json!(ids.service_machine_id));
        }

        let updated = serde_json::to_string_pretty(&config)
            .map_err(|e| format!("序列化storage.json失败: {}", e))?;
        fs::write(&storage_path, updated)
            .map_err(|e| format!("写入storage.json失败: {}", e))?;
    }

    Ok(())
}

// ========== 重置机器码核心函数 ==========

/// 执行完整的机器码重置（生成新ID + 写磁盘 + 更新状态供JS拉取）
pub fn perform_machine_reset() -> Result<MachineIds, String> {
    let ids = generate_machine_ids();

    // 写入磁盘文件
    update_disk_files(&ids)?;

    // 更新状态（供注入的JS轮询拉取）
    if let Ok(mut state) = MACHINE_STATE.lock() {
        *state = Some(MachineResetState {
            is_new: true,
            machine_ids: ids.clone(),
        });
    }

    Ok(ids)
}

/// 仅将已有的机器码推送给JS（更新状态供轮询拉取，不重新生成也不写磁盘）
pub fn push_ids_to_js(ids: &MachineIds) {
    if let Ok(mut state) = MACHINE_STATE.lock() {
        *state = Some(MachineResetState {
            is_new: true,
            machine_ids: ids.clone(),
        });
    }
}

// ========== 本地HTTP服务器（供注入JS轮询） ==========

/// 启动本地HTTP服务器（非阻塞，后台运行）
pub fn start_local_server() {
    if SERVER_RUNNING.load(Ordering::SeqCst) {
        return;
    }

    SERVER_RUNNING.store(true, Ordering::SeqCst);

    // 安全启动：检测 tokio runtime 是否可用
    // 如果在 tauri setup 之前调用（无 runtime），则自建线程+runtime
    let spawn_ok = tokio::runtime::Handle::try_current()
        .map(|handle| {
            handle.spawn(run_server());
            true
        })
        .unwrap_or(false);

    if !spawn_ok {
        std::thread::spawn(|| {
            let rt = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .expect("failed to create tokio runtime for local server");
            rt.block_on(run_server());
        });
    }
}

async fn run_server() {
    use tokio::net::TcpListener;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    let addr = format!("127.0.0.1:{}", LOCAL_SERVER_PORT);
    let listener = match TcpListener::bind(&addr).await {
        Ok(l) => l,
        Err(_) => {
            SERVER_RUNNING.store(false, Ordering::SeqCst);
            return;
        }
    };

    while SERVER_RUNNING.load(Ordering::SeqCst) {
        let accept_result = tokio::select! {
            result = listener.accept() => result,
            _ = tokio::time::sleep(std::time::Duration::from_secs(1)) => continue,
        };

        let (mut stream, _) = match accept_result {
            Ok(s) => s,
            Err(_) => continue,
        };

        tokio::spawn(async move {
            let mut buf = vec![0u8; 4096];
            let n = match stream.read(&mut buf).await {
                Ok(n) if n > 0 => n,
                _ => return,
            };

            let request = String::from_utf8_lossy(&buf[..n]).to_string();
            let response = handle_request(&request);

            let http_response = format!(
                "HTTP/1.1 200 OK\r\n\
                 Content-Type: application/json\r\n\
                 Access-Control-Allow-Origin: *\r\n\
                 Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n\
                 Access-Control-Allow-Headers: Content-Type\r\n\
                 Content-Length: {}\r\n\
                 Connection: close\r\n\
                 \r\n\
                 {}",
                response.len(),
                response
            );

            let _ = stream.write_all(http_response.as_bytes()).await;
        });
    }
}

/// 停止本地HTTP服务器
pub fn stop_local_server() {
    SERVER_RUNNING.store(false, Ordering::SeqCst);
}

fn handle_request(request: &str) -> String {
    let first_line = request.lines().next().unwrap_or("");

    if first_line.contains("OPTIONS") {
        return "{}".to_string();
    }

    if first_line.contains("GET /api/machine-state") {
        return handle_get_machine_state();
    }

    if first_line.contains("POST /api/ack-reset") {
        return handle_ack_reset();
    }

    // JS心跳 + 状态上报
    if first_line.contains("POST /api/heartbeat") {
        return handle_heartbeat(request);
    }

    serde_json::json!({"error": "not found"}).to_string()
}

fn handle_get_machine_state() -> String {
    let state = MACHINE_STATE.lock().ok().and_then(|g| g.clone());

    match state {
        Some(s) => serde_json::json!({
            "is_new": s.is_new,
            "devDeviceId": s.machine_ids.dev_device_id,
            "macMachineId": s.machine_ids.mac_machine_id,
            "machineId": s.machine_ids.machine_id,
            "sqmId": s.machine_ids.sqm_id,
            "serviceMachineId": s.machine_ids.service_machine_id,
        }).to_string(),
        None => serde_json::json!({
            "is_new": false,
        }).to_string(),
    }
}

fn handle_ack_reset() -> String {
    if let Ok(mut state) = MACHINE_STATE.lock() {
        if let Some(ref mut s) = *state {
            s.is_new = false;
        }
    }
    if let Ok(mut status) = INJECT_STATUS.lock() {
        status.last_reset_ack = now_ts();
        status.reset_count += 1;
    }
    serde_json::json!({"success": true}).to_string()
}

fn handle_heartbeat(request: &str) -> String {
    // 解析 body 中的 store_captured 字段
    let store_captured = request.contains("\"store_captured\":true")
        || request.contains("\"store_captured\": true");

    if let Ok(mut status) = INJECT_STATUS.lock() {
        status.js_connected = true;
        status.last_heartbeat = now_ts();
        if store_captured {
            status.store_captured = true;
        }
    }
    serde_json::json!({"success": true}).to_string()
}

/// 获取注入状态（供前端查询）
pub fn get_inject_status() -> InjectStatus {
    let mut status = INJECT_STATUS.lock()
        .map(|s| s.clone())
        .unwrap_or(InjectStatus {
            js_connected: false,
            store_captured: false,
            last_heartbeat: 0,
            last_reset_ack: 0,
            reset_count: 0,
        });
    // 如果超过 10 秒没有心跳，认为 JS 已断开
    if status.last_heartbeat > 0 && now_ts() - status.last_heartbeat > 10 {
        status.js_connected = false;
    }
    status
}

// ========== Workbench JS 注入 ==========

/// 获取 workbench.desktop.main.js 路径
fn get_workbench_js_path(base_path: &str) -> PathBuf {
    Path::new(base_path)
        .join("out")
        .join("vs")
        .join("workbench")
        .join("workbench.desktop.main.js")
}

/// 构建注入到 workbench.desktop.main.js 的 JS 代码
/// 包含3个注入点：
/// 0 - 禁用完整性检查通知
/// 1 - 暴露 window.store（StorageService）
/// 2 - 轮询本地服务拉取新机器码并通过 window.store.set() 写入内存
fn build_workbench_inject_code() -> String {
    let port = LOCAL_SERVER_PORT;

    format!(
        r#"{start}
;(function(){{
var _mcBase='http://127.0.0.1:{port}';
/* === 注入点1: 暴露 window.store === */
try{{
var _mcStoreCaptured=false;
const _origDefProp=Object.defineProperty;
Object.defineProperty=function(t,p,d){{
if(!_mcStoreCaptured){{
if((p==='storageService'||p==='_storageService')&&d&&d.value&&typeof d.value.store==='function'){{
try{{window.store=d.value;_mcStoreCaptured=true;}}catch(e){{}}
}}
}}
return _origDefProp.call(this,t,p,d);
}};
}}catch(e){{}}

/* === 注入点2: 心跳 + 轮询机器码 === */
try{{
var _mcLastIds='';
function _mcHB(){{try{{fetch(_mcBase+'/api/heartbeat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{store_captured:!!window.store}})}}).catch(function(){{}});}}catch(e){{}}}}
async function _mcPoll(){{
try{{
var r=await fetch(_mcBase+'/api/machine-state');
var d=await r.json();
if(!d.is_new)return;
var idKey=d.machineId||'';
if(idKey===_mcLastIds)return;
if(window.store&&typeof window.store.store==='function'){{
window.store.store('telemetry.devDeviceId',-1,d.devDeviceId);
window.store.store('telemetry.macMachineId',-1,d.macMachineId);
window.store.store('telemetry.machineId',-1,d.machineId);
window.store.store('telemetry.sqmId',-1,d.sqmId);
window.store.store('storage.serviceMachineId',-1,d.serviceMachineId);
_mcLastIds=idKey;
fetch(_mcBase+'/api/ack-reset',{{method:'POST'}}).catch(function(){{}});
}}
}}catch(e){{}}
}}
setInterval(_mcPoll,2000);
setInterval(_mcHB,5000);
setTimeout(_mcHB,2000);
setTimeout(_mcPoll,3000);
}}catch(e){{}}
}})();
{end}
"#,
        start = WB_PATCH_START,
        end = WB_PATCH_END,
        port = port,
    )
}

/// 注入 workbench.desktop.main.js
pub fn patch_workbench(base_path: &str) -> serde_json::Value {
    let wb_path = get_workbench_js_path(base_path);

    if !wb_path.exists() {
        return serde_json::json!({
            "success": false,
            "error": format!("workbench.desktop.main.js不存在: {}", wb_path.display())
        });
    }

    let content = match fs::read_to_string(&wb_path) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({
                "success": false,
                "error": format!("读取文件失败: {}", e)
            });
        }
    };

    // 已注入过？先移除旧的
    let content = if content.contains(WB_PATCH_START) {
        remove_patch_from_content(&content)
    } else {
        content
    };

    // 创建备份
    let backup = format!("{}.mc_bak", wb_path.to_string_lossy());
    if !Path::new(&backup).exists() {
        let _ = fs::copy(&wb_path, &backup);
    }

    let inject_code = build_workbench_inject_code();
    // 注入到文件末尾（不影响原始代码解析）
    let new_content = format!("{}\n{}", content, inject_code);

    let write_result = utils::safe_modify_file(&wb_path, || {
        fs::write(&wb_path, &new_content).map_err(|e| format!("写入文件失败: {}", e))
    });

    match write_result {
        Ok(()) => {
            // 清除 V8 字节码缓存
            clear_v8_cache();

            // macOS: 重签名
            #[cfg(target_os = "macos")]
            {
                let install_path = cursor_paths::get_cursor_install_from_base_path(base_path);
                let app_path = install_path.to_string_lossy();
                let _ = std::process::Command::new("xattr")
                    .args(["-cr", &*app_path])
                    .output();
                let _ = std::process::Command::new("codesign")
                    .args(["--force", "--deep", "--sign", "-", &*app_path])
                    .output();
            }

            serde_json::json!({"success": true, "message": "机器码注入成功"})
        }
        Err(e) => serde_json::json!({"success": false, "error": e}),
    }
}

/// 移除 workbench.desktop.main.js 中的注入
pub fn unpatch_workbench(base_path: &str) -> serde_json::Value {
    let wb_path = get_workbench_js_path(base_path);

    if !wb_path.exists() {
        return serde_json::json!({"success": true, "message": "文件不存在，无需移除"});
    }

    let content = match fs::read_to_string(&wb_path) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({"success": false, "error": e.to_string()});
        }
    };

    if !content.contains(WB_PATCH_START) {
        return serde_json::json!({"success": true, "message": "未检测到注入"});
    }

    let new_content = remove_patch_from_content(&content);

    let write_result = utils::safe_modify_file(&wb_path, || {
        fs::write(&wb_path, &new_content).map_err(|e| format!("写入失败: {}", e))
    });

    match write_result {
        Ok(()) => {
            #[cfg(target_os = "macos")]
            {
                let install_path = cursor_paths::get_cursor_install_from_base_path(base_path);
                let app_path = install_path.to_string_lossy();
                let _ = std::process::Command::new("xattr")
                    .args(["-cr", &*app_path])
                    .output();
                let _ = std::process::Command::new("codesign")
                    .args(["--force", "--deep", "--sign", "-", &*app_path])
                    .output();
            }
            serde_json::json!({"success": true, "message": "注入已移除"})
        }
        Err(e) => serde_json::json!({"success": false, "error": e}),
    }
}

/// 检查 workbench 是否已注入
#[allow(dead_code)]
pub fn check_workbench_patched(base_path: &str) -> bool {
    let wb_path = get_workbench_js_path(base_path);
    if let Ok(content) = fs::read_to_string(&wb_path) {
        content.contains(WB_PATCH_START)
    } else {
        false
    }
}

fn remove_patch_from_content(content: &str) -> String {
    if let (Some(start_idx), Some(end_idx)) = (
        content.find(WB_PATCH_START),
        content.find(WB_PATCH_END),
    ) {
        let end_with_marker = end_idx + WB_PATCH_END.len();
        let mut result = String::new();
        result.push_str(&content[..start_idx]);
        if end_with_marker < content.len() {
            // 跳过紧跟的换行符
            let remaining = &content[end_with_marker..];
            let trimmed = remaining.strip_prefix('\n').unwrap_or(remaining);
            result.push_str(trimmed);
        }
        result
    } else {
        content.to_string()
    }
}

/// 程序启动时自动检测：如果 workbench 已注入，则自动启动 HTTP 服务
pub fn auto_start_if_patched() {
    let paths = super::cursor_paths::get_cursor_paths();
    if let Some(ref bp) = paths.base_path {
        if paths.error.is_none() && check_workbench_patched(bp) {
            start_local_server();
        }
    }
}

/// 清除 V8 字节码缓存（Electron 加载旧缓存会导致注入失效）
fn clear_v8_cache() {
    let cursor_dir = match utils::get_cursor_data_dir() {
        Some(d) => d,
        None => return,
    };

    // GPUCache 和 Code Cache 目录
    let cache_dirs = [
        cursor_dir.join("GPUCache"),
        cursor_dir.join("Code Cache"),
        cursor_dir.join("CachedData"),
    ];

    for dir in &cache_dirs {
        if dir.exists() {
            let _ = fs::remove_dir_all(dir);
        }
    }
}
