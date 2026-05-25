import React, { memo } from "react";

interface FormFieldProps {
  label: string;
  required?: boolean;
  children: React.ReactNode;
  description?: string;
}

/**
 * 通用表单字段包装器
 * 使用 memo 避免不必要的重新渲染
 */
export const FormField = memo(({ 
  label, 
  required = false, 
  children,
  description 
}: FormFieldProps) => {
  return (
    <div>
      <label className="block mb-2 text-sm font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      {children}
      {description && (
        <p className="mt-1 text-xs text-gray-500">{description}</p>
      )}
    </div>
  );
});

FormField.displayName = "FormField";

interface TextInputProps {
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "email" | "password";
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
}

export const TextInput = memo(({ 
  value, 
  onChange, 
  type = "text", 
  placeholder,
  disabled = false,
  onKeyDown,
}: Omit<TextInputProps, 'rows'>) => {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      disabled={disabled}
      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
      placeholder={placeholder}
    />
  );
});

TextInput.displayName = "TextInput";

/**
 * 多行文本输入框（memo优化）
 */
export const TextareaInput = memo(({ 
  value, 
  onChange, 
  placeholder,
  rows = 3,
  disabled = false
}: TextInputProps) => {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
      rows={rows}
      placeholder={placeholder}
    />
  );
});

TextareaInput.displayName = "TextareaInput";

interface CheckboxProps {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}

/**
 * 复选框（memo优化）
 */
export const Checkbox = memo(({ id, checked, onChange, label }: CheckboxProps) => {
  return (
    <div className="flex items-center space-x-2">
      <input
        type="checkbox"
        id={id}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
      />
      <label htmlFor={id} className="text-sm text-gray-700">
        {label}
      </label>
    </div>
  );
});

Checkbox.displayName = "Checkbox";

