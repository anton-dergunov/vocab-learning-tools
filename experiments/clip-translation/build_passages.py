"""One-shot author's tool: writes passages.json with the clause partition checked.

Kept in the directory because the partition rule — the clause texts must concatenate back to the
source exactly — is only enforceable where the clauses are written.
"""
import json
from pathlib import Path

# The three passages that are literally in Acervo's own recorded corpus response. Their provenance
# is read back from it rather than retyped, so a row can never claim a channel the corpus did not
# give it.
FIXTURE = Path(__file__).resolve().parents[2] / "tests/unit/clips/fixtures/search-es-picar.json"
RECORDED = {
    r["segment_id"]: r for r in json.loads(FIXTURE.read_text(encoding="utf-8"))["results"]
}

P = []


def _dense(text: str) -> bool:
    """True for Han, Kana or Hangul — the scripts that put a word in one or two characters."""
    return any(
        "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff" or "\uac00" <= c <= "\ud7af"
        for c in text
    )

def passage(**kw):
    kw.setdefault("selfContainedRuleRejects", False)
    src = "".join(c["src"] for c in kw["clauses"])
    assert src == kw["sentence"], (
        f"{kw['id']}: clauses do not reconstruct the source\n  {src!r}\n  {kw['sentence']!r}")
    for c in kw["clauses"]:
        for lang, anchors in c["any"].items():
            assert lang in kw["targets"], f"{kw['id']}: anchors for untargeted {lang}"
            for a in anchors:
                # Three characters is the floor for a script that delimits words, because anchors
                # are matched as stems (word-start bounded, suffix allowed) and a two-letter stem
                # would hit half the language. A dense script carries a word in one or two
                # characters, so the same floor there would forbid every honest anchor. A numeral
                # is exact rather than a stem, so it needs no room either.
                floor = 1 if (_dense(a) or a.isdigit()) else 3
                assert len(a) >= floor, f"{kw['id']}: anchor {a!r} is too short to be safe"
    for lang in kw["targets"]:
        for c in kw["clauses"]:
            assert lang in c["any"], f"{kw['id']}: clause {c['src']!r} has no {lang} anchors"
    recorded = RECORDED.get(kw["provenance"]["segmentId"])
    if recorded:
        assert recorded["sentence"] == kw["sentence"], f"{kw['id']}: not the recorded sentence"
        assert recorded["matched_surface"] == kw["matchedForm"], f"{kw['id']}: not the recorded form"
        video = recorded["video"]
        kw["provenance"] = {
            "segmentId": recorded["segment_id"], "channel": video["channel"],
            "videoTitle": video["title"], "videoUrl": video["url"],
            "speechStyle": list(video.get("speech_style") or []),
            "variety": list(video.get("varieties") or []),
            "captionKind": video.get("caption_kind") or recorded.get("caption_kind") or "automatic",
            "boundary": recorded["boundary"]["reason"],
            "clipStart": recorded["clip_start"], "clipEnd": recorded["clip_end"],
            "source": "corpus fixture",
        }
    else:
        kw["provenance"].setdefault("videoUrl", "https://www.youtube.com/watch?v=00000000000")
        kw["provenance"].setdefault("clipStart", 0.0)
        kw["provenance"].setdefault("clipEnd", 12.0)
        kw["provenance"]["source"] = "authored"
    P.append(kw)


