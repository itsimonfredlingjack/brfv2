import type { RefusalReason, RejectReason } from '../api/types'

/* A refusal is the product working correctly. It is presented in amber, with
 * a plain explanation and something the user can actually do next — never as
 * an error, and never as an empty answer. Ported verbatim from
 * xs_mobilapp/src/lib/refusals.ts: this copy is proven product decision, not
 * restyled per screen. */

export interface RefusalCopy {
  /** Amber (correct behavior) vs red (something is actually broken). */
  tone: 'refusal' | 'error'
  title: string
  body: string
  /** What to try instead. Omitted where there is nothing honest to suggest. */
  next?: string
}

/** Shown under every refusal. It appears often enough to become a promise. */
export const GROUNDING_PROMISE = 'Inget svar visas utan belägg.'

const COPY: Record<RefusalReason, RefusalCopy> = {
  no_documents: {
    tone: 'refusal',
    title: 'Inga dokument att söka i',
    body: 'Föreningen har inga dokument uppladdade ännu.',
    next: 'En administratör laddar upp dokument i webbappen.',
  },
  low_relevance: {
    tone: 'refusal',
    title: 'Ingen tillräckligt nära träff',
    body: 'Ingen passage i era dokument matchar frågan tillräckligt väl.',
    next: 'Pröva att formulera om frågan med ord som troligen står i dokumentet.',
  },
  insufficient_data: {
    tone: 'refusal',
    title: 'Svaret finns inte i dokumenten',
    body: 'Dokumenten innehåller inte svaret på den här frågan.',
    next: 'Kontrollera i Bibliotek om rätt dokument är uppladdat.',
  },
  grounding_failed: {
    tone: 'refusal',
    title: 'Svaret kunde inte beläggas',
    body: 'Ett svar togs fram men gick inte att belägga ordagrant i era dokument, så det visas inte.',
    next: 'Pröva en smalare fråga om ett enskilt förhållande.',
  },
  numeric_grounding_failed: {
    tone: 'refusal',
    title: 'Siffran kunde inte beläggas',
    body: 'Svaret innehöll en siffra som inte gick att belägga i den citerade texten, så det visas inte.',
    next: 'Fråga efter passagen i stället, så kan du läsa siffran i källan.',
  },
  provider_error: {
    tone: 'error',
    title: 'Modelltjänsten svarar inte',
    body: 'Frågan kunde inte besvaras eftersom språkmodellen inte gick att nå.',
    next: 'Pröva igen om en liten stund.',
  },
}

/**
 * Copy for a refusal reason. An unknown reason — a backend that grew a new
 * one — still refuses honestly rather than rendering an empty card.
 */
export function refusalCopy(reason: RefusalReason | null): RefusalCopy {
  if (reason && reason in COPY) return COPY[reason]
  return {
    tone: 'refusal',
    title: 'Frågan besvarades inte',
    body: 'Systemet kunde inte ge ett belagt svar på frågan.',
  }
}

/** Diagnostics, shown only behind the "Varför visas inget svar?" disclosure. */
const REJECT_COPY: Record<RejectReason, string> = {
  quote_not_found: 'Citatet gick inte att hitta ordagrant i dokumentet.',
  provenance_mismatch: 'Citatet fanns någon annanstans än i den angivna källan.',
  bbox_out_of_bounds: 'Citatets position hamnade utanför sidan.',
  unknown_chunk: 'Citatet pekade på ett textstycke som inte finns.',
  too_many_spans: 'Citatet var uppdelat på för många fragment.',
}

export function rejectCopy(reason: RejectReason): string {
  return REJECT_COPY[reason] ?? 'Citatet avvisades vid verifieringen.'
}
