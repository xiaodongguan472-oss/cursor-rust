// ============================================================================
// Cursor 模型锁 UI 解锁：MITM 代理 + CA 安装 + 环境变量 + settings.json 合并
//
// 总体思路（来自 UNLOCK_DESIGN.md）：
//   - 本地 MITM 代理监听 127.0.0.1:8189，拦截 /auth/full_stripe_profile，
//     将 membershipType / individualMembershipType 改写为 "pro" → UI 上的锁消失。
//   - 完全透传所有其它请求，不动用户真实账号 token / 配额。
//
// 部署链路（启动时三件事）：
//   A. 生成 / 复用 CA → 装到系统信任根
//      - Windows: 写 HKCU\Software\Microsoft\SystemCertificates\Root\Certificates\<thumb>\Blob
//                 （注册表直写，无任何 UI 提示）
//      - macOS:   security add-trusted-cert -p ssl -k ~/Library/Keychains/login.keychain-db
//                 （会弹一次「输入登录密码」对话框）
//   B. 设 NODE_EXTRA_CA_CERTS 环境变量（Electron 的 Node 需要这个）
//      - Windows: setx 写 HKCU\Environment
//      - macOS:   launchctl setenv + LaunchAgent plist（重启后仍生效）
//   C. 写入 Cursor settings.json 的 http.proxy / http.experimental.systemCertificatesV2
//
// 关闭时：
//   - 停 MITM 进程内监听
//   - 删 settings.json 中我们写入的键
//   - 清 NODE_EXTRA_CA_CERTS 环境变量
//   - 删除 CA 证书（系统钥匙串 / 注册表 + 本地 PEM）
//
// 用户偏好（与文档默认略不同）：
//   - 程序关闭时不清证书；只在用户点击「关闭激活无感换号」时清。
//   - 程序启动如果检测到 CA 证书还在 → 自动起 MITM 代理（不需要用户重新点击）。
// ============================================================================

use std::fs;
use std::io::Write;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex as StdMutex, OnceLock};
use tokio::sync::oneshot;

use hudsucker::{
    certificate_authority::RcgenAuthority,
    hyper::{header, Request, Response, StatusCode},
    rcgen::{CertificateParams, DistinguishedName, DnType, Issuer, KeyPair, KeyUsagePurpose, ExtendedKeyUsagePurpose, BasicConstraints, IsCa},
    rustls::crypto::aws_lc_rs,
    Body, HttpContext, HttpHandler, Proxy, RequestOrResponse,
};
use http_body_util::BodyExt;

use super::utils;

// ============================================================================
// 常量
// ============================================================================

const PROXY_ADDR: ([u8; 4], u16) = ([127, 0, 0, 1], 8189);
const PROXY_URL: &str = "http://127.0.0.1:8189";

/// 改写目标 membershipType（"pro" 或 "ultra"，与文档一致）
const TARGET_MEMBERSHIP: &str = "pro";

/// 我们维护的 settings.json 键集合 —— 卸载时只移除这些
const MANAGED_SETTINGS_KEYS: &[&str] = &[
    "http.proxy",
    "http.experimental.systemCertificatesV2",
];

// ============================================================================
// 全局状态
// ============================================================================

/// MITM 当前是否运行
static MITM_RUNNING: AtomicBool = AtomicBool::new(false);

/// 关闭代理的 oneshot 发送端
static SHUTDOWN_TX: OnceLock<std::sync::Mutex<Option<oneshot::Sender<()>>>> = OnceLock::new();

fn shutdown_slot() -> &'static std::sync::Mutex<Option<oneshot::Sender<()>>> {
    SHUTDOWN_TX.get_or_init(|| std::sync::Mutex::new(None))
}

// ============================================================================
// 数据目录 / CA 路径
// ============================================================================

fn unlock_data_dir() -> PathBuf {
    let d = utils::get_app_data_dir().join("unlock");
    let _ = fs::create_dir_all(&d);
    d
}

fn ca_cert_pem_path() -> PathBuf { unlock_data_dir().join("ca.crt") }
fn ca_key_pem_path() -> PathBuf { unlock_data_dir().join("ca.key") }

// ============================================================================
// CA 生成 / 加载
// ============================================================================

/// 生成新的根 CA（自签名），写到 `unlock/ca.crt` 和 `unlock/ca.key`。
fn generate_ca() -> Result<(), String> {
    use rcgen::Certificate;

    let mut params = CertificateParams::new(vec!["cursor-renewal-unlock-ca".to_string()])
        .map_err(|e| format!("rcgen params: {}", e))?;
    let mut dn = DistinguishedName::new();
    dn.push(DnType::CommonName, "Cursor Renewal Unlock CA");
    dn.push(DnType::OrganizationName, "Cursor Renewal");
    params.distinguished_name = dn;
    params.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
    params.key_usages = vec![KeyUsagePurpose::KeyCertSign, KeyUsagePurpose::CrlSign, KeyUsagePurpose::DigitalSignature];
    params.extended_key_usages = vec![ExtendedKeyUsagePurpose::ServerAuth];

    // 10 年有效期
    let now = time::OffsetDateTime::now_utc();
    params.not_before = now - time::Duration::days(1);
    params.not_after = now + time::Duration::days(3650);

    let key_pair = KeyPair::generate().map_err(|e| format!("rcgen keypair: {}", e))?;
    let cert: Certificate = params
        .self_signed(&key_pair)
        .map_err(|e| format!("rcgen self_signed: {}", e))?;

    fs::write(ca_cert_pem_path(), cert.pem()).map_err(|e| format!("写 CA cert 失败: {}", e))?;
    fs::write(ca_key_pem_path(), key_pair.serialize_pem())
        .map_err(|e| format!("写 CA key 失败: {}", e))?;
    Ok(())
}

/// 确保 CA 存在（不存在则生成）。
fn ensure_ca_exists() -> Result<(), String> {
    if ca_cert_pem_path().exists() && ca_key_pem_path().exists() {
        return Ok(());
    }
    generate_ca()
}

