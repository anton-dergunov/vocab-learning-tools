/* Acervo — prototype fixture data.
   Shapes follow web/src/domain.ts so the mock-up can be wired to the real
   repository later without reshaping the view layer. Content is illustrative, except `la obra` and
   `animarse`, which are copied from a real account to judge the article redesign against.

   Three things here are ahead of the schema on purpose, for the article redesign spike:
   - a sense carries an `emoji`, and its `domain` is a one-word label for *every* sense rather than
     only for specialist ones;
   - a picture names the example it was drawn from as `anchor`, an index into `examples` (the
     application's `ImagePrompt.exampleId`); no anchor means it was drawn from the sense alone;
   - an example drawn from an attestation names it as `sourceAttestationId`, so the article can show
     that sentence once instead of twice.
   An example with a `clip` is a subtitle example: the sentence is the corpus's, the clip is where it
   was said. `approved` is gone from the picture because it carried no information. */

const LANGUAGES = [
  { code: "es",      flag: "\u{1F1EA}\u{1F1F8}", name: "Spanish",             definitionLang: "es", glossLangs: ["en"], notesLang: "en" },
  { code: "en",      flag: "\u{1F1EC}\u{1F1E7}", name: "English",             definitionLang: "en", glossLangs: ["ru"], notesLang: "ru" },
  { code: "zh-Hans", flag: "\u{1F1E8}\u{1F1F3}", name: "Chinese (Simplified)", definitionLang: "en", glossLangs: ["ru", "en"], notesLang: "ru" }
];

const TOPICS = [
  { key: "emotions",   name: "Emotions",   icon: "\u{1F4AD}" },
  { key: "actions",    name: "Actions",    icon: "⚡" },
  { key: "nature",     name: "Nature",     icon: "\u{1F33F}" },
  { key: "culture",    name: "Culture",    icon: "\u{1F3AD}" },
  { key: "food",       name: "Food",       icon: "\u{1F37D}️" },
  { key: "health",     name: "Health",     icon: "\u{1FA7A}" },
  { key: "appearance", name: "Appearance", icon: "\u{1F464}" },
  { key: "technology", name: "Technology", icon: "\u{1F4BB}" },
  { key: "travel",     name: "Travel",     icon: "\u{1F9ED}" },
  { key: "slang",      name: "Slang",      icon: "\u{1F4AC}" },
  { key: "social",     name: "Social",     icon: "\u{1F91D}" },
  { key: "places",     name: "Places",     icon: "\u{1F4CD}" },
  { key: "misc",       name: "Misc",       icon: "\u{1F4CC}" }
];

