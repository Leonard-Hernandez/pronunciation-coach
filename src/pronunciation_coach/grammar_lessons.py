"""Grammar lessons for the most common errors of Spanish speakers (single source of truth).

Teaching content is in neutral Spanish; titles and identifiers are English (UI chrome).
Each lesson has an explanation, wrong/right examples and a short exercise that is
checked locally by `check_answers` (no LLM needed).

Exercise items:
- kind "fill": `prompt` contains one "___"; `answers` lists the accepted words/phrases.
- kind "fix": `prompt` is a wrong sentence; `answers` lists accepted corrected sentences.
"""

from __future__ import annotations

import re
import unicodedata

# Fixed error categories used by corrections (value -> English label).
CATEGORIES: dict[str, str] = {
    "articles": "Articles",
    "prepositions": "Prepositions",
    "verb_tense": "Verb tenses",
    "verb_form": "Verb forms (-ing / to + verb)",
    "subject_verb_agreement": "Subject-verb agreement",
    "word_order": "Word order",
    "missing_subject": "Missing subject",
    "false_friend": "False friends",
    "collocation": "Collocations",
    "word_choice": "Word choice",
    "countability": "Countable / uncountable",
    "pronoun": "Pronouns",
    "negation": "Negation",
    "spelling": "Spelling",
    "punctuation": "Punctuation",
    "capitalization": "Capitalization",
    "register": "Register (formal / informal)",
    "other": "Other",
}

# Lesson to suggest for a category when the model does not name a better one.
CATEGORY_LESSON: dict[str, str | None] = {
    "articles": "articles",
    "prepositions": "prepositions-time-place",
    "verb_tense": "present-perfect-past-simple",
    "verb_form": "gerund-infinitive",
    "subject_verb_agreement": "third-person-s",
    "word_order": "word-order",
    "missing_subject": "missing-subject-it",
    "false_friend": "false-friends",
    "collocation": "collocations",
    "word_choice": "collocations",
    "countability": "much-many",
    "pronoun": "explain-to",
    "negation": "double-negatives",
    "spelling": None,
    "punctuation": "punctuation",
    "capitalization": "punctuation",
    "register": "register",
    "other": None,
}

