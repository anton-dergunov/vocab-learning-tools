### Representation — is the mapper worth writing?

| Source | Entries | Source MiB | fields MiB | html MiB | html ÷ fields | Mapped | Invented | Unmapped POS kinds |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| `kaikki-es-es` | 838,769 | 94.7 | 229.3 | 168.2 | 0.73× | 95.3 % | — | 14 |

#### `kaikki-es-es` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19+dict | 16.0 | 18.7 | 64 KiB | 340 KiB | **35.1 MiB** | 1.00× | 64 KiB | 50 KiB | 0.2511 ms |
| packed+block256 | zstd19 | 18.0 | 18.7 | — | 8 KiB | **36.7 MiB** | 1.05× | 64 KiB | 50 KiB | 0.2388 ms |
| packed+block256 | deflate+dict | 18.4 | 18.7 | 64 KiB | — | **37.2 MiB** | 1.06× | 64 KiB | 50 KiB | 0.2517 ms |
| packed+block256 | deflate | 19.3 | 18.7 | — | — | **38.0 MiB** | 1.08× | 64 KiB | 50 KiB | 0.2502 ms |
| sqlite+block256 | deflate | 57.1 | 0.0 | — | 1,275 KiB | **58.3 MiB** | 1.66× | 2,048 KiB | 164 KiB | 0.1277 ms |

#### `kaikki-es-es` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19+dict | 13.7 | 19.6 | 64 KiB | 340 KiB | **33.7 MiB** | 1.00× | 64 KiB | 36 KiB | 0.2201 ms |
| packed+block256 | deflate+dict | 15.7 | 19.6 | 64 KiB | — | **35.4 MiB** | 1.05× | 64 KiB | 36 KiB | 0.2396 ms |
| packed+block256 | zstd19 | 15.8 | 19.6 | — | 8 KiB | **35.4 MiB** | 1.05× | 64 KiB | 36 KiB | 0.2116 ms |
| packed+block256 | deflate | 16.8 | 19.6 | — | — | **36.4 MiB** | 1.08× | 64 KiB | 36 KiB | 0.2319 ms |
| sqlite+block256 | deflate | 57.0 | 0.0 | — | 1,275 KiB | **58.3 MiB** | 1.73× | 2,048 KiB | 116 KiB | 0.1119 ms |
