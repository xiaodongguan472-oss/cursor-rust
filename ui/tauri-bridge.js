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

  // 命令名称映射
  const COMMAND_MAP = {
    'get-settings': 'x0a',
    'save-settings': 'x0b',
    'quit-app': 'x0c',
    'get-cursor-paths': 'x1a',
    'get-user-data-path': 'x1b',
    'get-machine-id': 'x2a',
    'reset-cursor-machine-id': 'x2b',
    'reset-machine-ids-standalone': 'x2c',
    'find-all-cursor-databases': 'x3a',
    'manual-search-cursor-database': 'x3b',
    'update-cursor-sqlite-db': 'x3c',
    'update-cursor-auth': 'x3d',
    'logout-current-cursor-account': 'x3e',
    'python-style-account-switch': 'x3f',
    'read-file': 'x4a',
    'write-file': 'x4b',
    'open-file-dialog': 'x4c',
    'open-folder-dialog': 'x4d',
    'open-external-url': 'x4e',
    'modify-cursor-main-js': 'x5a',
    'analyze-cursor-file': 'x5b',
    'restore-cursor-backup': 'x5c',
    'modify-cursor-workbench': 'x5d',
    'check-cursor-running': 'x6a',
    'force-close-cursor': 'x6b',
    'restart-cursor': 'x6c',
    'restart-cursor-complete': 'x6d',
    'launch-cursor': 'x6e',
    'verify-card': 'x7a',
    'verify-card-only': 'x7b',
    'get-card-info': 'x7c',
    'save-card-info': 'x7d',
    'load-card-info': 'x7e',
    'clear-card-info': 'x7f',
    'record-usage': 'x7g',
    'get-latest-notice': 'x8a',
    'get-latest-tool-version': 'x8b',
    'get-latest-popup': 'x8c',
    'get-qrcode-image': 'x8d',
    'check-version-update': 'x8e',
    'get-current-permissions': 'x9a',
    'disable-cursor-auto-update': 'x9b',
    'set-cursor-default-model': 'xa1',
    'check-cursor-settings-status': 'xb1',
    'update-cursor-settings': 'xb2',
    'patch-ext-host': 'xc1',
    'unpatch-ext-host': 'xc2',
    'check-ext-host-patched': 'xc3',
    'write-active-token': 'xc4',
    'read-active-token': 'xc5',
    'clear-active-token': 'xc6',
    'check-cursor-usage': 'xc7',
    'get-cursor-account-quota': 'xc8',
    'seamless-switch': 'xc9',
    'one-click-switch': 'xca',
    'toggle-auto-switch': 'xcb',
    'get-auto-switch-status': 'xcc',
    'save-current-workspace': 'xd1',
    'load-saved-workspace': 'xd2',
    'download-and-update': 'xe1',
    'minimize-window': 'xf1',
    'close-window': 'xf2',
    'show-main-window': 'xf3',
  };

  // 参数映射
  const PARAM_MAP = {
    'x0b': ['settings'],
    'x3b': ['searchPath'],
    'x3c': ['dbPath'],
    'x3d': ['dbPath', 'email', 'accessToken', 'refreshToken', 'machineIdReset'],
    'x3e': ['dbPath'],
    'x3f': ['dbPath', 'email', 'accessToken', 'refreshToken'],
    'x4a': ['filePath'],
    'x4b': ['filePath', 'content'],
    'x4e': ['url'],
    'x5a': ['mainPath'],
    'x5b': ['filePath'],
    'x5c': ['filePath'],
    'x5d': ['workbenchPath', 'isValid', 'days'],
    'x6c': ['cursorPath'],
    'x6e': ['workspacePath'],
    'x7a': ['cardCode'],
    'x7b': ['cardCode'],
    'x7c': ['cardCode'],
    'x7d': ['cardInfo'],
    'x7g': ['cardCode'],
    'xa1': ['model'],
    'xb2': ['enabled'],
    'xc4': ['token'],
    'xc7': ['accessToken'],
    'xc8': ['accessToken'],
    'xc9': ['dbPath', 'email', 'accessToken', 'refreshToken'],
    'xca': ['dbPath', 'cardCode'],
    'xcb': ['enabled', 'cardCode'],
    'xd1': ['dbPath'],
    'xd2': ['dbPath'],
    'xe1': ['url', 'fileName'],
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