/// 加载 RcgenAuthority（hudsucker 用这个对每个上游 host 动态签发叶子证书）。
fn load_authority() -> Result<RcgenAuthority, String> {
    let cert_pem = fs::read_to_string(ca_cert_pem_path()).map_err(|e| format!("读 CA cert: {}", e))?;
    let key_pem = fs::read_to_string(ca_key_pem_path()).map_err(|e| format!("读 CA key: {}", e))?;

    let key_pair = KeyPair::from_pem(&key_pem).map_err(|e| format!("解析 CA key: {}", e))?;
    let issuer = Issuer::from_ca_cert_pem(&cert_pem, key_pair)
        .map_err(|e| format!("构造 Issuer: {}", e))?;

    Ok(RcgenAuthority::new(issuer, 1_000, aws_lc_rs::default_provider()))
}

// ============================================================================
// MITM Handler：只改 /auth/full_stripe_profile，其他全透传
//
// hudsucker 0.24 的 HttpContext 只暴露 client_addr，无法在 handle_response 中
// 直接读到请求 URI/host —— 必须在 handle_request 把 URI/host 缓存到 handler
// 实例里。同一请求/响应对会路由到「同一个」 handler 实例（hudsucker 文档承诺），
// 所以用 Arc<Mutex<Option<...>>> 即可避免跨请求串扰。
// ============================================================================

#[derive(Clone, Default)]
struct UnlockHandler {
    last_request: Arc<StdMutex<Option<RequestMeta>>>,
}

#[derive(Clone, Debug)]
struct RequestMeta {
    host: String,
    path: String,
}

impl HttpHandler for UnlockHandler {
    async fn handle_request(
        &mut self,
        _ctx: &HttpContext,
        req: Request<Body>,
    ) -> RequestOrResponse {
        // 抽取 host / path 留给 handle_response 用
        let host = req
            .uri()
            .host()
            .map(|h| h.to_lowercase())
            .or_else(|| {
                req.headers()
                    .get(header::HOST)
                    .and_then(|v| v.to_str().ok())
                    .map(|s| s.split(':').next().unwrap_or(s).to_lowercase())
            })
            .unwrap_or_default();
        let path = req.uri().path().to_string();
        if let Ok(mut slot) = self.last_request.lock() {
            *slot = Some(RequestMeta { host, path });
        }
        req.into()
    }

    async fn handle_response(
        &mut self,
        _ctx: &HttpContext,
        res: Response<Body>,
    ) -> Response<Body> {
        let meta = self.last_request.lock().ok().and_then(|g| g.clone());
        let meta = match meta {
            Some(m) => m,
            None => return res,
        };

        // 1. 只关心 cursor 相关域名
        if !is_cursor_host(&meta.host) {
            return res;
        }

        // 2. 只改 /auth/full_stripe_profile
        if !meta.path.ends_with("/auth/full_stripe_profile") {
            return res;
        }

        // 3. 只处理 200 OK
        if res.status() != StatusCode::OK {
            return res;
        }

        // 4. 读 body 并尝试 JSON 改写；失败则原样返回
        let (parts, body) = res.into_parts();
        let collected = match body.collect().await {
            Ok(c) => c.to_bytes(),
            Err(_) => return Response::from_parts(parts, Body::empty()),
        };
        let raw = collected.to_vec();

        // 不是 JSON（OPTIONS 预检 204 / 空 body）
        if raw.is_empty() || !raw.iter().any(|b| !b.is_ascii_whitespace()) {
            return Response::from_parts(parts, Body::from(raw));
        }
        let text = match std::str::from_utf8(&raw) {
            Ok(t) => t,
            Err(_) => return Response::from_parts(parts, Body::from(raw)),
        };
        if !text.trim_start().starts_with('{') {
            return Response::from_parts(parts, Body::from(raw));
        }

        let mut data: serde_json::Value = match serde_json::from_str(text) {
            Ok(v) => v,
            Err(_) => return Response::from_parts(parts, Body::from(raw)),
        };
        if !data.is_object() {
            return Response::from_parts(parts, Body::from(raw));
        }

        // 5. 改写关键字段
        let obj = data.as_object_mut().unwrap();
        let mut changed = false;

        if obj.get("membershipType").and_then(|v| v.as_str()) != Some(TARGET_MEMBERSHIP) {
            obj.insert("membershipType".to_string(), serde_json::Value::String(TARGET_MEMBERSHIP.to_string()));
            changed = true;
        }
        // individualMembershipType 只在原本就是字符串时改写（null 保持 null，避免误判）
        if obj.get("individualMembershipType").and_then(|v| v.as_str()).is_some()
            && obj.get("individualMembershipType").and_then(|v| v.as_str()) != Some(TARGET_MEMBERSHIP)
        {
            obj.insert("individualMembershipType".to_string(), serde_json::Value::String(TARGET_MEMBERSHIP.to_string()));
            changed = true;
        }
        // 规避「账号异常」横幅
        if obj.get("trialWasCancelled").and_then(|v| v.as_bool()) == Some(true) {
            obj.insert("trialWasCancelled".to_string(), serde_json::Value::Bool(false));
            changed = true;
        }
        if obj.get("pendingCancellationDate").map(|v| !v.is_null()).unwrap_or(false) {
            obj.insert("pendingCancellationDate".to_string(), serde_json::Value::Null);
            changed = true;
        }
        if obj.get("lastPaymentFailed").and_then(|v| v.as_bool()) == Some(true) {
            obj.insert("lastPaymentFailed".to_string(), serde_json::Value::Bool(false));
            changed = true;
        }

        if !changed {
            return Response::from_parts(parts, Body::from(raw));
        }

        let new_body = match serde_json::to_vec(&data) {
            Ok(b) => b,
            Err(_) => return Response::from_parts(parts, Body::from(raw)),
        };

        // 重建 response：保持原 content-type（text/plain; charset=utf-8）
        let mut headers = parts.headers.clone();
        headers.remove(header::CONTENT_LENGTH);
        headers.remove(header::CONTENT_ENCODING); // body 已被 collect 解码 → 不能再带 encoding
        headers.insert(
            header::CONTENT_LENGTH,
            header::HeaderValue::from_str(&new_body.len().to_string()).unwrap(),
        );

        let mut new_parts = parts;
        new_parts.headers = headers;
        Response::from_parts(new_parts, Body::from(new_body))
    }
}

