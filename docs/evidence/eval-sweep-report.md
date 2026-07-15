
### Knob sweep (retrieval-only) — proof that settings are wired

| knob | value | recall@k | chunks |
|---|---|---|---|
| searchWeighting | 0 | 1.000 | 13 |
| searchWeighting | 50 (default) | 1.000 | 13 |
| searchWeighting | 100 | 0.957 | 13 |
| topK | 1 | 0.870 | 13 |
| topK | 3 | 0.957 | 13 |
| topK | 6 (default) | 1.000 | 13 |
| topK | 10 | 1.000 | 13 |
| chunkSize | 80 | 1.000 | 27 |
| chunkSize | 220 (default) | 1.000 | 13 |
| chunkSize | 500 | 1.000 | 13 |
| chunkStrategy | fixed | 1.000 | 13 |
| chunkStrategy | sentence | 1.000 | 13 |
| chunkStrategy | recursive (default) | 1.000 | 13 |
