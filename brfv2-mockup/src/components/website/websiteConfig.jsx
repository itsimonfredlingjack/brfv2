import React from 'react';
import { Button, FaqItem, Media, Prose } from './blocks';
import { formatDate, splitDate } from './dates';

// The BRF website's component vocabulary, wired to the editor.
//
// This is the *mirror* of backend/app/website/components.py, which is the
// authority. Two declarations exist because the backend has to validate a
// vocabulary and the browser has to draw one, and neither can do the other's
// job — so they are locked together instead: `websiteVocabulary.test.js` reads
// backend/app/website/VOCABULARY.lock.json and fails when a component or field
// here disagrees with it. Changing the vocabulary means changing both sides and
// re-recording the lock, deliberately.
//
// The same config renders the editor canvas and the published page. There is no
// second, "public" rendering path and no stored HTML anywhere: a published page
// is the same structured blocks going through the same components. The blocks
// themselves live in blocks.jsx.

const imageField = (label) => ({
  type: 'object',
  label,
  objectFields: {
    src: { type: 'text', label: 'Bildadress' },
    alt: { type: 'text', label: 'Alt-text (beskriv bilden)' },
  },
});

const linkField = (label) => ({
  type: 'object',
  label,
  objectFields: {
    label: { type: 'text', label: 'Text på knappen' },
    href: { type: 'text', label: 'Adress' },
  },
});

const TONE_OPTIONS = [
  { value: 'info', label: 'Information' },
  { value: 'warning', label: 'Viktigt' },
  { value: 'critical', label: 'Akut' },
];

const TONE_LABELS = { info: 'Information', warning: 'Viktigt', critical: 'Akut' };

const STATE_LABELS = { done: 'Klart', ongoing: 'Pågår', planned: 'Planerat' };

/**
 * Build the Puck config.
 *
 * `documents` are the association's own indexed documents, which is what turns
 * the document block from "paste a link" into "pick the stadgar you already
 * have" — and the backend refuses a document id that is not this tenant's, so
 * the list and the validation agree.
 */
