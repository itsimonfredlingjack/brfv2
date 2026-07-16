import React from 'react';
import './SettingsView.css';

const SettingsView = ({ settingsConfig, setSettingsConfig, activeSettingsTab, setActiveSettingsTab, onSave, saveState, readOnly = false }) => {
  const tabs = [
    { id: 'dokument', label: 'Dokument' },
    { id: 'chunking', label: 'Chunking' },
    { id: 'sokning', label: 'Sökning' },
    { id: 'ai', label: 'AI-svar' },
    { id: 'kallmarkering', label: 'Källmarkering' },
  ];

  const handleToggle = (key) => {
    setSettingsConfig(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleChange = (key, value) => {
    setSettingsConfig(prev => ({ ...prev, [key]: value }));
  };

  const renderToggle = (label, description, stateKey) => (
    <div className="settings-card">
      <div className="settings-card-info">
        <div className="settings-card-title">{label}</div>
        <div className="settings-card-description">{description}</div>
      </div>
      <div className="settings-card-action">
        <div className={`toggle-switch ${settingsConfig[stateKey] ? 'on' : 'off'}`} onClick={() => handleToggle(stateKey)}>
          <div className="toggle-thumb" />
        </div>
      </div>
    </div>
  );

  const renderSlider = (label, description, stateKey, min, max, step = 1, unit = '') => (
    <div className="settings-card">
      <div className="settings-card-info">
        <div className="settings-card-title">{label}</div>
        <div className="settings-card-description">{description}</div>
      </div>
      <div className="settings-card-action slider-action">
        <input 
          type="range" 
          min={min} 
          max={max} 
          step={step}
          value={settingsConfig[stateKey]} 
          onChange={(e) => handleChange(stateKey, Number(e.target.value))}
          className="settings-slider"
        />
        <div className="slider-value-display">
          {settingsConfig[stateKey]}{unit}
        </div>
      </div>
    </div>
  );

  const renderSelect = (label, description, stateKey, options) => (
    <div className="settings-card">
      <div className="settings-card-info">
        <div className="settings-card-title">{label}</div>
        <div className="settings-card-description">{description}</div>
      </div>
      <div className="settings-card-action">
        <select 
          className="settings-select"
          value={settingsConfig[stateKey]}
          onChange={(e) => handleChange(stateKey, e.target.value)}
        >
          {options.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
    </div>
  );

  return (
    <div className="settings-view-container">
      <div className="settings-header">
        <div>
          <h1>Systeminställningar</h1>
          <p>Här kan du konfigurera tekniska parametrar för dokumenthantering och AI-modellen.</p>
        </div>
        <div className="settings-save-area">
          {readOnly ? (
            <span className="settings-save-status readonly">Endast administratörer kan ändra inställningar</span>
          ) : (
            <>
              {saveState === 'saved' && <span className="settings-save-status ok">Sparat — index uppdaterat</span>}
              {saveState === 'error' && <span className="settings-save-status err">Kunde inte spara</span>}
              <button className="primary-btn" onClick={onSave} disabled={saveState === 'saving'}>
                {saveState === 'saving' ? 'Sparar…' : 'Spara inställningar'}
              </button>
            </>
          )}
        </div>
      </div>
      
      <div className="settings-layout">
        <div className="settings-sidebar">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`settings-tab-btn ${activeSettingsTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveSettingsTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="settings-content glass-panel">
          {activeSettingsTab === 'dokument' && (
            <div className="settings-section">
              <h2>Dokument</h2>
              {renderSelect('Tillåtna filformat', 'Vilka filformat systemet ska tillåta för uppladdning.', 'allowedFormats', [
                { value: 'pdf,docx,jpg', label: 'PDF, Word, Bilder' },
                { value: 'pdf', label: 'Endast PDF' }
              ])}
              {renderSlider('Maximal filstorlek', 'Högsta tillåtna storlek per dokument (MB).', 'maxFileSize', 10, 100, 1, ' MB')}
              {renderSelect('OCR (Optisk teckenläsning)', 'Hur skannade dokument utan textlager ska hanteras.', 'ocrMode', [
                { value: 'auto', label: 'Automatiskt (rekommenderas)' },
                { value: 'manual', label: 'Kräv manuellt godkännande' },
                { value: 'off', label: 'Inaktiverat' }
              ])}
              {renderToggle('Språkidentifiering', 'Identifiera automatiskt vilket språk dokumentet är skrivet på för bättre RAG-prestanda.', 'languageDetection')}
              {renderToggle('Dubblettkontroll', 'Varna eller förhindra uppladdning om ett identiskt dokument redan existerar.', 'duplicateCheck')}
            </div>
          )}

          {activeSettingsTab === 'chunking' && (
            <div className="settings-section">
              <h2>Chunking (Textsegmentering)</h2>
              {renderSelect('Strategi', 'Vilken metod som används för att dela upp texten. Ändring chunkar om alla dokument.', 'chunkStrategy', [
                { value: 'recursive', label: 'Rekursiv (stycke → mening)' },
                { value: 'sentence', label: 'Meningsbaserad' },
                { value: 'fixed', label: 'Fast längd (glidande fönster)' }
              ])}
              {renderSlider('Chunk-storlek', 'Riktvärde för hur många ord varje textsegment ska innehålla.', 'chunkSize', 40, 1000, 20, ' ord')}
              {renderSlider('Överlappning mellan segment', 'Hur mycket text som återanvänds mellan angränsande segment. Högre värde minskar risken att information delas mitt i ett sammanhang, men ökar indexstorleken.', 'chunkOverlap', 0, 200, 10, ' ord')}
              {renderToggle('Rubrikhantering', 'Försök hålla ihop rubriker med deras underliggande brödtext istället för att bryta mitt i.', 'headerHandling')}
              {renderSelect('Tabellhantering', 'Hur tabeller ska formateras före vektorisering.', 'tableHandling', [
                { value: 'markdown', label: 'Markdown (Bäst för LLMs)' },
                { value: 'html', label: 'HTML' },
                { value: 'raw', label: 'Rå text (radvis)' }
              ])}
            </div>
          )}

          {activeSettingsTab === 'sokning' && (
            <div className="settings-section">
              <h2>Sökning & Reranking</h2>
              {renderSlider('Semantisk/BM25-viktning (hybrid)', 'Balansen mellan exakta nyckelord (0 = ren BM25) och semantisk sökning (100 = ren embedding).', 'searchWeighting', 0, 100, 5, '% semantik')}
              {renderSlider('Antal kandidater (retrieve)', 'Hur många segment varje delsökning hämtar innan poängen vägs samman.', 'candidateCount', 10, 200, 10)}
              {renderSlider('Top-K till modellen', 'Antalet segment som skickas till AI-modellen som faktagrund.', 'topK', 1, 20, 1)}
              {renderSlider('Minimikrav på relevans', 'Konfidensgräns: under denna nivå vägrar systemet hellre än gissar (0 = av).', 'minRelevance', 0, 1.0, 0.01)}
            </div>
          )}

          {activeSettingsTab === 'ai' && (
            <div className="settings-section">
              <h2>AI-svar & Modell</h2>
              {renderSelect('Modell', 'Vilken LLM som ska användas för att generera slutsvar.', 'aiModel', [
                { value: 'claude-opus-4-8', label: 'Claude Opus 4.8' },
                { value: 'claude-sonnet-5', label: 'Claude Sonnet 5' },
                { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' }
              ])}
              {renderSlider('Maximal svarslängd', 'Högsta antal tokens modellen tillåts generera i ett enskilt svar.', 'maxResponseLength', 200, 4000, 100, ' tokens')}
              {renderToggle('Krav på källor', 'Svar utan verifierbara källhänvisningar visas inte alls.', 'requireSources')}
              {renderSelect('Beteende vid otillräckligt underlag', 'Vad systemet ska göra om dokumenten inte räcker för att svara.', 'insufficientDataBehavior', [
                { value: 'refuse', label: 'Avstå från att svara (hallucinationsskydd)' },
                { value: 'warn', label: 'Svara men flagga svaret som osäkert' }
              ])}
            </div>
          )}

          {activeSettingsTab === 'kallmarkering' && (
            <div className="settings-section">
              <h2>Källmarkering & Navigering</h2>
              {renderToggle('Sidnummer krävs', 'Tvinga källhänvisningar att innehålla exakt sidnummer om det är en PDF.', 'requirePageNumbers')}
              {renderToggle('Bounding boxes krävs', 'Kräv XY-koordinater för texten för att möjliggöra "highlighting" inuti PDF-visaren.', 'requireBoundingBoxes')}
              {renderToggle('Tillåt passage utan koordinater', 'Om en passage saknar koordinater, ska den ändå visas i källhänvisningen?', 'allowPassageWithoutCoords')}
              {renderToggle('Fallback till sidnivå', 'Om bounding box misslyckas, hoppa till rätt sida utan att highlighta.', 'fallbackToPageLevel')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SettingsView;
