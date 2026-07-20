export function generationReadiness(health) {
  if (!health) {
    return { state: 'checking', message: null };
  }

  if (health.status !== 'ok') {
    return {
      state: 'blocked',
      message: 'Backend rapporterar att systemet inte är redo.',
    };
  }

  const provider = health.llm_provider;
  if (provider === 'fake') {
    return {
      state: 'blocked',
      message: 'AI-generering kör med testleverantören fake. Sökning fungerar, men riktiga svar kan inte genereras.',
    };
  }

  if (!provider || provider === 'none') {
    return {
      state: 'blocked',
      message: 'Ingen LLM-leverantör är konfigurerad. Starta backend med en riktig generation-provider.',
    };
  }

  if (health.mode === 'pilot' && provider !== 'selfhosted') {
    return {
      state: 'blocked',
      message: 'Pilotläge kräver en självhostad LLM-leverantör.',
    };
  }

  return { state: 'ready', message: null };
}
