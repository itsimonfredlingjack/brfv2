export const MOCK_DOCUMENTS = [
  { id: 'd1', name: 'Snöröjningsavtal 2026 MOCK.pdf', date: '2026-07-16', pages: 2, status: 'Färdigbehandlad', qa: 'Granskad', bevakningar: 1 },
  { id: 'd2', name: 'Stadgar Brf Gjutformen 12 MOCK.pdf', date: '2026-07-15', pages: 18, status: 'Färdigbehandlad', qa: 'Behöver granskas', bevakningar: 0 },
  { id: 'd3', name: 'Styrelseprotokoll 2026-03-12 MOCK.pdf', date: '2026-03-14', pages: 4, status: 'Färdigbehandlad', qa: 'Granskad', bevakningar: 2 },
  { id: 'd4', name: 'Årsredovisning 2025 MOCK.pdf', date: '2026-02-10', pages: 32, status: 'Behandlas', qa: 'Behöver granskas', bevakningar: 0 },
  { id: 'd5', name: 'Underhållsplan 2026-2036 MOCK.pdf', date: '2026-01-05', pages: 14, status: 'Färdigbehandlad', qa: 'Granskad', bevakningar: 3 },
];

export const MOCK_BEVAKNINGAR = [
  { id: 'b1', docId: 'd1', title: 'Start snöröjningsjour', date: '15 Nov 2026', desc: 'Jouren träder i kraft och pågår till 15 april.', page: 1, done: false },
  { id: 'b2', docId: 'd3', title: 'Städdag', date: '24 Apr 2026', desc: 'Vårstädning av innegården.', page: 3, done: true },
  { id: 'b3', docId: 'd3', title: 'Filterbyte', date: '10 Okt 2026', desc: 'Byte av ventilationsfilter i alla lägenheter.', page: 4, done: false },
  { id: 'b4', docId: 'd5', title: 'Fasadrenovering', date: '01 Maj 2027', desc: 'Upphandling av fasadrenovering.', page: 5, done: false },
  { id: 'b5', docId: 'd5', title: 'OVK Besiktning', date: '15 Okt 2027', desc: 'Obligatorisk ventilationskontroll.', page: 8, done: false },
  { id: 'b6', docId: 'd5', title: 'Stambyte', date: '10 Jan 2030', desc: 'Planerat stambyte för alla trapphus.', page: 12, done: false },
];

export const MOCK_SEARCH_RESULTS = {
  query: 'andrahandsuthyrning',
  status: 'success',
  totalDocuments: 3,
  totalPassages: 5,
  results: [
    {
      id: 'res1',
      documentId: 'd2',
      documentName: 'Stadgar Brf Gjutformen 12 MOCK.pdf',
      documentType: 'Stadgar',
      page: 12,
      date: '2026-07-15',
      excerpt: "Bostadsrättshavaren får upplåta sin lägenhet i andra hand till annan för självständigt brukande endast om styrelsen ger sitt samtycke. Samtycke ska lämnas om bostadsrättshavaren har beaktansvärda skäl för upplåtelsen och föreningen inte har någon befogad anledning att vägra samtycke.",
      highlights: ['andra hand', 'samtycke', 'upplåtelse'],
    },
    {
      id: 'res2',
      documentId: 'd2',
      documentName: 'Stadgar Brf Gjutformen 12 MOCK.pdf',
      documentType: 'Stadgar',
      page: 14,
      date: '2026-07-15',
      excerpt: "Avgiften för andrahandsuthyrning uppgår till 10% av prisbasbeloppet per år. En upplåtelse i andra hand som sker utan samtycke är grund för förverkande av bostadsrätten.",
      highlights: ['andrahandsuthyrning', 'andra hand', 'utan samtycke'],
    }
  ]
};

export const MOCK_TEXT_EXTRACTION = {
  d1: {
    1: "AVTAL OM SNÖRÖJNING\n\nMellan Brf Gjutformen 12 och Vintertjänst AB.\n\n1. Omfattning\nEntreprenören åtar sig att utföra snöröjning och halkbekämpning av fastigheten Gjutformen 12.\n\n2. Tider\nJouren träder i kraft den 15 november och pågår till den 15 april varje år. Snöröjning ska påbörjas senast 2 timmar efter att snödjupet överstiger 5 cm.",
    2: "3. Avgift\nFöreningen betalar en fast avgift om 15 000 kr per säsong exklusive moms.\n\n4. Uppsägning\nAvtalet löper på 1 år och förlängs automatiskt om det inte sägs upp senast 3 månader innan avtalsperiodens utgång.\n\nSignaturer:\n[Olsläslig kråka] [Olsläslig kråka]"
  }
};
