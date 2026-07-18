import React from 'react';
import { Settings } from 'lucide-react';

export default function SettingsPlaceholder() {
  return (
    <div className="tab-content" style={{ maxWidth: '800px', margin: '0 auto', textAlign: 'center', paddingTop: '100px' }}>
      <Settings size={48} color="var(--panel-border)" style={{ marginBottom: '16px' }} />
      <h2 style={{ fontSize: '24px', fontWeight: '600', marginBottom: '8px' }}>Inställningar</h2>
      <p style={{ color: 'var(--text-secondary)' }}>Inställningar är inte tillgängliga i denna mockup.</p>
    </div>
  );
}
