"""Articulation tips for common Spanish-speaker errors in English."""

from __future__ import annotations

from .phoneme_guide import ALIASES, GUIDE

# (expected, produced) -> tip. Teaching text is in Spanish (the learner's language).
PAIR_TIPS: dict[tuple[str, str], str] = {
    ("θ", "t"): "/θ/ (think): pon la punta de la lengua entre los dientes y sopla. No cortes el aire como en /t/.",
    ("θ", "s"): "/θ/ (think): la lengua va entre los dientes, no detrás. La /s/ sisea detrás de los dientes.",
    ("θ", "f"): "/θ/ (think): usa la lengua, no el labio inferior, contra los dientes superiores.",
    ("ð", "d"): "/ð/ (this): lengua entre los dientes y con voz, como una /θ/ que zumba. La 'd' suave de 'nada' se acerca; no hagas una /d/ fuerte.",
    ("ð", "z"): "/ð/ (this): la lengua va entre los dientes, no detrás.",
    ("v", "b"): "/v/ (very): apoya los dientes superiores en el labio inferior y haz zumbar la voz. La /b/ junta los dos labios.",
    ("b", "v"): "/b/ (boat): cierra los dos labios por completo y luego suéltalos.",
    ("z", "s"): "/z/ (zoo, is, was): la misma posición que /s/, pero con voz: debe zumbar. La -s final de 'is' o 'dogs' suele ser /z/.",
    ("ʒ", "ʃ"): "/ʒ/ (vision): como /ʃ/, pero con voz: agrega el zumbido.",
    ("ʃ", "tʃ"): "/ʃ/ (she): un 'shh' continuo, sin golpe al inicio. La /tʃ/ empieza con una /t/.",
    ("tʃ", "ʃ"): "/tʃ/ (chair): empieza con la lengua tocando la encía detrás de los dientes y suéltala en 'sh'.",
    ("ʃ", "s"): "/ʃ/ (she): redondea los labios y lleva la lengua un poco hacia atrás, como cuando pides silencio.",
    ("dʒ", "j"): "/dʒ/ (just): empieza con un cierre de /d/ y suéltalo en un 'sh' que zumba. No es la 'y' española.",
    ("dʒ", "ʒ"): "/dʒ/ (just): empieza con la lengua tocando la encía (una /d/) y luego suéltala.",
    ("j", "dʒ"): "/j/ (yes): sin contacto; la lengua se desliza como la 'i' de 'hielo'.",
    ("h", "x"): "/h/ (house): solo un soplo suave desde la garganta. La 'j' española es demasiado áspera.",
    ("ɪ", "i"): "/ɪ/ (sit): más corta y relajada que /i/ (seat). No sonrías; relaja labios y lengua.",
    ("i", "ɪ"): "/i/ (seat): más larga y tensa; estira los labios como sonriendo.",
    ("æ", "ɛ"): "/æ/ (cat): abre la mandíbula más que para la 'e', con la lengua baja y adelante.",
    ("æ", "a"): "/æ/ (cat): entre la 'a' y la 'e' españolas: abre bien la boca, pero empuja la lengua hacia adelante.",
    ("æ", "ʌ"): "/æ/ (cat): abre más la mandíbula y estira los labios; /ʌ/ (cup) es más corta y central.",
    ("æ", "ɑ"): "/æ/ (cat): mantén la lengua adelante; /ɑ/ (father) va muy atrás.",
    ("ʌ", "a"): "/ʌ/ (cup): corta y relajada, con la boca medio abierta. Menos abierta que la 'a' española.",
    ("ʌ", "ɑ"): "/ʌ/ (cup): más corta, más central y menos abierta que /ɑ/ (father).",
    ("ʌ", "æ"): "/ʌ/ (cup): relaja los labios y deja la lengua en el centro, no adelante.",
    ("ʌ", "o"): "/ʌ/ (cup, love): sin redondear los labios. La 'o' escrita muchas veces suena /ʌ/.",
    ("ɑ", "a"): "/ɑ/ (father): abre mucho la boca y lleva la lengua hacia atrás.",
    ("ɑ", "ʌ"): "/ɑ/ (hot, father): abre más la boca y alarga la vocal.",
    ("ɑ", "o"): "/ɑ/ (hot): la 'o' de 'hot' en inglés americano es una 'a' abierta, no la 'o' española.",
    ("ʊ", "u"): "/ʊ/ (book): más corta y relajada que /u/ (food); labios apenas redondeados.",
    ("u", "ʊ"): "/u/ (food): más larga, con los labios bien redondeados.",
    ("ə", "a"): "/ə/ (schwa, 'about'): las sílabas sin acento son débiles y cortas; relájate por completo.",
    ("ə", "e"): "/ə/ (schwa): las vocales sin acento se reducen a una 'a' débil. No pronuncies completa la vocal escrita.",
    ("ə", "o"): "/ə/ (schwa): reduce las vocales sin acento: 'today' es /tə/, no 'tu'.",
    ("ə", "ɛ"): "/ə/ (schwa): reduce las vocales sin acento a una vocal débil y central.",
    ("ɹ", "ɾ"): "/ɹ/ (red): no golpees con la lengua. Cúrvala hacia atrás sin tocar el paladar.",
    ("ɚ", "ɛ"): "/ɚ/ (her, teacher): curva la lengua hacia atrás mientras dices la vocal; la 'r' tiñe toda la vocal.",
    ("ɜ", "ɛ"): "/ɝ/ (bird, work): vocal central con la lengua curvada hacia atrás, no una 'e' española.",
    ("eɪ", "e"): "/eɪ/ (day): deslízate de 'e' a 'i'; es un diptongo.",
    ("oʊ", "o"): "/oʊ/ (go): deslízate de 'o' a 'u', redondeando más los labios al final.",
    ("ŋ", "n"): "/ŋ/ (sing): la parte de atrás de la lengua toca el paladar blando; no agregues /ɡ/ ni cambies a /n/.",
    ("m", "n"): "/m/ final: cierra los labios por completo al final.",
    ("w", "ɡ"): "/w/ (would, wood): redondea los labios y deslízate; no agregues una /ɡ/ delante.",
}

