### Representation — is the mapper worth writing?

| Source | Entries | Source MiB | fields MiB | html MiB | html ÷ fields | Mapped | Invented | Unmapped POS kinds |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| `cc-cedict` | 5,000 | 3.8 | 1.3 | 0.7 | 0.56× | 100.0 % | pos | 0 |
| `kaikki-es-en` | 5,000 | 979.0 | 1.6 | 1.2 | 0.75× | 95.0 % | — | 12 |
| `kaikki-es-es` | 5,000 | 94.7 | 2.8 | 2.1 | 0.75× | 97.5 % | — | 9 |
| `jmdict-eng` | 5,000 | 11.0 | 1.4 | 0.5 | 0.36× | 98.0 % | — | 17 |
| `freedict-eng-rus-tei` | 5,000 | 3.8 | 1.0 | 0.4 | 0.41× | 97.8 % | — | 4 |
| `freedict-eng-rus-stardict` | 5,000 | 4.0 | 0.0 | 1.8 | 0.00× | 0.0 % | — | 0 |

#### `cc-cedict` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.00× | 64 KiB | 66 KiB | 0.047 ms |
| packed+block256 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.01× | 64 KiB | 66 KiB | 0.0673 ms |
| packed+block64 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.08× | 64 KiB | 16 KiB | 0.0223 ms |
| packed+block64 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.08× | 64 KiB | 16 KiB | 0.0148 ms |
| packed+block256 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.19× | 64 KiB | 66 KiB | 0.066 ms |
| packed+block64 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.21× | 64 KiB | 16 KiB | 0.0213 ms |

#### `cc-cedict` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.00× | 64 KiB | 37 KiB | 0.0635 ms |
| packed+block256 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.00× | 64 KiB | 37 KiB | 0.0432 ms |
| packed+block64 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.07× | 64 KiB | 9 KiB | 0.0198 ms |
| packed+block64 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.08× | 64 KiB | 9 KiB | 0.0154 ms |
| packed+block256 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.15× | 64 KiB | 37 KiB | 0.0622 ms |
| packed+block64 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.18× | 64 KiB | 9 KiB | 0.0206 ms |

#### `kaikki-es-en` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.3 | 0.1 | — | 8 KiB | **0.4 MiB** | 1.00× | 64 KiB | 85 KiB | 0.062 ms |
| packed+block256 | deflate | 0.3 | 0.1 | — | — | **0.4 MiB** | 1.03× | 64 KiB | 85 KiB | 0.1012 ms |
| packed+block64 | zstd19 | 0.3 | 0.1 | — | 8 KiB | **0.4 MiB** | 1.08× | 64 KiB | 21 KiB | 0.0255 ms |
| packed+block64 | deflate | 0.3 | 0.1 | — | — | **0.4 MiB** | 1.10× | 64 KiB | 21 KiB | 0.0408 ms |
| packed+block256 | deflate+dict | 0.3 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.17× | 64 KiB | 85 KiB | 0.0945 ms |
| packed+block64 | deflate+dict | 0.3 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.18× | 64 KiB | 21 KiB | 0.0366 ms |

#### `kaikki-es-en` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.3 | 0.1 | — | 8 KiB | **0.4 MiB** | 1.00× | 64 KiB | 60 KiB | 0.0529 ms |
| packed+block256 | deflate | 0.3 | 0.1 | — | — | **0.4 MiB** | 1.02× | 64 KiB | 60 KiB | 0.0879 ms |
| packed+block64 | zstd19 | 0.3 | 0.1 | — | 8 KiB | **0.4 MiB** | 1.10× | 64 KiB | 15 KiB | 0.0225 ms |
| packed+block64 | deflate | 0.3 | 0.1 | — | — | **0.4 MiB** | 1.11× | 64 KiB | 15 KiB | 0.0345 ms |
| packed+block256 | deflate+dict | 0.3 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.16× | 64 KiB | 60 KiB | 0.0818 ms |
| packed+block64 | deflate+dict | 0.3 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.16× | 64 KiB | 15 KiB | 0.0312 ms |

#### `kaikki-es-es` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.7 | 0.1 | — | 8 KiB | **0.8 MiB** | 1.00× | 64 KiB | 142 KiB | 0.1622 ms |
| packed+block256 | deflate | 0.7 | 0.1 | — | — | **0.8 MiB** | 1.07× | 64 KiB | 142 KiB | 0.2072 ms |
| packed+block64 | zstd19 | 0.7 | 0.1 | — | 8 KiB | **0.9 MiB** | 1.11× | 64 KiB | 36 KiB | 0.1202 ms |
| packed+block256 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.9 MiB** | 1.13× | 64 KiB | 142 KiB | 0.1916 ms |
| packed+block64 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.9 MiB** | 1.14× | 64 KiB | 36 KiB | 0.07 ms |
| packed+block64 | deflate | 0.8 | 0.1 | — | — | **0.9 MiB** | 1.14× | 64 KiB | 36 KiB | 0.0715 ms |

