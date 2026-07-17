// FABRICATED DEMO SCAFFOLDING — dev-only, single allowlisted data module.
//
// Every value below (document names, dates, page numbers, "extracted text",
// chunk previews, timeline entries) is hand-authored design-template
// filler. NONE of it came from the real retrieval/verification pipeline
// (api.ask -> AskResponse; resolve_citation). It exists only to give the
// pre-existing Granskning (QA review), Bevakningar (timeline), and Document
// Canvas demo tabs something to render in the dev server — see
// src/components/DemoWorkspace.jsx and src/components/DocumentView.jsx,
// both dev-gated via src/appModes.js's demoTabsEnabled() + a dynamic
// import() so this module and its consumers are excluded from production
// builds (verified by grepping `dist/` after `npm run build` — see
// docs/evidence/verified-ui-restore.md).
//
// This is the ONE product file allowed to contain pipeline-class data
// shapes (a source-document name + page, "extracted" body text, a
// quote-and-rects pair, etc.) — src/no-fabrication.test.js's tripwire scans
// every other product source file and fails if such shapes reappear there.
// A dedicated test in that same file asserts this module is imported ONLY
// from the two dev-gated components above, and that those components are
// never statically imported (only dynamically, behind the DEV gate) — so
// this allowlist-of-one stays honest even as the codebase changes.
//
// cleanup-global-constraints.md #1: this data must never reach a real user;
// dev-gating (Task 5) is what keeps that promise now that it lives here.