export function createWebsiteConfig({ documents = [], settings = {}, navigation = [], activePageId = '' } = {}) {
  const documentOptions = [
    { value: '', label: 'Välj dokument…' },
    ...documents.map((doc) => ({ value: doc.id, label: doc.name })),
  ];
  const documentName = (id) => documents.find((doc) => doc.id === id)?.name || '';

  return {
    root: {
      fields: {
        title: { type: 'text', label: 'Sidans rubrik' },
      },
      render: ({ children }) => (
        <div className="brf-site" data-accent={settings.accent || 'koppar'}>
          <header className="brf-site__header">
            <div className="brf-site__header-inner">
              <div className="brf-site__name">
                {settings.name || 'Föreningens webbplats'}
                {settings.tagline ? <span className="brf-site__tagline">{settings.tagline}</span> : null}
              </div>
              {navigation.length > 0 && (
                <nav className="brf-site__nav" aria-label="Webbplatsens meny">
                  {navigation.map((item) => (
                    <a
                      key={item.page_id}
                      href={`/${item.slug}`}
                      aria-current={item.page_id === activePageId ? 'page' : undefined}
                      onClick={(e) => e.preventDefault()}
                    >
                      {item.label}
                    </a>
                  ))}
                </nav>
              )}
            </div>
          </header>

          <main className="brf-site__body">{children}</main>

          <footer className="brf-site__footer">
            <div className="brf-site__footer-inner">
              <span>{settings.footer_text || settings.name || ''}</span>
              <span>
                {settings.contact_email && (
                  <a href={`mailto:${settings.contact_email}`}>{settings.contact_email}</a>
                )}
                {settings.contact_email && settings.contact_phone ? ' · ' : ''}
                {settings.contact_phone}
              </span>
            </div>
          </footer>
        </div>
      ),
    },

    categories: {
      innehåll: { title: 'Innehåll', components: ['Hero', 'TextSection', 'ImageWithText'] },
      information: {
        title: 'Information',
        components: ['ImportantNotice', 'NewsList', 'Calendar', 'Faq', 'ProjectStatus'],
      },
      kontakt: { title: 'Kontakt', components: ['ContactCard', 'FaultReport'] },
      förening: { title: 'Föreningen', components: ['DocumentList'] },
    },

    components: {
      // ---------- innehåll ----------
      Hero: {
        label: 'Toppsektion',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          preamble: { type: 'textarea', label: 'Ingress', contentEditable: true },
          image: imageField('Bild'),
          action: linkField('Knapp'),
          variant: {
            type: 'select',
            label: 'Utseende',
            options: [
              { value: 'image', label: 'Med bild' },
              { value: 'plain', label: 'Utan bild' },
              { value: 'compact', label: 'Låg' },
            ],
          },
        },
        defaultProps: {
          heading: 'Välkommen till föreningen',
          preamble: '',
          variant: 'image',
          image: { src: '', alt: '' },
          action: { label: '', href: '' },
        },
        render: ({ heading, preamble, image, action, variant }) => (
          <section className={`blk-hero blk-hero--${variant || 'image'}`}>
            <div className="blk-hero__inner">
              <div>
                <h1 className="blk-hero__heading">{heading}</h1>
                {preamble ? <p className="blk-hero__preamble">{preamble}</p> : null}
                <Button action={action} />
              </div>
              {variant === 'image' && (
                <Media image={image} className="blk-hero__media" emptyHint="Välj en bild på huset eller gården" />
              )}
            </div>
          </section>
        ),
      },

      TextSection: {
        label: 'Text',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          body: { type: 'richtext', label: 'Text', contentEditable: true },
          width: {
            type: 'select',
            label: 'Bredd',
            options: [
              { value: 'normal', label: 'Normal' },
              { value: 'narrow', label: 'Smal' },
              { value: 'wide', label: 'Bred' },
            ],
          },
        },
        defaultProps: { heading: 'Rubrik', body: '<p>Skriv här.</p>', width: 'normal' },
        render: ({ heading, body, width }) => (
          <section className={`blk blk--${width || 'normal'}`}>
            {heading ? <h2 className="blk__title">{heading}</h2> : null}
            <Prose value={body} placeholder="Skriv texten här." />
          </section>
        ),
      },

      ImageWithText: {
        label: 'Bild och text',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          body: { type: 'richtext', label: 'Text', contentEditable: true },
          image: imageField('Bild'),
          side: {
            type: 'select',
            label: 'Bildens placering',
            options: [
              { value: 'left', label: 'Vänster' },
              { value: 'right', label: 'Höger' },
            ],
          },
        },
        defaultProps: {
          heading: 'Rubrik',
          body: '<p>Skriv här.</p>',
          image: { src: '', alt: '' },
          side: 'left',
        },
        render: ({ heading, body, image, side }) => (
          <section className={`blk blk-imgtext blk-imgtext--${side || 'left'}`}>
            <div className="blk-imgtext__inner">
              <Media image={image} className="blk-imgtext__media" emptyHint="Välj en bild" />
              <div>
                {heading ? <h2 className="blk__title">{heading}</h2> : null}
                <Prose value={body} placeholder="Skriv texten här." />
              </div>
            </div>
          </section>
        ),
      },

      // ---------- information ----------
      ImportantNotice: {
        label: 'Viktigt meddelande',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          body: { type: 'richtext', label: 'Meddelande', contentEditable: true },
          tone: { type: 'select', label: 'Allvarsgrad', options: TONE_OPTIONS },
          valid_until: { type: 'text', label: 'Gäller till och med (ÅÅÅÅ-MM-DD)' },
        },
        defaultProps: { heading: 'Viktigt meddelande', body: '<p></p>', tone: 'info', valid_until: '' },
        render: ({ heading, body, tone, valid_until: validUntil }) => (
          <section className={`blk blk-notice blk-notice--${tone || 'info'}`}>
            <div className="blk-notice__card">
              <div className="blk-notice__label">{TONE_LABELS[tone] || TONE_LABELS.info}</div>
              <h2 className="blk-notice__heading">{heading}</h2>
              <Prose value={body} placeholder="Vad behöver de boende veta?" />
              {validUntil ? (
                <p className="blk-notice__until">Gäller till och med {formatDate(validUntil)}.</p>
              ) : null}
            </div>
          </section>
        ),
      },

      NewsList: {
        label: 'Nyheter',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          items: {
            type: 'array',
            label: 'Nyheter',
            max: 24,
            getItemSummary: (item, i) => item?.title || `Nyhet ${i + 1}`,
            arrayFields: {
              date: { type: 'text', label: 'Datum (ÅÅÅÅ-MM-DD)' },
              title: { type: 'text', label: 'Rubrik' },
              body: { type: 'richtext', label: 'Text' },
            },
            defaultItemProps: { date: '', title: 'Ny notis', body: '<p></p>' },
          },
        },
        defaultProps: { heading: 'Nyheter', items: [] },
        render: ({ heading, items }) => {
          const rows = [...(items || [])].sort((a, b) => String(b?.date || '').localeCompare(String(a?.date || '')));
          return (
            <section className="blk blk-news">
              {heading ? <h2 className="blk__title">{heading}</h2> : null}
              {rows.length === 0 ? (
                <p className="blk__placeholder">Inga nyheter ännu.</p>
              ) : (
                <div className="blk-news__list">
                  {rows.map((item, i) => (
                    <article className="blk-news__item" key={i}>
                      <div className="blk-news__date">{formatDate(item?.date)}</div>
                      <div>
                        <h3 className="blk-news__title">{item?.title}</h3>
                        <Prose value={item?.body} />
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          );
        },
      },

      Calendar: {
        label: 'Kalender',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          events: {
            type: 'array',
            label: 'Händelser',
            max: 36,
            getItemSummary: (item, i) => item?.title || `Händelse ${i + 1}`,
            arrayFields: {
              date: { type: 'text', label: 'Datum (ÅÅÅÅ-MM-DD)' },
              title: { type: 'text', label: 'Vad' },
              place: { type: 'text', label: 'Var' },
              note: { type: 'text', label: 'Kommentar' },
            },
            defaultItemProps: { date: '', title: '', place: '', note: '' },
          },
        },
        defaultProps: { heading: 'Kalender', events: [] },
        render: ({ heading, events }) => {
          const rows = [...(events || [])].sort((a, b) => String(a?.date || '').localeCompare(String(b?.date || '')));
          return (
            <section className="blk blk-cal">
              {heading ? <h2 className="blk__title">{heading}</h2> : null}
              {rows.length === 0 ? (
                <p className="blk__placeholder">Inga inplanerade datum.</p>
              ) : (
                <div className="blk-cal__list">
                  {rows.map((event, i) => {
                    const { day, month } = splitDate(event?.date);
                    return (
                      <div className="blk-cal__item" key={i}>
                        <div className="blk-cal__date">
                          <div className="blk-cal__day">{day}</div>
                          <div className="blk-cal__month">{month}</div>
                        </div>
                        <div>
                          <div className="blk-cal__what">{event?.title}</div>
                          {(event?.place || event?.note) && (
                            <div className="blk-cal__where">
                              {[event?.place, event?.note].filter(Boolean).join(' · ')}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          );
        },
      },

      Faq: {
        label: 'Frågor och svar',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          items: {
            type: 'array',
            label: 'Frågor',
            max: 40,
            getItemSummary: (item, i) => item?.question || `Fråga ${i + 1}`,
            arrayFields: {
              question: { type: 'text', label: 'Fråga' },
              answer: { type: 'richtext', label: 'Svar' },
            },
            defaultItemProps: { question: 'Ny fråga', answer: '<p></p>' },
          },
        },
        defaultProps: { heading: 'Frågor och svar', items: [] },
        render: ({ heading, items }) => (
          <section className="blk blk-faq">
            {heading ? <h2 className="blk__title">{heading}</h2> : null}
            {(items || []).length === 0 ? (
              <p className="blk__placeholder">Inga frågor ännu.</p>
            ) : (
              <div className="blk-faq__list">
                {(items || []).map((item, i) => (
                  <FaqItem key={i} question={item?.question} answer={item?.answer} defaultOpen={i === 0} />
                ))}
              </div>
            )}
          </section>
        ),
      },

      ProjectStatus: {
        label: 'Projektstatus',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          body: { type: 'richtext', label: 'Beskrivning', contentEditable: true },
          steps: {
            type: 'array',
            label: 'Steg',
            max: 12,
            getItemSummary: (item, i) => item?.label || `Steg ${i + 1}`,
            arrayFields: {
              label: { type: 'text', label: 'Steg' },
              state: {
                type: 'select',
                label: 'Läge',
                options: [
                  { value: 'done', label: 'Klart' },
                  { value: 'ongoing', label: 'Pågår' },
                  { value: 'planned', label: 'Planerat' },
                ],
              },
              note: { type: 'text', label: 'Kommentar' },
            },
            defaultItemProps: { label: 'Nytt steg', state: 'planned', note: '' },
          },
        },
        defaultProps: { heading: 'Projektstatus', body: '<p></p>', steps: [] },
        render: ({ heading, body, steps }) => (
          <section className="blk blk-proj">
            <h2 className="blk__title">{heading}</h2>
            <Prose value={body} />
            {(steps || []).length > 0 && (
              <div className="blk-proj__steps">
                {(steps || []).map((step, i) => (
                  <div className="blk-proj__step" data-state={step?.state || 'planned'} key={i}>
                    <div className="blk-proj__dot">{step?.state === 'done' ? '✓' : i + 1}</div>
                    <div>
                      <div className="blk-proj__label">{step?.label}</div>
                      <div className="blk-proj__state">
                        {STATE_LABELS[step?.state] || STATE_LABELS.planned}
                        {step?.note ? ` · ${step.note}` : ''}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        ),
      },

      // ---------- kontakt ----------
      ContactCard: {
        label: 'Kontakt',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          intro: { type: 'textarea', label: 'Ingress', contentEditable: true },
          entries: {
            type: 'array',
            label: 'Kontakter',
            max: 12,
            getItemSummary: (item, i) => item?.role || `Kontakt ${i + 1}`,
            arrayFields: {
              role: { type: 'text', label: 'Roll' },
              name: { type: 'text', label: 'Namn' },
              email: { type: 'text', label: 'E-post' },
              phone: { type: 'text', label: 'Telefon' },
            },
            defaultItemProps: { role: 'Styrelsen', name: '', email: '', phone: '' },
          },
        },
        defaultProps: { heading: 'Kontakt', intro: '', entries: [] },
        render: ({ heading, intro, entries }) => (
          <section className="blk blk-contact">
            {heading ? <h2 className="blk__title">{heading}</h2> : null}
            {intro ? <p className="blk__prose">{intro}</p> : null}
            {(entries || []).length === 0 ? (
              <p className="blk__placeholder">Inga kontakter tillagda.</p>
            ) : (
              <div className="blk-contact__grid">
                {(entries || []).map((entry, i) => (
                  <div className="blk-contact__card" key={i}>
                    <div className="blk-contact__role">{entry?.role}</div>
                    {entry?.name ? <div className="blk-contact__name">{entry.name}</div> : null}
                    {entry?.email ? (
                      <div className="blk-contact__line">
                        <a href={`mailto:${entry.email}`}>{entry.email}</a>
                      </div>
                    ) : null}
                    {entry?.phone ? (
                      <div className="blk-contact__line">
                        <a href={`tel:${String(entry.phone).replace(/\s/g, '')}`}>{entry.phone}</a>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </section>
        ),
      },

      FaultReport: {
        label: 'Felanmälan',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          body: { type: 'richtext', label: 'Så här gör du', contentEditable: true },
          phone: { type: 'text', label: 'Telefon dagtid' },
          email: { type: 'text', label: 'E-post' },
          emergency_phone: { type: 'text', label: 'Jour (akut)' },
          emergency_note: { type: 'text', label: 'När jouren gäller' },
          action: linkField('Knapp'),
        },
        defaultProps: {
          heading: 'Felanmälan',
          body: '<p></p>',
          phone: '',
          email: '',
          emergency_phone: '',
          emergency_note: '',
          action: { label: '', href: '' },
        },
        render: ({ heading, body, phone, email, emergency_phone: jour, emergency_note: jourNote, action }) => (
          <section className="blk blk-fault">
            <div className="blk-fault__card">
              <h2 className="blk__title">{heading}</h2>
              <Prose value={body} placeholder="Beskriv hur en boende anmäler fel." />
              <div className="blk-fault__rows">
                {phone ? (
                  <div className="blk-fault__row">
                    <div className="blk-fault__row-label">Telefon dagtid</div>
                    <div className="blk-fault__row-value">
                      <a href={`tel:${phone.replace(/\s/g, '')}`}>{phone}</a>
                    </div>
                  </div>
                ) : null}
                {email ? (
                  <div className="blk-fault__row">
                    <div className="blk-fault__row-label">E-post</div>
                    <div className="blk-fault__row-value">
                      <a href={`mailto:${email}`}>{email}</a>
                    </div>
                  </div>
                ) : null}
                {jour ? (
                  <div className="blk-fault__row blk-fault__row--emergency">
                    <div className="blk-fault__row-label">Jour — akut</div>
                    <div className="blk-fault__row-value">
                      <a href={`tel:${jour.replace(/\s/g, '')}`}>{jour}</a>
                    </div>
                    {jourNote ? <div className="blk-fault__row-note">{jourNote}</div> : null}
                  </div>
                ) : null}
              </div>
              <Button action={action} />
            </div>
          </section>
        ),
      },

      // ---------- förening ----------
      DocumentList: {
        label: 'Dokument',
        fields: {
          heading: { type: 'text', label: 'Rubrik', contentEditable: true },
          intro: { type: 'textarea', label: 'Ingress', contentEditable: true },
          documents: {
            type: 'array',
            label: 'Dokument',
            max: 40,
            getItemSummary: (item, i) => item?.label || documentName(item?.document_id) || `Dokument ${i + 1}`,
            arrayFields: {
              document_id: { type: 'select', label: 'Dokument', options: documentOptions },
              label: { type: 'text', label: 'Visas som' },
            },
            defaultItemProps: { document_id: '', label: '' },
          },
        },
        defaultProps: { heading: 'Dokument', intro: '', documents: [] },
        render: ({ heading, intro, documents: rows }) => (
          <section className="blk blk-docs">
            {heading ? <h2 className="blk__title">{heading}</h2> : null}
            {intro ? <p className="blk__prose">{intro}</p> : null}
            {(rows || []).length === 0 ? (
              <p className="blk__placeholder">Inga dokument valda ännu.</p>
            ) : (
              <div className="blk-docs__list">
                {(rows || []).map((row, i) => {
                  const name = row?.label || documentName(row?.document_id) || 'Dokument';
                  return (
                    <a className="blk-docs__item" key={i} href={`#${row?.document_id || ''}`} onClick={(e) => e.preventDefault()}>
                      <span className="blk-docs__icon">PDF</span>
                      <span className="blk-docs__name">{name}</span>
                    </a>
                  );
                })}
              </div>
            )}
          </section>
        ),
      },
    },
  };
}
