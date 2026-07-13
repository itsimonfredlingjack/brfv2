import React from 'react';
import { Calendar, Search, FileText } from 'lucide-react';

export default function ContextCard({ type, data, topPosition }) {
  if (!data) return null;

  const isDeadline = type === 'deadline';
  const Icon = isDeadline ? Calendar : Search;

  return (
    <div
      className="context-card-wrapper"
      style={{ top: `${topPosition}px` }}
    >
      <div className="context-card glass-panel">
        <div className={`card-header ${type}`}>
          <Icon size={14} />
          {isDeadline ? 'Bevakning / Tidsfrist' : 'Frågesvar'}
        </div>

        <div className="card-title">
          {data.title}
        </div>

        <div className="card-description">
          {data.description}
        </div>

        <div className="card-footer">
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <FileText size={12} />
            {data.sourceDoc}
          </span>
          <span>Sidan {data.page}</span>
        </div>
      </div>
    </div>
  );
}