// ---- Granskning (QA review) tab — src/App.jsx's former `qaDocuments` state seed ----
export const qaDocuments = [
  {
    id: 0,
    title: 'SNÖRÖJNINGSAVTAL_2024.pdf',
    health: 98,
    pages: 3,
    ocrPages: 1,
    chunks: 45,
    problemsCount: 0,
    textCoverage: '100%',
    warnings: [],
    date: '2024-10-01',
    pagesContent: [
      {
        pageNum: 1,
        isOcr: false,
        status: 'approved',
        originalMock: {
          header: 'AVTAL OM SNÖRÖJNING 2024',
          meta: 'Datum: 2024-10-01 | Referens: SNÖ-BRF-99',
          paragraphs: [
            'Detta avtal har ingåtts mellan Bostadsrättsföreningen Lappen (nedan kallad Föreningen) och Snösvängen AB (nedan kallad Entreprenören).',
            '§1. OMFATTNING',
            'Entreprenören åtar sig att utföra snöröjning, maskinell sopning samt halkbekämpning på Föreningens gemensamma körytor, gångbanor samt entréer i enlighet med överenskommet schema.'
          ]
        },
        extractedText: `AVTAL OM SNÖRÖJNING 2024\nDatum: 2024-10-01 | Referens: SNÖ-BRF-99\n\nDetta avtal har ingåtts mellan Bostadsrättsföreningen Lappen (nedan kallad Föreningen) och Snösvängen AB (nedan kallad Entreprenören).\n\n§1. OMFATTNING\nEntreprenören åtar sig att utföra snöröjning, maskinell sopning samt halkbekämpning på Föreningens gemensamma körytor, gångbanor samt entréer i enlighet med överenskommet schema.`
      },
      {
        pageNum: 2,
        isOcr: true,
        status: 'unchecked',
        originalMock: {
          header: '§2. PRISER OCH JOURTIDER',
          meta: 'Utrustning och Timers',
          paragraphs: [
            'Aktiviteter debiteras enligt följande prislista:',
            '- Maskinell snöröjning (traktor): 1 250 kr/tim',
            '- Manuell skottning (trappor & entréer): 450 kr/tim',
            '- Halkbekämpning (salt/sand): 350 kr/säck',
            'Jourperioden löper oavkortat från 15 november till 15 april.'
          ]
        },
        extractedText: `§2. PRISER OCH JOURTIDER\nUtrustning och Timers\n\nAktiviteter debiteras enligt följande prislista:\n- Maskinell snöröjning (traktor): 1 250 kr/tim\n- Manuell skottning (trappor & entréer): 450 kr/tim\n- Halkbekämpning (salt/sand): 350 kr/säck\n\nJourperioden löper oavkortat från 15 november till 15 april.`
      },
      {
        pageNum: 3,
        isOcr: false,
        status: 'unchecked',
        originalMock: {
          header: '§3. UPPFÖLJNING & SIGNATUR',
          meta: 'Särskilda avtalsvillkor',
          paragraphs: [
            'Eventuella anmärkningar mot utfört arbete skall anmälas senast 24 timmar efter slutfört pass.',
            'Underskrivet elektroniskt:',
            'Brf Lappen: Simon R. (Styrelseordförande)',
            'Snösvängen AB: Gunnar S. (VD)'
          ]
        },
        extractedText: `§3. UPPFÖLJNING & SIGNATUR\nSärskilda avtalsvillkor\n\nEventuella anmärkningar mot utfört arbete skall anmälas senast 24 timmar efter slutfört pass.\n\nUnderskrivet elektroniskt:\nBrf Lappen: Simon R. (Styrelseordförande)\nSnösvängen AB: Gunnar S. (VD)`
      }
    ]
  },
  {
    id: 1,
    title: 'STYRELSEPROTOKOLL_MARS.pdf',
    health: 65,
    pages: 2,
    ocrPages: 2,
    chunks: 12,
    problemsCount: 2,
    textCoverage: '89%',
    warnings: ['Sida 2: Otydlig tabellstruktur identifierad under parsing', 'Sida 2: Innehåller handskrivna anteckningar i marginalen som kan ha förbisetts'],
    date: '2024-03-12',
    pagesContent: [
      {
        pageNum: 1,
        isOcr: true,
        status: 'approved',
        originalMock: {
          header: 'STYRELSEPROTOKOLL - BRF LAPPEN',
          meta: 'Mötesdatum: 2024-03-12 | Närvarande: Simon, Karin, Johan',
          paragraphs: [
            'Mötet öppnades kl 19:00 av ordförande Simon.',
            '§1. FÖREGÅENDE PROTOKOLL',
            'Protokollet från februarmötet lades till handlingarna utan anmärkningar.'
          ]
        },
        extractedText: `STYRELSEPROTOKOLL - BRF LAPPEN\nMötesdatum: 2024-03-12 | Närvarande: Simon, Karin, Johan\n\nMötet öppnades kl 19:00 av ordförande Simon.\n\n§1. FÖREGÅENDE PROTOKOLL\nProtokollet från februarmötet lades till handlingarna utan anmärkningar.`
      },
      {
        pageNum: 2,
        isOcr: true,
        status: 'warning',
        originalMock: {
          header: '§2. BESLUT OM UNDERHÅLL OCH BUDGET',
          meta: 'Protokollfört ekonomibeslut',
          isTable: true,
          tableRows: [
            { col1: 'Åtgärd', col2: 'Budget', col3: 'Status' },
            { col1: 'Fasadmålning', col2: '150 000 kr', col3: 'Beviljad' },
            { col1: 'OVK-besiktning', col2: '22 000 kr', col3: 'Påbörjad' },
            { col1: 'Stamspolning', col2: '85 000 kr', col3: 'Skjuten' }
          ]
        },
        extractedText: `§2. BESLUT OM UNDERHÅLL OCH BUDGET\nProtokollfört ekonomibeslut\n\n[PARSING ERROR - MERGED TABLE CELL VALUES]\nÅtgärdBudgetStatus\nFasadmålning150 000 krBeviljad\nOVK-besiktning22 000 krPåbörjad\nStamspolning85 000 krSkjuten`
      }
    ]
  },
  {
    id: 2,
    title: 'STADGAR_BRF_LAPPEN.pdf',
    health: 100,
    pages: 2,
    ocrPages: 0,
    chunks: 120,
    problemsCount: 0,
    textCoverage: '100%',
    warnings: [],
    date: '2023-11-20',
    pagesContent: [
      {
        pageNum: 1,
        isOcr: false,
        status: 'unchecked',
        originalMock: {
          header: 'STADGAR FÖR BOSTADSRÄTTSFÖRENINGEN LAPPEN',
          meta: 'Registrerad hos Bolagsverket: 2023-11-20',
          paragraphs: [
            'Föreningens firma är Bostadsrättsföreningen Lappen. Föreningen har till ändamål att främja medlemmarnas ekonomiska intressen genom att upplåta bostadslägenheter under nyttjanderätt.',
            '§1. MEDLEMSKAP',
            'Medlemskap i föreningen kan sökas av fysisk eller juridisk person som förvärvat bostadsrätt i föreningens fastighet.'
          ]
        },
        extractedText: `STADGAR FÖR BOSTADSRÄTTSFÖRENINGEN LAPPEN\nRegistrerad hos Bolagsverket: 2023-11-20\n\nFöreningens firma är Bostadsrättsföreningen Lappen. Föreningen har till ändamål att främja medlemmarnas ekonomiska intressen genom att upplåta bostadslägenheter under nyttjanderätt.\n\n§1. MEDLEMSKAP\nMedlemskap i föreningen kan sökas av fysisk eller juridisk person som förvärvat bostadsrätt i föreningens fastighet.`
      },
      {
        pageNum: 2,
        isOcr: false,
        status: 'unchecked',
        originalMock: {
          header: '§2. AVGIFTER & ÖVERLÅTELSE',
          meta: 'Ekonomiska förpliktelser',
          paragraphs: [
            'Årsavgiften fastställs av styrelsen och fördelas på bostadsrätterna efter lägenheternas andelstal.',
            'Överlåtelseavgift och pantsättningsavgift får tas ut efter beslut av styrelsen.'
          ]
        },
        extractedText: `§2. AVGIFTER & ÖVERLÅTELSE\nEkonomiska förpliktelser\n\nÅrsavgiften fastställs av styrelsen och fördelas på bostadsrätterna efter lägenheternas andelstal.\n\nÖverlåtelseavgift och pantsättningsavgift får tas ut efter beslut av styrelsen.`
      }
    ]
  }
];

