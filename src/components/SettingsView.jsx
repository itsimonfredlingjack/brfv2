import React from 'react';
import './SettingsView.css';

const SettingsView = ({ settingsConfig, setSettingsConfig, activeSettingsTab, setActiveSettingsTab }) => {
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
        <h1>Systeminställningar</h1>
        <p>Här kan du konfigurera tekniska parametrar för dokumenthantering och AI-modellen.</p>
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
              {renderSelect('Strategi', 'Vilken metod som används för att dela upp texten.', 'chunkStrategy', [
                { value: 'recursive', label: 'Rekursiv (Semantic)' },
                { value: 'fixed', label: 'Fast längd' }
              ])}
              {renderSlider('Chunk-storlek', 'Riktvärde för hur många tokens varje textsegment ska innehålla.', 'chunkSize', 200, 2000, 50, ' tokens')}
              {renderSlider('Överlappning mellan segment', 'Hur mycket text som återanvänds mellan angränsande segment. Högre värde minskar risken att information delas mitt i ett sammanhang, men ökar indexstorleken.', 'chunkOverlap', 0, 500, 10, ' tokens')}
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
              {renderSlider('Dense/BM25-viktning (Hybrid)', 'Balansen mellan semantisk sökning (0%) och sökning på exakta nyckelord (100%).', 'searchWeighting', 0, 100, 5, '% (BM25)')}
              {renderSlider('Antal kandidater (Retrieve)', 'Hur många dokumentsegment som ska hämtas initialt från vektordatabasen innan reranking.', 'candidateCount', 10, 200, 10)}
              {renderSlider('Top-K efter Reranking', 'Antalet segment som ska skickas in till AI-modellen som faktagrund.', 'topK', 3, 20, 1)}
              {renderSlider('Minimikrav på relevans', 'Lägsta relevanspoäng som krävs för att ett segment ska anses vara användbart (0.0 - 1.0).', 'minRelevance', 0.1, 1.0, 0.05)}
            </div>
          )}

          {activeSettingsTab === 'ai' && (
            <div className="settings-section">
              <h2>AI-svar & Modell</h2>
              {renderSelect('Modell', 'Vilken LLM som ska användas för att generera slutsvar.', 'aiModel', [
                { value: 'gpt-4o', label: 'GPT-4o' },
                { value: 'claude-3-5', label: 'Claude 3.5 Sonnet' },
                { value: 'gemini-1-5', label: 'Gemini 1.5 Pro' }
              ])}
              {renderSlider('Temperatur', 'Hur "kreativ" eller deterministisk modellen får vara (0.0 = strikt, 1.0 = kreativ).', 'temperature', 0.0, 1.0, 0.1)}
              {renderSlider('Maximal svarslängd', 'Högsta antal tokens modellen tillåts generera i ett enskilt svar.', 'maxResponseLength', 200, 4000, 100, ' tokens')}
              {renderToggle('Krav på källor', 'Svaret MÅSTE innehålla referenser till de hämtade dokumenten.', 'requireSources')}
              {renderSelect('Beteende vid otillräckligt underlag', 'Vad modellen ska göra om den inte hittar svaret i dokumenten.', 'insufficientDataBehavior', [
                { value: 'refuse', label: 'Neka artigt (Hallucinationsskydd)' },
                { value: 'guess', label: 'Försök svara ändå utifrån allmän kunskap' }
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