fn is_cursor_host(host: &str) -> bool {
    let h = host.trim_end_matches('.').to_lowercase();
    h == "api2.cursor.sh" || h == "api3.cursor.sh" || h.ends_with(".cursor.sh")
}

// ============================================================================
// MITM 代理启动 / 停止
// ============================================================================

async fn run_proxy() -> Result<(), String> {
    let ca = load_authority()?;

    let (tx, rx) = oneshot::channel::<()>();
    if let Ok(mut slot) = shutdown_slot().lock() {
        *slot = Some(tx);
    }

    let addr = SocketAddr::from(PROXY_ADDR);
    let proxy = Proxy::builder()
        .with_addr(addr)
        .with_ca(ca)
        .with_rustls_connector(aws_lc_rs::default_provider())
        .with_http_handler(UnlockHandler::default())
        .with_graceful_shutdown(async move {
            let _ = rx.await;
        })
        .build()
        .map_err(|e| format!("构建 hudsucker proxy 失败: {}", e))?;

    MITM_RUNNING.store(true, Ordering::SeqCst);
    let result: Result<(), String> = match proxy.start().await {
        Ok(_) => Ok(()),
        Err(e) => Err(format!("proxy.start: {}", e)),
    };
    MITM_RUNNING.store(false, Ordering::SeqCst);
    result
}

/// 在后台 spawn MITM 代理；如已运行则 no-op。
pub fn start_mitm_in_background() -> Result<(), String> {
    if MITM_RUNNING.load(Ordering::SeqCst) {
        return Ok(());
    }
    ensure_ca_exists()?;
    // aws-lc-rs 默认 provider 是进程级单例，多次安装是 no-op，但为了未来可能 panic 风险忽略错误
    let _ = aws_lc_rs::default_provider().install_default();

    tokio::spawn(async {
        let _ = run_proxy().await;
    });
    Ok(())
}

/// 通知运行中的 MITM 代理优雅退出
pub fn stop_mitm() {
    if let Ok(mut slot) = shutdown_slot().lock() {
        if let Some(tx) = slot.take() {
            let _ = tx.send(());
        }
    }
}

pub fn is_mitm_running() -> bool {
    MITM_RUNNING.load(Ordering::SeqCst)
}

// ============================================================================
// CA 指纹（SHA1 of DER）—— certutil 用大写无分隔的 SHA1 作为 thumbprint
// ============================================================================

fn ca_sha1_thumbprint() -> Result<String, String> {
    use sha2::Sha256; // 仅借用 trait crate；下面用 sha1 等价物
    let _ = Sha256::default; // suppress unused

    let pem = fs::read_to_string(ca_cert_pem_path()).map_err(|e| format!("读 CA cert: {}", e))?;
    let mut der: Vec<u8> = Vec::new();
    let mut in_block = false;
    let mut b64 = String::new();
    for line in pem.lines() {
        if line.contains("BEGIN CERTIFICATE") { in_block = true; continue; }
        if line.contains("END CERTIFICATE") { break; }
        if in_block { b64.push_str(line.trim()); }
    }
    let bytes = base64::Engine::decode(&base64::engine::general_purpose::STANDARD, &b64)
        .map_err(|e| format!("解析 PEM base64 失败: {}", e))?;
    der.extend_from_slice(&bytes);

    // 用 sha1 算法 —— 我们没有引 sha1 crate，但 SHA-1 在 sha2 crate 里没提供。
    // 自己实现一份精简 SHA-1（CA thumbprint 不需要密码学强度，本身就是 SHA-1）。
    Ok(sha1_hex_upper(&der))
}

/// 极简 SHA-1（RFC 3174）—— 仅用于计算证书指纹给 certutil 比对，不参与任何安全决策。
fn sha1_hex_upper(data: &[u8]) -> String {
    let h = sha1_bytes(data);
    let mut s = String::with_capacity(40);
    for b in &h { s.push_str(&format!("{:02X}", b)); }
    s
}

/// 标准 SHA-1，返回 20 字节原始 hash。
fn sha1_bytes(data: &[u8]) -> [u8; 20] {
    let mut h0: u32 = 0x67452301;
    let mut h1: u32 = 0xEFCDAB89;
    let mut h2: u32 = 0x98BADCFE;
    let mut h3: u32 = 0x10325476;
    let mut h4: u32 = 0xC3D2E1F0;

    let mut msg = data.to_vec();
    let bit_len = (data.len() as u64) * 8;
    msg.push(0x80);
    while msg.len() % 64 != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in msg.chunks_exact(64) {
        let mut w = [0u32; 80];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([chunk[i*4], chunk[i*4+1], chunk[i*4+2], chunk[i*4+3]]);
        }
        for i in 16..80 {
            w[i] = (w[i-3] ^ w[i-8] ^ w[i-14] ^ w[i-16]).rotate_left(1);
        }
        let (mut a, mut b, mut c, mut d, mut e) = (h0, h1, h2, h3, h4);
        for i in 0..80 {
            let (f, k) = match i {
                0..=19  => ((b & c) | ((!b) & d), 0x5A827999),
                20..=39 => (b ^ c ^ d, 0x6ED9EBA1),
                40..=59 => ((b & c) | (b & d) | (c & d), 0x8F1BBCDC),
                _       => (b ^ c ^ d, 0xCA62C1D6),
            };
            let temp = a.rotate_left(5).wrapping_add(f).wrapping_add(e).wrapping_add(k).wrapping_add(w[i]);
            e = d; d = c; c = b.rotate_left(30); b = a; a = temp;
        }
        h0 = h0.wrapping_add(a);
        h1 = h1.wrapping_add(b);
        h2 = h2.wrapping_add(c);
        h3 = h3.wrapping_add(d);
        h4 = h4.wrapping_add(e);
    }

    let mut out = [0u8; 20];
    out[0..4].copy_from_slice(&h0.to_be_bytes());
    out[4..8].copy_from_slice(&h1.to_be_bytes());
    out[8..12].copy_from_slice(&h2.to_be_bytes());
    out[12..16].copy_from_slice(&h3.to_be_bytes());
    out[16..20].copy_from_slice(&h4.to_be_bytes());
    out
}

