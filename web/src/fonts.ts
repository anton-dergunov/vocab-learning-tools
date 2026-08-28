/* Self-hosted faces. Acervo is offline-first and self-hosted, so no webfont CDN is used.
   Only the subsets the vocabulary actually needs are imported — latin and latin-ext for Spanish
   and English, cyrillic for Russian glosses. Everything else (CJK in particular) falls back to
   the system faces named in the stylesheet, which is what the prototype already assumed. */

import "@fontsource/literata/latin-400.css";
import "@fontsource/literata/latin-600.css";
import "@fontsource/literata/latin-700.css";
import "@fontsource/literata/latin-400-italic.css";
import "@fontsource/literata/latin-600-italic.css";
import "@fontsource/literata/latin-ext-400.css";
import "@fontsource/literata/latin-ext-600.css";
import "@fontsource/literata/cyrillic-400.css";
import "@fontsource/literata/cyrillic-600.css";

import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-ext-400.css";
import "@fontsource/ibm-plex-sans/cyrillic-400.css";
import "@fontsource/ibm-plex-sans/cyrillic-500.css";

import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-mono/latin-600.css";
import "@fontsource/ibm-plex-mono/cyrillic-400.css";
