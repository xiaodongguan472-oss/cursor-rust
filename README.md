# Cursor续杯助手 - Rust + Tauri 版

[![Build Multi-Platform](https://github.com/xiaodongguan472-oss/cursor-rust/actions/workflows/build.yml/badge.svg)](https://github.com/xiaodongguan472-oss/cursor-rust/actions/workflows/build.yml)

将原 Electron 版本完整迁移至 **Tauri v1 + Rust** 后端，前端 UI 保持不变。

## 自动化构建

通过 GitHub Actions 一次性产出 **Windows / macOS Intel / macOS Apple Silicon** 三平台二进制：

- 推送到 `main` / `master` 分支或发起 PR：自动构建并上传 Artifacts（保留 30 天）
- 推送 `v*` 标签（如 `v8.4.0`）：自动构建并发布 GitHub Release

### 触发构建

```bash
# 1) 普通推送（仅产出 Artifacts）
git push origin main

# 2) 发版（产出 Release）
git tag v8.4.0
git push origin v8.4.0

# 3) 手动触发
# Actions 页面 → Build Multi-Platform → Run workflow
```

### 产物命名

| 平台 | 产物 |
|---|---|
| Windows x64 | `续杯助手-windows-x64.exe` |
| macOS Intel | `续杯助手-mac-intel-x64` |
| macOS Apple Silicon (M1/M2/M3) | `续杯助手-mac-apple-silicon-arm64` |



## 项目结构

```
cursor-rust/
├── src-tauri/                  # Rust 后端 (Tauri)
│   ├── Cargo.toml              # Rust 依赖配置
│   ├── build.rs                # Tauri 构建脚本
│   ├── tauri.conf.json         # Tauri 应用配置
│   ├── icons/                  # 应用图标
│   └── src/
│       ├── main.rs             # 入口，注册所有命令
│       └── commands/
│           ├── mod.rs           # 模块声明
│           ├── utils.rs         # 工具函数（路径、HTTP、加密）
│           ├── settings.rs      # 应用设置读写
│           ├── cursor_paths.rs  # Cursor 安装路径检测
│           ├── machine_id.rs    # 机器码生成与重置
│           ├── database.rs      # SQLite 数据库操作
│           ├── file_ops.rs      # 文件读写与对话框
│           ├── cursor_modify.rs # Cursor main.js/workbench 修改
│           ├── cursor_process.rs# 进程检测/关闭/启动
│           ├── card.rs          # 卡密验证与管理
│           ├── api.rs           # 后端 API 调用
│           ├── permissions.rs   # 权限检测/禁用自动更新
│           ├── model.rs         # 默认 AI 模型设置
│           ├── proxy.rs         # 代理/地区限制设置
│           ├── seamless_switch.rs # 无感换号/自动换号
│           ├── workspace.rs     # 工作区保存与恢复
│           └── window_ctrl.rs   # 窗口最小化/关闭
└── ui/                         # 前端文件
    ├── index.html              # 主页面 (从 Electron 版复制，最小修改)
    ├── tauri-bridge.js         # Electron IPC → Tauri invoke 桥接层
    ├── element-plus.css        # Element Plus 样式
    ├── element-plus.js         # Element Plus 组件库
    └── vue.global.js           # Vue 3 运行时
```

## 架构说明

### Electron → Tauri 迁移策略

1. **前端零修改**：UI/样式代码完全保留，仅替换 `<script>` 标签中的环境检测逻辑
2. **桥接层透明代理**：`tauri-bridge.js` 将 `require('electron').ipcRenderer.invoke()` 透明映射到 `window.__TAURI__.tauri.invoke()`
3. **Rust 后端完整实现**：所有 Electron `ipcMain.handle()` 处理器均用 Rust `#[tauri::command]` 重新实现

### IPC 命令对照表（共 50+ 命令）

| 类别 | 命令数 | Rust 模块 |
|------|--------|-----------|
| 设置管理 | 3 | `settings.rs` |
| 路径检测 | 2 | `cursor_paths.rs` |
| 机器码 | 3 | `machine_id.rs` |
| 数据库操作 | 5 | `database.rs` |
| 文件操作 | 5 | `file_ops.rs` |
| 文件修改 | 4 | `cursor_modify.rs` |
| 进程管理 | 5 | `cursor_process.rs` |
| 卡密验证 | 7 | `card.rs` |
| API 调用 | 5 | `api.rs` |
| 权限管理 | 2 | `permissions.rs` |
| 模型设置 | 1 | `model.rs` |
| 代理设置 | 2 | `proxy.rs` |
| 无感换号 | 12 | `seamless_switch.rs` |
| 工作区 | 2 | `workspace.rs` |
| 窗口控制 | 2 | `window_ctrl.rs` |

## 开发

### 环境要求

- Rust 1.70+
- 系统 WebView2 运行时 (Windows 自带)

### 开发模式

```bash
cd src-tauri
cargo build
# 或直接运行
cargo run
```

### 生产构建

```bash
cd src-tauri
cargo build --release
```

Release 二进制位于 `src-tauri/target/release/cursor-renewal.exe`

### 打包分发 (可选)

安装 Tauri CLI 后可生成安装包：

```bash
cargo install tauri-cli
cargo tauri build
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 框架 | Tauri v1.8 |
| 后端 | Rust (tokio async runtime) |
| 前端 | Vue 3 + Element Plus (CDN/本地) |
| HTTP | reqwest (rustls-tls) |
| 数据库 | rusqlite (SQLite bundled) |
| 加密 | sha2, uuid, md5 |
| 进程管理 | sysinfo, std::process |

## 相比 Electron 版的优势

- **体积**：~24 MB (debug) → ~8 MB (release)，Electron 版 ~150 MB
- **内存**：~30 MB 运行时，Electron 版 ~200 MB
- **安全**：Rust 编译的二进制，核心逻辑不可直接反编译
- **启动**：秒开，无 Node.js 启动开销