// ============================================================================
// Windows: 证书安装 / 卸载（certutil + 可选 PowerShell UAC 提权）
// ============================================================================

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

#[cfg(target_os = "windows")]
fn run_certutil(args: &[&str]) -> std::io::Result<std::process::Output> {
    use std::os::windows::process::CommandExt;
    std::process::Command::new("certutil.exe")
        .args(args)
        .creation_flags(CREATE_NO_WINDOW)
        .output()
}

/// 检查证书是否已在 store 中（thumbprint 大写无分隔）。
/// HKCU 直接 reg query；HKLM 用 certutil（只读，不弹任何 UI）。
#[cfg(target_os = "windows")]
fn is_cert_installed(thumbprint: &str, user_store: bool) -> bool {
    if user_store {
        use std::os::windows::process::CommandExt;
        let key_path = format!(
            "HKCU\\Software\\Microsoft\\SystemCertificates\\Root\\Certificates\\{}",
            thumbprint
        );
        let out = std::process::Command::new("reg")
            .args(["query", &key_path, "/v", "Blob"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
        return matches!(out, Ok(o) if o.status.success());
    }
    let args = vec!["-verifystore", "Root", thumbprint];
    match run_certutil(&args) {
        Ok(out) => {
            let stdout = String::from_utf8_lossy(&out.stdout).to_uppercase();
            out.status.success() && stdout.contains(thumbprint)
        }
        Err(_) => false,
    }
}

/// 装到 CurrentUser\Root —— 直接写注册表 `HKCU\Software\Microsoft\SystemCertificates\Root\Certificates\<thumb>\Blob`
///
/// 注意：certutil -addstore Root 会弹出 Windows 内置的「安全警告」对话框（无法绕过），
/// 因此放弃 certutil 改走注册表方式。Windows 在 CryptoAPI 初始化时会读取该注册表项，
/// 无任何 UI 提示，效果与 certutil 等价。
///
/// Blob 二进制格式（多个 TLV 拼接，每个 TLV = propId(DWORD) + flags(DWORD=1) + len(DWORD) + value）：
///   PropID 0x03 (CERT_SHA1_HASH_PROP_ID): SHA-1 of DER, 20 字节
///   PropID 0x20 (CERT_CERT_PROP_ID):      DER 证书完整字节
#[cfg(target_os = "windows")]
fn build_cert_blob(der: &[u8], sha1: &[u8; 20]) -> Vec<u8> {
    let mut blob: Vec<u8> = Vec::with_capacity(20 * 2 + 12 * 2 + der.len());

    // 1. SHA-1 hash 属性
    blob.extend_from_slice(&0x03u32.to_le_bytes()); // CERT_SHA1_HASH_PROP_ID
    blob.extend_from_slice(&0x01u32.to_le_bytes()); // reserved/flags
    blob.extend_from_slice(&(sha1.len() as u32).to_le_bytes());
    blob.extend_from_slice(sha1);

    // 2. 证书本体
    blob.extend_from_slice(&0x20u32.to_le_bytes()); // CERT_CERT_PROP_ID
    blob.extend_from_slice(&0x01u32.to_le_bytes());
    blob.extend_from_slice(&(der.len() as u32).to_le_bytes());
    blob.extend_from_slice(der);

    blob
}

#[cfg(target_os = "windows")]
fn install_cert_user_store(_pem: &Path) -> bool {
    // 读 DER + 算 SHA-1
    let (der, sha1) = match read_ca_der_and_sha1() {
        Ok(v) => v,
        Err(_) => return false,
    };
    let thumb = sha1_bytes_to_hex_upper(&sha1);
    let blob = build_cert_blob(&der, &sha1);

    // 写入注册表 HKCU\Software\Microsoft\SystemCertificates\Root\Certificates\<THUMB>\Blob
    // reg add 接受 REG_BINARY 的 /d 参数为连续 hex 字符串（无分隔）
    let hex: String = blob.iter().map(|b| format!("{:02X}", b)).collect();
    let key_path = format!(
        "HKCU\\Software\\Microsoft\\SystemCertificates\\Root\\Certificates\\{}",
        thumb
    );

    use std::os::windows::process::CommandExt;
    let out = std::process::Command::new("reg")
        .args(["add", &key_path, "/v", "Blob", "/t", "REG_BINARY", "/d", &hex, "/f"])
        .creation_flags(CREATE_NO_WINDOW)
        .output();
    matches!(out, Ok(o) if o.status.success())
}

/// 读取 CA 的 DER 字节 + 计算 SHA-1（20 字节，无格式化）。
#[cfg(target_os = "windows")]
fn read_ca_der_and_sha1() -> Result<(Vec<u8>, [u8; 20]), String> {
    let pem = fs::read_to_string(ca_cert_pem_path()).map_err(|e| format!("读 CA cert: {}", e))?;
    let mut in_block = false;
    let mut b64 = String::new();
    for line in pem.lines() {
        if line.contains("BEGIN CERTIFICATE") { in_block = true; continue; }
        if line.contains("END CERTIFICATE") { break; }
        if in_block { b64.push_str(line.trim()); }
    }
    let der = base64::Engine::decode(&base64::engine::general_purpose::STANDARD, &b64)
        .map_err(|e| format!("解析 PEM base64 失败: {}", e))?;
    let sha1 = sha1_bytes(&der);
    Ok((der, sha1))
}

#[cfg(target_os = "windows")]
fn sha1_bytes_to_hex_upper(sha1: &[u8; 20]) -> String {
    let mut s = String::with_capacity(40);
    for b in sha1 { s.push_str(&format!("{:02X}", b)); }
    s
}

/// 装到 LocalMachine\Root（通过 PowerShell -Verb RunAs 弹一次 UAC）。
/// 用户点"否" → exit code 1223 → 返回 false。
#[cfg(target_os = "windows")]
fn install_cert_machine_store_with_uac(pem: &Path) -> bool {
    use std::os::windows::process::CommandExt;
    let p = pem.to_string_lossy().replace('\'', "''");
    let script = format!(
        "$p = Start-Process -FilePath 'certutil.exe' \
         -ArgumentList @('-addstore','Root','{}') \
         -Verb RunAs -WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode",
        p
    );
    let out = std::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", &script])
        .creation_flags(CREATE_NO_WINDOW)
        .output();
    matches!(out, Ok(o) if o.status.success())
}

/// 卸载：从 user store 和 machine store 都试一次。失败忽略。
#[cfg(target_os = "windows")]
fn uninstall_cert_all_stores(thumbprint: &str) {
    use std::os::windows::process::CommandExt;
    // 用户 store —— 直接删注册表项（与安装方式对称，无 UAC、无对话框）
    let key_path = format!(
        "HKCU\\Software\\Microsoft\\SystemCertificates\\Root\\Certificates\\{}",
        thumbprint
    );
    let _ = std::process::Command::new("reg")
        .args(["delete", &key_path, "/f"])
        .creation_flags(CREATE_NO_WINDOW)
        .output();
    // 兜底：旧版本可能用 certutil 装到 user store 过，也删一下（静默无 UI）
    let _ = run_certutil(&["-user", "-delstore", "Root", thumbprint]);

    // 机器 store —— 需要 UAC，用 PowerShell 提权
    let script = format!(
        "$p = Start-Process -FilePath 'certutil.exe' \
         -ArgumentList @('-delstore','Root','{}') \
         -Verb RunAs -WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode",
        thumbprint
    );
    let _ = std::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", &script])
        .creation_flags(CREATE_NO_WINDOW)
        .output();
}

/// 确保 CA 安装到 Windows 信任根。返回最终所在 store 名。
#[cfg(target_os = "windows")]
pub fn ensure_ca_installed_in_system_store() -> Result<String, String> {
    let pem = ca_cert_pem_path();
    if !pem.exists() {
        return Err("CA 证书文件不存在".to_string());
    }
    let thumb = ca_sha1_thumbprint()?;

    if is_cert_installed(&thumb, true) {
        return Ok("CurrentUser\\Root".to_string());
    }
    if is_cert_installed(&thumb, false) {
        return Ok("LocalMachine\\Root".to_string());
    }
    if install_cert_user_store(&pem) {
        return Ok("CurrentUser\\Root".to_string());
    }
    if install_cert_machine_store_with_uac(&pem) {
        return Ok("LocalMachine\\Root".to_string());
    }
    Err("证书安装失败：用户拒绝 UAC 或 certutil 报错".to_string())
}

#[cfg(target_os = "windows")]
pub fn uninstall_ca_from_system_store() {
    if let Ok(thumb) = ca_sha1_thumbprint() {
        uninstall_cert_all_stores(&thumb);
    }
}

/// 检查 CA 是否已安装到任一 Windows store
#[cfg(target_os = "windows")]
pub fn is_ca_installed_in_system_store() -> bool {
    let thumb = match ca_sha1_thumbprint() {
        Ok(t) => t,
        Err(_) => return false,
    };
    is_cert_installed(&thumb, true) || is_cert_installed(&thumb, false)
}

// ============================================================================
// macOS: 证书安装 / 卸载（钥匙串 + security 命令）
// ============================================================================
//
// 关键事实：
//   - macOS 没有"用户根 / 机器根"两个 store 的概念，统一用钥匙串。
//   - 装到登录钥匙串（~/Library/Keychains/login.keychain-db）只需要用户输一次
//     登录密码（GUI 弹框，不是 sudo），效果对所有用户应用都生效。
//   - `-p ssl` 表示"仅 SSL 用途信任"，比 `-r trustRoot` 弹框更轻量。
//   - Cursor 主进程 Chromium 部分会读钥匙串；内嵌 Node 不读 →
//     另外靠 NODE_EXTRA_CA_CERTS 环境变量补刀。
//
// 命令：
//   security add-trusted-cert -p ssl -k ~/Library/Keychains/login.keychain-db <pem>
//   security delete-certificate -Z <SHA1> ~/Library/Keychains/login.keychain-db
//   security find-certificate -a -Z ~/Library/Keychains/login.keychain-db | grep <SHA1>
// ============================================================================

#[cfg(target_os = "macos")]
fn login_keychain_path() -> PathBuf {
    let home = dirs::home_dir().unwrap_or_default();
    home.join("Library").join("Keychains").join("login.keychain-db")
}

/// 计算 CA 的 SHA-1 thumbprint（与 Windows 共用，但 macOS 上需要单独入口）
#[cfg(target_os = "macos")]
fn ca_sha1_thumbprint_mac() -> Result<String, String> {
    ca_sha1_thumbprint()
}

#[cfg(target_os = "macos")]
pub fn ensure_ca_installed_in_system_store() -> Result<String, String> {
    let pem = ca_cert_pem_path();
    if !pem.exists() {
        return Err("CA 证书文件不存在".to_string());
    }

    // 如果已装，直接返回
    if is_ca_installed_in_system_store() {
        return Ok("login.keychain".to_string());
    }

    let keychain = login_keychain_path();
    let pem_str = pem.to_string_lossy().to_string();
    let kc_str = keychain.to_string_lossy().to_string();

    // 装到登录钥匙串，仅 SSL 用途信任 —— 会弹一次「输入登录密码」对话框
    let out = std::process::Command::new("security")
        .args(["add-trusted-cert", "-p", "ssl", "-k", &kc_str, &pem_str])
        .output()
        .map_err(|e| format!("调用 security 失败: {}", e))?;

    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        return Err(format!("钥匙串安装失败: {}", stderr.trim()));
    }
    Ok("login.keychain".to_string())
}

#[cfg(target_os = "macos")]
pub fn uninstall_ca_from_system_store() {
    let thumb = match ca_sha1_thumbprint_mac() {
        Ok(t) => t,
        Err(_) => return,
    };
    let keychain = login_keychain_path();
    let kc_str = keychain.to_string_lossy().to_string();

    // -Z 后跟大写无分隔 SHA-1
    let _ = std::process::Command::new("security")
        .args(["delete-certificate", "-Z", &thumb, &kc_str])
        .output();
}

#[cfg(target_os = "macos")]
pub fn is_ca_installed_in_system_store() -> bool {
    let thumb = match ca_sha1_thumbprint_mac() {
        Ok(t) => t,
        Err(_) => return false,
    };
    let keychain = login_keychain_path();
    let kc_str = keychain.to_string_lossy().to_string();

    // -a 列出所有，-Z 显示 SHA-1；grep 找指纹
    let out = std::process::Command::new("security")
        .args(["find-certificate", "-a", "-Z", &kc_str])
        .output();
    match out {
        Ok(o) => {
            let s = String::from_utf8_lossy(&o.stdout).to_uppercase();
            o.status.success() && s.contains(&thumb)
        }
        Err(_) => false,
    }
}

// === Linux / 其它平台占位 ===
#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub fn ensure_ca_installed_in_system_store() -> Result<String, String> {
    Err("当前平台不支持自动安装 CA".to_string())
}
#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub fn uninstall_ca_from_system_store() {}
#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub fn is_ca_installed_in_system_store() -> bool { false }

