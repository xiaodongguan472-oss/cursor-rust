import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  
  // 路径别名配置
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@/components": path.resolve(__dirname, "./src/components"),
      "@/services": path.resolve(__dirname, "./src/services"),
      "@/types": path.resolve(__dirname, "./src/types"),
      "@/utils": path.resolve(__dirname, "./src/utils"),
      "@/styles": path.resolve(__dirname, "./src/styles"),
    },
  },

  // Tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    watch: {
      // 3. tell vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },
  
  // 清除控制台警告
  clearScreen: false,
  
  // Env变量前缀
  envPrefix: ["VITE_", "TAURI_"],

  // 构建优化配置
  build: {
    // 目标浏览器
    target: "esnext",
    
    // 启用 CSS 代码分割
    cssCodeSplit: true,
    
    // sourcemap 仅在开发环境
    sourcemap: false,
    
    // chunk 大小警告限制（kb）
    chunkSizeWarningLimit: 1000,
    
    // Rollup 打包配置
    rollupOptions: {
      output: {
        // 手动代码分割
        manualChunks: {
          // React 核心库
          'react-vendor': ['react', 'react-dom'],
          
          // 图表库（较大）
          'charts': ['recharts'],
          
          // Tauri API（常用）
          'tauri-core': [
            '@tauri-apps/api',
            '@tauri-apps/plugin-dialog',
            '@tauri-apps/plugin-fs',
            '@tauri-apps/plugin-shell',
          ],
          
          // react-window 虚拟滚动
          'virtual-scroll': ['react-window'],
        },
        
        // 静态资源分类
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name?.split('.');
          let extType = info?.[info.length - 1];
          
          if (/\.(png|jpe?g|gif|svg|webp|ico)$/i.test(assetInfo.name || '')) {
            return `assets/images/[name]-[hash][extname]`;
          } else if (/\.(woff2?|eot|ttf|otf)$/i.test(assetInfo.name || '')) {
            return `assets/fonts/[name]-[hash][extname]`;
          }
          
          return `assets/[name]-[hash][extname]`;
        },
        
        // 入口文件命名
        entryFileNames: 'assets/[name]-[hash].js',
        
        // chunk 文件命名
        chunkFileNames: 'assets/[name]-[hash].js',
      },
    },
    
    // 压缩配置
    minify: 'terser',
    terserOptions: {
      compress: {
        // 生产环境移除 console 和 debugger
        drop_console: true,
        drop_debugger: true,
        // 移除无用代码
        pure_funcs: ['console.log', 'console.info', 'console.debug'],
      },
      format: {
        // 移除注释
        comments: false,
      },
    },
  },

  // 依赖优化
  optimizeDeps: {
    // 预构建依赖
    include: [
      'react',
      'react-dom',
      'recharts',
      'react-window',
      '@tauri-apps/api',
      '@tauri-apps/plugin-dialog',
    ],
    
    // 排除预构建
    exclude: [
      '@tauri-apps/api/event',
      '@tauri-apps/api/core',
    ],
  },
});

