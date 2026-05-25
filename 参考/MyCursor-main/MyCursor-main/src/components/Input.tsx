import React, { memo, CSSProperties } from "react";

interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'prefix'> {
  label?: string;
  error?: string;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
}

const Input: React.FC<InputProps> = memo(({
  label,
  error,
  prefix,
  suffix,
  className = "",
  style,
  ...props
}) => {
  const inputStyle: CSSProperties = {
    backgroundColor: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    border: `1px solid ${error ? 'var(--danger-color)' : 'var(--border-primary)'}`,
    borderRadius: 'var(--border-radius)',
    transition: 'all 0.2s ease',
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
      <div className="relative">
        {prefix && (
          <div
            className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--text-tertiary)' }}
          >
            {prefix}
          </div>
        )}
        <input
          className={`
            w-full px-3 py-2
            text-base
            focus:outline-none
            disabled:cursor-not-allowed
            ${prefix ? "pl-10" : ""}
            ${suffix ? "pr-10" : ""}
            ${className}
          `}
          style={inputStyle}
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
        {suffix && (
          <div
            className="absolute right-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--text-tertiary)' }}
          >
            {suffix}
          </div>
        )}
      </div>
      {error && (
        <p className="mt-1 text-sm" style={{ color: 'var(--danger-color)' }}>
          {error}
        </p>
      )}
    </div>
  );
});

Input.displayName = "Input";

export default Input;