// ============================================================================
// NODE_EXTRA_CA_CERTS 环境变量
// ============================================================================
//
// Windows: 用 `setx` 写 HKCU\Environment（用户级，无 UAC）；卸载用 `reg delete`。
//
// macOS: 双管齐下 ——
//   - `launchctl setenv NODE_EXTRA_CA_CERTS <pem>` 立即让当前登录会话生效
//   - 写 LaunchAgent plist 到 `~/Library/LaunchAgents/com.cursor-renewal.unlock.plist`
//     注册 setenv，重启 / 重新登录后由 launchd 自动重放
//
// 关键：launchctl 设的环境变量只对从「同一个 launchd 会话」启动的进程生效。
// 用户从 Dock / Finder / Spotlight 启动的 Cursor 都走这个 session，所以 OK；
// 但从已运行的 Terminal 启动的 Cursor 会读 shell 的 env，不一定能拿到 ——
// 这是 macOS 自己的限制，无法绕过，提示用户用 Dock 启动即可。
// ============================================================================

#[cfg(target_os = "windows")]
pub fn set_node_extra_ca_certs_user(pem: &Path) -> Result<(), String> {
    use std::os::windows::process::CommandExt;
    let p = pem.to_string_lossy().to_string();

    let out = std::process::Command::new("setx")
        .args(["NODE_EXTRA_CA_CERTS", &p])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
        .map_err(|e| format!("setx 失败: {}", e))?;
    if !out.status.success() {
        return Err(format!("setx 返回非零: {}", out.status));
    }
    // 当前进程也立即生效
    std::env::set_var("NODE_EXTRA_CA_CERTS", &p);
    Ok(())
}

