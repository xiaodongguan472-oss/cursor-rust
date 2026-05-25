/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Fluent Design 配色方案 - 天蓝色系
      colors: {
        primary: {
          DEFAULT: '#4a89dc',
          hover: '#357abd',
          light: '#e8f4fd',
          dark: '#2c5aa0',
          green: '#2aeb31',
        },
        success: {
          DEFAULT: '#52c41a',
        },
        warning: {
          DEFAULT: '#faad14',
        },
        error: {
          DEFAULT: '#ff4d4f',
        },
        info: {
          DEFAULT: '#1890ff',
        },
      },

      // 圆角规范 - Fluent Design
      borderRadius: {
        'sm': '4px',
        'DEFAULT': '6px',
        'md': '6px',
        'lg': '8px',
        'xl': '12px',
      },

      // 阴影规范 - 三级系统
      boxShadow: {
        'light': '0 1px 3px rgba(0, 0, 0, 0.1)',
        'medium': '0 2px 8px rgba(0, 0, 0, 0.15)',
        'heavy': '0 4px 12px rgba(0, 0, 0, 0.15)',
        'control': '0 1px 3px rgba(0, 0, 0, 0.1)',
        'hover': '0 2px 8px rgba(74, 137, 220, 0.15)',
        'active': '0 2px 8px rgba(74, 137, 220, 0.2)',
      },

      // 动画时长
      transitionDuration: {
        'DEFAULT': '200ms',
        'slow': '300ms',
      },

      // 字体大小
      fontSize: {
        'xs': '12px',
        'sm': '13px',
        'base': '14px',
        'md': '15px',
        'lg': '16px',
        'xl': '18px',
        '2xl': '20px',
        '3xl': '24px',
      },

      // 间距系统 - 4px 基准网格
      spacing: {
        'xs': '4px',
        'sm': '8px',
        'md': '12px',
        'lg': '16px',
        'xl': '20px',
        '2xl': '24px',
        '3xl': '32px',
      },

      // 毛玻璃效果
      backdropBlur: {
        'DEFAULT': '10px',
        'heavy': '20px',
      },
    },
  },
  plugins: [],
}