const LEXEMES = [
  {
    id: "k3m91xq7d0a2vbe", language: "es",
    headword: "picar", lemma: "picar", reading: null,
    pos: "verb", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F336}️", topics: ["food", "health", "actions"],
    status: "active", shortGloss: "to itch; to sting; to chop; to nibble",
    ipa: "/piˈkaɾ/",
    notes: [
      "One of the most overloaded verbs in everyday Spanish — the sense is almost always carried by the object, not the verb.",
      "In Mexico, <b>picar</b> for “to be spicy” is far more common than <i>ser picante</i>.",
      "<b>picar algo</b> before dinner is the standard way to say “have a nibble”; the noun <i>el picoteo</i> follows from it."
    ],
    createdAt: "2026-02-11", editedAt: "2026-08-24", revision: 7,
    senses: [
      {
        definition: "Producir una sensación de comezón o escozor en alguna parte del cuerpo.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to itch", "to feel prickly"] }],
        domain: "itch", emoji: "\u{1F927}",
        examples: [
          { text: "Me <b>pica</b> la nariz, creo que voy a estornudar.", translation: "My nose <b>itches</b>, I think I’m going to sneeze.",
            origin: "attestation", modelId: "gemini-3-flash", approved: true, audio: true },
          { text: "La lana de este jersey <b>pica</b> muchísimo.", translation: "The wool of this jumper <b>is</b> really <b>itchy</b>.",
            origin: "tatoeba", modelId: null, approved: true, audio: true },
          /* Deliberately too long for a phone card, so the one card that has to scroll can be seen
             scrolling on its own. */
          { text: "Cuando era pequeño y pasábamos los veranos en el pueblo de mis abuelos, la hierba seca del campo me <b>picaba</b> tanto en las piernas que volvía a casa rascándome sin parar, y mi abuela, sin decir nada, me ponía un poco de aceite de oliva y me mandaba a la cama.",
            translation: "When I was little and we spent the summers in my grandparents’ village, the dry grass in the fields <b>made</b> my legs <b>itch</b> so much that I came home scratching nonstop, and my grandmother, without a word, would rub a little olive oil on them and send me to bed.",
            origin: "llm", modelId: "gemini-3-flash", approved: true, audio: false }
        ],
        images: [{ src: "img/sense-a.webp", style: "flat-vector", prompt: "A hand hovering near an itchy nose, flat vector, bold shapes, limited palette, no text", anchor: 0 }]
      },
      {
        definition: "Dicho de un alimento: producir una sensación ardiente en la boca.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to be spicy", "to be hot"] }],
        domain: "spicy", emoji: "\u{1F336}️",
        examples: [
          { text: "¿Te <b>pica</b> mucho la salsa?", translation: "Is the sauce very <b>spicy</b> for you?",
            origin: "subtitle", modelId: "gemini-3.1-flash-lite", approved: true, audio: true,
            clip: { title: "Comiendo en un mercado de Ciudad de México 🌮🔥 #mexico #streetfood", channel: "Easy Spanish", at: "7:41" } }
        ],
        images: [{ src: "img/sense-d.webp", style: "storybook", prompt: "A chilli pepper glowing on a spoon of red sauce, soft storybook gouache, warm light, no text", anchor: 0 }]
      },
      {
        definition: "Cortar algo en trozos muy pequeños con un cuchillo.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to chop", "to mince", "to dice"] }],
        domain: "chop", emoji: "\u{1F52A}",
        examples: [
          { text: "<b>Pica</b> la cebolla bien fina antes de sofreírla.", translation: "<b>Chop</b> the onion very finely before frying it.",
            origin: "llm", modelId: "gemini-3-flash", approved: true, audio: false }
        ],
        images: []
      },
      {
        definition: "Comer una cantidad pequeña de algo, generalmente entre horas.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to nibble", "to snack"] }],
        domain: "snack", emoji: "\u{1F968}",
        examples: [
          { text: "Vamos a <b>picar</b> algo antes de cenar.", translation: "Let’s <b>have a nibble</b> before dinner.",
            origin: "llm", modelId: "gemini-3-flash", approved: false, audio: false, note: "Waiting for review — check whether “nibble” reads as too British." }
        ],
        images: []
      },
      {
        definition: "Dicho de un insecto o de un ave: morder o herir con el pico o el aguijón.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to bite", "to sting"] }],
        domain: "bite", emoji: "\u{1F99F}",
        examples: [
          { text: "Me <b>picaron</b> los mosquitos toda la noche.", translation: "The mosquitoes <b>bit</b> me all night.",
            origin: "tatoeba", modelId: null, approved: true, audio: true }
        ],
        images: []
      }
    ],
    attestations: [
      { text: "cuidado que esa salsa pica un monton eh", translation: null,
        sourceKind: "conversation", sourceTitle: "WhatsApp — grupo del curso", sourceUrl: null, capturedAt: "11 Feb 2026" },
      { text: "Se pican las verduras en dados de un centimetro y se reservan.", translation: "The vegetables are diced into one-centimetre cubes and set aside.",
        sourceKind: "web", sourceTitle: "Receta — pisto manchego, El Comidista", sourceUrl: "https://example.com/pisto", capturedAt: "3 Mar 2026",
        /* Photo capture (docs/plans/photo-capture.md) will keep the picture a sentence was read
           from. Drawn here only so the section is designed with room for one. */
        photo: "img/met-photo.jpg" }
    ],
    study: { system: "anki", reps: 21, lapses: 4, stability: 18.3, difficulty: 8.4, retrievability: 0.71, lastReview: "22 Aug 2026" }
  },

  /* ── copied from a real account, 15 Sep 2026 ── */
  {
    id: "3vu6u4sqccfs6fl", language: "es",
    headword: "la obra", lemma: "obra", reading: null,
    pos: "noun", gender: "feminine", register: "neutral", dialect: null,
    emoji: "\u{1F3AD}", topics: [],
    status: "inbox", shortGloss: "work; play; construction site",
    ipa: "/la ˈoβɾa/",
    notes: [
      "This word has a very broad meaning depending on the context. It can refer to a 'work of art' (una obra de arte), a 'theatrical play' (una obra de teatro), or physical construction work.",
      "When referring to construction, it often implies the physical site where building is happening, e.g., 'el arquitecto está en la obra'."
    ],
    createdAt: "2026-09-13", editedAt: "2026-09-13", revision: 660,
    imageModelId: "vertex_ai/gemini-3.1-flash-lite-image",
    senses: [
      {
        definition: "Cosa hecha o producida por un agente; especialmente una creación artística o literaria.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["work", "piece"] }],
        domain: "art", emoji: "\u{1F3A8}",
        examples: [
          { text: "A ella solo le queda la satisfacción de que vinieron a admirar su trabajo, sus no horas, no días, no semanas, sus años de trabajo invertidos en esta masiva <b>obra</b> de arte.",
            translation: "She only has the satisfaction that they came to admire her work, not her hours, not her days, not her weeks, but her years of work invested in this massive <b>work</b> of art.",
            origin: "subtitle", modelId: "gemini/gemini-3.1-flash-lite", audio: true,
            clip: { title: "En este pueblo humanos tienen prohibido vivir 🚫", channel: "Luisito Comunica", at: "19:39" } }
        ],
        /* Drawn from the sense alone, although the sense has a clip. */
        images: [{ src: "img/obra-art.webp", style: "oil-painting" }]
      },
      {
        definition: "Representación teatral de un texto dramático.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["play"] }],
        domain: "theater", emoji: "\u{1F3AD}",
        examples: [
          { text: "Nosotros veníamos con una <b>obra</b> que se llamaba Lado del amor, que la había ido muy bien, con una gira muy exitosa.",
            translation: "We were touring a <b>play</b> called Lado del amor, which had gone very well, with a very successful tour.",
            origin: "subtitle", modelId: "gemini/gemini-3.1-flash-lite", audio: true,
            clip: { title: "#ANTESQUENADIE | TERAPIA CON GABRIEL ROLÓN: PONER LÍMITES, AMOR ETERNO Y TOMAR DECISIONES", channel: "LUZU TV", at: "44:55" } }
        ],
        /* Drawn from the clip's sentence: a picture can belong to a clip. */
        images: [{ src: "img/obra-theater.webp", style: "baroque-chiaroscuro", anchor: 0 }]
      },
      {
        definition: "Conjunto de trabajos realizados para construir un edificio o una infraestructura.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["construction", "building site"] }],
        domain: "construction", emoji: "\u{1F3D7}️",
        examples: [],
        images: [{ src: "img/obra-construction.webp", style: "gouache-poster" }]
      }
    ],
    attestations: [],
    study: null
  },

  {
    id: "9tmbiepw0yjey3j", language: "es",
    headword: "animarse", lemma: "animarse", reading: null,
    pos: "verb", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F9D7}", topics: [],
    status: "inbox", shortGloss: "to dare; to be up for",
    ipa: "/a.niˈmaɾ.se/",
    notes: [
      "Used to express having the courage or the willingness to take on an activity, especially when it involves some risk, difficulty, or hesitation.",
      "Commonly followed by 'a' + infinitive."
    ],
    createdAt: "2026-09-13", editedAt: "2026-09-13", revision: 674,
    imageModelId: "vertex_ai/gemini-3.1-flash-lite-image",
    senses: [
      {
        definition: "Tener el valor o la disposición necesaria para hacer algo.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to dare", "to be up for", "to build up the courage"] }],
        /* Stored with no domain: the prompt reserves it for specialist words today. */
        domain: "courage", emoji: "\u{1F4AA}",
        examples: [
          { text: "¿Te <b>animás</b> a comer en una casa de desconocidos?", translation: "Do you <b>dare</b> to eat at a stranger's house?",
            origin: "attestation", sourceAttestationId: "2ct6z7ypkoucc0w", modelId: null, audio: true },
          { text: "y ella te lo supo demostrar acá, que esa motivación y el <b>animarse</b> a supuestamente a esa altura de su vida hizo que hoy esté, no sé, más inspirada y más fuerte.",
            translation: "And she knew how to show you here, that that motivation and <b>daring</b> to do so at that stage of her life meant that today she is, I don't know, more inspired and stronger.",
            origin: "subtitle", modelId: "gemini/gemini-3.1-flash-lite", audio: true,
            clip: { title: "#NADIEDICENADA | CONOCEMOS A MARTA, LA SEÑORA QUE ESTÁ POR CUMPLIR 101 AÑOS", channel: "LUZU TV", at: "27:14" } }
        ],
        images: [{ src: "img/animarse.webp", style: "anime-cel", anchor: 0 }]
      }
    ],
    attestations: [
      { id: "2ct6z7ypkoucc0w", text: "¿Te animás a comer en una casa de desconocidos?", translation: "Do you dare to eat at a stranger's house?",
        sourceKind: "unknown", sourceTitle: null, sourceUrl: null, capturedAt: "13 Sep 2026" }
    ],
    study: null
  },

  {
    id: "b7t42naz9c6uk1p", language: "es",
    headword: "desmayarse", lemma: "desmayarse", reading: null,
    pos: "verb", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F635}‍\u{1F4AB}", topics: ["health", "actions"],
    status: "active", shortGloss: null,
    ipa: "/desmaˈjaɾse/",
    notes: ["Always pronominal in this meaning. <i>Desmayar</i> without the pronoun is literary and means “to lose heart”."],
    createdAt: "2026-01-14", editedAt: "2026-06-02", revision: 3,
    senses: [
      {
        definition: "Perder el sentido y el conocimiento de forma temporal.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to faint", "to pass out"] }],
        domain: "faint", emoji: "\u{1F635}",
        examples: [
          { text: "Me <b>desmayé</b> cuando vi a la aterradora criatura.", translation: "I <b>fainted</b> when I saw the terrifying creature.",
            origin: "attestation", sourceAttestationId: "att-desmayarse", modelId: null, approved: true, audio: true },
          { text: "Se <b>desmayó</b> en pleno directo, delante de las cámaras.", translation: "She <b>passed out</b> live on air, in front of the cameras.",
            origin: "subtitle", modelId: null, approved: true, audio: true,
            clip: { title: "INFORME SEMANAL | Lo que pasó esta semana 📺", channel: "DW Español", at: "4:12" } }
        ],
        images: [{ src: "img/sense-c.webp", style: "retro-futurist", prompt: "A figure swooning backwards, stars circling, 1970s sci-fi paperback, muted print palette, no text", anchor: 1 }]
      },
      {
        definition: "Quedar sobrecogido por una emoción muy intensa.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to be overcome", "to swoon"] }],
        domain: "emotion", emoji: "\u{1F60D}",
        examples: [
          { text: "Casi me <b>desmayo</b> de la emoción.", translation: "I almost <b>swooned</b> with excitement.",
            origin: "tatoeba", modelId: null, approved: true, audio: false }
        ],
        images: []
      }
    ],
    attestations: [
      { id: "att-desmayarse", text: "Me desmaye cuando vi a la aterradora criatura", translation: null,
        sourceKind: "book", sourceTitle: "Cuentos de la selva — Horacio Quiroga", sourceUrl: null, capturedAt: "14 Jan 2026" }
    ],
    study: { system: "anki", reps: 14, lapses: 1, stability: 96.4, difficulty: 4.1, retrievability: 0.93, lastReview: "19 Aug 2026" }
  },

  {
    id: "q8v53mrb2e7wl4d", language: "es",
    headword: "la sobremesa", lemma: "sobremesa", reading: null,
    pos: "noun", gender: "feminine", register: "neutral", dialect: null,
    emoji: "☕", topics: ["culture", "food", "social"],
    status: "active", shortGloss: "the talk that keeps everyone at the table after a meal",
    ipa: "/soβɾeˈmesa/",
    notes: [
      "No English word covers it — this is the case where the Spanish definition does the work and the gloss cannot.",
      "Common collocations: <i>hacer sobremesa</i>, <i>una sobremesa larga</i>, <i>alargar la sobremesa</i>."
    ],
    createdAt: "2026-03-08", editedAt: "2026-03-08", revision: 1,
    senses: [
      {
        definition: "Tiempo que se está a la mesa después de haber comido, charlando con los demás comensales.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["after-dinner conversation", "lingering at the table"] }],
        domain: null,
        examples: [
          { text: "La comida duró una hora, pero la <b>sobremesa</b> se alargó hasta las seis.", translation: "Lunch lasted an hour, but the <b>sobremesa</b> stretched until six.",
            origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }
        ],
        images: [{ src: "img/sense-b.webp", style: "storybook", prompt: "Empty coffee cups and crumbs on a sunlit table, chairs pushed back, soft storybook gouache, no text" }]
      }
    ],
    attestations: [],
    study: { system: "anki", reps: 5, lapses: 0, stability: 12.9, difficulty: 5.2, retrievability: 0.88, lastReview: "16 Aug 2026" }
  },

  {
    id: "z1c64pdw8f3hj7s", language: "es",
    headword: "que se mejoren", lemma: "que se mejoren", reading: null,
    pos: "expression", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F496}", topics: ["health", "social"],
    status: "learned", shortGloss: "get better; feel better soon",
    ipa: "/ke se meˈxoɾen/",
    notes: ["Plural form; use <i>que te mejores</i> to one person you address informally."],
    createdAt: "2026-01-30", editedAt: "2026-05-19", revision: 2,
    senses: [
      {
        definition: "Fórmula para desear a alguien una pronta recuperación.",
        definitionLang: "es",
        glosses: [
          { lang: "en", terms: ["get better", "feel better soon"] },
          { lang: "ru", terms: ["выздоравливайте"] }
        ],
        domain: null,
        examples: [
          { text: "Espero <b>que se mejoren</b> pronto. Un abrazo a toda la familia.", translation: "I hope <b>you get better</b> soon. A hug to the whole family.",
            origin: "attestation", sourceAttestationId: "att-mejoren", modelId: "gemini-3-flash", approved: true, audio: true }
        ],
        images: []
      }
    ],
    attestations: [
      { id: "att-mejoren", text: "espero que se mejoren pronto un abrazo a toda la familia", translation: null,
        sourceKind: "conversation", sourceTitle: "WhatsApp — grupo del curso", sourceUrl: null, capturedAt: "30 Jan 2026" }
    ],
    study: { system: "anki", reps: 26, lapses: 0, stability: 402.7, difficulty: 2.8, retrievability: 0.97, lastReview: "2 Aug 2026" }
  },

  {
    id: "m5r18kts4b9gy2n", language: "es",
    headword: "el atasco", lemma: "atasco", reading: null,
    pos: "noun", gender: "masculine", register: "neutral", dialect: "es-ES",
    emoji: "\u{1F697}", topics: ["travel", "places"],
    status: "active", shortGloss: "traffic jam",
    ipa: "/aˈtasko/",
    notes: ["Peninsular. In Mexico you will hear <i>el embotellamiento</i> or <i>el tráfico</i>."],
    createdAt: "2026-02-02", editedAt: "2026-02-02", revision: 1,
    senses: [{
      definition: "Congestión de vehículos que impide circular con normalidad.",
      definitionLang: "es",
      glosses: [{ lang: "en", terms: ["traffic jam", "gridlock"] }],
      domain: null,
      examples: [{ text: "Ayer hubo un <b>atasco</b> tremendo en la M-30.", translation: "Yesterday there was a terrible <b>traffic jam</b> on the M-30.",
        origin: "manual", modelId: null, approved: true, audio: true }],
      images: []
    }],
    attestations: [],
    study: { system: "anki", reps: 9, lapses: 1, stability: 44.1, difficulty: 4.9, retrievability: 0.9, lastReview: "12 Aug 2026" }
  },

  {
    id: "w9h27fjc5d1qx8v", language: "es",
    headword: "currar", lemma: "currar", reading: null,
    pos: "verb", gender: null, register: "colloquial", dialect: "es-ES",
    emoji: "\u{1F477}", topics: ["slang", "actions"],
    status: "active", shortGloss: "to work; to graft",
    ipa: "/kuˈraɾ/",
    notes: ["Noun form <i>el curro</i> = the job. Both are everyday Peninsular colloquial, not rude."],
    createdAt: "2026-04-21", editedAt: "2026-04-21", revision: 1,
    senses: [{
      definition: "Trabajar, especialmente de forma dura o continuada.",
      definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to work", "to graft", "to slog"] }],
      domain: null,
      examples: [{ text: "Lleva <b>currando</b> desde las siete de la mañana.", translation: "He’s been <b>working</b> since seven in the morning.",
        origin: "subtitle", modelId: null, approved: true, audio: true, clip: { title: "Aquí la Tierra - 12/03/2026", channel: "RTVE", at: "12:03" } }],
      images: []
    }],
    attestations: [],
    study: { system: "anki", reps: 3, lapses: 2, stability: 4.2, difficulty: 9.1, retrievability: 0.44, lastReview: "26 Aug 2026" }
  },

  {
    id: "p2n85gvx7k4rt3c", language: "es",
    headword: "espolvorear", lemma: "espolvorear", reading: null,
    pos: "verb", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F9C2}", topics: ["food", "actions"],
    status: "inbox", shortGloss: "to sprinkle; to dust",
    ipa: "/espolβoɾeˈaɾ/",
    notes: [],
    createdAt: "2026-08-27", editedAt: "2026-08-27", revision: 0,
    senses: [{
      definition: "Esparcir sobre algo una materia hecha polvo.",
      definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to sprinkle", "to dust"] }],
      domain: "cooking",
      examples: [{ text: "<b>Espolvoreé</b> canela sobre el pastel.", translation: "I <b>sprinkled</b> cinnamon on the cake.",
        origin: "attestation", sourceAttestationId: "att-espolvorear", modelId: "gemini-3-flash", approved: false, audio: false }],
      images: []
    }],
    attestations: [{ id: "att-espolvorear", text: "Espolvoree canela sobre el pastel.", translation: "I sprinkled cinnamon on the cake.",
      sourceKind: "unknown", sourceTitle: null, sourceUrl: null, capturedAt: "27 Aug 2026" }],
    study: null
  },

  {
    id: "d4y96wlq1m8sz5b", language: "es",
    headword: "tirarse panza arriba", lemma: "tirarse panza arriba", reading: null,
    pos: "phrase", gender: null, register: "colloquial", dialect: null,
    emoji: "\u{1F3D6}️", topics: ["travel", "actions"],
    status: "active", shortGloss: "to sprawl out on your back",
    ipa: null,
    notes: [],
    createdAt: "2026-05-05", editedAt: "2026-05-05", revision: 1,
    senses: [{
      definition: "Tumbarse boca arriba de manera relajada, sin hacer nada.",
      definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to lie on one’s back", "to sprawl out"] }],
      domain: null,
      examples: [{ text: "Me gusta <b>tirarme panza arriba</b> en la playa.", translation: "I like to <b>lie on my back</b> at the beach.",
        origin: "manual", modelId: null, approved: true, audio: true }],
      images: []
    }],
    attestations: [],
    study: { system: "anki", reps: 7, lapses: 0, stability: 61.5, difficulty: 3.6, retrievability: 0.94, lastReview: "10 Aug 2026" }
  },

  {
    id: "f6k39xzb8n2ph7m", language: "es",
    headword: "la balsa", lemma: "balsa", reading: null,
    pos: "noun", gender: "feminine", register: "neutral", dialect: null,
    emoji: "\u{1F6F6}", topics: ["travel", "nature"],
    status: "active", shortGloss: "raft",
    ipa: "/ˈbalsa/",
    notes: [],
    createdAt: "2026-01-22", editedAt: "2026-01-22", revision: 1,
    senses: [
      { definition: "Embarcación plana formada por maderos unidos entre sí.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["raft"] }], domain: null,
        examples: [{ text: "Cruzaron el río en una <b>balsa</b> improvisada.", translation: "They crossed the river on a makeshift <b>raft</b>.",
          origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: [] },
      { definition: "Hueco del terreno que se llena de agua, natural o artificialmente.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["pond", "pool"] }], domain: null,
        examples: [{ text: "El agua de la <b>balsa</b> estaba completamente quieta.", translation: "The water of the <b>pond</b> was completely still.",
          origin: "tatoeba", modelId: null, approved: true, audio: false }], images: [] }
    ],
    attestations: [],
    study: { system: "anki", reps: 11, lapses: 0, stability: 74.2, difficulty: 3.9, retrievability: 0.95, lastReview: "8 Aug 2026" }
  },

  {
    id: "n7s24bqk6v9dm3t", language: "es",
    headword: "ponerse malo", lemma: "ponerse malo", reading: null,
    pos: "phrase", gender: null, register: "colloquial", dialect: "es-ES",
    emoji: "\u{1F912}", topics: ["health"],
    status: "active", shortGloss: "to get sick",
    ipa: null, notes: [],
    createdAt: "2026-02-18", editedAt: "2026-02-18", revision: 1,
    senses: [{
      definition: "Empezar a encontrarse mal de salud.",
      definitionLang: "es", glosses: [{ lang: "en", terms: ["to become ill", "to get sick"] }], domain: null,
      examples: [{ text: "Me he <b>puesto muy malo</b> después de cenar.", translation: "I’ve <b>become very ill</b> after dinner.",
        origin: "attestation", modelId: null, approved: true, audio: true }], images: []
    }],
    attestations: [], study: { system: "anki", reps: 12, lapses: 2, stability: 30.8, difficulty: 6.4, retrievability: 0.83, lastReview: "20 Aug 2026" }
  },

  {
    id: "v8j51ctr3x7bn6q", language: "es",
    headword: "el tobillo", lemma: "tobillo", reading: null,
    pos: "noun", gender: "masculine", register: "neutral", dialect: null,
    emoji: "\u{1F9B5}", topics: ["health", "appearance"],
    status: "learned", shortGloss: "ankle",
    ipa: "/toˈβiʊo/", notes: [],
    createdAt: "2026-01-19", editedAt: "2026-01-19", revision: 1,
    senses: [{
      definition: "Parte del cuerpo donde se une el pie con la pierna.",
      definitionLang: "es", glosses: [{ lang: "en", terms: ["ankle"] }], domain: "medicine",
      examples: [{ text: "Me torcí el <b>tobillo</b> bajando las escaleras.", translation: "I twisted my <b>ankle</b> going down the stairs.",
        origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: []
    }],
    attestations: [], study: { system: "anki", reps: 19, lapses: 0, stability: 388.1, difficulty: 2.4, retrievability: 0.98, lastReview: "1 Jul 2026" }
  },

  {
    id: "g3q76mwd9j5fk1z", language: "es",
    headword: "la azafata", lemma: "azafata", reading: null,
    pos: "noun", gender: "feminine", register: "neutral", dialect: null,
    emoji: "\u{1F469}‍✈️", topics: ["travel", "social"],
    status: "active", shortGloss: "flight attendant",
    ipa: "/aθaˈfata/", notes: ["Masculine counterpart: <i>el auxiliar de vuelo</i>."],
    createdAt: "2026-03-30", editedAt: "2026-03-30", revision: 1,
    senses: [{
      definition: "Persona encargada de atender a los pasajeros a bordo de un avión.",
      definitionLang: "es", glosses: [{ lang: "en", terms: ["flight attendant", "stewardess"] }], domain: null,
      examples: [{ text: "La <b>azafata</b> nos pidió abrocharnos el cinturón.", translation: "The <b>flight attendant</b> asked us to fasten our seatbelts.",
        origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: []
    }],
    attestations: [], study: { system: "anki", reps: 6, lapses: 1, stability: 21.6, difficulty: 5.8, retrievability: 0.86, lastReview: "18 Aug 2026" }
  },

  {
    id: "h2l83nfy7c4vs9r", language: "en",
    headword: "turmoil", lemma: "turmoil", reading: null,
    pos: "noun", gender: null, register: "formal", dialect: null,
    emoji: "\u{1F32A}️", topics: ["emotions", "misc"],
    status: "active", shortGloss: "суматоха; смятение",
    ipa: "/ˈtɜːmɔɪl/",
    notes: ["Mass noun — no plural. Usually <i>in turmoil</i>, rarely <i>a turmoil</i>."],
    createdAt: "2026-02-25", editedAt: "2026-07-14", revision: 4,
    senses: [{
      definition: "A state of great confusion, disturbance or uncertainty.",
      definitionLang: "en",
      glosses: [{ lang: "ru", terms: ["суматоха", "смятение", "потрясения"] }],
      domain: null,
      examples: [
        { text: "The country was in <b>turmoil</b> for weeks after the vote.", translation: "Страна несколько недель находилась в <b>смятении</b> после голосования.",
          origin: "attestation", modelId: "gemini-3-flash", approved: true, audio: true },
        { text: "Her mind was in <b>turmoil</b> and she could not sleep.", translation: "В её голове царила <b>суматоха</b>, и она не могла заснуть.",
          origin: "wiktionary", modelId: null, approved: true, audio: false }
      ],
      images: []
    }],
    attestations: [{ text: "Markets remained in turmoil as the deadline passed without an agreement.", translation: null,
      sourceKind: "web", sourceTitle: "Reuters — markets live blog", sourceUrl: "https://example.com/markets", capturedAt: "25 Feb 2026" }],
    study: { system: "anki", reps: 8, lapses: 1, stability: 33.4, difficulty: 5.5, retrievability: 0.89, lastReview: "21 Aug 2026" }
  },

  {
    id: "c9d47ztk2h6mp8w", language: "en",
    headword: "hoax", lemma: "hoax", reading: null,
    pos: "noun", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F3AD}", topics: ["culture", "misc"],
    status: "active", shortGloss: "мистификация; розыгрыш",
    ipa: "/həʊks/", notes: [],
    createdAt: "2026-04-02", editedAt: "2026-04-02", revision: 1,
    senses: [{
      definition: "A deliberate deception intended to make people believe something untrue.",
      definitionLang: "en",
      glosses: [{ lang: "ru", terms: ["мистификация", "розыгрыш", "обман"] }],
      domain: null,
      examples: [{ text: "The photograph turned out to be an elaborate <b>hoax</b>.", translation: "Фотография оказалась тщательно подготовленной <b>мистификацией</b>.",
        origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: []
    }],
    attestations: [], study: { system: "anki", reps: 4, lapses: 0, stability: 17.2, difficulty: 4.4, retrievability: 0.91, lastReview: "23 Aug 2026" }
  },

  {
    id: "t5b62vqj9n3xw7f", language: "zh-Hans",
    headword: "图书馆", lemma: "图书馆", reading: "tú shū guǎn",
    pos: "noun", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F4DA}", topics: ["places", "culture"],
    status: "active", shortGloss: "библиотека; library",
    ipa: null,
    notes: ["图 (picture) + 书 (book) + 馆 (public building) — the third character recurs in 博物馆 and 体育馆."],
    createdAt: "2026-06-11", editedAt: "2026-06-11", revision: 1,
    senses: [{
      definition: "A building where books are kept and may be borrowed.",
      definitionLang: "en",
      glosses: [
        { lang: "ru", terms: ["библиотека"] },
        { lang: "en", terms: ["library"] }
      ],
      domain: null,
      examples: [{ text: "我在<b>图书馆</b>学习了一下午。", translation: "I studied at the <b>library</b> all afternoon.",
        origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: []
    }],
    attestations: [], study: null
  }
];

/* External dictionaries — what a search finds that is NOT yours (design §08, Stage 3).
   Never mixed into LEXEMES: an external entry has no id, no study state and no owner, and the
   whole point of the section below the rule is that the difference is visible. */
const EXTERNAL = [
  {
    word: "picadura", gloss: "Mordedura o herida hecha por un insecto.", origin: "device",
    sources: [{ id: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device" },
              { id: "wikdict-es-en", name: "WikDict (es→en)", origin: "device" }],
    ipa: "[pikaˈðuɾa]", posLabel: "noun",
    sections: [
      { id: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device", tier: "fields",
        attribution: "Wiktionary contributors, via kaikki.org. CC BY-SA 4.0.", licence: "CC BY-SA 4.0",
        senses: [
          { definition: "Mordedura o herida hecha por un insecto.",
            examples: [{ text: "Una picadura de mosquito.", translation: "A mosquito bite." }] },
          { definition: "Acción y efecto de picar tabaco." }
        ] },
      { id: "wikdict-es-en", name: "WikDict (es→en)", origin: "device", tier: "html",
        attribution: "WikDict, derived from DBnary/Wiktionary. CC BY-SA 4.0.", licence: "CC BY-SA 4.0",
        html: '<p class="ext-gram">noun</p><ol class="ext-senses">'
            + '<li>Mordedura de un insecto.<p class="ext-tr">bite</p></li>'
            + '<li>Tabaco picado.<p class="ext-tr">shredded tobacco</p></li></ol>' }
    ]
  },
  {
    word: "picante", gloss: "Que pica al paladar.", origin: "device",
    sources: [{ id: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device" }],
    posLabel: "adjective",
    sections: [
      { id: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device", tier: "fields",
        attribution: "Wiktionary contributors, via kaikki.org. CC BY-SA 4.0.", licence: "CC BY-SA 4.0",
        senses: [{ definition: "Que pica al paladar." }] }
    ]
  },
  {
    word: "picotear", gloss: "to peck; to nibble", origin: "online",
    sources: [{ id: "freedictionaryapi", name: "Free Dictionary API", origin: "online" }],
    posLabel: "verb", online: true,
    sections: [
      { id: "freedictionaryapi", name: "Free Dictionary API", origin: "online", tier: "fields",
        attribution: "freedictionaryapi.com, Wiktionary-derived. CC BY-SA 4.0.", licence: "CC BY-SA 4.0",
        senses: [{ definition: "to peck (of a bird)" }, { definition: "to nibble; to snack" }] }
    ]
  }
];