#[cfg(target_os = "windows")]
pub fn clear_node_extra_ca_certs() {
    use std::os::windows::process::CommandExt;
    let _ = std::process::Command::new("reg")
        .args(["delete", "HKCU\\Environment", "/F", "/V", "NODE_EXTRA_CA_CERTS"])
        .creation_flags(CREATE_NO_WINDOW)
        .output();
    std::env::remove_var("NODE_EXTRA_CA_CERTS");
}

#[cfg(target_os = "windows")]
#[allow(dead_code)]
pub fn get_node_extra_ca_certs() -> Option<String> {
    // 优先看 HKCU（setx 写入位置）
    use std::os::windows::process::CommandExt;
    let out = std::process::Command::new("reg")
        .args(["query", "HKCU\\Environment", "/v", "NODE_EXTRA_CA_CERTS"])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
        .ok()?;
    if !out.status.success() { return None; }
    let s = String::from_utf8_lossy(&out.stdout);
    // 解析 "REG_SZ <value>"
    for line in s.lines() {
        if line.contains("NODE_EXTRA_CA_CERTS") {
            if let Some(idx) = line.find("REG_SZ") {
                let v = line[idx + 6..].trim();
                if !v.is_empty() { return Some(v.to_string()); }
            }
        }
    }
    None
}

// === macOS ===
#[cfg(target_os = "macos")]
const MAC_LAUNCH_AGENT_LABEL: &str = "com.cursor-renewal.unlock";

#[cfg(target_os = "macos")]
fn mac_launch_agent_plist_path() -> PathBuf {
    let home = dirs::home_dir().unwrap_or_default();
    home.join("Library")
        .join("LaunchAgents")
        .join(format!("{}.plist", MAC_LAUNCH_AGENT_LABEL))
}

#[cfg(target_os = "macos")]
pub fn set_node_extra_ca_certs_user(pem: &Path) -> Result<(), String> {
    let p = pem.to_string_lossy().to_string();

    // 1. launchctl setenv：立即让 GUI 会话所有新进程生效
    let out = std::process::Command::new("launchctl")
        .args(["setenv", "NODE_EXTRA_CA_CERTS", &p])
        .output()
        .map_err(|e| format!("调用 launchctl 失败: {}", e))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(format!("launchctl setenv 失败: {}", err.trim()));
    }

    // 2. 写 LaunchAgent plist —— 重启后自动重放 setenv
    let plist_path = mac_launch_agent_plist_path();
    if let Some(parent) = plist_path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("创建 LaunchAgents 目录失败: {}", e))?;
    }
    let plist_content = format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/launchctl</string>
        <string>setenv</string>
        <string>NODE_EXTRA_CA_CERTS</string>
        <string>{pem}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"#,
        label = MAC_LAUNCH_AGENT_LABEL,
        pem = xml_escape(&p),
    );
    fs::write(&plist_path, plist_content)
        .map_err(|e| format!("写 LaunchAgent plist 失败: {}", e))?;

    // 3. launchctl load 启用（如已 load 失败可忽略；macOS 12+ 推荐用 bootstrap，
    //    旧版仍兼容 load，这里都试一遍）
    let plist_str = plist_path.to_string_lossy().to_string();
    let _ = std::process::Command::new("launchctl")
        .args(["unload", &plist_str])
        .output();
    let _ = std::process::Command::new("launchctl")
        .args(["load", &plist_str])
        .output();

    // 4. 当前进程也立即生效（不影响 Cursor，但保持一致性）
    std::env::set_var("NODE_EXTRA_CA_CERTS", &p);
    Ok(())
}

