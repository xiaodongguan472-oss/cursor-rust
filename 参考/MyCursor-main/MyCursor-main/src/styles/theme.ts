/**
 * MyCursor 设计系统 - 主题配置
 * 基于 style_word.md 的"经典活力"配色方案
 */

export const colors = {
  // 主色调 - 橙色系
  primary: {
    50: "#FFF3E0",
    100: "#FFE0B2",
    200: "#FFCC80",
    300: "#FFB74D",
    400: "#FFA726",
    500: "#FF8C00", // 浅橙
    600: "#FF6A00", // 标准橙（主色）
    700: "#DD5500", // 深橙（悬停）
    800: "#C94C00",
    900: "#B54300",
  },

  // 信息色 - 湖蓝色
  info: {
    500: "#0099FF",
    600: "#0077CC",
  },

  // 成功色 - 翠绿色
  success: {
    500: "#00C853",
    600: "#00A844",
  },

  // 危险色 - 珊瑚红
  danger: {
    500: "#FF3D00",
    600: "#DD2C00",
  },

  // 工具提示 - 宝蓝色
  tooltip: {
    500: "#2196F3",
  },

  // 渐变背景
  background: {
    start: "#00BCD4", // 天蓝色
    end: "#4CAF50", // 草绿色
  },

  // 中性色
  neutral: {
    white: "#FFFFFF",
    gray50: "#F8F9FA",
    gray100: "#F5F5F5",
    gray200: "#E0E0E0",
    gray300: "#BBBBBB",
    gray400: "#999999",
    gray500: "#666666",
    gray600: "#2C3E50",
  },
};

// 阴影规范
export const shadows = {
  card: "0 10px 30px rgba(0, 0, 0, 0.08)",
  cardHover: "0 15px 40px rgba(0, 0, 0, 0.12)",
  button: "0 4px 15px rgba(255, 106, 0, 0.4)",
  buttonHover: "0 6px 20px rgba(255, 106, 0, 0.5)",
  input: "0 0 0 4px rgba(255, 106, 0, 0.1)",
};

// 圆角规范
export const borderRadius = {
  sm: "8px",
  md: "12px",
  lg: "16px",
  xl: "20px",
  full: "9999px",
};

// 间距规范
export const spacing = {
  xs: "8px",
  sm: "12px",
  md: "16px",
  lg: "20px",
  xl: "24px",
  "2xl": "32px",
  "3xl": "48px",
};

// 过渡时长
export const transitions = {
  fast: "0.2s",
  normal: "0.3s",
  slow: "0.5s",
};

// 字体规范
export const typography = {
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  fontSize: {
    xs: "12px",
    sm: "13px",
    base: "15px",
    md: "16px",
    lg: "18px",
    xl: "20px",
    "2xl": "24px",
    "3xl": "36px",
    "4xl": "48px",
  },
  fontWeight: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
};

// 导出完整主题
export const theme = {
  colors,
  shadows,
  borderRadius,
  spacing,
  transitions,
  typography,
};

export default theme;