// ---- Document Canvas tab — src/App.jsx's former `cardData` ----
export const cardData = {
  p3: { title: 'Jourperiod startar', description: 'Systemet har automatiskt skapat en bevakning för startdatum av snöröjningsjouren.', sourceDoc: 'SNÖRÖJNINGSAVTAL_2024.pdf', page: 2 },
  p5: { title: 'Regler för halkbekämpning', description: 'Halkbekämpning (saltning) ska utföras i förebyggande syfte eller senast 1 timme efter snöröjning.', sourceDoc: 'SNÖRÖJNINGSAVTAL_2024.pdf', page: 2 }
};

// ---- Bevakningar (timeline) tab — src/App.jsx's former `timelineData` ----
export const timelineData = [
  { id: 't1', date: '15 Nov 2024', title: 'Start snöröjningsjour', description: 'Snöröjningsjour startar årligen den 15 november.', doc: 'SNÖRÖJNINGSAVTAL_2024.pdf', page: 2 },
  { id: 't2', date: '31 Dec 2024', title: 'Budgetrapportering', description: 'Årlig budgetuppföljning och rapportering till styrelsen.', doc: 'ANSTÄLLNINGSAVTAL_VD.pdf', page: 6 },
  { id: 't3', date: '15 Apr 2025', title: 'Slut snöröjningsjour', description: 'Perioden för dygnet runt-jour avslutas.', doc: 'SNÖRÖJNINGSAVTAL_2024.pdf', page: 2 },
];

// ---- Document Canvas tab — src/components/DocumentView.jsx's former `documentData` ----
// Simulated extracted paragraphs from SNÖRÖJNINGSAVTAL_2024.pdf
export const documentData = [
  {
    id: 'p1',
    text: 'Detta avtal ("Avtalet") är upprättat mellan Beställaren och Entreprenören avseende snöröjning och halkbekämpning för perioden 2024-2025.',
  },
  {
    id: 'p2',
    text: 'Entreprenören åtar sig att utföra snöröjning och halkbekämpning på de ytor som anges i Bilaga 1. Arbetet ska utföras fackmannamässigt och i enlighet med gällande branschstandard.',
  },
  {
    id: 'p3',
    text: 'Snöröjningsjour startar årligen den 15 november och pågår fram till den 15 april. Under denna period ska Entreprenören vara tillgänglig dygnet runt.',
    highlightWord: '15 november',
    type: 'deadline'
  },
  {
    id: 'p4',
    text: 'Vid snöfall som överstiger 5 cm ska plogning påbörjas senast inom 2 timmar från det att snöfallet upphört. Om det snöar ihållande ska kontinuerlig plogning ske för att säkerställa framkomlighet.',
  },
  {
    id: 'p5',
    text: 'Halkbekämpning (saltning eller sandning) ska utföras förebyggande när risk för frosthalka föreligger, samt senast inom 1 timme efter avslutad snöröjning om behov finns för att förhindra isbildning.',
    highlightWord: 'saltning eller sandning',
    type: 'search'
  },
  {
    id: 'p6',
    text: 'Fakturering sker månadsvis i efterskott. Fakturan ska innehålla specifikation över utförda insatser, datum och klockslag. Betalningsvillkor är 30 dagar netto.',
  }
];
