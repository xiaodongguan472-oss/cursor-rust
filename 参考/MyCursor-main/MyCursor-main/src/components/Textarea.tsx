import React, { memo, CSSProperties } from "react";

interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

const Textarea: React.FC<TextareaProps> = memo(({
  label,
  error,
  className = "",
  style,
  ...props
}) => {
  const textareaStyle: CSSProperties = {
    backgroundColor: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    border: `1px solid ${error ? 'var(--danger-color)' : 'var(--border-primary)'}`,
    borderRadius: 'var(--border-radius)',
    transition: 'all 0.2s ease',
    resize: 'none',
    ...style,
  };

  return (
    <div className="w-full">
      {label && (
        <label
          className="block text-sm font-medium mb-2"
          style={{ color: 'var(--text-secondary)' }}
        >
          {label}
        </label>
      )}
      <textarea
        className={`w-full px-3 py-2 text-base focus:outline-none disabled:cursor-not-allowed ${className}`}
        style={textareaStyle}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = error ? 'var(--danger-color)' : 'var(--primary-color)';
          e.currentTarget.style.boxShadow = error
            ? '0 0 0 3px rgba(239, 68, 68, 0.1)'
            : '0 0 0 3px rgba(74, 137, 220, 0.1)';
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = error ? 'var(--danger-color)' : 'var(--border-primary)';
          e.currentTarget.style.boxShadow = 'none';
        }}
        {...props}
      />
      {error && (
        <p className="mt-1 text-sm" style={{ color: 'var(--danger-color)' }}>
          {error}
        </p>
      )}
    </div>
  );
});

Textarea.displayName = "Textarea";

export default Textarea;
