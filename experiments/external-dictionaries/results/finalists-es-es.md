### Representation — is the mapper worth writing?

| Source | Entries | Source MiB | fields MiB | html MiB | html ÷ fields | Mapped | Invented | Unmapped POS kinds |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| `kaikki-es-es` | 838,769 | 94.7 | 251.7 | 168.2 | 0.67× | 99.5 % | — | 14 |

#### `kaikki-es-es` · `fields` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19+dict | 16.6 | 19.5 | 64 KiB | 340 KiB | **36.5 MiB** | 1.00× | 64 KiB | 65 KiB | 0.2339 ms |
| packed+block256 | zstd19 | 18.7 | 19.5 | — | 8 KiB | **38.2 MiB** | 1.05× | 64 KiB | 65 KiB | 0.2251 ms |
| packed+block256 | deflate+dict | 19.1 | 19.5 | 64 KiB | — | **38.7 MiB** | 1.06× | 64 KiB | 65 KiB | 0.294 ms |
| packed+block256 | deflate | 20.2 | 19.5 | — | — | **39.7 MiB** | 1.09× | 64 KiB | 65 KiB | 4.9451 ms |
| sqlite+block256 | deflate | 59.6 | 0.0 | — | 1,275 KiB | **60.9 MiB** | 1.67× | 2,048 KiB | 169 KiB | 0.1233 ms |

#### `kaikki-es-es` · `html` payload

| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19+dict | 13.7 | 19.6 | 64 KiB | 340 KiB | **33.7 MiB** | 1.00× | 64 KiB | 36 KiB | 0.2302 ms |
| packed+block256 | deflate+dict | 15.7 | 19.6 | 64 KiB | — | **35.4 MiB** | 1.05× | 64 KiB | 36 KiB | 0.2377 ms |
| packed+block256 | zstd19 | 15.8 | 19.6 | — | 8 KiB | **35.4 MiB** | 1.05× | 64 KiB | 36 KiB | 0.2109 ms |
| packed+block256 | deflate | 16.8 | 19.6 | — | — | **36.4 MiB** | 1.08× | 64 KiB | 36 KiB | 0.248 ms |
| sqlite+block256 | deflate | 57.0 | 0.0 | — | 1,275 KiB | **58.3 MiB** | 1.73× | 2,048 KiB | 116 KiB | 0.127 ms |
