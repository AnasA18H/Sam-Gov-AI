/**
 * Custom dropdown – theme-styled, accessible. Replaces native <select> for consistent look.
 * @param {Array<{ value: string, label: string }>} options
 * @param {string} value – current selected value
 * @param {(value: string) => void} onChange
 * @param {string} [placeholder] – shown when no value
 * @param {string} [id] – for label association
 * @param {string} [className] – extra classes for the trigger
 */
import { useState, useRef, useEffect } from 'react';
import { HiOutlineSelector } from 'react-icons/hi';

const CustomDropdown = ({ options = [], value, onChange, placeholder = 'Select…', id, className = '' }) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  const selectedOption = options.find((o) => o.value === value);
  const displayLabel = selectedOption ? selectedOption.label : placeholder;

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        id={id}
        onClick={() => setOpen((prev) => !prev)}
        className={`w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated text-gray-900 dark:text-white text-sm text-left transition-colors focus:ring-2 focus:ring-[#14B8A6] dark:focus:ring-teal-dm focus:border-transparent hover:border-gray-300 dark:hover:border-dark-hover ${className}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={id ? `${id}-label` : undefined}
      >
        <span className="truncate">{displayLabel}</span>
        <HiOutlineSelector className={`w-4 h-4 shrink-0 text-gray-400 dark:text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute z-50 mt-1 w-full min-w-[120px] max-h-56 overflow-auto rounded-xl border border-gray-200 dark:border-dark-border bg-white dark:bg-dark-elevated shadow-lg py-1 focus:outline-none"
          aria-activedescendant={value ? `${id || 'dropdown'}-opt-${value}` : undefined}
        >
          {options.map((opt) => {
            const isSelected = opt.value === value;
            return (
              <li
                key={opt.value}
                id={id ? `${id}-opt-${opt.value}` : undefined}
                role="option"
                aria-selected={isSelected}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={`px-3 py-2 text-sm cursor-pointer transition-colors ${
                  isSelected
                    ? 'bg-[#14B8A6]/10 dark:bg-teal-dm/20 text-[#14B8A6] dark:text-teal-dm font-medium'
                    : 'text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-dark-hover'
                }`}
              >
                {opt.label}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export default CustomDropdown;