LESSONS: list[dict] = [
    {
        "id": "missing-subject-it",
        "title": "Every sentence needs a subject: it",
        "categories": ["missing_subject"],
        "summary": "En inglés el sujeto nunca se omite. Si no hay uno, se usa «it».",
        "explanation": (
            "En español el verbo ya indica la persona («Es importante», «Llueve»), así que el sujeto "
            "se omite. En inglés casi siempre debe aparecer un sujeto explícito. Cuando no hay un sujeto "
            "real (para opiniones, el clima, la hora o distancias), se usa el sujeto vacío «it»: "
            "«It is important», «It's raining», «It's 5 o'clock»."
        ),
        "examples": [
            {"wrong": "Is important to say that…", "right": "It is important to say that…"},
            {"wrong": "Is raining a lot today.", "right": "It is raining a lot today."},
            {"wrong": "I like this job because is interesting.", "right": "I like this job because it is interesting."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "___ is difficult to find a good job without English.",
             "answers": ["it"], "explanation": "Falta el sujeto vacío «it»."},
            {"kind": "fix", "prompt": "Is necessary to finish the report today.",
             "answers": ["It is necessary to finish the report today.", "It's necessary to finish the report today."],
             "explanation": "«Es necesario» → «It is necessary»."},
            {"kind": "fix", "prompt": "I bought this laptop because was cheap.",
             "answers": ["I bought this laptop because it was cheap."],
             "explanation": "Después de «because» también hace falta sujeto: «it was»."},
            {"kind": "fill", "prompt": "Take an umbrella: ___ is going to rain.",
             "answers": ["it"], "explanation": "El clima usa «it» como sujeto."},
        ],
    },
    {
        "id": "there-is-are",
        "title": "There is / there are, not “have”",
        "categories": ["missing_subject", "word_choice"],
        "summary": "«Hay» se dice «there is / there are», no «have» ni «it has».",
        "explanation": (
            "Para decir que algo existe («hay») se usa «there is» con singular o incontable y «there are» "
            "con plural. «Have» significa «tener» y necesita un sujeto que posea algo. En pasado: "
            "«there was / there were»; en futuro: «there will be»."
        ),
        "examples": [
            {"wrong": "In my city have many parks.", "right": "In my city there are many parks."},
            {"wrong": "It has a problem with the system.", "right": "There is a problem with the system."},
            {"wrong": "Yesterday there was many people.", "right": "Yesterday there were many people."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "___ are three candidates for the position.",
             "answers": ["there"], "explanation": "«Hay tres candidatos» → «There are»."},
            {"kind": "fix", "prompt": "In the office have a new coffee machine.",
             "answers": ["In the office there is a new coffee machine.", "There is a new coffee machine in the office.",
                         "In the office there's a new coffee machine.", "There's a new coffee machine in the office."],
             "explanation": "«Hay» = «there is», no «have»."},
            {"kind": "fill", "prompt": "Last year there ___ a lot of changes in the company.",
             "answers": ["were"], "explanation": "Plural en pasado: «there were»."},
            {"kind": "fill", "prompt": "There ___ some information on the website.",
             "answers": ["is", "'s"], "explanation": "«Information» es incontable: «there is»."},
        ],
    },
    {
        "id": "people-plural",
        "title": "People is plural",
        "categories": ["subject_verb_agreement"],
        "summary": "«People» es plural: «people are», «people have», «people think».",
        "explanation": (
            "En español «la gente» es singular («la gente es amable»), pero en inglés «people» es el plural "
            "de «person». Por eso el verbo va en plural (are, were, have, think) y los pronombres son "
            "«they / them / their». Nunca se dice «peoples» para hablar de personas en general."
        ),
        "examples": [
            {"wrong": "People is very kind.", "right": "People are very kind."},
            {"wrong": "People thinks that…", "right": "People think that…"},
            {"wrong": "The people in my team is great.", "right": "The people in my team are great."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "People in this city ___ very friendly.",
             "answers": ["are"], "explanation": "«People» lleva verbo plural."},
            {"kind": "fix", "prompt": "Many people doesn't know how to use this tool.",
             "answers": ["Many people don't know how to use this tool.", "Many people do not know how to use this tool."],
             "explanation": "Plural: «people don't»."},
            {"kind": "fill", "prompt": "Young people ___ (want) flexible jobs.",
             "answers": ["want"], "explanation": "Sin «-s»: el sujeto es plural."},
            {"kind": "fix", "prompt": "The people was waiting outside.",
             "answers": ["The people were waiting outside."], "explanation": "Pasado plural: «were»."},
        ],
    },
    {
        "id": "age-with-be",
        "title": "Age uses be: I am 25",
        "categories": ["verb_tense", "word_choice"],
        "summary": "La edad se dice con «be»: «I am 25 (years old)», nunca «I have 25 years».",
        "explanation": (
            "En español «tenemos» años, pero en inglés «somos» una edad: «I am 25» o «I am 25 years old». "
            "No se puede decir «I am 25 years» (sin «old») ni usar «have». Para preguntar: "
            "«How old are you?». También: «a 25-year-old engineer» (con guiones y «year» en singular)."
        ),
        "examples": [
            {"wrong": "I have 25 years.", "right": "I am 25 years old. / I'm 25."},
            {"wrong": "My sister has 30 years.", "right": "My sister is 30."},
            {"wrong": "How many years do you have?", "right": "How old are you?"},
        ],
        "exercise": [
            {"kind": "fix", "prompt": "I have 28 years and I live in Bogotá.",
             "answers": ["I am 28 years old and I live in Bogotá.", "I'm 28 years old and I live in Bogotá.",
                         "I am 28 and I live in Bogotá.", "I'm 28 and I live in Bogotá."],
             "explanation": "Edad con «be»: «I am 28 (years old)»."},
            {"kind": "fill", "prompt": "My boss ___ 45 years old.", "answers": ["is", "'s"],
             "explanation": "«Is», no «has»."},
            {"kind": "fill", "prompt": "How ___ are you?", "answers": ["old"],
             "explanation": "La pregunta es «How old…?»."},
            {"kind": "fix", "prompt": "She is a 30-years-old designer.",
             "answers": ["She is a 30-year-old designer.", "She's a 30-year-old designer."],
             "explanation": "Delante de un sustantivo, «year» va en singular: «a 30-year-old designer»."},
        ],
    },
    {
        "id": "since-for",
        "title": "Since vs for (with present perfect)",
        "categories": ["prepositions", "verb_tense"],
        "summary": "«Since» + punto de inicio; «for» + duración. Ambos con present perfect.",
        "explanation": (
            "Para algo que empezó en el pasado y sigue ahora, el español usa el presente "
            "(«trabajo aquí desde 2020»), pero el inglés usa el present perfect: «I have worked here since 2020». "
            "«Since» va con el momento de inicio (2020, Monday, I was a child). «For» va con la duración "
            "(five years, two weeks, a long time). Nunca «since five years» ni «from 2020» en este sentido."
        ),
        "examples": [
            {"wrong": "I work in this company since 2020.", "right": "I have worked at this company since 2020."},
            {"wrong": "I live here for five years.", "right": "I have lived here for five years."},
            {"wrong": "I have studied English since three years.", "right": "I have studied English for three years."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "I have known her ___ 2018.", "answers": ["since"],
             "explanation": "2018 es el punto de inicio → «since»."},
            {"kind": "fill", "prompt": "We have been waiting ___ two hours.", "answers": ["for"],
             "explanation": "Dos horas es una duración → «for»."},
            {"kind": "fix", "prompt": "I study English since I was a child.",
             "answers": ["I have studied English since I was a child.", "I've studied English since I was a child.",
                         "I have been studying English since I was a child.", "I've been studying English since I was a child."],
             "explanation": "Acción que continúa: present perfect («have studied»)."},
            {"kind": "fix", "prompt": "She works here for three months.",
             "answers": ["She has worked here for three months.", "She's worked here for three months.",
                         "She has been working here for three months.", "She's been working here for three months."],
             "explanation": "Duración hasta ahora: «has worked … for»."},
        ],
    },
    {
        "id": "present-perfect-past-simple",
        "title": "Present perfect vs past simple",
        "categories": ["verb_tense"],
        "summary": "Momento terminado y concreto → past simple. Sin momento o hasta ahora → present perfect.",
        "explanation": (
            "Usa el past simple cuando dices o se entiende CUÁNDO pasó, en un tiempo terminado: "
            "«yesterday», «in 2019», «last week», «two days ago». Usa el present perfect para experiencias "
            "sin fecha («I have visited Canada»), resultados actuales («I have lost my keys») o periodos "
            "que siguen abiertos («this year», «since…», «for…»). Error típico: «I have finished it yesterday»."
        ),
        "examples": [
            {"wrong": "I have finished the report yesterday.", "right": "I finished the report yesterday."},
            {"wrong": "Did you ever work abroad?", "right": "Have you ever worked abroad?"},
            {"wrong": "I have started this job in 2021.", "right": "I started this job in 2021."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "I ___ (send) the email two hours ago.", "answers": ["sent"],
             "explanation": "«Ago» marca un momento terminado → past simple."},
            {"kind": "fill", "prompt": "___ you ever been to Mexico?", "answers": ["have"],
             "explanation": "Experiencia sin fecha → present perfect."},
            {"kind": "fix", "prompt": "We have met the client last Monday.",
             "answers": ["We met the client last Monday."], "explanation": "«Last Monday» → past simple."},
            {"kind": "fill", "prompt": "I can't log in. I ___ (forget) my password.",
             "answers": ["have forgotten", "'ve forgotten"], "explanation": "Resultado presente → present perfect."},
        ],
    },
    {
        "id": "third-person-s",
        "title": "Third person -s (he works)",
        "categories": ["subject_verb_agreement"],
        "summary": "Con he, she, it (y un sujeto singular) el verbo en presente lleva «-s».",
        "explanation": (
            "En presente simple, la tercera persona del singular agrega «-s» o «-es»: «she works», "
            "«it goes», «he watches». En negativas y preguntas la «-s» pasa a «does» y el verbo queda "
            "en base: «she doesn't work», «Does it work?». Cuidado con sujetos largos: «My manager "
            "always answers quickly». Ojo también con «have» → «has»."
        ),
        "examples": [
            {"wrong": "My boss work from home.", "right": "My boss works from home."},
            {"wrong": "She don't like meetings.", "right": "She doesn't like meetings."},
            {"wrong": "Does he works here?", "right": "Does he work here?"},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "The company ___ (have) 200 employees.", "answers": ["has"],
             "explanation": "Tercera persona: «has»."},
            {"kind": "fix", "prompt": "My colleague speak three languages.",
             "answers": ["My colleague speaks three languages."], "explanation": "«Colleague» = he/she → «speaks»."},
            {"kind": "fix", "prompt": "He doesn't knows the answer.",
             "answers": ["He doesn't know the answer.", "He does not know the answer."],
             "explanation": "Con «doesn't» el verbo va sin «-s»."},
            {"kind": "fill", "prompt": "The meeting usually ___ (finish) at five.", "answers": ["finishes"],
             "explanation": "Verbo terminado en -sh → «-es»."},
        ],
    },
    {
        "id": "articles",
        "title": "Articles: the, a/an or nothing",
        "categories": ["articles"],
        "summary": "Para hablar en general en plural o incontable, el inglés NO usa «the».",
        "explanation": (
            "El español usa «el/la/los/las» para generalizar («La tecnología cambia el mundo», «Me gustan "
            "los perros»). En inglés, las generalizaciones con plurales o incontables van sin artículo: "
            "«Technology changes the world», «I like dogs». «The» se usa para algo específico o ya conocido. "
            "Con profesiones y sustantivos singulares contables hace falta «a/an»: «I am an engineer» "
            "(no «I am engineer»)."
        ),
        "examples": [
            {"wrong": "The life is difficult.", "right": "Life is difficult."},
            {"wrong": "I am engineer.", "right": "I am an engineer."},
            {"wrong": "The technology is important for the companies.", "right": "Technology is important for companies."},
        ],
        "exercise": [
            {"kind": "fix", "prompt": "The education is the key to success.",
             "answers": ["Education is the key to success."], "explanation": "Generalización incontable: sin «the»."},
            {"kind": "fill", "prompt": "My brother is ___ accountant.", "answers": ["an"],
             "explanation": "Profesión en singular: «a/an»; «an» antes de vocal."},
            {"kind": "fix", "prompt": "I think the people should read more.",
             "answers": ["I think people should read more."], "explanation": "«People» en general: sin «the»."},
            {"kind": "fill", "prompt": "Can you close ___ door, please? It's cold.", "answers": ["the"],
             "explanation": "Una puerta específica que ambos conocen: «the»."},
        ],
    },
    {
        "id": "prepositions-time-place",
        "title": "In, on, at (time and place)",
        "categories": ["prepositions"],
        "summary": "«At» para un punto, «on» para días y superficies, «in» para periodos y espacios.",
        "explanation": (
            "Tiempo: «at» con horas y momentos puntuales (at 7 pm, at night, at the weekend en británico); "
            "«on» con días y fechas (on Monday, on 3 May); «in» con meses, años, estaciones y partes del día "
            "(in July, in 2020, in the morning). Lugar: «at» para un punto o institución (at work, at the bus stop), "
            "«on» para superficies (on the table, on the second floor), «in» para espacios cerrados y ciudades "
            "(in the office, in Lima). Se dice «work AT/FOR a company», no «in a company»."
        ),
        "examples": [
            {"wrong": "The meeting is in Monday.", "right": "The meeting is on Monday."},
            {"wrong": "I work in this company.", "right": "I work at / for this company."},
            {"wrong": "I was born on 1999.", "right": "I was born in 1999."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "The interview is ___ 10 a.m.", "answers": ["at"], "explanation": "Hora exacta → «at»."},
            {"kind": "fill", "prompt": "We launched the product ___ March.", "answers": ["in"], "explanation": "Mes → «in»."},
            {"kind": "fill", "prompt": "See you ___ Friday!", "answers": ["on"], "explanation": "Día → «on»."},
            {"kind": "fill", "prompt": "My office is ___ the third floor.", "answers": ["on"], "explanation": "Piso → «on»."},
        ],
    },
    {
        "id": "dependent-prepositions",
        "title": "Verbs and adjectives with fixed prepositions",
        "categories": ["prepositions", "collocation"],
        "summary": "depend on, married to, interested in, good at, arrive at/in: se memorizan como bloque.",
        "explanation": (
            "Muchas preposiciones no se traducen palabra por palabra. «Depender de» es «depend ON»; "
            "«casado con» es «married TO»; «interesado en» es «interested IN»; «bueno para» es «good AT»; "
            "«soñar con» es «dream OF/ABOUT»; «consistir en» es «consist OF»; «llegar a» es «arrive AT» "
            "(lugar) o «arrive IN» (ciudad/país), nunca «arrive to». «Discuss» y «enter» no llevan preposición."
        ),
        "examples": [
            {"wrong": "It depends of the situation.", "right": "It depends on the situation."},
            {"wrong": "She is married with a doctor.", "right": "She is married to a doctor."},
            {"wrong": "We discussed about the budget.", "right": "We discussed the budget."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "The price depends ___ the size.", "answers": ["on"], "explanation": "«Depend on»."},
            {"kind": "fill", "prompt": "I'm very interested ___ this position.", "answers": ["in"], "explanation": "«Interested in»."},
            {"kind": "fix", "prompt": "We arrived to the airport at six.",
             "answers": ["We arrived at the airport at six."], "explanation": "«Arrive at» un lugar concreto."},
            {"kind": "fix", "prompt": "Let's discuss about the new project.",
             "answers": ["Let's discuss the new project.", "Let us discuss the new project."],
             "explanation": "«Discuss» no lleva preposición."},
        ],
    },
    {
        "id": "make-do",
        "title": "Make vs do",
        "categories": ["collocation", "word_choice"],
        "summary": "«Make» = crear/producir; «do» = tareas, trabajo y actividades. Hay que memorizar combinaciones.",
        "explanation": (
            "Ambos son «hacer». En general, «make» se usa para crear o producir algo (make a cake, make a "
            "decision, make a mistake, make money, make a plan, make an effort) y «do» para tareas, trabajo "
            "y actividades sin un producto concreto (do homework, do the dishes, do business, do your best, "
            "do research, do a course). Las colocaciones más frecuentes conviene aprenderlas de memoria."
        ),
        "examples": [
            {"wrong": "I did a mistake.", "right": "I made a mistake."},
            {"wrong": "We need to make more research.", "right": "We need to do more research."},
            {"wrong": "She does a lot of money.", "right": "She makes a lot of money."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "We have to ___ a decision today.", "answers": ["make"], "explanation": "«Make a decision»."},
            {"kind": "fill", "prompt": "I always ___ my best at work.", "answers": ["do"], "explanation": "«Do your best»."},
            {"kind": "fill", "prompt": "Sorry, I ___ a mistake in the invoice.", "answers": ["made"], "explanation": "«Make a mistake» (pasado: made)."},
            {"kind": "fill", "prompt": "She is ___ a course in data analysis.", "answers": ["doing"], "explanation": "«Do a course»."},
        ],
    },
    {
        "id": "say-tell",
        "title": "Say vs tell",
        "categories": ["word_choice"],
        "summary": "«Tell» necesita a quién: «tell someone». «Say» no: «say something (to someone)».",
        "explanation": (
            "«Tell» lleva la persona directamente después: «He told me the truth», «Tell her to call me». "
            "«Say» se centra en las palabras y, si mencionas a la persona, necesita «to»: «He said that he was "
            "busy», «She said hello to me». Nunca «He said me». Expresiones fijas con «tell»: tell the truth, "
            "tell a lie, tell a story, tell the difference."
        ),
        "examples": [
            {"wrong": "He said me that he was tired.", "right": "He told me that he was tired."},
            {"wrong": "She told that the meeting was cancelled.", "right": "She said that the meeting was cancelled."},
            {"wrong": "Can you say me the time?", "right": "Can you tell me the time?"},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "My manager ___ me to send the report.", "answers": ["told"], "explanation": "Persona después del verbo → «tell»."},
            {"kind": "fill", "prompt": "She ___ that she would be late.", "answers": ["said"], "explanation": "Sin persona → «say»."},
            {"kind": "fix", "prompt": "They said us the news yesterday.",
             "answers": ["They told us the news yesterday."], "explanation": "«Tell us», no «say us»."},
            {"kind": "fill", "prompt": "Always ___ the truth in an interview.", "answers": ["tell"], "explanation": "«Tell the truth»."},
        ],
    },
    {
        "id": "explain-to",
        "title": "Explain to me (not “explain me”)",
        "categories": ["pronoun", "verb_form"],
        "summary": "explain, describe, suggest, say: la persona va con «to», nunca justo después del verbo.",
        "explanation": (
            "En español decimos «me explicó», pero en inglés «explain» no acepta la persona como objeto directo. "
            "La estructura es «explain something TO someone»: «She explained the process to me» o «She explained "
            "to me how it works». Lo mismo con «describe», «suggest», «propose» y «say». Además, «suggest» no va "
            "con infinitivo: «I suggest that you call» o «I suggest calling»."
        ),
        "examples": [
            {"wrong": "They explained me everything.", "right": "They explained everything to me."},
            {"wrong": "Can you explain me the problem?", "right": "Can you explain the problem to me?"},
            {"wrong": "He suggested me to apply.", "right": "He suggested that I apply. / He suggested applying."},
        ],
        "exercise": [
            {"kind": "fix", "prompt": "My trainer explained me the new software.",
             "answers": ["My trainer explained the new software to me."], "explanation": "«Explain something to someone»."},
            {"kind": "fill", "prompt": "Could you describe the role ___ me?", "answers": ["to"], "explanation": "«Describe something to someone»."},
            {"kind": "fix", "prompt": "Please explain us the rules.",
             "answers": ["Please explain the rules to us."], "explanation": "«Explain the rules to us»."},
            {"kind": "fix", "prompt": "She suggested me to take a break.",
             "answers": ["She suggested that I take a break.", "She suggested that I should take a break.",
                         "She suggested taking a break.", "She suggested I take a break."],
             "explanation": "«Suggest» + «that I…» o + «-ing»."},
        ],
    },
    {
        "id": "double-negatives",
        "title": "Only one negative",
        "categories": ["negation"],
        "summary": "En inglés estándar solo hay una negación por frase: «I don't know anything».",
        "explanation": (
            "En español es normal «No sé nada» o «No vino nadie». En inglés estándar dos negaciones se anulan "
            "y suenan incorrectas. Si el verbo es negativo (don't, didn't, can't), usa «any-»: anything, anyone, "
            "anywhere, any. Si quieres la palabra negativa, el verbo va en afirmativo: «I know nothing», "
            "«Nobody came». Con «nobody/nothing» como sujeto, nunca se agrega «don't»."
        ),
        "examples": [
            {"wrong": "I don't know nothing about it.", "right": "I don't know anything about it."},
            {"wrong": "Nobody didn't call.", "right": "Nobody called."},
            {"wrong": "We didn't go nowhere.", "right": "We didn't go anywhere."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "I didn't see ___ at the office.", "answers": ["anyone", "anybody"],
             "explanation": "Verbo negativo + «anyone»."},
            {"kind": "fix", "prompt": "They don't have no experience.",
             "answers": ["They don't have any experience.", "They have no experience.", "They do not have any experience."],
             "explanation": "Una sola negación."},
            {"kind": "fix", "prompt": "Nothing didn't happen.",
             "answers": ["Nothing happened."], "explanation": "«Nothing» ya niega: verbo afirmativo."},
            {"kind": "fill", "prompt": "She can't find her keys ___.", "answers": ["anywhere"],
             "explanation": "Verbo negativo + «anywhere»."},
        ],
    },
    {
        "id": "gerund-infinitive",
        "title": "-ing or to + verb",
        "categories": ["verb_form"],
        "summary": "Algunos verbos van con «-ing» (enjoy, avoid, finish), otros con «to» (want, decide, hope).",
        "explanation": (
            "Cuando dos verbos van juntos, el segundo toma una forma fija según el primero. Con «-ing»: "
            "enjoy, avoid, finish, mind, consider, suggest, keep, look forward to. Con «to + verbo»: want, "
            "decide, hope, plan, need, agree, refuse, would like. Después de cualquier preposición (in, of, "
            "about, for, without, before) el verbo va siempre en «-ing»: «I'm interested in learning», "
            "«I look forward to hearing from you»."
        ),
        "examples": [
            {"wrong": "I enjoy to work in a team.", "right": "I enjoy working in a team."},
            {"wrong": "I look forward to hear from you.", "right": "I look forward to hearing from you."},
            {"wrong": "She decided changing jobs.", "right": "She decided to change jobs."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "We want ___ (improve) our customer service.", "answers": ["to improve"],
             "explanation": "«Want» + to + verbo."},
            {"kind": "fill", "prompt": "Avoid ___ (use) informal language in the email.", "answers": ["using"],
             "explanation": "«Avoid» + -ing."},
            {"kind": "fix", "prompt": "I am interested in apply for this job.",
             "answers": ["I am interested in applying for this job.", "I'm interested in applying for this job."],
             "explanation": "Después de preposición: -ing."},
            {"kind": "fill", "prompt": "I look forward to ___ (meet) you.", "answers": ["meeting"],
             "explanation": "«Look forward to» + -ing."},
        ],
    },
    {
        "id": "gerund-subject",
        "title": "-ing as the subject",
        "categories": ["verb_form", "missing_subject"],
        "summary": "Para usar una acción como sujeto, usa «-ing»: «Learning English is useful».",
        "explanation": (
            "En español el infinitivo puede ser sujeto («Aprender inglés es útil»). En inglés, el sujeto que es "
            "una acción suele ir en «-ing»: «Learning English is useful», «Working from home saves time». "
            "El verbo base solo no puede ser sujeto («Learn English is useful» es incorrecto). También es "
            "posible «It is useful to learn English»."
        ),
        "examples": [
            {"wrong": "Learn English is very important.", "right": "Learning English is very important."},
            {"wrong": "Travel is my passion to know new cultures.", "right": "Travelling to learn about new cultures is my passion."},
            {"wrong": "Work from home is more comfortable.", "right": "Working from home is more comfortable."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "___ (read) every day improves your vocabulary.", "answers": ["reading"],
             "explanation": "Acción como sujeto → «Reading»."},
            {"kind": "fix", "prompt": "Speak in public makes me nervous.",
             "answers": ["Speaking in public makes me nervous."], "explanation": "Sujeto en -ing."},
            {"kind": "fill", "prompt": "___ (exercise) regularly is good for your health.", "answers": ["exercising"],
             "explanation": "Acción como sujeto → «Exercising»."},
            {"kind": "fix", "prompt": "Save money is difficult for young people.",
             "answers": ["Saving money is difficult for young people.", "It is difficult for young people to save money.",
                         "It's difficult for young people to save money."],
             "explanation": "«Saving money is…» o «It is difficult to save money»."},
        ],
    },
    {
        "id": "much-many",
        "title": "Much / many and uncountable nouns",
        "categories": ["countability"],
        "summary": "«Many» con plurales; «much» con incontables. information, advice y news no tienen plural.",
        "explanation": (
            "«Many» y «few» van con sustantivos contables en plural (many emails, few people). «Much» y «little» "
            "van con incontables (much time, little money). «A lot of» sirve para ambos y es más natural en "
            "frases afirmativas. Ojo: palabras incontables en inglés que en español sí se cuentan: information, "
            "advice, news, furniture, equipment, homework, feedback, knowledge. No llevan «-s» ni «a»: "
            "«some advice», «a piece of information»."
        ),
        "examples": [
            {"wrong": "I need more informations.", "right": "I need more information."},
            {"wrong": "There are much problems.", "right": "There are many problems."},
            {"wrong": "She gave me an advice.", "right": "She gave me some advice. / a piece of advice."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "How ___ employees work here?", "answers": ["many"], "explanation": "«Employees» es contable plural."},
            {"kind": "fill", "prompt": "We don't have ___ time left.", "answers": ["much"], "explanation": "«Time» es incontable."},
            {"kind": "fix", "prompt": "Thank you for your advices.",
             "answers": ["Thank you for your advice."], "explanation": "«Advice» no tiene plural."},
            {"kind": "fix", "prompt": "The news are very good.",
             "answers": ["The news is very good."], "explanation": "«News» es incontable: verbo singular."},
        ],
    },
    {
        "id": "adjectives",
        "title": "Adjectives: before the noun, never plural",
        "categories": ["word_order", "subject_verb_agreement"],
        "summary": "El adjetivo va antes del sustantivo y no lleva «-s»: «two important meetings».",
        "explanation": (
            "En inglés los adjetivos no concuerdan en número: «new projects», no «news projects». Además van "
            "ANTES del sustantivo: «a difficult decision». Si hay varios, el orden habitual es: opinión, tamaño, "
            "edad, forma, color, origen, material, propósito → «a beautiful old Italian car», «a small black "
            "leather bag». Los sustantivos usados como adjetivo tampoco van en plural: «a three-day course»."
        ),
        "examples": [
            {"wrong": "They are importants clients.", "right": "They are important clients."},
            {"wrong": "I have a car red.", "right": "I have a red car."},
            {"wrong": "a wooden big table", "right": "a big wooden table"},
        ],
        "exercise": [
            {"kind": "fix", "prompt": "We need differents solutions.",
             "answers": ["We need different solutions."], "explanation": "El adjetivo no lleva «-s»."},
            {"kind": "fix", "prompt": "She works in a company international.",
             "answers": ["She works in an international company.", "She works for an international company.",
                         "She works at an international company."], "explanation": "Adjetivo antes del sustantivo."},
            {"kind": "fix", "prompt": "I bought a leather black jacket.",
             "answers": ["I bought a black leather jacket."], "explanation": "Color antes de material."},
            {"kind": "fix", "prompt": "It was a two-hours meeting.",
             "answers": ["It was a two-hour meeting."], "explanation": "Sustantivo como adjetivo: singular."},
        ],
    },
    {
        "id": "word-order",
        "title": "Word order: verb + object together",
        "categories": ["word_order"],
        "summary": "Sujeto + verbo + objeto, sin separar el verbo del objeto: «I like football very much».",
        "explanation": (
            "En inglés el orden es más rígido: sujeto + verbo + objeto + modo/lugar/tiempo. No se pone un "
            "adverbio entre el verbo y su objeto («I like very much football» es incorrecto → «I like football "
            "very much»). Los adverbios de frecuencia van antes del verbo principal pero después de «be»: "
            "«I always arrive early», «She is always late»."
        ),
        "examples": [
            {"wrong": "I like very much my job.", "right": "I like my job very much."},
            {"wrong": "I speak very well English.", "right": "I speak English very well."},
            {"wrong": "I go always to the gym.", "right": "I always go to the gym."},
        ],
        "exercise": [
            {"kind": "fix", "prompt": "She speaks fluently French.",
             "answers": ["She speaks French fluently."], "explanation": "No separes verbo y objeto."},
            {"kind": "fix", "prompt": "I check usually my email in the morning.",
             "answers": ["I usually check my email in the morning."], "explanation": "Frecuencia antes del verbo principal."},
            {"kind": "fix", "prompt": "He is late never.",
             "answers": ["He is never late.", "He's never late."], "explanation": "Frecuencia después de «be»."},
            {"kind": "fix", "prompt": "We enjoyed a lot the trip.",
             "answers": ["We enjoyed the trip a lot.", "We really enjoyed the trip."], "explanation": "Verbo + objeto juntos."},
        ],
    },
    {
        "id": "question-order",
        "title": "Question word order",
        "categories": ["word_order"],
        "summary": "Preguntas: auxiliar + sujeto + verbo. En preguntas indirectas, orden normal.",
        "explanation": (
            "En español basta la entonación («¿Tú trabajas aquí?»). En inglés hace falta un auxiliar antes del "
            "sujeto: «Do you work here?», «Where does she live?», «What did they say?». En las preguntas "
            "indirectas, muy comunes en emails formales («Could you tell me…», «I would like to know…»), "
            "el orden vuelve a ser afirmativo y no se usa do/does: «Could you tell me where the office is?»."
        ),
        "examples": [
            {"wrong": "Where you work?", "right": "Where do you work?"},
            {"wrong": "Why she is angry?", "right": "Why is she angry?"},
            {"wrong": "Could you tell me what time does the course start?", "right": "Could you tell me what time the course starts?"},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "What time ___ the meeting start?", "answers": ["does"], "explanation": "Auxiliar «does» antes del sujeto."},
            {"kind": "fix", "prompt": "How much it costs?",
             "answers": ["How much does it cost?"], "explanation": "«does» + sujeto + verbo base."},
            {"kind": "fix", "prompt": "Can you tell me where is the station?",
             "answers": ["Can you tell me where the station is?"], "explanation": "Indirecta: orden afirmativo."},
            {"kind": "fix", "prompt": "I would like to know when will the job start.",
             "answers": ["I would like to know when the job will start.", "I'd like to know when the job will start."],
             "explanation": "Indirecta: «when the job will start»."},
        ],
    },
    {
        "id": "false-friends",
        "title": "False friends",
        "categories": ["false_friend"],
        "summary": "Palabras que parecen españolas pero significan otra cosa: actually, assist, library, sensible…",
        "explanation": (
            "Los falsos amigos son palabras parecidas en forma y distintas en significado. Las más peligrosas: "
            "«actually» = en realidad (actualmente = currently); «assist» = ayudar (asistir = attend); «library» = "
            "biblioteca (librería = bookshop); «sensible» = sensato (sensible = sensitive); «embarrassed» = "
            "avergonzado (embarazada = pregnant); «carpet» = alfombra (carpeta = folder); «exit» = salida "
            "(éxito = success); «realize» = darse cuenta (realizar = carry out); «eventually» = finalmente "
            "(eventualmente = possibly); «career» = carrera profesional (carrera universitaria = degree); "
            "«notice» = notar/aviso (noticia = news)."
        ),
        "examples": [
            {"wrong": "Actually I work as a designer. (= actualmente)", "right": "Currently, I work as a designer."},
            {"wrong": "I assisted to the conference.", "right": "I attended the conference."},
            {"wrong": "I bought the book in a library.", "right": "I bought the book in a bookshop."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "I ___ (asistí a) three workshops last year.", "answers": ["attended"],
             "explanation": "«Asistir a» = «attend»."},
            {"kind": "fill", "prompt": "___ (actualmente), I am looking for a new job.", "answers": ["currently", "at the moment", "at present"],
             "explanation": "«Actualmente» = «currently», no «actually»."},
            {"kind": "fill", "prompt": "Save the documents in the shared ___ (carpeta).", "answers": ["folder"],
             "explanation": "«Carpeta» = «folder»; «carpet» es alfombra."},
            {"kind": "fill", "prompt": "The launch was a great ___ (éxito).", "answers": ["success"],
             "explanation": "«Éxito» = «success»; «exit» es salida."},
        ],
    },
    {
        "id": "collocations",
        "title": "Common collocations",
        "categories": ["collocation", "word_choice"],
        "summary": "Combinaciones fijas: take a photo, pay attention, make a decision, heavy rain.",
        "explanation": (
            "Una colocación es una combinación natural de palabras que no se puede traducir literalmente. "
            "Algunas muy útiles para el examen: take a photo / a break / an exam / a decision (o make a decision); "
            "pay attention; have a shower / a meeting; give a presentation; raise a question; meet a deadline; "
            "strong coffee; heavy rain / traffic; high price; a big mistake. Usar colocaciones correctas sube "
            "mucho la nota de vocabulario."
        ),
        "examples": [
            {"wrong": "I want to do a question.", "right": "I want to ask a question."},
            {"wrong": "We need to put attention.", "right": "We need to pay attention."},
            {"wrong": "There was strong traffic.", "right": "There was heavy traffic."},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "Please ___ attention to the details.", "answers": ["pay"], "explanation": "«Pay attention»."},
            {"kind": "fill", "prompt": "Can I ___ a question?", "answers": ["ask"], "explanation": "«Ask a question»."},
            {"kind": "fill", "prompt": "We must ___ the deadline on Friday.", "answers": ["meet"], "explanation": "«Meet a deadline»."},
            {"kind": "fill", "prompt": "Let's ___ a short break.", "answers": ["take", "have"], "explanation": "«Take/have a break»."},
        ],
    },
    {
        "id": "punctuation",
        "title": "Run-on sentences, commas and capitals",
        "categories": ["punctuation", "capitalization"],
        "summary": "Una coma no une dos oraciones completas. Días, meses, idiomas y «I» van con mayúscula.",
        "explanation": (
            "En español es común unir oraciones con comas. En inglés, dos oraciones completas se separan con "
            "punto, punto y coma o un conector (and, but, so, because): «I was tired, so I went home». "
            "Antes de «however» empieza una oración nueva o usa punto y coma: «It was late; however, we continued». "
            "Mayúsculas obligatorias: el pronombre «I», días (Monday), meses (May), idiomas y nacionalidades "
            "(English, Colombian)."
        ),
        "examples": [
            {"wrong": "I finished the report, I sent it to my boss.", "right": "I finished the report and sent it to my boss."},
            {"wrong": "The plan was good, however it was expensive.", "right": "The plan was good. However, it was expensive."},
            {"wrong": "i study english on mondays.", "right": "I study English on Mondays."},
        ],
        "exercise": [
            {"kind": "fix", "prompt": "i speak spanish and english.",
             "answers": ["I speak Spanish and English."], "explanation": "«I» e idiomas con mayúscula."},
            {"kind": "fix", "prompt": "The meeting is on friday in march.",
             "answers": ["The meeting is on Friday in March."], "explanation": "Días y meses con mayúscula."},
            {"kind": "fix", "prompt": "It was raining, we stayed at home.",
             "answers": ["It was raining, so we stayed at home.", "It was raining. We stayed at home.",
                         "It was raining; we stayed at home.", "Because it was raining, we stayed at home.",
                         "We stayed at home because it was raining."],
             "explanation": "Une las oraciones con un conector o sepáralas."},
            {"kind": "fill", "prompt": "The salary is low. ___, the benefits are excellent.", "answers": ["however"],
             "explanation": "Contraste al inicio de oración: «However,»."},
        ],
    },
    {
        "id": "register",
        "title": "Formal vs informal register",
        "categories": ["register"],
        "summary": "Emails formales: sin contracciones ni jerga, con fórmulas fijas de saludo y despedida.",
        "explanation": (
            "En los exámenes B2 e IELTS se evalúa si el tono corresponde a la situación. En un email formal "
            "(a una empresa, un jefe que no conoces): «Dear Mr Smith / Dear Sir or Madam», sin contracciones "
            "(I am, I would), vocabulario neutro (receive en vez de get, request en vez de ask for) y cierre "
            "«Yours sincerely» (si sabes el nombre) o «Yours faithfully» (si no), o «Kind regards». En uno "
            "informal (a un amigo): «Hi Ana», contracciones, phrasal verbs y cierre «Best wishes / See you soon»."
        ),
        "examples": [
            {"wrong": "Hi guys, I wanna apply for the job.", "right": "Dear Sir or Madam, I would like to apply for the position."},
            {"wrong": "Send me the info ASAP.", "right": "I would be grateful if you could send me the information as soon as possible."},
            {"wrong": "Dear Sir or Madam, … Yours sincerely (to an unknown person)", "right": "Dear Sir or Madam, … Yours faithfully"},
        ],
        "exercise": [
            {"kind": "fill", "prompt": "Formal: I ___ be grateful if you could reply soon.", "answers": ["would"],
             "explanation": "Formal y sin contracción: «I would»."},
            {"kind": "fix", "prompt": "Formal: I'm writing to ask for info about the course.",
             "answers": ["I am writing to request information about the course.",
                         "I am writing to ask for information about the course.",
                         "I am writing to enquire about the course.", "I am writing to inquire about the course."],
             "explanation": "Sin contracciones ni «info»."},
            {"kind": "fill", "prompt": "Dear Sir or Madam, … Yours ___,", "answers": ["faithfully"],
             "explanation": "Sin nombre del destinatario → «Yours faithfully»."},
            {"kind": "fill", "prompt": "Informal: ___ from you soon! (Espero saber de ti)", "answers": ["hope to hear", "hoping to hear"],
             "explanation": "Cierre informal típico."},
        ],
    },
]