passage(
    id="castillo-picar", real=True, expect="usable",
    note="The observed regression, and the passage this prompt quotes as a good candidate.",
    brokenness=["cut-open", "cut-close", "multi-sentence", "repetition"],
    sourceLang="es", targets=["en", "zh"],
    headword="picar", lemma="picar", pos="verb", shortGloss="to itch; to chop",
    matchedForm="picaba",
    sense={"definition": "Causar picor o comezón.", "definitionLang": "es",
           "glosses": [{"lang": "en", "terms": ["to itch"]}]},
    decoySense={"definition": "Cortar en trozos muy pequeños.", "definitionLang": "es",
                "glosses": [{"lang": "en", "terms": ["to chop"]}]},
    provenance={"segmentId": "seg_c9a1f0e7d2b48a153c66", "channel": "Spanish After Hours",
                "videoTitle": "a cozy podcast about work | spanish after hours",
                "speechStyle": ["podcast", "conversation"], "variety": ["España"],
                "captionKind": "automatic", "boundary": "cut"},
    sentence="era un castillo un poco pijo, pero sí, trabajaba de camarera en un castillo que "
             "celebraba bodas. Y en el castillo nos daban un traje que picaba mucho, picaba mucho "
             "y era de color gris con",
    clauses=[
        {"src": "era un castillo ",
         "any": {"en": ["castle"], "zh": ["城堡"]}},
        {"src": "un poco pijo, ",
         "any": {"en": ["posh", "fancy", "snooty", "upmarket", "swanky", "chic", "classy",
                        "pretentious", "poncy", "high-end", "up itself"],
                 # `有点装` and `拽` were added during the pilot: a model wrote 有点装的城堡,
                 # which conveys the clause perfectly and the first list did not cover. Corrected
                 # before the measured run, and applied to both arms.
                 "zh": ["高档", "讲究", "时髦", "阔气", "豪华", "浮夸", "装腔", "有点装", "装的",
                        "拽", "派头", "排场", "高级", "资产阶级", "气派", "贵气", "上档次",
                        "上流", "势利", "小资"]}},
        {"src": "pero sí, ",
         "any": {"en": ["but yes", "but yeah", "yeah", "well yes", "but it"],
                 "zh": ["但是", "不过", "是的", "对啊", "但确实", "确实", "但", "可是"]}},
        {"src": "trabajaba de camarera ",
         "any": {"en": ["waitress", "waiting tables", "waited tables", "served tables", "waiter"],
                 "zh": ["服务员", "服务生", "女侍", "侍应", "当服务"]}},
        {"src": "en un castillo que celebraba bodas. ",
         "any": {"en": ["wedding"], "zh": ["婚礼", "婚宴"]}},
        {"src": "Y en el castillo nos daban un traje ",
         "any": {"en": ["outfit", "suit", "uniform", "costume", "get-up", "dress"],
                 "zh": ["衣服", "制服", "套装", "服装"]}},
        {"src": "que picaba mucho, ",
         "any": {"en": ["itch", "scratchy", "prickly"], "zh": ["痒", "扎", "刺"]}},
        {"src": "picaba mucho ",
         "any": {"en": ["itch", "scratchy", "prickly"], "zh": ["痒", "扎", "刺"]}},
        {"src": "y era de color gris con",
         "any": {"en": ["gray", "grey"], "zh": ["灰"]}},
    ],
)

passage(
    id="ella-picar", real=True, expect="usable",
    note="The control: short, one sentence, ends in punctuation. Coverage below 1.0 here means the "
         "metric is broken, not the model. Real corpus segment.",
    brokenness=["clean"],
    sourceLang="es", targets=["en"],
    headword="picar", lemma="picar", pos="verb", shortGloss="to itch; to chop",
    matchedForm="picar",
    sense={"definition": "Causar picor o comezón.", "definitionLang": "es",
           "glosses": [{"lang": "en", "terms": ["to itch"]}]},
    decoySense={"definition": "Cortar en trozos muy pequeños.", "definitionLang": "es",
                "glosses": [{"lang": "en", "terms": ["to chop"]}]},
    provenance={"segmentId": "seg_fafe38592cc31df5c430", "channel": "Dreaming Spanish",
                "videoTitle": "superbeginner: el picor",
                "speechStyle": ["lesson"], "variety": ["España"],
                "captionKind": "automatic", "boundary": "sentence"},
    sentence="Y ella ya le va a empezar a picar porque es raro, chicos.",
    clauses=[
        {"src": "Y ella ya le va a empezar a picar ", "any": {"en": ["itch"]}},
        {"src": "porque es raro, ", "any": {"en": ["odd", "weird", "strange", "unusual"]}},
        {"src": "chicos.", "any": {"en": ["guys", "folks", "kids", "lads", "boys", "everyone"]}},
    ],
)

