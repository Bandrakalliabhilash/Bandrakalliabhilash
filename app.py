from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import itertools
import string
import nltk
from nltk.corpus import wordnet
from deep_translator import GoogleTranslator
from functools import lru_cache
from database.db import init_db
init_db()
from ai_engine.performance_tracker import save_result
import random

app = Flask(__name__)
init_db()
app.secret_key = "your-secret-key-change-this"

# Ensure NLTK data is available (quiet)
nltk.download('wordnet', quiet=True)
nltk.download('omw-1.4', quiet=True)

# Build set of English words (lowercased, underscores -> spaces)
english_words = set(w.replace("_", " ").lower() for w in wordnet.all_lemma_names())

INDIAN_LANGS = {
    "assamese": "as", "bengali": "bn", "dogri": "doi", "gujarati": "gu",
    "hindi": "hi", "kannada": "kn", "maithili": "mai",
    "malayalam": "ml", "marathi": "mr", "nepali": "ne", "odia": "or",
    "punjabi": "pa", "sanskrit": "sa","sindhi": "sd", "tamil": "ta",
    "telugu": "te", "urdu": "ur"
}
LANG_DISPLAY = [("en", "English"), *[(code, name.title()) for name, code in INDIAN_LANGS.items()]]

USERS = {
    "student1": {"pwd": "student1pwd", "role": "student"},
    "teacher1": {"pwd": "teacher1pwd", "role": "teacher"},
    "parent1": {"pwd": "parent1pwd", "role": "parent"},
}
ROLES = ["student", "teacher", "parent"]

@lru_cache(maxsize=10000)
def translate_meaning_cached(meaning: str, target_lang: str):
    """Translate a single English meaning to target_lang, with small fallbacks on error."""
    if not meaning:
        return None
    if target_lang == "en" or not target_lang:
        return meaning
    try:
        return GoogleTranslator(source="en", target=target_lang).translate(meaning)
    except Exception:
        fallback_map = {
            "kn": "ಅರ್ಥ ಲಭ್ಯವಿಲ್ಲ", "hi": "अर्थ उपलब्ध नहीं है", "te": "అర్థం అందుబాటులో లేదు",
            "ta": "பொருள் கிடைக்கவில்லை", "bn": "অর্থ পাওয়া যায়নি", "ml": "അർത്ഥം ലഭ്യമല്ല",
            "mr": "अर्थ उपलब्ध नाही", "gu": "અર્થ ઉપલબ્ધ નથી", "pa": "ਅਰਥ ਉਪਲਬਧ ਨਹੀਂ ਹੈ",
            "ur": "معنی دستیاب نہیں", "as": "অর্থ উপলব্ধ নহয়", "ne": "अर्थ उपलब्ध छैन",
        }
        return fallback_map.get(target_lang, "(Meaning not available)")

def get_meaning(word: str, lang: str = "en"):
    """Return first WordNet definition for `word`, translated to `lang` if requested."""
    synsets = wordnet.synsets(word.replace(" ", "_"))
    if not synsets:
        return None
    meaning = synsets[0].definition()
    return translate_meaning_cached(meaning, lang)

@app.route("/")
@app.route("/index")
def index():
    if session.get("user"):
        return render_template("index.html", languages=LANG_DISPLAY, user=session.get("user"), role=session.get("role"))
    return render_template("welcome.html")