LESSONS_BY_ID: dict[str, dict] = {lesson["id"]: lesson for lesson in LESSONS}


def lesson_for(category: str, preferred: str | None = None) -> str | None:
    """The lesson to link from an error: the model's pick if it exists, else the category default."""
    if preferred and preferred in LESSONS_BY_ID:
        return preferred
    return CATEGORY_LESSON.get(category)


def public_lessons() -> list[dict]:
    """Lessons for the client, without the accepted answers (checking happens server-side)."""
    out = []
    for lesson in LESSONS:
        item = {k: v for k, v in lesson.items() if k != "exercise"}
        item["exercise"] = [{"kind": e["kind"], "prompt": e["prompt"]} for e in lesson["exercise"]]
        item["category_labels"] = [CATEGORIES[c] for c in lesson["categories"]]
        out.append(item)
    return out


# ------------------------------------------------------------------ checking
_CONTRACTIONS = {
    "won't": "will not", "can't": "cannot", "shan't": "shall not", "n't": " not",
    "i'm": "i am", "'re": " are", "'ve": " have", "'ll": " will", "'d": " would",
    "it's": "it is", "that's": "that is", "there's": "there is", "he's": "he is",
    "she's": "she is", "what's": "what is", "let's": "let us",
}
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def normalize_answer(text: str) -> str:
    """Lowercase, unify quotes/space, drop accents, end punctuation and expand contractions."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).lower().strip()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = text.strip(" .!?\"")
    for short in ("won't", "can't", "shan't"):
        text = re.sub(rf"\b{short}\b", _CONTRACTIONS[short], text)
    for short in ("i'm", "it's", "that's", "there's", "he's", "she's", "what's", "let's"):
        text = re.sub(rf"(?<![\w']){re.escape(short)}(?![\w'])", _CONTRACTIONS[short], text)
    for suffix in ("n't", "'re", "'ve", "'ll", "'d"):
        text = text.replace(suffix, _CONTRACTIONS[suffix])
    if text.startswith("'"):
        text = text[1:]  # fill answers like "'s" / "'ve forgotten"
    text = text.replace("cannot", "can not")
    return re.sub(r"\s+", " ", text).strip()


def check_answers(lesson_id: str, answers: list[str]) -> dict:
    """Check the user's answers against a lesson's exercise. Raises KeyError for unknown lessons."""
    lesson = LESSONS_BY_ID[lesson_id]
    results = []
    for i, item in enumerate(lesson["exercise"]):
        given = answers[i] if i < len(answers) and answers[i] is not None else ""
        accepted = {normalize_answer(a) for a in item["answers"]}
        if item["kind"] == "fill":
            # Accept short forms of "be" for fill-ins like "'s" -> "is".
            accepted |= {normalize_answer(a.replace("'s", "is")) for a in item["answers"] if a.startswith("'")}
        ok = bool(given.strip()) and normalize_answer(given) in accepted
        results.append({"correct": ok, "answer": item["answers"][0], "explanation": item["explanation"]})
    return {"lesson_id": lesson_id, "results": results,
            "score": sum(r["correct"] for r in results), "total": len(results)}
