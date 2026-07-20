import { describe, expect, it } from 'vitest';
import { generationReadiness } from './providerReadiness';

describe('generationReadiness', () => {
  it('waits while health is unresolved', () => {
    expect(generationReadiness(null)).toEqual({ state: 'checking', message: null });
  });

  it('blocks the fake provider used only for tests', () => {
    const result = generationReadiness({ status: 'ok', mode: 'dev', llm_provider: 'fake' });
    expect(result.state).toBe('blocked');
    expect(result.message).toContain('fake');
  });

  it('blocks when no provider is configured', () => {
    expect(generationReadiness({ status: 'ok', mode: 'dev', llm_provider: 'none' }).state).toBe('blocked');
  });

  it('accepts the verified self-hosted pilot path', () => {
    expect(generationReadiness({ status: 'ok', mode: 'pilot', llm_provider: 'selfhosted' }))
      .toEqual({ state: 'ready', message: null });
  });

  it('rejects a non-self-hosted provider in pilot mode', () => {
    const result = generationReadiness({ status: 'ok', mode: 'pilot', llm_provider: 'claude-cli' });
    expect(result.state).toBe('blocked');
    expect(result.message).toContain('självhostad');
  });
});
