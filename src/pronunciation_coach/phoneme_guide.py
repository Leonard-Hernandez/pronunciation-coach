"""Phoneme guide: one entry per sound the scorer can show, with teaching content.

This module is the single source of truth for per-phoneme information. It feeds:

* ``GET /api/phonemes`` (the "Sounds" tab and the clickable phoneme chips),
* ``GET /api/tts/phoneme`` (how each sound is synthesized, see ``SoundSpec``),
* ``tips.PHONEME_TIPS`` (fallback tip for an expected phoneme).

Symbols are the normalized tokens produced by ``phonemes.tokenize_ipa``. A few
entries have aliases: espeak writes the stressed r-colored vowel of "bird" as /ɜ/,
which the guide shows as /ɝ/.

Teaching text (``how``, ``spanish``, ``tip``, pair notes) is neutral Spanish because
the learner is a Spanish speaker; names and everything else stay in English.

Examples use bracket notation: ``"[th]ink"`` highlights the letters that make the sound.

How a sound is played is decided in ``phoneme_audio``: a human recording from
Wikimedia Commons when one is bundled, else the first example word slowly (Piper),
else espeak-ng. ``SoundSpec`` describes that last-resort espeak-ng synthesis
(phoneme mnemonics, ``[[...]]``), by method:

* ``isolated``: vowels, diphthongs and r-colored vowels are rendered on their own.
* ``sustained``: voiceless fricatives (θ f s ʃ) are held (``T:::``) and then repeated
  before a schwa (``T@``), so the noise is heard alone and in a syllable.
* ``frame``: voiced continuants (v ð z ʒ m n l) are held into a schwa (``v:::@``),
  /ŋ/ after one (``@N:::``) and the flap between vowels (``A:t#A:``). On their own,
  espeak renders them too short (30-160 ms) to hear.
* ``syllable``: stops, affricates, glides, /h/ and /ɹ/ cannot be sustained; they are
  played before a schwa ("tuh", "ruh").

Piper (raw phoneme ids) was tried as well, but without word context the voice
produces unrelated vowels, so Piper only ever speaks the example word.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CATEGORIES: tuple[tuple[str, str], ...] = (
    ("vowel", "Vowels"),
    ("r_colored", "R-colored vowels"),
    ("diphthong", "Diphthongs"),
    ("consonant", "Consonants"),
    ("other", "Spanish sounds you may see in feedback"),
)


@dataclass(frozen=True)
class SoundSpec:
    """How to synthesize the sound: espeak-ng mnemonic parts, played with a short gap."""

    method: str  # isolated | sustained | frame | syllable
    parts: tuple[str, ...]
    voice: str = "en-us"


@dataclass(frozen=True)
class MinimalPair:
    words: tuple[str, str]  # (word with this sound, word with the contrasting sound)
    contrast: str | None  # symbol of the contrasting sound (None: the sound is dropped)
    note: str = ""


@dataclass(frozen=True)
class Phoneme:
    symbol: str
    name: str
    category: str
    hard: bool  # hard for Spanish speakers
    how: str  # how to produce it (Spanish)
    spanish: str  # closest Spanish sound, or that it does not exist (Spanish)
    tip: str  # one-line reminder (Spanish)
    sound: SoundSpec
    examples: tuple[str, ...] = ()
    pair: MinimalPair | None = None
    aliases: tuple[str, ...] = ()
    manner: str = ""  # consonants: stop, fricative, affricate, nasal, liquid, glide, flap


def _iso(mn: str) -> SoundSpec:
    return SoundSpec("isolated", (mn,))


def _sus(mn: str) -> SoundSpec:
    return SoundSpec("sustained", (f"{mn}:::", f"{mn}@"))


def _frame(*parts: str) -> SoundSpec:
    return SoundSpec("frame", parts)


def _syl(mn: str) -> SoundSpec:
    return SoundSpec("syllable", (f"{mn}@",))


def _es(*parts: str) -> SoundSpec:
    return SoundSpec("isolated", parts, voice="es")


NO_SPANISH = "No existe en español."

GUIDE: tuple[Phoneme, ...] = (
    # ------------------------------------------------------------------ vowels
    Phoneme(
        "i", "Long EE (as in see)", "vowel", True,
        "Estira los labios como en una sonrisa leve. La lengua va alta y adelante, tensa. "
        "Es una vocal larga.",
        "Parecida a la 'i' de 'vino', pero más larga y tensa.",
        "/i/ (see): larga y tensa, labios estirados.",
        _iso("i:"), ("s[ee]", "[ea]t", "sh[ee]p"),
        MinimalPair(("seat", "sit"), "ɪ", "Si la acortas y relajas, 'seat' se convierte en 'sit'."),
    ),
    Phoneme(
        "ɪ", "Short I (as in sit)", "vowel", True,
        "Labios relajados, sin sonreír. La lengua queda un poco más baja y floja que para /i/. "
        "Es corta: suena entre la 'i' y la 'e' del español.",
        "No existe en español. Está entre la 'i' y la 'e'.",
        "/ɪ/ (sit): corta y relajada, entre 'i' y 'e'.",
        _iso("I"), ("s[i]t", "b[i]g", "[i]s"),
        MinimalPair(("ship", "sheep"), "i", "'ship' es corta y relajada; 'sheep' es larga y tensa."),
    ),
    Phoneme(
        "ɛ", "Short E (as in bed)", "vowel", False,
        "Como la 'e' española, con la boca un poco más abierta y la lengua relajada.",
        "Parecida a la 'e' de 'perro'.",
        "/ɛ/ (bed): una 'e' abierta y corta.",
        _iso("E"), ("b[e]d", "r[e]d", "s[ai]d"),
        MinimalPair(("bed", "bad"), "æ", "Para 'bad' abre más la mandíbula y lleva la lengua más abajo."),
    ),
    Phoneme(
        "æ", "Short A (as in cat)", "vowel", True,
        "Abre bien la mandíbula como para una 'a', pero empuja la lengua hacia adelante y abajo, "
        "con los labios algo estirados. Suena entre la 'a' y la 'e'.",
        "No existe en español. Es una mezcla de 'a' y 'e'.",
        "/æ/ (cat): mandíbula abierta, lengua baja y adelante.",
        _iso("a"), ("c[a]t", "h[a]nd", "bl[a]ck"),
        MinimalPair(("cat", "cut"), "ʌ", "'cat' abre más la boca y adelanta la lengua; 'cut' es corta y central."),
    ),
    Phoneme(
        "ɑ", "Open AH (as in father, hot)", "vowel", True,
        "Boca muy abierta, lengua baja y retraída hacia atrás, labios sin redondear. "
        "La 'o' de 'hot' o 'stop' suena así en inglés americano.",
        "Parecida a la 'a' de 'casa', pero más abierta, más atrás y más larga.",
        "/ɑ/ (father, hot): boca muy abierta, lengua atrás.",
        _iso("A:"), ("f[a]ther", "h[o]t", "st[o]p"),
        MinimalPair(("hot", "hut"), "ʌ", "'hot' es más abierta y larga; 'hut' es corta y relajada."),
    ),
    Phoneme(
        "ɔ", "AW (as in law, thought)", "vowel", False,
        "Labios ligeramente redondeados, boca abierta y lengua atrás. Muchos estadounidenses "
        "la pronuncian igual que /ɑ/ (father).",
        "Parecida a una 'o' muy abierta, casi 'a'.",
        "/ɔ/ (law): una 'o' muy abierta, casi 'a'.",
        _iso("O:"), ("l[aw]", "th[ou]ght", "w[a]ter"),
    ),
    Phoneme(
        "ʌ", "Short U (as in cup)", "vowel", True,
        "Boca medio abierta, lengua en el centro y relajada, labios neutros. Es corta, como una "
        "'a' débil. Suele escribirse con 'u' (cup) o con 'o' (love, son).",
        "No existe en español. Es una 'a' corta y relajada.",
        "/ʌ/ (cup): corta y relajada, como una 'a' débil.",
        _iso("V"), ("c[u]p", "l[o]ve", "b[u]t"),
        MinimalPair(("cut", "cat"), "æ", "'cut' no estira los labios ni adelanta la lengua."),
    ),
    Phoneme(
        "ʊ", "Short OO (as in book)", "vowel", True,
        "Labios apenas redondeados y relajados, lengua alta y atrás, pero floja. "
        "Es corta: suena entre la 'u' y la 'o'.",
        "No existe en español. Es una 'u' corta y floja.",
        "/ʊ/ (book): corta, labios apenas redondeados.",
        _iso("U"), ("b[oo]k", "g[oo]d", "p[u]t"),
        MinimalPair(("full", "fool"), "u", "'full' es corta y floja; 'fool' es larga, con labios tensos."),
    ),
    Phoneme(
        "u", "Long OO (as in food)", "vowel", True,
        "Labios bien redondeados y tensos, lengua alta y atrás. Es una vocal larga.",
        "Como la 'u' de 'luna', pero más larga.",
        "/u/ (food): larga, labios redondeados y tensos.",
        _iso("u:"), ("f[oo]d", "bl[ue]", "t[oo]"),
        MinimalPair(("fool", "full"), "ʊ", "Mantén los labios tensos y alarga la vocal."),
    ),
    Phoneme(
        "ə", "Schwa: weak 'uh' (as in about)", "vowel", True,
        "Es la vocal más común del inglés. Todo relajado: boca entreabierta, lengua en el centro, "
        "sin fuerza y muy corta. Aparece en sílabas sin acento, se escriba como se escriba.",
        "No existe en español. En español todas las vocales suenan completas; en inglés las "
        "sílabas sin acento se debilitan.",
        "/ə/ (about): vocal débil y corta de las sílabas sin acento.",
        _iso("@"), ("[a]bout", "sof[a]", "t[o]day"),
    ),
    # --------------------------------------------------------- r-colored vowels
    Phoneme(
        "ɚ", "Unstressed ER (as in teacher)", "r_colored", True,
        "Una schwa con la lengua curvada hacia atrás, sin tocar el paladar, durante toda la vocal. "
        "No es una 'e' seguida de una 'r' vibrante: la 'r' tiñe toda la vocal.",
        NO_SPANISH,
        "/ɚ/ (teacher): schwa con la lengua curvada hacia atrás.",
        _iso("3"), ("teach[er]", "doct[or]", "butt[er]"),
    ),
    Phoneme(
        "ɝ", "Stressed ER (as in bird)", "r_colored", True,
        "Como /ɚ/, pero acentuada y más larga: lengua curvada hacia atrás y labios un poco "
        "redondeados. 'bird', 'word' y 'heard' tienen la misma vocal.",
        "No existe en español. No digas 'e' + 'r'.",
        "/ɝ/ (bird): vocal larga con la lengua curvada hacia atrás, sin 'e'.",
        _iso("3:"), ("b[ir]d", "w[or]k", "h[er]"),
        MinimalPair(("bird", "bed"), "ɛ", "Si dices 'e' y luego 'r', 'bird' se acerca a 'bed'."),
        aliases=("ɜ",),
    ),
    # --------------------------------------------------------------- diphthongs
    Phoneme(
        "eɪ", "Long A (as in day)", "diphthong", True,
        "Empieza en 'e' y deslízate hacia 'i' dentro de la misma sílaba: 'ei'. "
        "No te quedes en una 'e' pura.",
        "Como 'ei' en 'rey'.",
        "/eɪ/ (day): desliza de 'e' a 'i', no una 'e' pura.",
        _iso("eI"), ("d[ay]", "m[a]ke", "r[ai]n"),
        MinimalPair(("late", "let"), "ɛ", "'late' tiene deslizamiento a 'i'; 'let' es una 'e' corta."),
    ),
    Phoneme(
        "aɪ", "Long I (as in my)", "diphthong", False,
        "Empieza en 'a' abierta y deslízate hacia 'i'.",
        "Como 'ai' en 'baile'.",
        "/aɪ/ (my): como 'ai' en 'baile'.",
        _iso("aI"), ("m[y]", "t[i]me", "l[i]ke"),
    ),
    Phoneme(
        "ɔɪ", "OY (as in boy)", "diphthong", False,
        "Empieza en una 'o' abierta y deslízate hacia 'i'.",
        "Como 'oi' en 'hoy'.",
        "/ɔɪ/ (boy): como 'oi' en 'hoy'.",
        _iso("OI"), ("b[oy]", "n[oi]se", "c[oi]n"),
    ),
    Phoneme(
        "oʊ", "Long O (as in go)", "diphthong", True,
        "Empieza en 'o' y termina en 'u', redondeando más los labios al final. "
        "No es una 'o' pura.",
        "Como 'ou' dicho rápido; la 'o' española sola no basta.",
        "/oʊ/ (go): desliza de 'o' a 'u', cerrando los labios.",
        _iso("oU"), ("g[o]", "h[o]me", "kn[ow]"),
        MinimalPair(("boat", "bought"), "ɔ", "'boat' cierra los labios hacia 'u'; 'bought' se queda abierta."),
    ),
    Phoneme(
        "aʊ", "OW (as in now)", "diphthong", False,
        "Empieza en 'a' abierta y deslízate hacia 'u', redondeando los labios.",
        "Como 'au' en 'causa'.",
        "/aʊ/ (now): como 'au' en 'causa'.",
        _iso("aU"), ("n[ow]", "h[ou]se", "[ou]t"),
    ),
    # --------------------------------------------------------------- consonants
    Phoneme(
        "p", "P (with a puff of air)", "consonant", True,
        "Cierra los labios y suéltalos con un soplo de aire fuerte al inicio de una sílaba "
        "acentuada (pen). Pon la mano frente a la boca: debes sentir el aire.",
        "Existe, pero la 'p' española no lleva soplo; sin él, 'pin' puede sonar a 'bin'.",
        "/p/ (pen): suelta los labios con un soplo de aire.",
        _syl("p"), ("[p]en", "[p]ark", "ha[pp]y"),
        MinimalPair(("pin", "bin"), "b", "Sin el soplo de aire, 'pin' suena a 'bin'."),
        manner="stop",
    ),
    Phoneme(
        "b", "B (both lips)", "consonant", False,
        "Cierra ambos labios por completo y suéltalos con voz. Entre vocales no la suavices "
        "como en 'lobo': mantén el cierre completo.",
        "Como la 'b' de 'bote' al inicio de palabra.",
        "/b/ (boy): cierra los dos labios por completo.",
        _syl("b"), ("[b]oy", "a[b]out", "ca[b]"),
        MinimalPair(("berry", "very"), "v", "'berry' junta los labios; 'very' pone los dientes en el labio."),
        manner="stop",
    ),
    Phoneme(
        "t", "T (with a puff of air)", "consonant", True,
        "La punta de la lengua toca la encía detrás de los dientes superiores, no los dientes. "
        "Al inicio de una sílaba acentuada lleva un soplo de aire (top). Entre vocales, en "
        "inglés americano suele convertirse en /ɾ/ (water).",
        "Parecida a la 't' española, pero esta toca los dientes y no lleva soplo.",
        "/t/ (top): lengua en la encía y un soplo de aire.",
        _syl("t"), ("[t]op", "[t]ime", "ca[t]"),
        MinimalPair(("tie", "die"), "d", "'tie' lleva soplo y no tiene voz; 'die' vibra."),
        manner="stop",
    ),
    Phoneme(
        "d", "D", "consonant", False,
        "Punta de la lengua en la encía detrás de los dientes superiores, con voz. Siempre con "
        "cierre completo, también entre vocales y al final (bad).",
        "Como la 'd' de 'donde'. La 'd' suave de 'nada' se parece más a /ð/.",
        "/d/ (dog): cierre completo de la lengua en la encía, con voz.",
        _syl("d"), ("[d]og", "ba[d]", "rea[d]y"),
        MinimalPair(("day", "they"), "ð", "'day' toca la encía; 'they' pone la lengua entre los dientes."),
        manner="stop",
    ),
    Phoneme(
        "k", "K (with a puff of air)", "consonant", True,
        "La parte de atrás de la lengua toca el paladar blando. Al inicio de una sílaba "
        "acentuada lleva un soplo de aire (cat).",
        "Como la 'c' de 'casa', pero con soplo de aire.",
        "/k/ (cat): parte de atrás de la lengua, con soplo de aire.",
        _syl("k"), ("[c]at", "[k]ey", "ba[ck]"),
        MinimalPair(("coat", "goat"), "ɡ", "'coat' lleva soplo y no tiene voz; 'goat' vibra."),
        manner="stop",
    ),
    Phoneme(
        "ɡ", "G (hard G)", "consonant", False,
        "La parte de atrás de la lengua contra el paladar blando, con voz. Siempre fuerte, "
        "también entre vocales.",
        "Como la 'g' de 'gato'.",
        "/ɡ/ (go): cierre completo atrás, con voz.",
        _syl("g"), ("[g]o", "bi[g]", "a[g]ain"),
        MinimalPair(("goat", "coat"), "k"),
        aliases=("g",), manner="stop",
    ),
    Phoneme(
        "tʃ", "CH (as in church)", "consonant", False,
        "La lengua toca la encía y se suelta en una 'sh'. Empieza con un pequeño golpe.",
        "Como la 'ch' de 'chico'.",
        "/tʃ/ (church): como la 'ch' de 'chico'.",
        _syl("tS"), ("[ch]air", "wa[tch]", "tea[ch]er"),
        MinimalPair(("chip", "ship"), "ʃ", "'chip' empieza con un golpe; 'ship' es un siseo continuo."),
        manner="affricate",
    ),
    Phoneme(
        "dʒ", "J (as in judge)", "consonant", True,
        "Como /tʃ/ pero con voz: la lengua toca la encía y se suelta en una 'sh' que vibra. "
        "No es la 'y' suave de 'mayo' ni la 'j' española.",
        "No existe en el español estándar. Se parece a una 'y' pronunciada con fuerza, como en '¡yo!'.",
        "/dʒ/ (judge): golpe de la lengua en la encía y luego un zumbido.",
        _syl("dZ"), ("[j]ust", "[j]ob", "a[ge]"),
        MinimalPair(("jet", "yet"), "j", "'jet' empieza con contacto de la lengua; 'yet' no toca nada."),
        manner="affricate",
    ),
    Phoneme(
        "f", "F", "consonant", False,
        "Apoya los dientes superiores en el labio inferior y sopla aire sin voz.",
        "Como la 'f' de 'foco'.",
        "/f/ (fish): dientes en el labio, sin voz.",
        _sus("f"), ("[f]ish", "o[ff]ice", "li[f]e"),
        MinimalPair(("fan", "van"), "v", "'fan' solo sopla aire; 'van' vibra."),
        manner="fricative",
    ),
    Phoneme(
        "v", "V (teeth on lip, buzzing)", "consonant", True,
        "Apoya suavemente los dientes superiores en el labio inferior y haz vibrar la voz: "
        "debe zumbar. Los labios no se juntan; eso sería /b/.",
        "No existe en español: la 'v' española suena igual que la 'b'.",
        "/v/ (very): dientes en el labio inferior, con zumbido.",
        _frame("v:::@"), ("[v]ery", "li[v]e", "ha[v]e"),
        MinimalPair(("very", "berry"), "b", "Si juntas los labios, 'very' suena a 'berry'."),
        manner="fricative",
    ),
    Phoneme(
        "θ", "Voiceless TH (as in think)", "consonant", True,
        "Saca la punta de la lengua un poco entre los dientes y sopla aire sin voz. No detengas "
        "el aire (eso sería /t/) ni metas la lengua detrás de los dientes (eso sería /s/).",
        "Como la 'z' o la 'c' de España ('cena' en Madrid). No existe en el español de América.",
        "/θ/ (think): lengua entre los dientes y sopla, sin voz.",
        _sus("T"), ("[th]ink", "[th]ree", "ba[th]"),
        MinimalPair(("think", "sink"), "s", "Si la lengua queda detrás de los dientes, 'think' suena a 'sink'."),
        manner="fricative",
    ),
    Phoneme(
        "ð", "Voiced TH (as in this)", "consonant", True,
        "La misma posición que /θ/ (lengua entre los dientes), pero con voz: debe zumbar. "
        "Aparece en palabras muy frecuentes: the, this, that, they.",
        "Parecida a la 'd' suave de 'nada' o 'dedo', con la lengua más adelante.",
        "/ð/ (this): lengua entre los dientes, con zumbido.",
        _frame("D:::@"), ("[th]is", "[th]e", "mo[th]er"),
        MinimalPair(("they", "day"), "d", "Si la lengua toca la encía, 'they' suena a 'day'."),
        manner="fricative",
    ),
    Phoneme(
        "s", "S", "consonant", False,
        "Acerca la punta de la lengua a la encía sin tocarla y deja salir un siseo. No agregues "
        "una 'e' antes de s + consonante: 'school', no 'eschool'.",
        "Como la 's' de 'sol'.",
        "/s/ (sun): siseo; sin 'e' delante en 'school', 'Spain'.",
        _sus("s"), ("[s]un", "ye[s]", "[s]chool"),
        MinimalPair(("sip", "zip"), "z", "'sip' solo sisea; 'zip' zumba."),
        manner="fricative",
    ),
    Phoneme(
        "z", "Z (buzzing S)", "consonant", True,
        "La misma posición que /s/, pero con voz: debe zumbar como una abeja. Es muy común al "
        "final de palabra: is, was, dogs, his.",
        "No existe en el español estándar: la 'z' española suena como 's' (o /θ/ en España).",
        "/z/ (zoo, is): una 's' que zumba.",
        _frame("z:::@"), ("[z]oo", "i[s]", "dog[s]"),
        MinimalPair(("zip", "sip"), "s", "Pon la mano en la garganta: en 'zip' debe vibrar."),
        manner="fricative",
    ),
    Phoneme(
        "ʃ", "SH (as in she)", "consonant", True,
        "Labios redondeados y hacia adelante, lengua un poco más atrás que para /s/. Es un siseo "
        "continuo, como cuando pides silencio: 'shhh'.",
        "No existe en el español estándar. Se parece a la 'ch' sin el golpe inicial.",
        "/ʃ/ (she): labios hacia adelante, siseo continuo 'shhh'.",
        _sus("S"), ("[sh]e", "[sh]ip", "na[ti]on"),
        MinimalPair(("she", "see"), "s", "Redondea los labios y retrasa la lengua para 'she'."),
        manner="fricative",
    ),
    Phoneme(
        "ʒ", "ZH (as in vision)", "consonant", True,
        "Como /ʃ/, pero con voz: debe zumbar. Es poco frecuente: vision, measure, usually.",
        "Se parece a la 'll' o 'y' del español rioplatense ('yo' en Buenos Aires).",
        "/ʒ/ (vision): una 'sh' que zumba.",
        _frame("Z:::@"), ("vi[s]ion", "mea[s]ure", "u[s]ually"),
        manner="fricative",
    ),
    Phoneme(
        "h", "H (soft breath)", "consonant", True,
        "Solo un soplo suave de aire desde la garganta, como cuando empañas un vidrio. Sin roce: "
        "la 'j' española es demasiado fuerte. Y nunca es muda: 'house' no es 'ouse'.",
        "Como una 'j' muy suave, aspirada.",
        "/h/ (house): un soplo suave, nunca muda ni áspera como la 'j'.",
        _syl("h"), ("[h]ouse", "[h]ello", "be[h]ind"),
        MinimalPair(("hair", "air"), None, "Sin el soplo inicial, 'hair' suena a 'air'."),
        manner="fricative",
    ),
    Phoneme(
        "m", "M", "consonant", False,
        "Cierra los labios y deja salir la voz por la nariz. Al final de palabra cierra los "
        "labios por completo: 'team', no 'tean'.",
        "Como la 'm' de 'mamá'.",
        "/m/: cierra los labios por completo, también al final.",
        _frame("m:::@"), ("[m]an", "ti[m]e", "co[m]e"),
        MinimalPair(("some", "sun"), "n", "Al final de 'some' los labios se cierran."),
        manner="nasal",
    ),
    Phoneme(
        "n", "N", "consonant", False,
        "Punta de la lengua en la encía detrás de los dientes superiores; la voz sale por la nariz.",
        "Como la 'n' de 'nada'.",
        "/n/: punta de la lengua en la encía, voz por la nariz.",
        _frame("n:::@"), ("[n]o", "su[n]", "te[n]"),
        MinimalPair(("sin", "sing"), "ŋ", "'sin' toca con la punta de la lengua; 'sing' con la parte de atrás."),
        manner="nasal",
    ),
    Phoneme(
        "ŋ", "NG (as in sing)", "consonant", True,
        "La parte de atrás de la lengua se pega al paladar blando y el aire sale por la nariz. "
        "En 'sing' no se pronuncia una /ɡ/ al final, ni se cambia por /n/.",
        "Existe en español antes de 'g' o 'c' ('tengo', 'banco'), pero en inglés también "
        "aparece al final de palabra.",
        "/ŋ/ (sing): parte de atrás de la lengua en el paladar, sin /ɡ/ final.",
        _frame("@N:::"), ("si[ng]", "thi[n]k", "lo[ng]"),
        MinimalPair(("sing", "sin"), "n", "No cambies la /ŋ/ final por /n/."),
        manner="nasal",
    ),
    Phoneme(
        "l", "L", "consonant", False,
        "Punta de la lengua en la encía. Al final de palabra (feel, ball) también se eleva la "
        "parte de atrás de la lengua: suena más oscura y hueca.",
        "Como la 'l' de 'luna' al inicio; al final de palabra es más oscura.",
        "/l/: punta de la lengua en la encía; al final, más oscura.",
        _frame("l:::@"), ("[l]ight", "fee[l]", "he[ll]o"),
        MinimalPair(("light", "right"), "ɹ", "'light' toca la encía; 'right' no toca nada."),
        manner="liquid",
    ),
    Phoneme(
        "ɹ", "American R", "consonant", True,
        "Curva la punta de la lengua hacia atrás (o recógela) sin tocar el paladar, con los "
        "labios un poco redondeados. No vibra ni golpea como la 'r' española.",
        "No existe en español. La 'r' de 'pero' es un golpe y la de 'perro' una vibración; "
        "esta no toca nada.",
        "/ɹ/ (red): lengua curvada hacia atrás, sin tocar ni vibrar.",
        _syl("r"), ("[r]ed", "ca[r]", "ve[r]y"),
        MinimalPair(("right", "light"), "l", "Para 'right' la lengua no toca el paladar."),
        aliases=("r",), manner="liquid",
    ),
    Phoneme(
        "j", "Y (as in yes)", "consonant", False,
        "La lengua se acerca al paladar sin tocarlo, como una 'i' rápida que se desliza hacia la "
        "vocal. Sin roce ni fuerza.",
        "Como la 'i' de 'hielo' o 'tiene'.",
        "/j/ (yes): una 'i' rápida, sin contacto.",
        _syl("j"), ("[y]es", "[y]ou", "[y]ellow"),
        MinimalPair(("yet", "jet"), "dʒ", "En 'yet' la lengua no toca el paladar."),
        manner="glide",
    ),
    Phoneme(
        "w", "W", "consonant", False,
        "Redondea mucho los labios como para una 'u' y deslízate hacia la vocal. No agregues una "
        "/ɡ/ delante: 'wood', no 'güud'.",
        "Como la 'u' de 'huevo' o 'cuando'.",
        "/w/ (we): labios redondeados que se deslizan, sin /ɡ/ delante.",
        _syl("w"), ("[w]e", "[w]ater", "a[w]ay"),
        MinimalPair(("west", "vest"), "v", "'west' redondea los labios; 'vest' pone los dientes en el labio."),
        manner="glide",
    ),
    Phoneme(
        "ɾ", "Flap T (as in water)", "consonant", False,
        "En inglés americano, una /t/ o /d/ entre vocales, antes de una sílaba sin acento, se "
        "convierte en un toque rápido de la lengua en la encía: water, better, city.",
        "Existe: es la 'r' suave de 'pero' o 'cara'.",
        "/ɾ/ (water): toque rápido de la lengua, como la 'r' de 'pero'.",
        _frame("A:t#A:"), ("wa[t]er", "be[tt]er", "ci[t]y"),
        manner="flap",
    ),
    # ------------------------------------------- Spanish sounds the recognizer may hear
    Phoneme(
        "a", "Spanish A", "other", False,
        "Es la 'a' del español. En inglés casi siempre se necesita otra vocal: /æ/ (cat), "
        "/ɑ/ (hot), /ʌ/ (cup) o /ə/ (about).",
        "Es la 'a' de 'casa'.",
        "Se oyó una 'a' española: revisa si era /æ/, /ɑ/, /ʌ/ o /ə/.",
        _es("a"),
    ),
    Phoneme(
        "e", "Spanish E", "other", False,
        "Es la 'e' del español. En inglés suele ser /ɛ/ (bed) o /eɪ/ (day, que se desliza a 'i').",
        "Es la 'e' de 'mesa'.",
        "Se oyó una 'e' española: revisa si era /ɛ/ o /eɪ/.",
        _es("e"),
    ),
    Phoneme(
        "o", "Spanish O", "other", False,
        "Es la 'o' del español. En inglés suele ser /oʊ/ (go, que se desliza a 'u'), "
        "/ɑ/ (hot) o /ɔ/ (law).",
        "Es la 'o' de 'todo'.",
        "Se oyó una 'o' española: revisa si era /oʊ/, /ɑ/ o /ɔ/.",
        _es("o"),
    ),
    Phoneme(
        "x", "Spanish J (jota)", "other", False,
        "Es la 'j' del español, con roce en la parte de atrás de la boca. No existe en inglés: "
        "para la 'h' usa /h/, un soplo suave sin roce.",
        "Es la 'j' de 'jamón'.",
        "Se oyó una 'j' española: la /h/ inglesa es solo un soplo suave.",
        _es("x", "xa"),
    ),
    Phoneme(
        "β", "Spanish soft B (as in 'lobo')", "other", False,
        "Es la 'b' suave del español entre vocales: los labios se acercan sin cerrarse. En inglés "
        "usa /b/ (labios cerrados del todo) o /v/ (dientes en el labio inferior).",
        "Es la 'b' de 'lobo'.",
        "Se oyó una 'b' suave: cierra los labios para /b/ o usa los dientes para /v/.",
        _es("aBa"),
    ),
)

BY_SYMBOL: dict[str, Phoneme] = {p.symbol: p for p in GUIDE}
ALIASES: dict[str, str] = {a: p.symbol for p in GUIDE for a in p.aliases}

_EXAMPLE_RE = re.compile(r"\[([^\]]+)\]")


def lookup(symbol: str) -> Phoneme | None:
    """Entry for a normalized token or one of its aliases."""
    symbol = symbol.strip()
    return BY_SYMBOL.get(symbol) or BY_SYMBOL.get(ALIASES.get(symbol, ""))


def example_word(example: str) -> str:
    return example.replace("[", "").replace("]", "")


def parse_example(example: str) -> dict:
    """``"[th]ink"`` -> ``{"word": "think", "parts": [{"text": "th", "focus": True}, ...]}``."""
    parts: list[dict] = []
    pos = 0
    for m in _EXAMPLE_RE.finditer(example):
        if m.start() > pos:
            parts.append({"text": example[pos : m.start()], "focus": False})
        parts.append({"text": m.group(1), "focus": True})
        pos = m.end()
    if pos < len(example):
        parts.append({"text": example[pos:], "focus": False})
    return {"word": example_word(example), "parts": parts}


def fallback_word(entry: Phoneme) -> str | None:
    """Word to play (slowly) when the isolated sound cannot be synthesized."""
    return example_word(entry.examples[0]) if entry.examples else None


def entry_to_dict(p: Phoneme) -> dict:
    from .phoneme_audio import planned_source, recording_for  # it imports this module

    rec = recording_for(p)
    return {
        "symbol": p.symbol, "aliases": list(p.aliases), "name": p.name,
        "category": p.category, "manner": p.manner, "hard": p.hard,
        "how": p.how, "spanish": p.spanish, "tip": p.tip,
        "examples": [parse_example(e) for e in p.examples],
        "pair": None if p.pair is None else {
            "words": list(p.pair.words), "contrast": p.pair.contrast, "note": p.pair.note,
        },
        "sound_method": p.sound.method,
        # recording | piper | espeak: what /api/tts/phoneme plays first for this sound
        "source": planned_source(p),
        "recording": None if rec is None else rec.to_dict(),
        "listen_word": fallback_word(p),
    }


def guide_payload() -> dict:
    return {
        "categories": [{"id": cid, "title": title} for cid, title in CATEGORIES],
        "phonemes": [entry_to_dict(p) for p in GUIDE],
        "aliases": dict(ALIASES),
    }
