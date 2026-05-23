/**
 * Electron → Tauri 桥接层
 * 将 Electron 的 ipcRenderer API 映射到 Tauri 的 invoke/listen API
 * 前端代码无需修改，通过此桥接层透明使用 Tauri 后端
 */
(function () {
  'use strict';

  // 延迟获取 Tauri API，避免在 __TAURI__ 还未注入时崩溃
  let _invoke = null;
  let _listen = null;
  let _appWindow = null;

  function getTauriApi() {
    if (_invoke) return true;
    if (window.__TAURI__) {
      _invoke = window.__TAURI__.tauri.invoke;
      _listen = window.__TAURI__.event.listen;
      _appWindow = window.__TAURI__.window.appWindow;
      return true;
    }
    return false;
  }

  // 命令名称映射: Electron IPC channel name → Tauri command name
  const COMMAND_MAP = {
    // Settings
    'get-settings': 'get_settings',
    'save-settings': 'save_settings',
    'quit-app': 'quit_app',
    // Cursor paths
    'get-cursor-paths': 'get_cursor_paths',
    'get-user-data-path': 'get_user_data_path',
    // Machine ID
    'get-machine-id': 'get_machine_id',
    'reset-cursor-machine-id': 'reset_cursor_machine_id',
    'reset-machine-ids-standalone': 'reset_machine_ids_standalone',
    // Database
    'find-all-cursor-databases': 'find_all_cursor_databases',
    'manual-search-cursor-database': 'manual_search_cursor_database',
    'update-cursor-sqlite-db': 'update_cursor_sqlite_db',
    'update-cursor-auth': 'update_cursor_auth',
    'logout-current-cursor-account': 'logout_current_cursor_account',
    'python-style-account-switch': 'python_style_account_switch',
    // File operations
    'read-file': 'read_file_content',
    'write-file': 'write_file_content',
    'open-file-dialog': 'open_file_dialog',
    'open-folder-dialog': 'open_folder_dialog',
    'open-external-url': 'open_external_url',
    // Cursor file modification
    'modify-cursor-main-js': 'modify_cursor_main_js',
    'analyze-cursor-file': 'analyze_cursor_file',
    'restore-cursor-backup': 'restore_cursor_backup',
    'modify-cursor-workbench': 'modify_cursor_workbench',
    // Cursor process
    'check-cursor-running': 'check_cursor_running',
    'force-close-cursor': 'force_close_cursor',
    'restart-cursor': 'restart_cursor',
    'restart-cursor-complete': 'restart_cursor_complete',
    'launch-cursor': 'launch_cursor',
    // Card
    'verify-card': 'verify_card',
    'verify-card-only': 'verify_card_only',
    'get-card-info': 'get_card_info',
    'save-card-info': 'save_card_info',
    'load-card-info': 'load_card_info',
    'clear-card-info': 'clear_card_info',
    'record-usage': 'record_usage',
    // API
    'get-latest-notice': 'get_latest_notice',
    'get-latest-tool-version': 'get_latest_tool_version',
    'get-latest-popup': 'get_latest_popup',
    'get-qrcode-image': 'get_qrcode_image',
    'check-version-update': 'check_version_update',
    // Permissions
    'get-current-permissions': 'get_current_permissions',
    'disable-cursor-auto-update': 'disable_cursor_auto_update',
    // Model
    'set-cursor-default-model': 'set_cursor_default_model',
    // Proxy
    'check-cursor-settings-status': 'check_cursor_settings_status',
    'update-cursor-settings': 'update_cursor_settings',
    // Seamless switch
    'patch-ext-host': 'patch_ext_host',
    'unpatch-ext-host': 'unpatch_ext_host',
    'check-ext-host-patched': 'check_ext_host_patched',
    'write-active-token': 'write_active_token',
    'read-active-token': 'read_active_token',
    'clear-active-token': 'clear_active_token',
    'check-cursor-usage': 'check_cursor_usage',
    'get-cursor-account-quota': 'get_cursor_account_quota',
    'seamless-switch': 'seamless_switch_cmd',
    'one-click-switch': 'one_click_switch',
    'toggle-auto-switch': 'toggle_auto_switch',
    'get-auto-switch-status': 'get_auto_switch_status',
    // Workspace
    'save-current-workspace': 'save_current_workspace',
    'load-saved-workspace': 'load_saved_workspace',
    // Updater
    'download-and-update': 'download_and_update',
    // Window control (these use send, not invoke)
    'minimize-window': 'minimize_window',
    'close-window': 'close_window',
    'show-main-window': 'show_main_window',
  };

  // 参数映射: 将 Electron invoke 的参数数组转为 Tauri invoke 的对象参数
  // 格式: command_name → 参数名数组（按位置映射）
  const PARAM_MAP = {
    'save_settings': ['settings'],
    'manual_search_cursor_database': ['searchPath'],
    'update_cursor_sqlite_db': ['dbPath'],
    'update_cursor_auth': ['dbPath', 'email', 'accessToken', 'refreshToken', 'machineIdReset'],
    'logout_current_cursor_account': ['dbPath'],
    'python_style_account_switch': ['dbPath', 'email', 'accessToken', 'refreshToken'],
    'read_file_content': ['filePath'],
    'write_file_content': ['filePath', 'content'],
    'open_external_url': ['url'],
    'modify_cursor_main_js': ['mainPath'],
    'analyze_cursor_file': ['filePath'],
    'restore_cursor_backup': ['filePath'],
    'modify_cursor_workbench': ['workbenchPath', 'isValid', 'days'],
    'restart_cursor': ['cursorPath'],
    'launch_cursor': ['workspacePath'],
    'verify_card': ['cardCode'],
    'verify_card_only': ['cardCode'],
    'get_card_info': ['cardCode'],
    'save_card_info': ['cardInfo'],
    'record_usage': ['cardCode'],
    'set_cursor_default_model': ['model'],
    'update_cursor_settings': ['enabled'],
    'write_active_token': ['token'],
    'check_cursor_usage': ['accessToken'],
    'get_cursor_account_quota': ['accessToken'],
    'seamless_switch_cmd': ['dbPath', 'email', 'accessToken', 'refreshToken'],
    'one_click_switch': ['dbPath', 'cardCode'],
    'toggle_auto_switch': ['enabled', 'cardCode'],
    'save_current_workspace': ['dbPath'],
    'load_saved_workspace': ['dbPath'],
    'download_and_update': ['url', 'fileName'],
  };

  // 事件监听器存储
  const eventListeners = new Map();

  /**
   * 将 Electron invoke 的参数数组转为 Tauri invoke 的命名参数对象
   */
  function buildInvokeArgs(tauriCmd, args) {
    const paramNames = PARAM_MAP[tauriCmd];
    if (!paramNames || !args || args.length === 0) {
      return {};
    }

    const result = {};
    for (let i = 0; i < paramNames.length && i < args.length; i++) {
      if (args[i] !== undefined) {
        result[paramNames[i]] = args[i];
      }
    }
    return result;
  }

  // 创建兼容的 ipcRenderer 对象
  const ipcRenderer = {
    /**
     * invoke(channel, ...args) → Tauri invoke(command, args)
     */
    invoke: async function (channel, ...args) {
      if (!getTauriApi()) {
        console.error('[Tauri Bridge] __TAURI__ 尚未就绪，无法调用:', channel);
        return null;
      }
      const tauriCmd = COMMAND_MAP[channel];
      if (!tauriCmd) {
        console.warn(`[Tauri Bridge] 未映射的IPC通道: ${channel}`);
        return null;
      }

      const invokeArgs = buildInvokeArgs(tauriCmd, args);

      console.log(`[Tauri Bridge] invoke: ${channel} → ${tauriCmd}`, invokeArgs);
      try {
        const result = await _invoke(tauriCmd, invokeArgs);
        console.log(`[Tauri Bridge] invoke ${channel} 成功:`, typeof result);
        return result;
      } catch (error) {
        console.error(`[Tauri Bridge] invoke ${channel} → ${tauriCmd} 失败:`, error);
        throw error;
      }
    },

    /**
     * send(channel, ...args) → Tauri invoke (fire-and-forget)
     */
    send: function (channel, ...args) {
      if (!getTauriApi()) {
        console.error('[Tauri Bridge] __TAURI__ 尚未就绪，无法发送:', channel);
        return;
      }
      const tauriCmd = COMMAND_MAP[channel];
      if (!tauriCmd) {
        console.warn(`[Tauri Bridge] 未映射的IPC通道 (send): ${channel}`);
        return;
      }

      // 窗口控制命令
      if (channel === 'minimize-window') {
        _appWindow.minimize();
        return;
      }
      if (channel === 'close-window') {
        _appWindow.close();
        return;
      }

      const invokeArgs = buildInvokeArgs(tauriCmd, args);
      _invoke(tauriCmd, invokeArgs).catch(err => {
        console.warn(`[Tauri Bridge] send ${channel} → ${tauriCmd} 失败:`, err);
      });
    },

    /**
     * on(channel, listener) → Tauri listen
     */
    on: function (channel, listener) {
      if (!getTauriApi()) {
        console.error('[Tauri Bridge] __TAURI__ 尚未就绪，无法监听:', channel);
        return;
      }
      // 将 Electron 事件格式映射到 Tauri
      const unlisten = _listen(channel, (event) => {
        // Electron: (event, data) → Tauri: (event with payload)
        listener(null, event.payload);
      });

      // Store for potential removal
      if (!eventListeners.has(channel)) {
        eventListeners.set(channel, []);
      }
      eventListeners.get(channel).push(unlisten);
    },

    /**
     * removeAllListeners(channel)
     */
    removeAllListeners: function (channel) {
      if (eventListeners.has(channel)) {
        const listeners = eventListeners.get(channel);
        listeners.forEach(async (unlistenPromise) => {
          const unlisten = await unlistenPromise;
          if (typeof unlisten === 'function') {
            unlisten();
          }
        });
        eventListeners.delete(channel);
      }
    },
  };

  // 模拟 Node.js path 模块（前端使用的部分）
  const pathModule = {
    join: function (...parts) {
      const sep = navigator.platform.startsWith('Win') ? '\\' : '/';
      return parts
        .filter(p => p != null && p !== '')
        .join(sep)
        .replace(/[/\\]+/g, sep);
    },
    basename: function (p) {
      const sep = navigator.platform.startsWith('Win') ? '\\' : '/';
      const parts = p.split(/[/\\]/);
      return parts[parts.length - 1] || '';
    },
    dirname: function (p) {
      const sep = navigator.platform.startsWith('Win') ? '\\' : '/';
      const parts = p.split(/[/\\]/);
      parts.pop();
      return parts.join(sep);
    },
    sep: navigator.platform.startsWith('Win') ? '\\' : '/',
  };

  // 模拟 process.env 和 process 对象
  const processShim = {
    env: {
      NODE_ENV: 'production',
      APPDATA: '', // Will be resolved by backend
    },
    platform: navigator.platform.startsWith('Win')
      ? 'win32'
      : navigator.platform.startsWith('Mac')
        ? 'darwin'
        : 'linux',
  };

  // 模拟 Node.js fs 模块（前端不使用，仅防止 require 报错）
  const fsModule = {
    readFileSync: function() { return ''; },
    writeFileSync: function() {},
    existsSync: function() { return false; },
  };

  // 模拟 Node.js os 模块
  const osModule = {
    platform: function() { return processShim.platform; },
    homedir: function() { return ''; },
    type: function() { return 'Windows_NT'; },
  };

  // 模拟 require() 函数
  window.require = function (moduleName) {
    console.log(`[Tauri Bridge] require('${moduleName}') 被调用`);
    if (moduleName === 'electron') {
      return { ipcRenderer: ipcRenderer };
    }
    if (moduleName === 'path') {
      return pathModule;
    }
    if (moduleName === 'fs') {
      return fsModule;
    }
    if (moduleName === 'os') {
      return osModule;
    }
    console.warn(`[Tauri Bridge] require('${moduleName}') 未实现`);
    return {};
  };

  // 兼容 Electron 的 process 全局对象
  if (!window.process) {
    window.process = processShim;
  }

  console.log('[Tauri Bridge] Electron → Tauri 桥接层已加载');
})();