@app.route("/gamebox")
def gamebox():
    return render_template("gamebox.html", user=session.get("user"), role=session.get("role"))

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action")
    lang = (data.get("lang") or "en").strip().lower()
    input_val = (data.get("input") or "").strip().lower()

    allowed_codes = {"en"} | set(INDIAN_LANGS.values())
    if lang not in allowed_codes:
        name_to_code = {name.lower(): code for name, code in INDIAN_LANGS.items()}
        if lang in name_to_code:
            lang = name_to_code[lang]

    if action == "letters_index":
        counts = {ch: 0 for ch in string.ascii_lowercase}
        for w in english_words:
            if w and w[0] in counts:
                counts[w[0]] += 1
        return jsonify({"status": "ok", "counts": counts})

    if action == "single":
        if not input_val or len(input_val) != 1 or not input_val.isalpha():
            return jsonify({"status": "error", "message": "Please provide exactly one letter (a–z)."}), 400
        found = sorted([w for w in english_words if w.startswith(input_val)])
        results = [{"word": w, "meaning": get_meaning(w, lang)} for w in found]
        return jsonify({"status": "ok", "count": len(results), "result": results})

    if action == "random":
        if not input_val or not input_val.isalpha() or not (2 <= len(input_val) <= 20):
            return jsonify({"status": "error", "message": "Enter 2–20 letters (a–z)."}), 400
        found = set()
        for i in range(1, len(input_val) + 1):
            for perm in set(itertools.permutations(input_val, i)):
                word = "".join(perm)
                if word in english_words:
                    found.add(word)
        results = [{"word": w, "meaning": get_meaning(w, lang)} for w in sorted(found)]
        return jsonify({"status": "ok", "count": len(results), "result": results})

    if action == "full_letter":
        if not input_val or len(input_val) != 1 or not input_val.isalpha():
            return jsonify({"status": "error", "message": "Provide one letter (a–z) for full dictionary view."}), 400
        found = sorted([w for w in english_words if w.startswith(input_val)])
        results = [{"word": w, "meaning": get_meaning(w, lang)} for w in found]
        return jsonify({"status": "ok", "count": len(results), "result": results})

    return jsonify({"status": "error", "message": "Unknown action."}), 400

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = USERS.get(username)
        if user and user.get("pwd") == password:
            session["user"] = username
            session["role"] = user.get("role", "student")
            flash(f"Logged in as {username} ({session['role']})", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.", "danger")
    return render_template("auth.html", show="login")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        role = request.form.get("role", "student")

        if not username or not password:
            flash("Please provide username and password.", "danger")
            return render_template("auth.html", show="register")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth.html", show="register")

        if username in USERS:
            flash("Username already exists. Please choose another.", "danger")
            return render_template("auth.html", show="register")

        USERS[username] = {"pwd": password, "role": role, "email": email}
        flash("Registered successfully — please login.", "success")
        return render_template("auth.html", show="login")
    return render_template("auth.html", show="register")

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("role", None)
    flash("Logged out.", "info")
    return redirect(url_for("login"))

@app.route("/game", methods=["GET","POST"])
def game():
    def pick_word():
        # pick words with visible length >=3 characters
        candidates = [w for w in english_words if len(w) >=3]
        while True:
            word = random.choice(candidates)
            synsets = wordnet.synsets(word.replace(" ", "_"))
            if synsets:
                return word, synsets[0].definition()

    if not session.get("game_word"):
        word, clue = pick_word()
        session["game_word"] = word
        session["game_clue"] = clue

    scrambled = "".join(random.sample(session["game_word"], len(session["game_word"])))
    clue = session.get("game_clue", "")
    feedback = None

    if request.method == "POST":
        guess = request.form.get("guess","").strip().lower()
        word = session.get("game_word")
        if guess == word:
            feedback = "Correct! 🎉"
            word, clue = pick_word()
            session["game_word"] = word
            session["game_clue"] = clue
            scrambled = "".join(random.sample(session["game_word"], len(session["game_word"])))
        else:
            feedback = "Try again!"
    return render_template("game.html", scrambled=scrambled, feedback=feedback, clue=clue)


@app.route("/dashboard")
def dashboard():
    from ai_engine.performance_tracker import get_topic_accuracy
    accuracy = get_topic_accuracy(session["user"])
    return render_template("dashboard.html", accuracy=accuracy)


@app.route("/game-mc", methods=["GET", "POST"])
def game_mc():
    def pick_word_and_meanings():
        # pick a word (len >=4) that has a WordNet definition, then prepare multiple meanings
        candidates = [w for w in english_words if len(w) >= 4]
        while True:
            word = random.choice(candidates)
            synsets = wordnet.synsets(word.replace(" ", "_"))
            if synsets:
                correct_meaning = synsets[0].definition()
                break

        all_meanings = set()
        # sample up to min(12000, total_words) candidates to gather distractors
        population = list(english_words)
        sample_size = min(12000, len(population))
        for w in random.sample(population, sample_size):
            syns = wordnet.synsets(w.replace(" ", "_"))
            if syns:
                m = syns[0].definition()
                if m != correct_meaning:
                    all_meanings.add(m)
                if len(all_meanings) >= 4:
                    break

        # ensure we have enough distractors; fallback to fewer options if not
        distractors = random.sample(list(all_meanings), k=min(len(all_meanings), 4))
        options = [correct_meaning] + distractors
        random.shuffle(options)
        return word, correct_meaning, options

    # Reset score if newgame requested
    if ("mc_correct_count" not in session 
        or "mc_total_count" not in session 
        or request.args.get("newgame")):
        session["mc_correct_count"] = 0
        session["mc_total_count"] = 0
        session["mc_feedback"] = ""
        session["mc_reveal"] = ""
        word, correct, options = pick_word_and_meanings()
        session["mc_word"] = word
        session["mc_correct"] = correct
        session["mc_options"] = options
        session["mc_answered"] = False

    # Handle POST (user submitted answer)
    if request.method == "POST":
        if not session.get("mc_answered", False):  # Only count if not already answered
            selected = request.form.get("option")
            word = session["mc_word"]
            correct = session["mc_correct"]
            session["mc_total_count"] += 1
            if selected == correct:
                session["mc_correct_count"] += 1
                session["mc_feedback"] = "Correct! 🎉"
            else:
                session["mc_feedback"] = "Try again! The correct answer is shown below."
            session["mc_reveal"] = correct
            session["mc_answered"] = True  # Mark as answered this question

    # On "Next", load new question and clear feedback
    if request.method == "GET" and request.args.get("new"):
        word, correct, options = pick_word_and_meanings()
        session["mc_word"] = word
        session["mc_correct"] = correct
        session["mc_options"] = options
        session["mc_feedback"] = ""
        session["mc_reveal"] = ""
        session["mc_answered"] = False

    score_str = f"{session.get('mc_correct_count',0)} / {session.get('mc_total_count',0)}"
    return render_template(
        "game_mc.html",
        word=session["mc_word"],
        options=session["mc_options"],
        feedback=session.get("mc_feedback",""),
        score=score_str,
        reveal_meaning=session.get("mc_reveal","")
    )

@app.route("/multi-meaning", methods=["GET", "POST"])
def multi_meaning():
    result = {}
    err = ""
    word = ""
    if request.method == "POST":
        word = request.form.get("word","").strip().lower()
        if len(word.split()) != 1:
            err = "Enter only one word."
        else:
            synsets = wordnet.synsets(word.replace(" ", "_"))
            if not synsets:
                err = "No meaning found for this word."
            else:
                en_meaning = synsets[0].definition()
                for code, name in LANG_DISPLAY:
                    if code == "en":
                        result["English"] = en_meaning
                    else:
                        try:
                            translated = GoogleTranslator(source="en", target=code).translate(en_meaning)
                        except Exception:
                            translated = "(Meaning not available)"
                        result[name] = translated

    return render_template("multi_meaning.html", err=err, word=word, result=result, languages=LANG_DISPLAY)

@app.route("/multi-meaning-sentence", methods=["GET", "POST"])
def multi_meaning_sentence():
    result = {}
    err = ""
    sentence = ""
    if request.method == "POST":
        sentence = request.form.get("sentence","").strip()
        if not sentence:
            err = "Please enter a sentence."
        else:
            for code, name in LANG_DISPLAY:
                try:
                    translated = GoogleTranslator(source="en", target=code).translate(sentence)
                except Exception:
                    translated = "(Translation not available)"
                result[name if code != 'en' else 'English'] = translated
    return render_template("multi_meaning_sentence.html", err=err, sentence=sentence, result=result, languages=LANG_DISPLAY)

@app.route("/game-articles", methods=["GET", "POST"])
def game_articles():
    # Some example questions (sentence with missing article, correct answer, and a simple rule/hint)
    questions = [
        {
            "text": "___ elephant is a large animal.",
            "options": ["A", "An", "The"],
            "answer": "An",
            "rule": "Use 'an' before words that begin with a vowel sound (a, e, i, o, u)."
        },
        {
            "text": "___ sun rises in the east.",
            "options": ["A", "An", "The"],
            "answer": "The",
            "rule": "Use 'the' when talking about something unique or already known."
        },
        {
            "text": "I saw ___ apple on the table.",
            "options": ["A", "An", "The"],
            "answer": "An",
            "rule": "Use 'an' before vowel sounds."
        },
        {
            "text": "She wants to read ___ book.",
            "options": ["A", "An", "The"],
            "answer": "A",
            "rule": "Use 'a' before words that begin with a consonant sound."
        },
        {
            "text": "___ moon shines at night.",
            "options": ["A", "An", "The"],
            "answer": "The",
            "rule": "Use 'the' for things known to everyone (like 'the moon')."
        },
        {
            "text": "I have ___ umbrella.",
            "options": ["A", "An", "The"],
            "answer": "An",
            "rule": "Use 'an' before vowel sounds."
        },
        {
            "text": "She bought ___ car yesterday.",
            "options": ["A", "An", "The"],
            "answer": "A",
            "rule": "Use 'a' before consonant sounds."
        },
        {
            "text": "___ earth goes around the sun.",
            "options": ["A", "An", "The"],
            "answer": "The",
            "rule": "Use 'the' for unique things or something mentioned before."
        },
        {
            "text": "He is ___ honest man.",
            "options": ["A", "An", "The"],
            "answer": "An",
            "rule": "Use 'an' before words that sound like a vowel ('honest' starts with a vowel sound)."
        },
        {
            "text": "___ cat is sitting on the wall.",
            "options": ["A", "An", "The"],
            "answer": "The",
            "rule": "Use 'the' when talking about something specific."
        },
    ]
    # For score: session stores current score, total played, and q_index
    if "article_score" not in session or request.args.get("restart"):
        session["article_score"] = 0
        session["article_total"] = 0
        session["article_q_index"] = random.randint(0, len(questions)-1)
        session["article_feedback"] = ""
    # On "Next" show a new question (random)
    if request.args.get("next"):
        session["article_q_index"] = random.randint(0, len(questions)-1)
        session["article_feedback"] = ""
    feedback = session.get("article_feedback", "")
    score_str = f"{session.get('article_score',0)} / {session.get('article_total',0)}"
    q = questions[session["article_q_index"]]
    if request.method == "POST":
        selected = request.form.get("option")
        session["article_total"] += 1
        if selected == q["answer"]:
            session["article_score"] += 1
            feedback = f"Correct! '{selected}' is the right article. Rule: {q['rule']}"
        else:
            feedback = f"Wrong! The correct answer is '{q['answer']}'. Rule: {q['rule']}"
        session["article_feedback"] = feedback
    return render_template("game_articles.html", question=q["text"], options=q["options"], score=score_str, feedback=feedback)


@app.route("/game-tense", methods=["GET", "POST"])
def game_tense():
    # Example sentences classified as Present, Past, Future
    questions = [
        {
            "sentence": "She is eating an apple.",
            "options": ["Present", "Past", "Future"],
            "answer": "Present",
            "rule": "Present tense describes actions happening now or regularly."
        },
        {
            "sentence": "They went to school yesterday.",
            "options": ["Present", "Past", "Future"],
            "answer": "Past",
            "rule": "Past tense describes actions that happened in the past."
        },
        {
            "sentence": "He will buy a new car.",
            "options": ["Present", "Past", "Future"],
            "answer": "Future",
            "rule": "Future tense describes actions that will happen later."
        },
        {
            "sentence": "The sun rises in the east.",
            "options": ["Present", "Past", "Future"],
            "answer": "Present",
            "rule": "Present tense can be used for general truths."
        },
        {
            "sentence": "The boys played cricket.",
            "options": ["Present", "Past", "Future"],
            "answer": "Past",
            "rule": "Past tense is used to describe completed actions."
        }
    ]

    # Initialize session values
    if "tense_score" not in session or request.args.get("restart"):
        session["tense_score"] = 0
        session["tense_total"] = 0
        session["tense_q_index"] = random.randint(0, len(questions)-1)
        session["tense_feedback"] = ""

    # Next question
    if request.args.get("next"):
        session["tense_q_index"] = random.randint(0, len(questions)-1)
        session["tense_feedback"] = ""

    feedback = session.get("tense_feedback", "")
    score_str = f"{session.get('tense_score',0)} / {session.get('tense_total',0)}"
    q = questions[session["tense_q_index"]]

    if request.method == "POST":
        selected = request.form.get("option")
        username = session.get("user")
        difficulty = "medium"   # For now fixed, later we make dynamic

        session["tense_total"] += 1

        if selected == q["answer"]:
            session["tense_score"] += 1
            feedback = f"Correct! This is a '{selected}' tense. Rule: {q['rule']}"
            
            # 🔥 SAVE AI DATA (Correct Answer)
            if username:
                save_result(username, "tense", difficulty, 1)

        else:
            feedback = f"Wrong! The correct answer is '{q['answer']}'. Rule: {q['rule']}"
            
            # 🔥 SAVE AI DATA (Wrong Answer)
            if username:
                save_result(username, "tense", difficulty, 0)

        session["tense_feedback"] = feedback

    return render_template(
        "game_tense.html",
        question=q["sentence"],
        options=q["options"],
        score=score_str,
        feedback=feedback
    )
@app.route("/game-pos", methods=["GET", "POST"])
def game_pos():
    # Example questions: sentence, part to identify, choices, correct, explanation, examples
    questions = [
        {
            "sentence": "Wow! That was an amazing performance.",
            "ask": "Which word in this sentence is an interjection?",
            "options": ["was", "an", "Wow", "performance"],
            "answer": "Wow",
            "pos": "Interjection",
            "explanation": "An interjection expresses strong emotion or surprise.",
            "examples": ["Wow!", "Ouch!", "Hey!", "Bravo!", "Oops!"]
        },{
            "sentence": "She quickly finished her homework.",
            "ask": "Which word in this sentence is an adverb?",
            "options": ["finished", "quickly", "homework", "her"],
            "answer": "quickly",
            "pos": "Adverb",
            "explanation": "An adverb describes how an action is performed.",
            "examples": ["quickly", "slowly", "happily", "sadly", "badly"]
        },{
            "sentence": "The small dog barked loudly.",
            "ask": "Which word in this sentence is an adjective?",
            "options": ["dog", "barked", "small", "loudly"],
            "answer": "small",
            "pos": "Adjective",
            "explanation": "An adjective describes or modifies a noun.",
            "examples": ["small", "big", "red", "happy", "old"]
        },{
            "sentence": "He and his brother play cricket.",
            "ask": "Which word in this sentence is a conjunction?",
            "options": ["He", "his", "play", "and"],
            "answer": "and",
            "pos": "Conjunction",
            "explanation": "A conjunction joins words or groups of words.",
            "examples": ["and", "or", "but", "so", "because"]
        },{
            "sentence": "The cat sat under the table.",
            "ask": "Which word in this sentence is a preposition?",
            "options": ["cat", "under", "sat", "the"],
            "answer": "under",
            "pos": "Preposition",
            "explanation": "A preposition shows the relationship of a noun or pronoun with another word.",
            "examples": ["under", "on", "in", "at", "by"]
        },{
            "sentence": "She is my friend.",
            "ask": "Which word in this sentence is a pronoun?",
            "options": ["She", "friend", "is", "my"],
            "answer": "She",
            "pos": "Pronoun",
            "explanation": "A pronoun replaces a noun.",
            "examples": ["I", "he", "she", "it", "they"]
        },{
            "sentence": "My brother gave me a gift.",
            "ask": "Which word in this sentence is a noun?",
            "options": ["gave", "me", "gift", "brother"],
            "answer": "gift",
            "pos": "Noun",
            "explanation": "A noun is the name of a person, place, thing, or idea.",
            "examples": ["book", "dog", "Abhilash", "city", "joy"]
        },{
            "sentence": "She runs fast.",
            "ask": "Which word in this sentence is a verb?",
            "options": ["She", "runs", "fast", "city"],
            "answer": "runs",
            "pos": "Verb",
            "explanation": "A verb is an action word.",
            "examples": ["run", "jump", "eat", "sleep", "play"]
        },{
            "sentence": "Aishwarya and Priya were happy.",
            "ask": "Which word in this sentence is a conjunction?",
            "options": ["happy", "and", "were", "Priya"],
            "answer": "and",
            "pos": "Conjunction",
            "explanation": "A conjunction connects words, phrases, or clauses.",
            "examples": ["and", "but", "because", "so", "or"]
        },{
            "sentence": "Ouch! I hurt my leg.",
            "ask": "Which word in this sentence is an interjection?",
            "options": ["Ouch", "hurt", "my", "leg"],
            "answer": "Ouch",
            "pos": "Interjection",
            "explanation": "Interjections express feelings or emotions.",
            "examples": ["Ouch!", "Hey!", "Oops!", "Wow!", "Yay!"]
        },{
            "sentence": "The birds fly in the sky.",
            "ask": "Which word in this sentence is a preposition?",
            "options": ["fly", "birds", "sky", "in"],
            "answer": "in",
            "pos": "Preposition",
            "explanation": "Prepositions show the position or relationship between words.",
            "examples": ["in", "on", "at", "under", "over"]
        },{
            "sentence": "That red car is very fast.",
            "ask": "Which word in this sentence is an adjective?",
            "options": ["car", "red", "very", "fast"],
            "answer": "red",
            "pos": "Adjective",
            "explanation": "Adjectives describe nouns.",
            "examples": ["red", "tall", "smart", "young", "pretty"]
        },{
            "sentence": "I saw a monkey at the zoo.",
            "ask": "Which word in this sentence is a noun?",
            "options": ["I", "monkey", "saw", "at"],
            "answer": "monkey",
            "pos": "Noun",
            "explanation": "Nouns are naming words.",
            "examples": ["monkey", "zoo", "tree", "student", "apple"]
        },{
            "sentence": "We are going to the market.",
            "ask": "Which word in this sentence is a verb?",
            "options": ["going", "market", "the", "We"],
            "answer": "going",
            "pos": "Verb",
            "explanation": "Verbs are action or being words.",
            "examples": ["go", "have", "see", "eat", "write"]
        },{
            "sentence": "She herself made the dress.",
            "ask": "Which word in this sentence is a pronoun?",
            "options": ["She", "made", "dress", "herself"],
            "answer": "herself",
            "pos": "Pronoun",
            "explanation": "Pronouns take the place of nouns.",
            "examples": ["you", "me", "him", "her", "ourselves"]
        },{
            "sentence": "He drives slowly.",
            "ask": "Which word in this sentence is an adverb?",
            "options": ["drives", "He", "slowly", "drives"],
            "answer": "slowly",
            "pos": "Adverb",
            "explanation": "Adverbs tell us more about the verb.",
            "examples": ["slowly", "easily", "well", "quietly", "quickly"]
        },{
            "sentence": "Please take your seat.",
            "ask": "Which word in this sentence is a verb?",
            "options": ["your", "seat", "take", "Please"],
            "answer": "take",
            "pos": "Verb",
            "explanation": "Verbs are doing words.",
            "examples": ["take", "sleep", "walk", "shake", "sing"]
        },{
            "sentence": "Rahul opened the old box.",
            "ask": "Which word in this sentence is an adjective?",
            "options": ["box", "opened", "Rahul", "old"],
            "answer": "old",
            "pos": "Adjective",
            "explanation": "Adjectives describe qualities of nouns.",
            "examples": ["old", "new", "beautiful", "black", "funny"]
        },{
            "sentence": "The ball is under the table.",
            "ask": "Which word in this sentence is a preposition?",
            "options": ["ball", "under", "table", "is"],
            "answer": "under",
            "pos": "Preposition",
            "explanation": "Prepositions show location.",
            "examples": ["under", "in", "on", "above", "below"]
        },{
            "sentence": "Wow! You did a great job!",
            "ask": "Which word in this sentence is an interjection?",
            "options": ["Wow", "You", "great", "job"],
            "answer": "Wow",
            "pos": "Interjection",
            "explanation": "Interjections show strong feelings.",
            "examples": ["Wow!", "Hey!", "Oh!", "Eureka!", "Oh no!"]
        },{
            "sentence": "She jumped high.",
            "ask": "Which word in this sentence is an adverb?",
            "options": ["jumped", "She", "high", "jumped"],
            "answer": "high",
            "pos": "Adverb",
            "explanation": "Adverbs answer 'how', 'when', 'where', or 'to what extent'.",
            "examples": ["high", "fast", "always", "tomorrow", "here"]
        },{
            "sentence": "The dog barked at the stranger.",
            "ask": "Which word in this sentence is a preposition?",
            "options": ["dog", "the", "barked", "at"],
            "answer": "at",
            "pos": "Preposition",
            "explanation": "Prepositions link nouns/pronouns to other words.",
            "examples": ["at", "by", "with", "from", "to"]
        },{
            "sentence": "She will bring her book and pen.",
            "ask": "Which word in this sentence is a conjunction?",
            "options": ["bring", "her", "and", "book"],
            "answer": "and",
            "pos": "Conjunction",
            "explanation": "Conjunctions join together words or groups.",
            "examples": ["and", "or", "but", "because", "if"]
        },{
            "sentence": "He gave me five apples.",
            "ask": "Which word in this sentence is a noun?",
            "options": ["gave", "me", "five", "apples"],
            "answer": "apples",
            "pos": "Noun",
            "explanation": "Nouns name people, places, things, or ideas.",
            "examples": ["apples", "students", "school", "idea", "river"]
        },{
            "sentence": "Her dress is very beautiful.",
            "ask": "Which word in this sentence is an adjective?",
            "options": ["dress", "Her", "very", "beautiful"],
            "answer": "beautiful",
            "pos": "Adjective",
            "explanation": "Adjectives describe nouns more specifically.",
            "examples": ["beautiful", "green", "thin", "heavy", "smooth"]
        }
    ]

    # initialize session values if missing or restart requested
    if "pos_score" not in session or request.args.get("restart"):
        session["pos_score"] = 0
        session["pos_total"] = 0
        session["pos_q_index"] = random.randint(0, len(questions)-1)
        session["pos_feedback"] = ""

    # Next question requested
    if request.args.get("next"):
        session["pos_q_index"] = random.randint(0, len(questions)-1)
        session["pos_feedback"] = ""

    # guard: ensure index is valid
    if session["pos_q_index"] >= len(questions):
        session["pos_q_index"] = 0

    q = questions[session["pos_q_index"]]
    feedback = ""
    score_str = f"{session['pos_score']} / {session['pos_total']}"


    if request.method == "POST":
        user_choice = request.form.get("option")
        session["pos_total"] += 1
        if user_choice == q["answer"]:
            session["pos_score"] += 1
            feedback = f"✅ Correct! '{user_choice}' is a {q['pos']}."
        else:
            feedback = f"❌ Wrong! The correct answer is '{q['answer']}' ({q['pos']}). Explanation: {q['explanation']}"
        session["pos_feedback"] = feedback

    return render_template(
        "game_pos.html",
        question=q["sentence"],
        ask=q["ask"],
        options=q["options"],
        feedback=session.get("pos_feedback", ""),
        pos=q["pos"],
        explanation=q["explanation"],
        examples=q["examples"],
        score=f"{session['pos_score']} / {session['pos_total']}"
    )
    
@app.route("/game-speech", methods=["GET", "POST"])
def game_speech():
    questions = [
        {
            "sentence": '"I am reading a book," he said.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Direct speech quotes the exact words spoken (in quotes).",
            "examples": [
                '"How are you?" asked Tom.',
                '"She loves music," said Harry.',
                '"I will come tomorrow," said Sita.',
                '"Where are you going?" he asked.',
                '"Can I help you?" she said.'
            ]
        },
        {
            "sentence": 'He said that he was reading a book.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "Indirect speech reports what was said, not the exact words (no quotes).",
            "examples": [
                'Tom asked how I was.',
                'Harry said that she loves music.',
                'Sita said that she would come the next day.',
                'He asked where I was going.',
                'She asked if she could help me.'
            ]
        },
        {
            "sentence": '"She will visit us next week," said Mother.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Direct speech uses quotation marks for actual words spoken.",
            "examples": [
                '"You must go now," she said.',
                '"I like drawing," said Manju.',
                '"Please sit down," said the teacher.',
                '"What time is it?" asked Ram.',
                '"He will be late," said Dad.'
            ]
        },
        {
            "sentence": 'Mother said that she would visit us the following week.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "Indirect speech often changes tense, pronouns, and time expressions.",
            "examples": [
                'She said that she liked drawing.',
                'Ram asked what time it was.',
                'Dad said that he would be late.',
                'Manju said that she liked painting.',
                'Teacher asked the students to sit down.'
            ]
        },
        {
            "sentence": '"I have finished my homework," said Ravi.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Direct speech can include statements of fact in quotes.",
            "examples": [
                '"My name is John," he said.',
                '"We are going out," said Maya.',
                '"It is raining," said the boy.',
                '"May I come in?" she asked.',
                '"I want a new toy," said Aman.'
            ]
        },
        {
            "sentence": 'Ravi said that he had finished his homework.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "Indirect speech is used for reporting what someone said.",
            "examples": [
                'John said that his name was John.',
                'Maya said that they were going out.',
                'The boy said that it was raining.',
                'She asked if she could come in.',
                'Aman said that he wanted a new toy.'
            ]
        },
        {
            "sentence": '"Are you coming to my party?" asked Priya.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Questions in direct speech preserve the sender's words.",
            "examples": [
                '"Can I ask you a question?" he said.',
                '"Did you see the movie?" asked Arun.',
                '"Will you help me?" the girl asked.',
                '"Is this your book?" said the teacher.',
                '"Have you done your homework?" Mom asked.'
            ]
        },
        {
            "sentence": 'Priya asked if I was coming to her party.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "In reporting questions, indirect speech changes word order, tense, and pronouns.",
            "examples": [
                'He asked if he could ask a question.',
                'Arun asked if I had seen the movie.',
                'The girl asked if I would help her.',
                'Teacher asked whether it was my book.',
                'Mom asked if I had done my homework.'
            ]
        },
        {
            "sentence": '"Please pass the salt," he said.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Requests or commands can be direct speech (with quotes and said/told).",
            "examples": [
                '"Open the window," she said.',
                '"Read the lesson," the teacher said.',
                '"Finish your lunch," Mom said.',
                '"Bring me the pen," said Dad.',
                '"Write your name," the clerk said.'
            ]
        },
        {
            "sentence": 'He asked me to pass the salt.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "Commands in indirect speech use 'told/asked to...'.",
            "examples": [
                'She told me to open the window.',
                'The teacher asked us to read the lesson.',
                'Mom told me to finish my lunch.',
                'Dad asked me to bring him the pen.',
                'The clerk told him to write his name.'
            ]
        },
        {
            "sentence": '"I cannot find my keys," she said.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Statements and opinions quoted are direct speech.",
            "examples": [
                '"It hurts," he said.',
                '"I love dancing," said Sara.',
                '"We are leaving now," Mom said.',
                '"I am tired," said the student.',
                '"He is hungry," said the teacher.'
            ]
        },
        {
            "sentence": 'She said that she could not find her keys.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "Reporting opinions is indirect speech, typically using 'that'.",
            "examples": [
                'He said that it hurt.',
                'Sara said that she loved dancing.',
                'Mom said that they were leaving then.',
                'The student said that he was tired.',
                'Teacher said that he was hungry.'
            ]
        },
        {
            "sentence": '"Bring me some water," said Grandpa.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Direct speech states instructions exactly.",
            "examples": [
                '"Switch off the light," he said.',
                '"Help me," said the old man.',
                '"Wash your hands," Mom said.',
                '"Eat your food," she said.',
                '"Run fast," the coach said.'
            ]
        },
        {
            "sentence": 'Grandpa asked me to bring him some water.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "Indirect speech uses 'asked/told to' for actions.",
            "examples": [
                'He asked me to switch off the light.',
                'The old man asked for help.',
                'Mom asked me to wash my hands.',
                'She told me to eat my food.',
                'The coach told us to run fast.'
            ]
        },
        {
            "sentence": '"I will call you tonight," he said.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Direct speech uses the actual words spoken.",
            "examples": [
                '"See you soon," she said.',
                '"I missed the bus," he said.',
                '"Let’s go out," Ram said.',
                '"That’s my book," she said.',
                '"You did well," the teacher said.'
            ]
        },
        {
            "sentence": 'He said that he would call me that night.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "In indirect speech, time words and tenses may change.",
            "examples": [
                'She said that she would see me soon.',
                'He said that he had missed the bus.',
                'Ram suggested that we go out.',
                'She said that it was her book.',
                'The teacher told me I had done well.'
            ]
        },
        {
            "sentence": '"Let’s go to the park," said Rohan.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Direct speech can quote suggestions/plans.",
            "examples": [
                '"What do you want?" she asked.',
                '"Be quick!" shouted Mom.',
                '"I like sports," said Arun.',
                '"Look out!" cried the driver.',
                '"I am late," said the teacher.'
            ]
        },
        {
            "sentence": 'Rohan suggested that we go to the park.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "Indirect speech paraphrases the speaker’s intention.",
            "examples": [
                'She asked what I wanted.',
                'Mom shouted to be quick.',
                'Arun said that he liked sports.',
                'The driver cried to look out.',
                'Teacher said that she was late.'
            ]
        },
        {
            "sentence": '"You must finish your work," said Dad.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Direct speech repeats command with quotes.",
            "examples": [
                '"Don’t forget your bag," Mom said.',
                '"Clean the room," said teacher.',
                '"Close the window," said he.',
                '"Stay quiet," said guard.',
                '"Eat your food," Mom said.'
            ]
        },
        {
            "sentence": 'Dad told me that I must finish my work.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "Indirect speech for command often uses ‘told’.",
            "examples": [
                'Mom told me not to forget my bag.',
                'Teacher told to clean the room.',
                'He told to close the window.',
                'Guard told to stay quiet.',
                'Mom told me to eat my food.'
            ]
        },
        {
            "sentence": '"Where do you live?" she asked.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Direct",
            "explanation": "Direct speech has exact question with quotes.",
            "examples": [
                '"How old are you?" asked teacher.',
                '"What is your name?" he asked.',
                '"Where are you from?" asked friend.',
                '"What color is this?" annoyed Mom.',
                '"Who cooked lunch?" Dad asked.'
            ]
        },
        {
            "sentence": 'She asked where I lived.',
            "ask": "Is this sentence in direct or indirect speech?",
            "options": ["Direct", "Indirect"],
            "answer": "Indirect",
            "explanation": "Indirect speech reporting questions changes order and pronouns.",
            "examples": [
                'Teacher asked how old I was.',
                'He asked what my name was.',
                'Friend asked where I was from.',
                'Mom asked what color that was.',
                'Dad asked who cooked lunch.'
            ]
        }
    ]
    if "speech_score" not in session or request.args.get("restart"):
        session["speech_score"] = 0
        session["speech_total"] = 0
        session["speech_q_index"] = random.randint(0, len(questions)-1)
        session["speech_feedback"] = ""
    if request.args.get("next"):
        session["speech_q_index"] = random.randint(0, len(questions)-1)
        session["speech_feedback"] = ""
    feedback = session.get("speech_feedback", "")
    score_str = f"{session.get('speech_score',0)} / {session.get('speech_total',0)}"
    q = questions[session["speech_q_index"]]
    if request.method == "POST":
        selected = request.form.get("option")
        session["speech_total"] += 1
        if selected == q["answer"]:
            session["speech_score"] += 1
            feedback = f"✅ Correct! This is {q['answer']} speech. Explanation: {q['explanation']}"
        else:
            feedback = f"❌ Wrong! The correct answer is {q['answer']}. Explanation: {q['explanation']}"
        session["speech_feedback"] = feedback
    return render_template("game_speech.html",
        sentence=q["sentence"], ask=q["ask"], options=q["options"],
        score=score_str, feedback=feedback,
        explanation=q["explanation"], examples=q["examples"])

@app.route("/game-kids")
def game_kids():
    # Simple, child-friendly grammar questions.
    kids_questions = [
        {
            "id": 1,
            "type": "articles",
            "sentence": "___ apple fell from the tree.",
            "blank": "___",
            "options": ["A", "An", "The"],
            "answer": "An",
            "hint": "Use 'an' before vowel sounds."
        },
        {
            "id": 2,
            "type": "pos",
            "sentence": "The dog barks loudly.",
            "ask": "Which word is the verb?",
            "options": ["dog", "barks", "loudly", "the"],
            "answer": "barks",
            "hint": "Verbs show action."
        },
        {
            "id": 3,
            "type": "tense",
            "sentence": "She will go to school tomorrow.",
            "ask": "Which tense is this?",
            "options": ["Present", "Past", "Future"],
            "answer": "Future",
            "hint": "Look for 'will' — that's future."
        },
        {
            "id": 4,
            "type": "pos",
            "sentence": "The colorful kite flew high.",
            "ask": "Which word is an adjective?",
            "options": ["flew", "kite", "colorful", "high"],
            "answer": "colorful",
            "hint": "Adjectives describe nouns."
        },
        {
            "id": 5,
            "type": "articles",
            "sentence": "Can I have ___ orange?",
            "blank": "___",
            "options": ["A", "An", "The"],
            "answer": "An",
            "hint": "Use 'an' before a vowel sound."
        }
    ]
    # Render the kid's game template with the questions embedded as JSON
    return render_template("game_kids.html", questions=kids_questions, user=session.get("user"), role=session.get("role"))


@app.route("/yogi", methods=["GET", "POST"])
def yogi():
    # Only common, easy words (edit this list as needed)
    common_words = [
        "apple", "banana", "cat", "dog", "fish", "book", "tree", "house", "chair",
        "milk", "blue", "green", "grass", "star", "car", "bird", "water", "door",
        "duck", "cake", "sun", "table", "school", "train", "sweet", "light"
    ]
    if not session.get("game_word"):
        while True:
            word = random.choice(common_words)
            synsets = wordnet.synsets(word)
            if synsets:
                break
        session["game_word"] = word
        session["game_clue"] = synsets[0].definition().capitalize()
    word = session["game_word"]
    # Ensure scrambled != original
    scrambled = word
    while scrambled == word:
        scrambled = "".join(random.sample(word, len(word)))
    clue = session.get("game_clue", "")
    feedback = None
    show_hint = True  # Set to False if you do not want to show first letter
    if request.method == "POST":
        guess = request.form.get("guess", "").strip().lower()
        if guess == word:
            feedback = "Correct! 🎉"
            while True:
                word = random.choice(common_words)
                synsets = wordnet.synsets(word)
                if synsets:
                    break
            session["game_word"] = word
            session["game_clue"] = synsets[0].definition().capitalize()
            scrambled = word
            while scrambled == word:
                scrambled = "".join(random.sample(word, len(word)))
            clue = session["game_clue"]
        else:
            feedback = "Try again! 😊"
    return render_template(
        "yogi.html",
        scrambled=scrambled,
        feedback=feedback,
        clue=clue,
        length=len(session["game_word"]),
        first_letter=session["game_word"][0] if show_hint else None
    )

@app.route("/rahul", methods=["GET", "POST"])
def rahul():
    # Only easy, familiar words for children
    kid_words = [
        "apple", "banana", "cat", "dog", "fish", "book", "tree", "house", "chair",
        "milk", "blue", "green", "grass", "star", "car", "bird", "water", "door",
        "duck", "cake", "sun", "table", "school", "train", "sweet", "light"
    ]

    def pick_word_and_meanings():
        while True:
            word = random.choice(kid_words)
            synsets = wordnet.synsets(word)
            if synsets:
                correct_meaning = synsets[0].definition().capitalize()
                break

        distractors = []
        for w in random.sample(kid_words, len(kid_words)):
            if w == word:
                continue
            syns = wordnet.synsets(w)
            if syns:
                m = syns[0].definition().capitalize()
                if m != correct_meaning and m not in distractors:
                    distractors.append(m)
            if len(distractors) >= 3:
                break
        # Always 4 options max
        options = [correct_meaning] + distractors
        options = options[:4]
        random.shuffle(options)
        return word, correct_meaning, options

    if ("mc_correct_count" not in session 
        or "mc_total_count" not in session 
        or request.args.get("newgame")):
        session["mc_correct_count"] = 0
        session["mc_total_count"] = 0
        session["mc_feedback"] = ""
        session["mc_reveal"] = ""
        word, correct, options = pick_word_and_meanings()
        session["mc_word"] = word
        session["mc_correct"] = correct
        session["mc_options"] = options
        session["mc_answered"] = False

    if request.method == "POST":
        if not session.get("mc_answered", False):
            selected = request.form.get("option")
            word = session["mc_word"]
            correct = session["mc_correct"]
            session["mc_total_count"] += 1
            if selected == correct:
                session["mc_correct_count"] += 1
                session["mc_feedback"] = "Correct! 🎉"
            else:
                session["mc_feedback"] = "Try again! The correct answer is shown below."
            session["mc_reveal"] = correct
            session["mc_answered"] = True

    if request.method == "GET" and request.args.get("new"):
        word, correct, options = pick_word_and_meanings()
        session["mc_word"] = word
        session["mc_correct"] = correct
        session["mc_options"] = options
        session["mc_feedback"] = ""
        session["mc_reveal"] = ""
        session["mc_answered"] = False

    # Bonus: show scrambled word as an extra clue
    word_scrambled = "".join(random.sample(session["mc_word"], len(session["mc_word"])))

    score_str = f"{session.get('mc_correct_count',0)} / {session.get('mc_total_count',0)}"
    return render_template(
        "rahul.html",
        word=session["mc_word"],
        word_scrambled=word_scrambled,
        options=session["mc_options"],
        feedback=session.get("mc_feedback",""),
        score=score_str,
        reveal_meaning=session.get("mc_reveal","")
    )
    
@app.route("/darshan", methods=["GET", "POST"])
def darshan():
    # Simple sentences for question tag practice
    tag_sentences = [
        ("You are a student", "aren't you?"),
        ("He is a teacher", "isn't he?"),
        ("She can swim", "can't she?"),
        ("We are friends", "aren't we?"),
        ("It is raining", "isn't it?"),
        ("They have a ball", "don't they?"),
        ("She likes apples", "doesn't she?"),
        ("You play football", "don't you?"),
        ("He was late", "wasn't he?"),
        ("Dogs bark", "don't they?"),
        ("The cat is sleeping", "isn't it?"),
        ("It was cold", "wasn't it?"),
        ("We should go", "shouldn't we?"),
        ("Tom played yesterday", "didn't he?"),
        ("They aren’t late", "are they?"),
    ]
    tag_distractors = [
        "is she?", "has he?", "was I?", "do we?", "aren't it?", "does she?",
        "wasn't they?", "can they?", "don't it?", "don't you?", "should we?",
        "isn't he?", "isn't it?", "hasn't she?", "did they?", "aren't we?",
        "doesn't they?", "was it?", "didn't she?", "can it?"
    ]

    def pick_question_tag_mode():
        sent, correct_tag = random.choice(tag_sentences)
        distractor_opts = set(tag_distractors)
        distractor_opts.discard(correct_tag)
        distractors = random.sample(list(distractor_opts), 3)
        options = [correct_tag] + distractors
        random.shuffle(options)
        return {
            "word": sent,
            "options": options,
            "correct": correct_tag,
            "display": f'Choose the right question tag for: <b>{sent}, ...</b>',
        }

    # Score initialization or reset
    if ("qt_correct_count" not in session 
        or "qt_total_count" not in session 
        or request.args.get("newgame")):
        session["qt_correct_count"] = 0
        session["qt_total_count"] = 0
        session["qt_feedback"] = ""
        session["qt_reveal"] = ""
        q = pick_question_tag_mode()
        session["qt_qdata"] = q
        session["qt_answered"] = False

    if request.method == "POST":
        if not session.get("qt_answered", False):
            selected = request.form.get("option")
            q = session["qt_qdata"]
            session["qt_total_count"] += 1
            if selected == q["correct"]:
                session["qt_correct_count"] += 1
                session["qt_feedback"] = "Correct! 🎉"
            else:
                session["qt_feedback"] = "Try again! The correct answer is shown below."
            session["qt_reveal"] = q["correct"]
            session["qt_answered"] = True

    if request.method == "GET" and request.args.get("new"):
        q = pick_question_tag_mode()
        session["qt_qdata"] = q
        session["qt_feedback"] = ""
        session["qt_reveal"] = ""
        session["qt_answered"] = False

    q = session["qt_qdata"]
    score_str = f"{session.get('qt_correct_count', 0)} / {session.get('qt_total_count', 0)}"
    return render_template(
        "darshan.html",
        question=q["display"],
        word=q["word"],
        options=q["options"],
        feedback=session.get("qt_feedback", ""),
        score=score_str,
        reveal_meaning=session.get("qt_reveal", ""),
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