#### `kaikki-es-es` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.6 | 0.1 | — | 8 KiB | **0.8 MiB** | 1.00× | 64 KiB | 103 KiB | 0.1302 ms |
| packed+block256 | deflate | 0.7 | 0.1 | — | — | **0.8 MiB** | 1.06× | 64 KiB | 103 KiB | 0.1842 ms |
| packed+block256 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.8 MiB** | 1.11× | 64 KiB | 103 KiB | 0.312 ms |
| packed+block64 | zstd19 | 0.7 | 0.1 | — | 8 KiB | **0.8 MiB** | 1.11× | 64 KiB | 26 KiB | 0.046 ms |
| packed+block64 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.9 MiB** | 1.11× | 64 KiB | 26 KiB | 0.0625 ms |
| packed+block16 | deflate+dict | 0.7 | 0.1 | 64 KiB | — | **0.9 MiB** | 1.14× | 64 KiB | 6 KiB | 0.028 ms |

#### `jmdict-eng` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.00× | 64 KiB | 74 KiB | 0.0521 ms |
| packed+block256 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.01× | 64 KiB | 74 KiB | 0.0789 ms |
| packed+block64 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.06× | 64 KiB | 19 KiB | 0.027 ms |
| packed+block64 | zstd19 | 0.2 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.07× | 64 KiB | 19 KiB | 0.0183 ms |
| packed+block256 | deflate+dict | 0.2 | 0.1 | 64 KiB | — | **0.4 MiB** | 1.19× | 64 KiB | 74 KiB | 0.0731 ms |
| packed+block16 | deflate | 0.2 | 0.1 | — | — | **0.4 MiB** | 1.20× | 64 KiB | 5 KiB | 0.0105 ms |

#### `jmdict-eng` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | deflate | 0.1 | 0.1 | — | — | **0.3 MiB** | 1.00× | 64 KiB | 28 KiB | 0.0582 ms |
| packed+block256 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.01× | 64 KiB | 28 KiB | 0.0407 ms |
| packed+block64 | deflate | 0.1 | 0.1 | — | — | **0.3 MiB** | 1.05× | 64 KiB | 7 KiB | 0.0194 ms |
| packed+block64 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.3 MiB** | 1.07× | 64 KiB | 7 KiB | 0.015 ms |
| packed+block16 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.15× | 64 KiB | 2 KiB | 0.0089 ms |
| packed+block256 | deflate+dict | 0.1 | 0.1 | 64 KiB | — | **0.3 MiB** | 1.19× | 64 KiB | 28 KiB | 0.056 ms |

#### `freedict-eng-rus-tei` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.00× | 64 KiB | 52 KiB | 0.0356 ms |
| packed+block256 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.2 MiB** | 1.00× | 64 KiB | 52 KiB | 0.0268 ms |
| packed+block64 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.06× | 64 KiB | 13 KiB | 0.0128 ms |
| packed+block64 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.2 MiB** | 1.08× | 64 KiB | 13 KiB | 0.0105 ms |
| packed+block16 | deflate | 0.2 | 0.1 | — | — | **0.3 MiB** | 1.24× | 64 KiB | 3 KiB | 0.0074 ms |
| packed+block256 | deflate+dict | 0.1 | 0.1 | 64 KiB | — | **0.3 MiB** | 1.26× | 64 KiB | 52 KiB | 0.0335 ms |

#### `freedict-eng-rus-tei` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.00× | 64 KiB | 20 KiB | 0.0293 ms |
| packed+block256 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.2 MiB** | 1.02× | 64 KiB | 20 KiB | 0.0325 ms |
| packed+block64 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.05× | 64 KiB | 5 KiB | 0.0118 ms |
| packed+block64 | zstd19 | 0.1 | 0.1 | — | 8 KiB | **0.2 MiB** | 1.09× | 64 KiB | 5 KiB | 0.0091 ms |
| packed+block16 | deflate | 0.1 | 0.1 | — | — | **0.2 MiB** | 1.18× | 64 KiB | 1 KiB | 0.0068 ms |
| indexeddb(payload floor) | deflate+dict | 0.2 | 0.0 | 64 KiB | — | **0.2 MiB** | 1.21× | 1,024 KiB | 0 KiB | — ms |

#### `freedict-eng-rus-stardict` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19 | 0.4 | 0.1 | — | 8 KiB | **0.5 MiB** | 1.00× | 64 KiB | 89 KiB | 0.0967 ms |
| packed+block256 | deflate | 0.4 | 0.1 | — | — | **0.5 MiB** | 1.04× | 64 KiB | 89 KiB | 0.1315 ms |
| packed+block64 | zstd19 | 0.4 | 0.1 | — | 8 KiB | **0.6 MiB** | 1.10× | 64 KiB | 22 KiB | 0.0304 ms |
| packed+block64 | deflate | 0.5 | 0.1 | — | — | **0.6 MiB** | 1.12× | 64 KiB | 22 KiB | 0.0424 ms |
| packed+block256 | deflate+dict | 0.4 | 0.1 | 64 KiB | — | **0.6 MiB** | 1.13× | 64 KiB | 89 KiB | 0.1229 ms |
| packed+block64 | deflate+dict | 0.4 | 0.1 | 64 KiB | — | **0.6 MiB** | 1.15× | 64 KiB | 22 KiB | 0.0375 ms |
