import React, { useEffect, CSSProperties } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}

const Modal: React.FC<ModalProps> = ({
  open,
  onClose,
  title,
  children,
  footer,
  size = "md",
}) => {
  // ESC键关闭
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (open) {
      document.addEventListener("keydown", handleEsc);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleEsc);
      document.body.style.overflow = "auto";
    };
  }, [open, onClose]);

  if (!open) return null;

  const sizeStyles = {
    sm: "max-w-md",      // 448px
    md: "max-w-lg",      // 512px
    lg: "max-w-xl",      // 576px
    xl: "max-w-[700px]", // 700px - 适应 800px 窗口
  };

  const modalStyle: CSSProperties = {
    backgroundColor: 'var(--bg-primary)',
    borderRadius: 'var(--border-radius-xl)',
    boxShadow: 'var(--shadow-heavy)',
    backdropFilter: 'blur(var(--backdrop-blur))',
    WebkitBackdropFilter: 'blur(var(--backdrop-blur))',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center animate-fadeIn">
      {/* 遮罩 */}
      <div
        className="absolute inset-0 backdrop-blur-sm"
        style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)' }}
        onClick={onClose}
      />

      {/* Modal内容 */}
      <div
        className={`
          relative
          w-full ${sizeStyles[size]} mx-4
          max-h-[90vh] overflow-hidden
          animate-fadeIn
        `}
        style={modalStyle}
      >
        {/* 标题 */}
        {title && (
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: '1px solid var(--border-primary)' }}
          >
            <h2
              className="text-lg font-semibold"
              style={{ color: 'var(--text-primary)' }}
            >
              {title}
            </h2>
            <button
              onClick={onClose}
              className="p-2 rounded-lg transition-all"
              style={{ color: 'var(--text-tertiary)' }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'var(--bg-hover)';
                e.currentTarget.style.color = 'var(--text-primary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent';
                e.currentTarget.style.color = 'var(--text-tertiary)';
              }}
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        )}

        {/* 内容 */}
        <div className="px-4 py-3 overflow-y-auto max-h-[calc(90vh-140px)]">
          {children}
        </div>

        {/* 底部 */}
        {footer && (
          <div
            className="flex justify-end gap-3 px-4 py-3"
            style={{ borderTop: '1px solid var(--border-primary)' }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};

export default Modal;
