/**
 * Dropdown Component - 自定义下拉框组件
 * 完全自定义的下拉框，符合整体设计风格
 */

import React, { useState, useRef, useEffect } from 'react';
import { Icon } from './Icon';

export interface DropdownOption {
  value: string;
  label: string;
}

interface DropdownProps {
  options: DropdownOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export const Dropdown: React.FC<DropdownProps> = ({
  options,
  value,
  onChange,
  placeholder = '请选择',
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 获取当前选中项的标签
  const selectedOption = options.find(opt => opt.value === value);
  const displayText = selectedOption ? selectedOption.label : placeholder;

  // 点击外部关闭下拉框
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleSelect = (optionValue: string) => {
    onChange(optionValue);
    setIsOpen(false);
  };

  return (
    <div 
      ref={dropdownRef} 
      className={`relative ${className}`}
      style={{
        minWidth: '100px',
      }}
    >
      {/* 选择按钮 */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: '100%',
          padding: '6px 32px 6px 10px',
          fontSize: '13px',
          fontWeight: 500,
          backgroundColor: 'var(--bg-primary)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-primary)',
          borderRadius: '6px',
          cursor: 'pointer',
          transition: 'all var(--transition-duration) ease',
          textAlign: 'left',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'relative',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = 'var(--primary-color)';
          e.currentTarget.style.boxShadow = '0 0 0 3px rgba(74, 137, 220, 0.1)';
        }}
        onMouseLeave={(e) => {
          if (!isOpen) {
            e.currentTarget.style.borderColor = 'var(--border-primary)';
            e.currentTarget.style.boxShadow = 'none';
          }
        }}
      >
        <span>{displayText}</span>
        <Icon 
          name="chevron-down" 
          size={14} 
          style={{
            position: 'absolute',
            right: '8px',
            transition: 'transform var(--transition-duration) ease',
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
          }}
        />
      </button>

      {/* 下拉选项列表 */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border-primary)',
            borderRadius: '6px',
            boxShadow: 'var(--shadow-medium)',
            zIndex: 1000,
            overflow: 'hidden',
            animation: 'fadeIn 0.15s ease',
          }}
        >
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => handleSelect(option.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                fontSize: '13px',
                backgroundColor: option.value === value 
                  ? 'rgba(74, 137, 220, 0.1)' 
                  : 'transparent',
                color: option.value === value 
                  ? 'var(--primary-color)' 
                  : 'var(--text-primary)',
                border: 'none',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'background-color var(--transition-duration) ease',
                fontWeight: option.value === value ? 600 : 400,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
              onMouseEnter={(e) => {
                if (option.value !== value) {
                  e.currentTarget.style.backgroundColor = 'rgba(74, 137, 220, 0.05)';
                }
              }}
              onMouseLeave={(e) => {
                if (option.value !== value) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                } else {
                  e.currentTarget.style.backgroundColor = 'rgba(74, 137, 220, 0.1)';
                }
              }}
            >
              <span>{option.label}</span>
              {option.value === value && (
                <Icon name="check" size={14} color="var(--primary-color)" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

