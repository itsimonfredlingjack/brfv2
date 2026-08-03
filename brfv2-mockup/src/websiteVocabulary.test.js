import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { createWebsiteConfig } from './components/website/websiteConfig';

// The editor half of the editor/backend contract.
//
// backend/app/website/components.py is the authority on what a page may contain;
// websiteConfig.jsx declares the same vocabulary again in React because the
// browser needs something to draw. Two declarations of one vocabulary drift, so
// they are locked to the same recorded file: the backend has a test that the
// lock matches its own module, and this is the test that the React config
// matches the lock.
//
// When this fails, the fix is never to edit the lock by hand. Change both sides
// and re-record it with `make website-vocabulary-lock`.

const here = dirname(fileURLToPath(import.meta.url));
const lock = JSON.parse(
  readFileSync(resolve(here, '../../backend/app/website/VOCABULARY.lock.json'), 'utf-8'),
);

const config = createWebsiteConfig({ documents: [] });

describe('komponentordlistan', () => {
  it('har exakt samma blocktyper som backend', () => {
    expect(Object.keys(config.components).sort()).toEqual(Object.keys(lock.components).sort());
  });

  it('har exakt samma fält per blocktyp som backend', () => {
    Object.entries(lock.components).forEach(([name, spec]) => {
      expect(
        Object.keys(config.components[name].fields).sort(),
        `fälten för ${name}`,
      ).toEqual(Object.keys(spec.fields).sort());
    });
  });

  it('erbjuder samma alternativ i varje val-fält som backend accepterar', () => {
    Object.entries(lock.components).forEach(([name, spec]) => {
      Object.entries(spec.fields).forEach(([fieldName, field]) => {
        if (field.kind !== 'select') return;
        const declared = field.options.map((o) => o.value).sort();
        const offered = (config.components[name].fields[fieldName].options || [])
          .map((o) => o.value)
          .sort();
        expect(offered, `${name}.${fieldName}`).toEqual(declared);
      });
    });
  });

  it('använder rich text exakt där backend gör det', () => {
    Object.entries(lock.components).forEach(([name, spec]) => {
      Object.entries(spec.fields).forEach(([fieldName, field]) => {
        const editorType = config.components[name].fields[fieldName].type;
        if (field.kind === 'richtext') {
          expect(editorType, `${name}.${fieldName}`).toBe('richtext');
        } else {
          expect(editorType, `${name}.${fieldName}`).not.toBe('richtext');
        }
      });
    });
  });

  it('gör listfält till redigerbara listor med samma underfält', () => {
    Object.entries(lock.components).forEach(([name, spec]) => {
      Object.entries(spec.fields).forEach(([fieldName, field]) => {
        if (field.kind !== 'list') return;
        const editorField = config.components[name].fields[fieldName];
        expect(editorField.type, `${name}.${fieldName}`).toBe('array');
        expect(Object.keys(editorField.arrayFields).sort()).toEqual(
          Object.keys(field.fields).sort(),
        );
      });
    });
  });

  it('placerar varje blocktyp i en kategori som backend känner till', () => {
    const categorised = Object.values(config.categories).flatMap((c) => c.components);
    expect(categorised.sort()).toEqual(Object.keys(lock.components).sort());
    Object.keys(config.categories).forEach((category) => {
      expect(lock.categories).toContain(category);
    });
  });

  it('har inget block som kan rendera fri HTML', () => {
    // The guarantee that makes the whole feature safe to point a model at: the
    // vocabulary contains no escape hatch, on either side.
    const suspicious = /html|embed|script|iframe|custom|raw/i;
    Object.entries(config.components).forEach(([name, spec]) => {
      expect(name).not.toMatch(suspicious);
      Object.keys(spec.fields).forEach((fieldName) => {
        expect(`${name}.${fieldName}`).not.toMatch(suspicious);
      });
    });
  });
});