passage(
    id="pistachos-picar", real=True, expect="usable",
    note="Nine short sentences, cut mid-sentence at the end. The shape most likely to be summarised. "
         "Real corpus segment.",
    brokenness=["multi-sentence", "cut-close", "list"],
    sourceLang="es", targets=["en"],
    headword="picar", lemma="picar", pos="verb", shortGloss="to snack; to itch",
    matchedForm="picar",
    sense={"definition": "Tomar una pequeña cantidad de comida, normalmente entre horas.",
           "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["to snack", "to nibble"]}]},
    decoySense={"definition": "Causar picor o comezón.", "definitionLang": "es",
                "glosses": [{"lang": "en", "terms": ["to itch"]}]},
    provenance={"segmentId": "seg_4270b0b102db1a08454c", "channel": "Español con Juan",
                "videoTitle": "un día conmigo en casa",
                "speechStyle": ["vlog", "monologue"], "variety": ["España"],
                "captionKind": "automatic", "boundary": "cut"},
    sentence="Tengo mucha sed. Quiero beber agua. A ver. Necesito mi botella. Aquí mi botella de "
             "agua. Me voy a llevar algo para picar, algo para comer. ¿Qué me puedo llevar? Tengo "
             "unos pistachos. Los voy a meter",
    clauses=[
        {"src": "Tengo mucha sed. ", "any": {"en": ["thirsty", "thirst"]}},
        {"src": "Quiero beber agua. ", "any": {"en": ["drink", "water"]}},
        {"src": "A ver. ", "any": {"en": ["let's see", "let me see", "right", "okay", "now then",
                                          "hmm", "well"]}},
        {"src": "Necesito mi botella. ", "any": {"en": ["need"]}},
        {"src": "Aquí mi botella de agua. ", "any": {"en": ["here"]}},
        {"src": "Me voy a llevar algo para picar, ",
         "any": {"en": ["snack", "nibble", "pick at", "munch", "something to eat"]}},
        {"src": "algo para comer. ", "any": {"en": ["eat", "food"]}},
        {"src": "¿Qué me puedo llevar? ", "any": {"en": ["what can i", "what should i", "take",
                                                         "bring"]}},
        {"src": "Tengo unos pistachos. ", "any": {"en": ["pistachio"]}},
        {"src": "Los voy a meter", "any": {"en": ["put", "pack", "stick", "throw", "pop"]}},
    ],
)

passage(
    id="empatia-picar", real=True, expect="usable",
    note="Run-on with a false start ('una un poco'), cut at both ends. Real corpus segment.",
    brokenness=["cut-open", "cut-close", "false-start", "run-on"],
    sourceLang="es", targets=["en", "ru"],
    headword="picar", lemma="picar", pos="verb", shortGloss="to snack; to itch",
    matchedForm="picar",
    sense={"definition": "Tomar una pequeña cantidad de comida, normalmente entre horas.",
           "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["to snack", "to nibble"]}]},
    decoySense={"definition": "Causar picor o comezón.", "definitionLang": "es",
                "glosses": [{"lang": "en", "terms": ["to itch"]}]},
    provenance={"segmentId": "seg_9f7fdafc6b0056a5a545", "channel": "Easy Spanish",
                "videoTitle": "vivir con compañeros de piso",
                "speechStyle": ["interview", "conversation"], "variety": ["España"],
                "captionKind": "automatic", "boundary": "cut"},
    sentence="Que tengas al final una un poco de empatía, que si necesitas cualquier cosa, aunque "
             "sea azúcar, que es algo que parece una tontería, pero es muy real y que puedas picar",
    clauses=[
        {"src": "Que tengas al final una un poco de empatía, ",
         "any": {"en": ["empathy", "empathetic"], "ru": ["эмпат", "сочувств", "понима"]}},
        {"src": "que si necesitas cualquier cosa, ",
         "any": {"en": ["need", "anything"], "ru": ["нужн", "надо", "понадоб"]}},
        {"src": "aunque sea azúcar, ",
         "any": {"en": ["sugar"], "ru": ["сахар"]}},
        {"src": "que es algo que parece una tontería, ",
         "any": {"en": ["silly", "trivial", "nonsense", "stupid", "daft", "nothing", "small thing",
                        "foolish", "silly thing", "insignificant"],
                 "ru": ["глуп", "ерунд", "мелоч", "пустяк", "несерьёз", "несерьез", "чепух"]}},
        {"src": "pero es muy real ",
         "any": {"en": ["real"], "ru": ["реальн", "всерьёз", "самом деле", "правда"]}},
        {"src": "y que puedas picar",
         "any": {"en": ["snack", "nibble", "pick", "bite"],
                 "ru": ["перекус", "пожева", "поесть", "перехват"]}},
    ],
)

passage(
    id="puertita-quedar", real=True, expect="usable", selfContainedRuleRejects=True,
    note="Quoted speech and a numeral. The prompt quotes this one as a passage to refuse — but it "
         "does so inside the `selfContainedOnly` section, which ships OFF, so under the shipped "
         "configuration picking it is not a failure. Its pick rate is reported as a diagnostic of "
         "that rule rather than scored as a wrong answer, and it is translated like any other row.",
    brokenness=["cut-open", "quoted-speech", "numeral", "unrecoverable-subject"],
    sourceLang="es", targets=["en"],
    headword="quedar", lemma="quedar", pos="verb", shortGloss="to stay; to remain",
    matchedForm="quedar",
    sense={"definition": "Permanecer en un lugar durante cierto tiempo.", "definitionLang": "es",
           "glosses": [{"lang": "en", "terms": ["to stay"]}]},
    decoySense={"definition": "Concertar una cita con alguien.", "definitionLang": "es",
                "glosses": [{"lang": "en", "terms": ["to arrange to meet"]}]},
    provenance={"segmentId": "seg_1d7c4b9ae0f35271ab84", "channel": "Hablando Claro",
                "videoTitle": "la peor noche de mi vida | hablando claro",
                "speechStyle": ["streaming", "conversation"], "variety": ["Argentina"],
                "captionKind": "automatic", "boundary": "cut"},
    sentence="enfermedades posibles, literal, la puertita, estaba así el flaco y me dice, «Usted, "
             "este tipo se tiene que quedar acá 48 horas mínimo en reposo.»",
    clauses=[
        {"src": "enfermedades posibles, ", "any": {"en": ["illness", "disease", "sickness"]}},
        {"src": "literal, ", "any": {"en": ["literal"]}},
        {"src": "la puertita, ", "any": {"en": ["door"]}},
        {"src": "estaba así el flaco y me dice, ",
         "any": {"en": ["says", "said", "tells", "told", "goes"]}},
        {"src": "«Usted, ", "any": {"en": ["you", "sir"]}},
        {"src": "este tipo se tiene que quedar acá ", "any": {"en": ["stay", "remain"]}},
        {"src": "48 horas mínimo ", "any": {"en": ["48"]}},
        {"src": "en reposo.»", "any": {"en": ["rest"]}},
    ],
)

passage(
    id="rabia-disfluency", real=False, expect="usable",
    note="Authored. Fillers and a self-correction, which the prompt forbids tidying away.",
    brokenness=["false-start", "filler", "cut-close"],
    sourceLang="es", targets=["en"],
    headword="rabia", lemma="rabia", pos="noun", shortGloss="anger; rage",
    matchedForm="rabia",
    sense={"definition": "Enfado muy grande.", "definitionLang": "es",
           "glosses": [{"lang": "en", "terms": ["anger", "rage"]}]},
    decoySense={"definition": "Enfermedad vírica que transmiten algunos animales.",
                "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["rabies"]}]},
    provenance={"segmentId": "seg_57b2ee3140c9a8f60d12", "channel": "Charlas de Café",
                "videoTitle": "cosas que nadie te cuenta de mudarte",
                "speechStyle": ["podcast", "conversation"], "variety": ["España"],
                "captionKind": "automatic", "boundary": "cut"},
    sentence="o sea, yo no, no es que me moleste, ¿sabes? pero cuando llegas y ves que la gente, "
             "bueno, que la gente ni te mira, pues te da un poco de rabia, la verdad",
    clauses=[
        {"src": "o sea, yo no, no es que me moleste, ",
         "any": {"en": ["bother", "mind", "annoy", "not that it"]}},
        {"src": "¿sabes? ", "any": {"en": ["you know", "know what i mean", "right?"]}},
        {"src": "pero cuando llegas ",
         "any": {"en": ["arrive", "get there", "turn up", "show up", "you come"]}},
        {"src": "y ves que la gente, bueno, que la gente ni te mira, ",
         "any": {"en": ["look at", "looks at", "even look", "acknowledge"]}},
        {"src": "pues te da un poco de rabia, ",
         "any": {"en": ["angry", "anger", "rage", "annoyed", "irritat", "mad", "wind you up",
                        "pisses"]}},
        {"src": "la verdad", "any": {"en": ["honest", "truth", "really", "to be fair"]}},
    ],
)

passage(
    id="cansada-turnos", real=False, expect="usable",
    note="Authored. Two speakers and an interruption; the repetition of 'loca' is the test that a "
         "reply cannot satisfy two clauses with one word.",
    brokenness=["two-speakers", "repetition", "cut-open"],
    sourceLang="es", targets=["en"],
    headword="cansado", lemma="cansado", pos="adjective", shortGloss="tired",
    matchedForm="cansada",
    sense={"definition": "Que siente cansancio o falta de fuerzas.", "definitionLang": "es",
           "glosses": [{"lang": "en", "terms": ["tired"]}]},
    decoySense={"definition": "Que resulta pesado o molesto de tan repetido.",
                "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["tiresome"]}]},
    provenance={"segmentId": "seg_3ac81f95d7e0b64c2201", "channel": "Radio Ambulante",
                "videoTitle": "la decisión | radio ambulante",
                "speechStyle": ["documentary", "conversation"], "variety": ["Argentina"],
                "captionKind": "authored", "boundary": "cut"},
    sentence="y entonces le dije que no pensaba volver, ¿pero tú estás loca?, no, loca no, "
             "cansada, que no es lo mismo",
    clauses=[
        {"src": "y entonces le dije que no pensaba volver, ",
         "any": {"en": ["go back", "come back", "coming back", "going back", "return", "be back"]}},
        {"src": "¿pero tú estás loca?, ", "any": {"en": ["crazy", "mad", "insane", "nuts", "out of "
                                                         "your mind"]}},
        {"src": "no, loca no, ", "any": {"en": ["crazy", "mad", "insane", "nuts"]}},
        {"src": "cansada, ", "any": {"en": ["tired", "exhausted", "worn out", "knackered"]}},
        {"src": "que no es lo mismo", "any": {"en": ["same", "different"]}},
    ],
)

passage(
    id="acostumbrarse-larga", real=False, expect="usable",
    # The Japanese anchors for 'bueno, lo que pasa es que', 'el primer mes' and 'hasta que se me
    # pasaba' were widened during the pilot: models wrote 何というか, 最初の月 and 収まる/気がまぎれる,
    # all of which carry the clause and none of which the first list covered. False negatives only,
    # corrected before the measured run and applied to both arms.
    note="Authored. Seventy words over ten clauses — the most power for the length metric and the "
         "worst case for quiet truncation.",
    brokenness=["long", "run-on", "cut-open", "multi-clause"],
    sourceLang="es", targets=["en", "ja"],
    headword="acostumbrarse", lemma="acostumbrarse", pos="verb", shortGloss="to get used to",
    matchedForm="acostumbré",
    sense={"definition": "Adquirir costumbre de algo, llegar a hacerlo con naturalidad.",
           "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["to get used to"]}]},
    decoySense={"definition": "Hacer que alguien adquiera una costumbre.", "definitionLang": "es",
                "glosses": [{"lang": "en", "terms": ["to accustom someone"]}]},
    provenance={"segmentId": "seg_82f0c6d413ba9e57f0aa", "channel": "Entiende Tu Mente",
                "videoTitle": "empezar de cero en una ciudad nueva",
                "speechStyle": ["podcast", "monologue"], "variety": ["España"],
                "captionKind": "automatic", "boundary": "cut"},
    sentence="bueno, lo que pasa es que yo llegué a Madrid sin conocer a nadie, ni un alma, y el "
             "primer mes fue durísimo, porque además llovía todos los días, y yo salía del trabajo "
             "a las nueve y no tenía a quién llamar, entonces me acostumbré a caminar sola por el "
             "centro hasta que se me pasaba, y mira, al final eso fue lo que me salvó",
    clauses=[
        {"src": "bueno, lo que pasa es que ",
         "any": {"en": ["the thing is", "what happened", "well", "basically", "point is"],
                 "ja": ["実は", "というのも", "まあ", "つまり", "あの", "ええと", "何が起き", "何と言うか",
                        "何というか"]}},
        {"src": "yo llegué a Madrid sin conocer a nadie, ",
         "any": {"en": ["madrid"], "ja": ["マドリード", "マドリッド"]}},
        {"src": "ni un alma, ",
         "any": {"en": ["soul", "anyone at all", "not one person", "single person", "nobody at all"],
                 "ja": ["一人も", "誰一人", "誰も"]}},
        {"src": "y el primer mes fue durísimo, ",
         "any": {"en": ["first month"], "ja": ["最初の一", "一ヶ月", "1ヶ月", "一か月", "最初の月", "初めの月", "ひと月"]}},
        {"src": "porque además llovía todos los días, ",
         "any": {"en": ["rain"], "ja": ["雨"]}},
        {"src": "y yo salía del trabajo a las nueve ",
         "any": {"en": ["nine"], "ja": ["九時", "9時"]}},
        {"src": "y no tenía a quién llamar, ",
         "any": {"en": ["call", "phone", "ring"], "ja": ["電話", "connect"]}},
        {"src": "entonces me acostumbré a caminar sola por el centro ",
         "any": {"en": ["walk"], "ja": ["歩く", "歩き", "散歩"]}},
        {"src": "hasta que se me pasaba, ",
         "any": {"en": ["passed", "wore off", "went away", "until it", "eased", "felt better", "calmed",
                        "better"],
                 "ja": ["おさま", "収ま", "治ま", "過ぎ", "落ち着", "まぎれ", "紛れ", "楽になる", "晴れ",
                        "気が済む"]}},
        {"src": "y mira, al final eso fue lo que me salvó",
         "any": {"en": ["saved", "saving", "salvation"], "ja": ["救っ", "救わ", "助け"]}},
    ],
)

passage(
    id="subir-precios", real=False, expect="usable",
    note="Authored. Three numerals, for the numeral-parity check, plus a spelled-out one ('dos') "
         "which that check must not require.",
    brokenness=["numeral", "cut-close"],
    sourceLang="es", targets=["en"],
    headword="subir", lemma="subir", pos="verb", shortGloss="to go up; to raise",
    matchedForm="subió",
    sense={"definition": "Aumentar una cantidad o un precio.", "definitionLang": "es",
           "glosses": [{"lang": "en", "terms": ["to go up"]}]},
    decoySense={"definition": "Ir a un lugar más alto.", "definitionLang": "es",
                "glosses": [{"lang": "en", "terms": ["to climb"]}]},
    provenance={"segmentId": "seg_6b5390fe2c1d47a8e0b3", "channel": "La Pija y la Quinqui",
                "videoTitle": "no llegamos a fin de mes",
                "speechStyle": ["podcast", "conversation"], "variety": ["España"],
                "captionKind": "automatic", "boundary": "cut"},
    sentence="el alquiler me subió de 600 a 850 euros en dos años, o sea un 40 por ciento, y el "
             "sueldo sigue igual, claro",
    clauses=[
        {"src": "el alquiler me subió de 600 a 850 euros ", "any": {"en": ["rent"]}},
        {"src": "en dos años, ", "any": {"en": ["two years", "2 years"]}},
        {"src": "o sea un 40 por ciento, ", "any": {"en": ["40", "forty"]}},
        {"src": "y el sueldo sigue igual, ", "any": {"en": ["salary", "wage", "pay"]}},
        {"src": "claro", "any": {"en": ["of course", "obviously", "naturally", "right"]}},
    ],
)

passage(
    id="oublier-fr", real=False, expect="usable",
    note="Authored. Not Spanish — catches an anchor scheme or a prompt that only works for one "
         "source language.",
    brokenness=["cut-open", "multi-clause"],
    sourceLang="fr", targets=["en"],
    headword="oublier", lemma="oublier", pos="verb", shortGloss="to forget",
    matchedForm="oublié",
    sense={"definition": "Ne plus avoir en mémoire, ne plus penser à quelque chose.",
           "definitionLang": "fr", "glosses": [{"lang": "en", "terms": ["to forget"]}]},
    decoySense={"definition": "Laisser quelque chose quelque part par inadvertance.",
                "definitionLang": "fr", "glosses": [{"lang": "en", "terms": ["to leave behind"]}]},
    provenance={"segmentId": "seg_ba417c0d9e6538f271cd", "channel": "InnerFrench",
                "videoTitle": "les petits mensonges du quotidien",
                "speechStyle": ["podcast", "monologue"], "variety": ["France"],
                "captionKind": "automatic", "boundary": "cut"},
    sentence="en fait, j'avais complètement oublié qu'on devait se voir ce jour-là, et quand elle "
             "m'a appelée j'étais encore en pyjama, donc j'ai dit que j'arrivais dans dix minutes, "
             "ce qui était totalement faux",
    clauses=[
        {"src": "en fait, ", "any": {"en": ["actually", "in fact", "basically", "the truth is"]}},
        {"src": "j'avais complètement oublié qu'on devait se voir ce jour-là, ",
         "any": {"en": ["forgot", "forgotten"]}},
        {"src": "et quand elle m'a appelée ", "any": {"en": ["called", "phoned", "rang"]}},
        {"src": "j'étais encore en pyjama, ", "any": {"en": ["pyjama", "pajama", "pjs"]}},
        {"src": "donc j'ai dit que j'arrivais dans dix minutes, ",
         "any": {"en": ["ten minutes", "10 minutes"]}},
        {"src": "ce qui était totalement faux",
         "any": {"en": ["false", "untrue", "a lie", "not true", "complete lie"]}},
    ],
)

out = {
    "schema": 1,
    "note": "Passages for the clip-translation experiment. `real: true` rows are segments the corpus "
            "actually returned (three from tests/unit/clips/fixtures/search-es-picar.json, two "
            "quoted inside prompts/acervo_clip_select.md itself); the rest are authored in the same "
            "shape and say so. The clause list must concatenate back to `sentence` exactly — that "
            "is what makes coverage a partition rather than a bag of words. One anchor disjunction "
            "per clause: if a clause needs two content words, split the clause.",
    "passages": P,
}
Path("passages.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
rows = sum(len(p["targets"]) for p in P)
print(f"{len(P)} passages, {rows} (passage, target) rows")
for p in P:
    print(f"  {p['id']:24s} {p['sourceLang']}→{','.join(p['targets']):8s} "
          f"{len(p['clauses']):2d} clauses  {len(p['sentence']):3d} chars  "
          f"{'real' if p['real'] else 'authored'}  expect={p['expect']}")