# Tips by expected phoneme (used when the exact pair is not listed), from the phoneme guide.
PHONEME_TIPS: dict[str, str] = {p.symbol: p.tip for p in GUIDE if p.category != "other"}
PHONEME_TIPS.update({alias: PHONEME_TIPS[symbol] for alias, symbol in ALIASES.items()})

STOPS_AND_FINALS = {"t", "d", "k", "ɡ", "p", "b", "s", "z", "v", "f", "θ", "ð", "l", "m", "n", "ŋ"}

FINAL_CONSONANT_TIP = (
    "No omitas las consonantes finales: en inglés muchas palabras terminan en consonante "
    "(y el -ed del pasado o la -s del plural cambian el significado). Termina la palabra con claridad."
)
EPENTHESIS_TIP = (
    "No agregues una 'e' antes de s + consonante (school, Spain, student): "
    "empieza directamente con el siseo de la /s/."
)
INSERTED_VOWEL_TIP = "Vocal de más: no agregues una vocal después de la consonante final (por ejemplo, 'big-e')."
VOWELS = set("aeiouæɑɒɔəɛɜɪʊʌɚ") | {"aɪ", "aʊ", "eɪ", "oʊ", "ɔɪ", "əʊ", "ɪə", "eə", "ʊə"}


def tip_for(kind: str, expected: str, actual: str, *, word_final: bool = False,
            word_initial_before_s: bool = False) -> str | None:
    """Return the most specific tip for an error, or None."""
    if kind == "substitution":
        return PAIR_TIPS.get((expected, actual)) or PHONEME_TIPS.get(expected)
    if kind == "deletion":
        if word_final and expected in STOPS_AND_FINALS:
            return FINAL_CONSONANT_TIP
        return PHONEME_TIPS.get(expected)
    if kind == "insertion":
        if actual in VOWELS and word_initial_before_s:
            return EPENTHESIS_TIP
        if actual in VOWELS and word_final:
            return INSERTED_VOWEL_TIP
        if actual == "x":
            return PHONEME_TIPS["h"]
    return None