#[cfg(target_os = "macos")]
pub fn clear_node_extra_ca_certs() {
    // 1. 卸载 LaunchAgent
    let plist_path = mac_launch_agent_plist_path();
    if plist_path.exists() {
        let plist_str = plist_path.to_string_lossy().to_string();
        let _ = std::process::Command::new("launchctl")
            .args(["unload", &plist_str])
            .output();
        let _ = fs::remove_file(&plist_path);
    }
    // 2. 从当前 GUI 会话清掉 setenv
    let _ = std::process::Command::new("launchctl")
        .args(["unsetenv", "NODE_EXTRA_CA_CERTS"])
        .output();
    std::env::remove_var("NODE_EXTRA_CA_CERTS");
}

#[cfg(target_os = "macos")]
#[allow(dead_code)]
pub fn get_node_extra_ca_certs() -> Option<String> {
    let out = std::process::Command::new("launchctl")
        .args(["getenv", "NODE_EXTRA_CA_CERTS"])
        .output()
        .ok()?;
    if !out.status.success() { return None; }
    let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if s.is_empty() { None } else { Some(s) }
}

#[cfg(target_os = "macos")]
fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

// === Linux / 其它平台占位 ===
#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub fn set_node_extra_ca_certs_user(_pem: &Path) -> Result<(), String> { Ok(()) }
#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub fn clear_node_extra_ca_certs() {}
#[cfg(not(any(target_os = "windows", target_os = "macos")))]
#[allow(dead_code)]
pub fn get_node_extra_ca_certs() -> Option<String> { None }

// ============================================================================
// Cursor settings.json 的安全合并（JSONC-tolerant，保留用户其它键）
// ============================================================================

fn cursor_user_settings_path() -> Option<PathBuf> {
    utils::get_cursor_data_dir().map(|d| d.join("User").join("settings.json"))
}

/// 剥离 JSONC 注释和尾随逗号，输出标准 JSON 文本。
fn strip_jsonc(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let n = bytes.len();
    let mut in_str = false;
    let mut escape = false;

    // 去 BOM
    let mut i = if bytes.starts_with(b"\xEF\xBB\xBF") { 3 } else { 0 };

    while i < n {
        let c = bytes[i];
        if in_str {
            out.push(c);
            if escape { escape = false; }
            else if c == b'\\' { escape = true; }
            else if c == b'"' { in_str = false; }
            i += 1;
            continue;
        }
        if c == b'"' { in_str = true; out.push(c); i += 1; continue; }
        if c == b'/' && i + 1 < n {
            let nxt = bytes[i + 1];
            if nxt == b'/' {
                i += 2;
                while i < n && bytes[i] != b'\n' { i += 1; }
                continue;
            }
            if nxt == b'*' {
                i += 2;
                while i + 1 < n && !(bytes[i] == b'*' && bytes[i + 1] == b'/') { i += 1; }
                i = (i + 2).min(n);
                continue;
            }
        }
        out.push(c); i += 1;
    }
    let cleaned = String::from_utf8(out).unwrap_or_default();
    // 去尾随逗号  ,}  ,]
    let re = regex::Regex::new(r",(\s*[}\]])").unwrap();
    re.replace_all(&cleaned, "$1").to_string()
}

fn load_cursor_settings() -> serde_json::Map<String, serde_json::Value> {
    let path = match cursor_user_settings_path() {
        Some(p) => p,
        None => return Default::default(),
    };
    if !path.exists() {
        return Default::default();
    }
    let raw = match fs::read_to_string(&path) {
        Ok(r) => r,
        Err(_) => return Default::default(),
    };
    if raw.trim().is_empty() {
        return Default::default();
    }
    let cleaned = strip_jsonc(&raw);
    let val: serde_json::Value = match serde_json::from_str(&cleaned) {
        Ok(v) => v,
        Err(_) => return Default::default(),
    };
    val.as_object().cloned().unwrap_or_default()
}

fn save_cursor_settings(obj: &serde_json::Map<String, serde_json::Value>) -> Result<(), String> {
    let path = match cursor_user_settings_path() {
        Some(p) => p,
        None => return Err("无法定位 Cursor settings.json 路径".to_string()),
    };
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("创建目录失败: {}", e))?;
    }
    let value = serde_json::Value::Object(obj.clone());
    let encoded = serde_json::to_string_pretty(&value)
        .map_err(|e| format!("序列化 settings.json 失败: {}", e))?
        + "\n";
    // 原子写：写到 .tmp 再 rename
    let tmp = path.with_extension("json.tmp");
    {
        let mut f = fs::File::create(&tmp).map_err(|e| format!("创建临时文件失败: {}", e))?;
        f.write_all(encoded.as_bytes())
            .map_err(|e| format!("写临时文件失败: {}", e))?;
        f.sync_all().ok();
    }
    utils::clear_macos_immutable_flag(&path);
    fs::rename(&tmp, &path).map_err(|e| format!("替换 settings.json 失败: {}", e))?;
    Ok(())
}

/// 写入代理配置（保留用户已有键，只追加 / 覆盖我们管理的键）。
pub fn apply_cursor_proxy_settings() -> Result<(), String> {
    let mut s = load_cursor_settings();
    s.insert(
        "http.proxy".to_string(),
        serde_json::Value::String(PROXY_URL.to_string()),
    );
    s.insert(
        "http.experimental.systemCertificatesV2".to_string(),
        serde_json::Value::Bool(true),
    );
    save_cursor_settings(&s)
}

