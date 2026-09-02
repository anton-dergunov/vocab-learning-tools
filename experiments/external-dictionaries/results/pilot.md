### Representation — is the mapper worth writing?

| Source | Entries | Source MiB | fields MiB | html MiB | html ÷ fields | Mapped | Invented | Unmapped POS kinds |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| `cc-cedict` | 5,000 | 3.8 | 1.2 | 0.7 | 0.59× | 100.0 % | — | 0 |
| `kaikki-es-en` | 5,000 | 979.0 | 1.8 | 1.2 | 0.66× | 100.0 % | — | 12 |
| `kaikki-es-es` | 5,000 | 94.7 | 2.9 | 2.1 | 0.71× | 98.7 % | — | 9 |
| `jmdict-eng` | 5,000 | 11.0 | 1.5 | 0.5 | 0.34× | 100.0 % | — | 17 |
| `freedict-eng-rus-tei` | 5,000 | 3.8 | 1.1 | 0.4 | 0.37× | 100.0 % | — | 4 |
| `freedict-eng-rus-stardict` | 5,000 | 4.0 | 0.0 | 1.8 | 0.00× | 0.0 % | — | 0 |

#### `cc-cedict` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.00× | 64 KiB | 62 KiB | 0.0465 ms |
| packed+block256 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.01× | 64 KiB | 62 KiB | 0.0671 ms |
| packed+block64 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.08× | 64 KiB | 16 KiB | 0.0226 ms |
| packed+block64 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.08× | 64 KiB | 16 KiB | 0.0146 ms |
| packed+block256 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.19× | 64 KiB | 62 KiB | 0.0655 ms |
| packed+block64 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.21× | 64 KiB | 16 KiB | 0.021 ms |

#### `cc-cedict` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.00× | 64 KiB | 37 KiB | 0.0621 ms |
| packed+block256 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.00× | 64 KiB | 37 KiB | 0.0421 ms |
| packed+block64 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.07× | 64 KiB | 9 KiB | 0.0199 ms |
| packed+block64 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.08× | 64 KiB | 9 KiB | 0.014 ms |
| packed+block256 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.15× | 64 KiB | 37 KiB | 0.0606 ms |
| packed+block64 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.18× | 64 KiB | 9 KiB | 0.0197 ms |

#### `kaikki-es-en` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.3 | 0.1 | — | 8 KiB | **0.4 MiB** | 1.00× | 64 KiB | 90 KiB | 0.064 ms |
| packed+block256 | deflate | 0.3 | 0.1 | — | — | **0.4 MiB** | 1.04× | 64 KiB | 90 KiB | 0.108 ms |
| packed+block64 | zstd19 | 0.3 | 0.1 | — | 8 KiB | **0.4 MiB** | 1.09× | 64 KiB | 23 KiB | 0.0292 ms |
| packed+block64 | deflate | 0.4 | 0.1 | — | — | **0.5 MiB** | 1.11× | 64 KiB | 23 KiB | 0.0417 ms |
| packed+block256 | deflate+dict | 0.3 | 0.1 | 64 KiB | — | **0.5 MiB** | 1.16× | 64 KiB | 90 KiB | 0.0998 ms |
| packed+block64 | deflate+dict | 0.3 | 0.1 | 64 KiB | — | **0.5 MiB** | 1.18× | 64 KiB | 23 KiB | 0.0388 ms |

#### `kaikki-es-en` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.3 | 0.1 | — | 8 KiB | **0.4 MiB** | 1.00× | 64 KiB | 60 KiB | 0.0522 ms |
| packed+block256 | deflate | 0.3 | 0.1 | — | — | **0.4 MiB** | 1.02× | 64 KiB | 60 KiB | 0.0846 ms |
| packed+block64 | zstd19 | 0.3 | 0.1 | — | 8 KiB | **0.4 MiB** | 1.10× | 64 KiB | 15 KiB | 0.0219 ms |
| packed+block64 | deflate | 0.3 | 0.1 | — | — | **0.4 MiB** | 1.11× | 64 KiB | 15 KiB | 0.0338 ms |
| packed+block256 | deflate+dict | 0.3 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.16× | 64 KiB | 60 KiB | 0.0798 ms |
| packed+block64 | deflate+dict | 0.3 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.16× | 64 KiB | 15 KiB | 0.0318 ms |

#### `kaikki-es-es` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.7 | 0.1 | — | 8 KiB | **0.8 MiB** | 1.00× | 64 KiB | 147 KiB | 0.1389 ms |
| packed+block256 | deflate | 0.7 | 0.1 | — | — | **0.9 MiB** | 1.08× | 64 KiB | 147 KiB | 0.2009 ms |
| packed+block64 | zstd19 | 0.8 | 0.1 | — | 8 KiB | **0.9 MiB** | 1.11× | 64 KiB | 37 KiB | 0.0488 ms |
| packed+block256 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.9 MiB** | 1.13× | 64 KiB | 147 KiB | 0.1886 ms |
| packed+block64 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.9 MiB** | 1.14× | 64 KiB | 37 KiB | 0.0721 ms |
| packed+block64 | deflate | 0.8 | 0.1 | — | — | **0.9 MiB** | 1.14× | 64 KiB | 37 KiB | 0.0746 ms |

