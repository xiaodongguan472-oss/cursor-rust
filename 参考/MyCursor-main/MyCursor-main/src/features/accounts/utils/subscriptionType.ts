export type SubscriptionVisualStyle = {
  bg: string;
  color: string;
  icon: "crown" | "gift" | "free" | "user" | "alert" | "bolt";
};

function toTitleCase(value: string) {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

/** 将订阅类型转成适合前端展示的动态文案 */
export function formatSubscriptionTypeLabel(type?: string | null, trialDaysRemaining?: number) {
  if (!type) {
    return "Free";
  }

  const normalized = type.trim();
  const lower = normalized.toLowerCase();

  if (lower === "token_expired") {
    return "Token 失效";
  }

  if (lower === "free") {
    return "Free";
  }

  if (lower.includes("trial")) {
    const baseLabel = toTitleCase(normalized.replace(/[:]/g, " "));
    return trialDaysRemaining !== undefined ? `${baseLabel} - ${trialDaysRemaining}天` : baseLabel;
  }

  if (normalized.includes(":")) {
    return normalized
      .split(":")
      .filter(Boolean)
      .map((segment) => toTitleCase(segment))
      .join(" / ");
  }

  return toTitleCase(normalized);
}

/** 按订阅大类返回统一视觉风格，具体名称由动态文案函数生成 */
export function getSubscriptionVisualStyle(type?: string | null): SubscriptionVisualStyle {
  const lower = (type || "free").trim().toLowerCase();

  if (lower === "token_expired") {
    return {
      bg: "rgba(244, 135, 113, 0.15)",
      color: "#f48771",
      icon: "alert",
    };
  }

  if (lower.startsWith("team")) {
    return {
      bg: "rgba(59, 130, 246, 0.15)",
      color: "#2563eb",
      icon: "user",
    };
  }

  if (lower.includes("trial")) {
    return {
      bg: "rgba(74, 137, 220, 0.15)",
      color: "var(--primary-color)",
      icon: "gift",
    };
  }

  if (lower === "free") {
    return {
      bg: "var(--bg-secondary)",
      color: "var(--text-secondary)",
      icon: "free",
    };
  }

  if (lower) {
    return {
      bg: "rgba(168, 85, 247, 0.15)",
      color: "#7c3aed",
      icon: "crown",
    };
  }

  return {
    bg: "rgba(74, 137, 220, 0.1)",
    color: "var(--primary-color)",
    icon: "bolt",
  };
}
