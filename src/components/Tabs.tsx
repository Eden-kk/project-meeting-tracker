import type { ReactNode } from 'react';

export type TabDef = {
  id: string;
  label: string;
  disabled?: boolean;
  tooltip?: string;
};

type Props = {
  tabs: TabDef[];
  value: string;
  onChange: (id: string) => void;
  children: ReactNode;
};

export function Tabs({ tabs, value, onChange, children }: Props) {
  return (
    <div>
      <div role="tablist" className="flex gap-2 border-b border-gray-200">
        {tabs.map((tab) => {
          const selected = tab.id === value;
          const baseClass = 'px-3 py-2 text-sm border-b-2';
          const stateClass = tab.disabled
            ? 'cursor-not-allowed text-gray-400 border-transparent'
            : selected
              ? 'border-gray-900 font-medium'
              : 'border-transparent text-gray-600 hover:text-gray-900';
          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-disabled={tab.disabled || undefined}
              title={tab.tooltip}
              disabled={tab.disabled}
              onClick={() => !tab.disabled && onChange(tab.id)}
              className={`${baseClass} ${stateClass}`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div className="py-4">{children}</div>
    </div>
  );
}