#### `kaikki-es-es` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.6 | 0.1 | — | 8 KiB | **0.8 MiB** | 1.00× | 64 KiB | 103 KiB | 0.1766 ms |
| packed+block256 | deflate | 0.7 | 0.1 | — | — | **0.8 MiB** | 1.06× | 64 KiB | 103 KiB | 0.1935 ms |
| packed+block256 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.8 MiB** | 1.11× | 64 KiB | 103 KiB | 0.2505 ms |
| packed+block64 | zstd19 | 0.7 | 0.1 | — | 8 KiB | **0.8 MiB** | 1.11× | 64 KiB | 26 KiB | 0.0726 ms |
| packed+block64 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.9 MiB** | 1.11× | 64 KiB | 26 KiB | 0.0618 ms |
| packed+block16 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.9 MiB** | 1.14× | 64 KiB | 6 KiB | 0.0295 ms |

#### `jmdict-eng` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.00× | 64 KiB | 79 KiB | 0.0942 ms |
| packed+block256 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.01× | 64 KiB | 79 KiB | 0.1345 ms |
| packed+block64 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.07× | 64 KiB | 20 KiB | 0.0327 ms |
| packed+block64 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.07× | 64 KiB | 20 KiB | 0.0229 ms |
| packed+block256 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.19× | 64 KiB | 79 KiB | 0.1608 ms |
| packed+block64 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.20× | 64 KiB | 20 KiB | 0.0433 ms |

#### `jmdict-eng` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | deflate | 0.1 | 0.1 | — | — | **0.3 MiB** | 1.00× | 64 KiB | 28 KiB | 0.0593 ms |
| packed+block256 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.01× | 64 KiB | 28 KiB | 0.0402 ms |
| packed+block64 | deflate | 0.1 | 0.1 | — | — | **0.3 MiB** | 1.05× | 64 KiB | 7 KiB | 0.037 ms |
| packed+block64 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.07× | 64 KiB | 7 KiB | 0.0145 ms |
| packed+block16 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.15× | 64 KiB | 2 KiB | 0.009 ms |
| packed+block256 | deflate+dict | 0.1 | 0.1 | 64 KiB | — | **0.3 MiB** | 1.19× | 64 KiB | 28 KiB | 0.0554 ms |

#### `freedict-eng-rus-tei` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.00× | 64 KiB | 56 KiB | 0.0367 ms |
| packed+block256 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.2 MiB** | 1.00× | 64 KiB | 56 KiB | 0.0278 ms |
| packed+block64 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.07× | 64 KiB | 14 KiB | 0.0137 ms |
| packed+block64 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.2 MiB** | 1.08× | 64 KiB | 14 KiB | 0.0109 ms |
| packed+block256 | deflate+dict | 0.1 | 0.1 | 64 KiB | — | **0.3 MiB** | 1.25× | 64 KiB | 56 KiB | 0.0346 ms |
| packed+block16 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.26× | 64 KiB | 3 KiB | 0.0076 ms |

#### `freedict-eng-rus-tei` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.00× | 64 KiB | 20 KiB | 0.0276 ms |
| packed+block256 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.2 MiB** | 1.02× | 64 KiB | 20 KiB | 0.0234 ms |
| packed+block64 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.05× | 64 KiB | 5 KiB | 0.0109 ms |
| packed+block64 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.2 MiB** | 1.09× | 64 KiB | 5 KiB | 0.0088 ms |
| packed+block16 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.18× | 64 KiB | 1 KiB | 0.0066 ms |
| indexeddb(payload floor) | deflate+dict | 0.2 | 0.0 | 64 KiB | — | **0.2 MiB** | 1.21× | 1,024 KiB | 0 KiB | — ms |

#### `freedict-eng-rus-stardict` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.4 | 0.1 | — | 8 KiB | **0.5 MiB** | 1.00× | 64 KiB | 89 KiB | 0.0985 ms |
| packed+block256 | deflate | 0.4 | 0.1 | — | — | **0.5 MiB** | 1.04× | 64 KiB | 89 KiB | 0.1373 ms |
| packed+block64 | zstd19 | 0.4 | 0.1 | — | 8 KiB | **0.6 MiB** | 1.10× | 64 KiB | 22 KiB | 0.0305 ms |
| packed+block64 | deflate | 0.5 | 0.1 | — | — | **0.6 MiB** | 1.12× | 64 KiB | 22 KiB | 0.0423 ms |
| packed+block256 | deflate+dict | 0.4 | 0.1 | 64 KiB | — | **0.6 MiB** | 1.13× | 64 KiB | 89 KiB | 0.1222 ms |
| packed+block64 | deflate+dict | 0.4 | 0.1 | 64 KiB | — | **0.6 MiB** | 1.15× | 64 KiB | 22 KiB | 0.047 ms |