/// 清理：只移除我们管理的键，用户其它键原样保留。
pub fn clear_cursor_proxy_settings() -> Result<(), String> {
    let mut s = load_cursor_settings();
    let mut changed = false;
    for k in MANAGED_SETTINGS_KEYS {
        if s.remove(*k).is_some() {
            changed = true;
        }
    }
    if changed { save_cursor_settings(&s) } else { Ok(()) }
}

/// 检查 settings.json 中是否已写入我们的代理键
#[allow(dead_code)]
pub fn cursor_proxy_settings_applied() -> bool {
    let s = load_cursor_settings();
    s.get("http.proxy").and_then(|v| v.as_str()) == Some(PROXY_URL)
}

// ============================================================================
// 对外编排：enable_unlock / disable_unlock / auto_restore_on_startup
// ============================================================================

/// 完整开启 UI 解锁：CA 装系统 → 设环境变量 → 写 settings.json → 启 MITM。
/// 任一步失败：尝试回滚已执行的步骤，返回错误。
pub fn enable_unlock() -> Result<(), String> {
    ensure_ca_exists()?;

    // 1. CA 安装
    if let Err(e) = ensure_ca_installed_in_system_store() {
        return Err(format!("CA 安装失败: {}", e));
    }

    // 2. NODE_EXTRA_CA_CERTS
    let pem = ca_cert_pem_path();
    if let Err(e) = set_node_extra_ca_certs_user(&pem) {
        // 不致命，但提醒；继续
        eprintln!("[unlock] 设置 NODE_EXTRA_CA_CERTS 失败: {}", e);
    }

    // 3. settings.json
    if let Err(e) = apply_cursor_proxy_settings() {
        return Err(format!("写入 Cursor settings.json 失败: {}", e));
    }

    // 4. 启 MITM
    if let Err(e) = start_mitm_in_background() {
        return Err(format!("启动 MITM 代理失败: {}", e));
    }

    Ok(())
}

/// 完整关闭：停 MITM → 删 settings.json 代理键 → 清环境变量 → 删 CA。
pub fn disable_unlock() -> Result<(), String> {
    stop_mitm();
    let _ = clear_cursor_proxy_settings();
    clear_node_extra_ca_certs();

    // 删 CA：先从系统 store 卸，再删本地 PEM
    uninstall_ca_from_system_store();
    let _ = fs::remove_file(ca_cert_pem_path());
    let _ = fs::remove_file(ca_key_pem_path());

    Ok(())
}

/// 程序启动时调用：如果检测到 CA 已经安装 → 自动启 MITM 代理（用户偏好）。
pub fn auto_restore_on_startup() {
    // 没生成过 CA → 用户从来没开过解锁 → 跳过
    if !ca_cert_pem_path().exists() {
        return;
    }
    // CA 不在 Windows 信任根 → 之前被清理过 → 跳过
    if !is_ca_installed_in_system_store() {
        return;
    }
    // 静默重启 MITM；任何错误吞掉，不打扰用户
    let _ = start_mitm_in_background();
}

/// 综合判断 UI 解锁是否处于「已开启」状态：
///   CA 已生成 + CA 在系统信任根 + settings.json 已写代理键 + MITM 在跑
#[allow(dead_code)]
pub fn is_unlock_enabled() -> bool {
    ca_cert_pem_path().exists()
        && is_ca_installed_in_system_store()
        && cursor_proxy_settings_applied()
        && is_mitm_running()
}

// ============================================================================
// Tauri commands —— 当前主流程通过 patch_ext_host / unpatch_ext_host
// 间接调用 enable_unlock / disable_unlock，这里的独立命令保留是为了
// 未来 UI 可能想单独控制（例如「只换 stripe profile 不打 ExtHost 补丁」）
// 以及方便手动诊断。
// ============================================================================

#[tauri::command]
#[allow(dead_code)]
pub async fn unlock_enable() -> serde_json::Value {
    match tokio::task::spawn_blocking(|| {
        // CA 安装可能弹 UAC，要在阻塞线程做
        ensure_ca_exists()?;
        if let Err(e) = ensure_ca_installed_in_system_store() {
            return Err(format!("CA 安装失败: {}", e));
        }
        let pem = ca_cert_pem_path();
        let _ = set_node_extra_ca_certs_user(&pem);
        apply_cursor_proxy_settings().map_err(|e| format!("写入 settings.json 失败: {}", e))?;
        Ok::<(), String>(())
    }).await
    {
        Ok(Ok(())) => {
            // MITM 启动要在 tokio runtime 上
            if let Err(e) = start_mitm_in_background() {
                return serde_json::json!({"success": false, "error": e});
            }
            serde_json::json!({"success": true, "message": "模型解锁已开启"})
        }
        Ok(Err(e)) => serde_json::json!({"success": false, "error": e}),
        Err(e) => serde_json::json!({"success": false, "error": format!("任务调度失败: {}", e)}),
    }
}

#[tauri::command]
#[allow(dead_code)]
pub async fn unlock_disable() -> serde_json::Value {
    stop_mitm();
    match tokio::task::spawn_blocking(|| {
        let _ = clear_cursor_proxy_settings();
        clear_node_extra_ca_certs();
        uninstall_ca_from_system_store();
        let _ = fs::remove_file(ca_cert_pem_path());
        let _ = fs::remove_file(ca_key_pem_path());
    }).await
    {
        Ok(_) => serde_json::json!({"success": true, "message": "模型解锁已关闭"}),
        Err(e) => serde_json::json!({"success": false, "error": format!("任务调度失败: {}", e)}),
    }
}

#[tauri::command]
#[allow(dead_code)]
pub async fn unlock_status() -> serde_json::Value {
    serde_json::json!({
        "enabled": is_unlock_enabled(),
        "caExists": ca_cert_pem_path().exists(),
        "caInstalled": is_ca_installed_in_system_store(),
        "proxyApplied": cursor_proxy_settings_applied(),
        "mitmRunning": is_mitm_running(),
    })
}
