"""Development set v2 (goal G2.1): dialogues built by varying declared dimensions.

Nothing here is written one sentence at a time. A dialogue is a *plan* (who holds
what, who gives what to whom, which questions follow) and a *setting* of the
declared dimensions below; the surface sentence of every turn is produced from
the plan by the small grammar of each language in this file. The dimension
values are assigned to dialogues by a balanced table (each value appears equally
often; each dimension is shuffled on its own by the recorded seed), and the names,
items and amounts are drawn with the same seed. The expected answer of every turn is computed
from the plan's events, never typed.

After generation the dialogues are split by the same seed into a build half (2/3)
and a check half (1/3), stratified by language; the split is written to
``split.txt``. Rules are written against the build half only.

    python data/benchmarks/dialogues_dev2/build.py          # writes *.json and split.txt
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20260923
SCHEMA = "marco1-dialogue-gate-v1"
PER_LANGUAGE = 36

# ---------------------------------------------------------------------------
# declared dimensions
# ---------------------------------------------------------------------------
DIMENSIONS = {
    "ko": {
        "word_order": ["canonical", "object_first", "recipient_first", "receiver_subject"],
        "register": ["banmal", "plain", "haeyo", "hapsyo"],
        "split": ["one_fact_per_turn", "two_facts_one_turn", "two_sentences_one_turn"],
        "numeral_form": ["digits", "native", "sino", "digits_spaced"],
        "counter": ["specific", "general"],
        "possession_frame": ["existential", "possessive_verb", "dative_existential", "copula"],
        "name_script": ["native", "native", "native", "other"],
        "name_suffix": ["bare", "suffixed"],
        "item_script": ["native", "native", "native", "other"],
        "question_form": ["exist", "now", "left", "have", "relative"],
        "question_position": ["after", "after", "before"],
        "transfer_verb": ["give", "hand", "lend", "give", "pass_on"],
    },
    "en": {
        "word_order": ["double_object", "prepositional", "receiver_subject", "passive"],
        "register": ["neutral", "casual", "formal"],
        "split": ["one_fact_per_turn", "two_facts_one_turn", "two_sentences_one_turn"],
        "numeral_form": ["digits", "words"],
        "counter": ["bare", "bare", "measure"],
        "possession_frame": ["has", "had", "owns", "got", "holding"],
        "name_script": ["native", "native", "native", "other"],
        "name_suffix": ["bare"],
        "item_script": ["native"],
        "question_form": ["have", "now", "got", "short", "left"],
        "question_position": ["after", "after", "before"],
        "transfer_verb": ["give", "hand", "pass", "lend", "give"],
    },
}

# ---------------------------------------------------------------------------
# lexicon (names, items) -- slots, not sentences
# ---------------------------------------------------------------------------
KO_NAMES = ["서연", "도윤", "하은", "지호", "예린", "민재", "수아", "태오", "나윤", "건우", "채원", "시우",
            "유나", "준서", "다인", "현우", "소율", "재민", "가은", "우진", "보람", "한결", "은호", "루아",
            "초롱", "다솜", "윤슬", "새봄", "이준", "석진", "혜원", "정민"]
KO_ROMAN = {"서연": "Seoyeon", "도윤": "Doyun", "하은": "Haeun", "지호": "Jiho", "예린": "Yerin", "민재": "Minjae",
            "수아": "Sua", "태오": "Taeo", "나윤": "Nayun", "건우": "Geonu", "채원": "Chaewon", "시우": "Siu",
            "유나": "Yuna", "준서": "Junseo", "다인": "Dain", "현우": "Hyeonu", "소율": "Soyul", "재민": "Jaemin",
            "가은": "Gaeun", "우진": "Ujin", "보람": "Boram", "한결": "Hangyeol", "은호": "Eunho", "루아": "Rua",
            "초롱": "Chorong", "다솜": "Dasom", "윤슬": "Yunseul", "새봄": "Saebom", "이준": "Ijun",
            "석진": "Seokjin", "혜원": "Hyewon", "정민": "Jeongmin"}
KO_LATIN_NAMES = {"Leo": False, "Mia": False, "Sam": True, "Ben": True, "Nora": False, "Hugo": False,
                  "Ivy": False, "Max": False, "Tom": True, "Eva": False, "Liam": True, "Zoe": False}
EN_NAMES = ["Aria", "Fenn", "Hazel", "Owen", "Ruby", "Silas", "Nina", "Clara", "Jonah", "Lena", "Iris",
            "Victor", "Wren", "Quinn", "Mabel", "Otis", "Pearl", "Rhys", "Tess", "Ezra", "Greta", "Hollis",
            "Ines", "Jude", "Kira", "Milo", "Nell", "Opal", "Pim", "Rosa", "Soren", "Uma"]
EN_HANGUL = {"Aria": "아리아", "Fenn": "펜", "Hazel": "헤이즐", "Owen": "오웬", "Ruby": "루비", "Silas": "사일러스",
             "Nina": "니나", "Clara": "클라라", "Jonah": "조나", "Lena": "레나", "Iris": "아이리스", "Victor": "빅터",
             "Wren": "렌", "Quinn": "퀸", "Mabel": "메이블", "Otis": "오티스", "Pearl": "펄", "Rhys": "리스",
             "Tess": "테스", "Ezra": "에즈라", "Greta": "그레타", "Hollis": "홀리스", "Ines": "이네스", "Jude": "주드",
             "Kira": "키라", "Milo": "마일로", "Nell": "넬", "Opal": "오팔", "Pim": "핌", "Rosa": "로사",
             "Soren": "소렌", "Uma": "우마"}
# Korean names written in the other script inside English dialogues.
EN_OTHER_NAMES = ["지우", "민서", "하늘", "도현", "서아", "윤호", "다은", "주원"]
EN_OTHER_ROMAN = {"지우": "Jiwoo", "민서": "Minseo", "하늘": "Haneul", "도현": "Dohyun", "서아": "Seoa",
                  "윤호": "Yunho", "다은": "Daeun", "주원": "Juwon"}
# Feminine / masculine for English pronoun questions (declared per name).
EN_SHE = {"Aria", "Hazel", "Ruby", "Nina", "Clara", "Lena", "Iris", "Wren", "Mabel", "Pearl", "Tess", "Greta",
          "Ines", "Kira", "Nell", "Opal", "Rosa", "Uma"}

# item, counter, domain, English gloss (plural), English singular
KO_ITEMS = [("연필", "자루", "stationery", "pencils", "pencil"), ("볼펜", "자루", "stationery", "pens", "pen"),
            ("공책", "권", "stationery", "notebooks", "notebook"), ("동화책", "권", "books", "storybooks", "storybook"),
            ("우표", "장", "hobby", "stamps", "stamp"), ("스티커", "장", "hobby", "stickers", "sticker"),
            ("색종이", "장", "craft", "colored papers", "colored paper"), ("사진", "장", "hobby", "photos", "photo"),
            ("귤", "개", "fruit", "tangerines", "tangerine"), ("복숭아", "개", "fruit", "peaches", "peach"),
            ("사탕", "개", "snacks", "candies", "candy"), ("쿠키", "개", "snacks", "cookies", "cookie"),
            ("구슬", "개", "toys", "marbles", "marble"), ("지우개", "개", "stationery", "erasers", "eraser"),
            ("우유", "병", "drinks", "milk bottles", "milk bottle"), ("주스", "병", "drinks", "juice bottles", "juice bottle"),
            ("장미", "송이", "flowers", "roses", "rose"), ("튤립", "송이", "flowers", "tulips", "tulip"),
            ("양말", "켤레", "clothes", "socks", "sock"), ("장갑", "켤레", "clothes", "gloves", "glove"),
            ("달걀", "알", "kitchen", "eggs", "egg"), ("과자", "봉지", "snacks", "snack bags", "snack bag"),
            ("금붕어", "마리", "pets", "goldfish", "goldfish"), ("화분", "개", "garden", "flowerpots", "flowerpot")]
# Whether the Latin-script word ends in a consonant when read in Korean (유에스비, 씨디, 엘이디).
KO_LATIN_FINALS = {"USB": False, "CD": False, "LED": False}
KO_LATIN_ITEMS = [("USB", "개", "office", "USB sticks", "USB stick"), ("CD", "장", "music", "CDs", "CD"),
                  ("LED", "개", "office", "LEDs", "LED")]
EN_ITEMS = [("pencils", "pencil", "stationery", "연필"), ("apples", "apple", "fruit", "사과"),
            ("stickers", "sticker", "hobby", "스티커"), ("marbles", "marble", "toys", "구슬"),
            ("cookies", "cookie", "snacks", "쿠키"), ("coins", "coin", "money", "동전"),
            ("stamps", "stamp", "hobby", "우표"), ("books", "book", "books", "책"),
            ("cards", "card", "games", "카드"), ("shells", "shell", "beach", "조개껍데기"),
            ("crayons", "crayon", "craft", "크레용"), ("bananas", "banana", "fruit", "바나나"),
            ("eggs", "egg", "kitchen", "달걀"), ("cupcakes", "cupcake", "snacks", "컵케이크"),
            ("tickets", "ticket", "events", "표"), ("buttons", "button", "craft", "단추"),
            ("beads", "bead", "craft", "구슬"), ("candles", "candle", "home", "양초"),
            ("balloons", "balloon", "party", "풍선"), ("plums", "plum", "fruit", "자두"),
            ("mugs", "mug", "kitchen", "머그잔"), ("batteries", "battery", "office", "건전지"),
            ("brushes", "brush", "craft", "붓"), ("peaches", "peach", "fruit", "복숭아")]
EN_MEASURES = [("bottles of juice", "bottle of juice", "drinks", "주스"), ("packs of gum", "pack of gum", "snacks", "껌"),
               ("boxes of crayons", "box of crayons", "craft", "크레용"), ("bags of chips", "bag of chips", "snacks", "과자"),
               ("cans of soda", "can of soda", "drinks", "탄산음료"), ("jars of jam", "jar of jam", "kitchen", "잼")]

# ---------------------------------------------------------------------------
# Korean grammar
# ---------------------------------------------------------------------------
NATIVE_DET = {1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉", 10: "열",
              20: "스무"}
NATIVE_UNITS = {1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉"}
SINO = {1: "일", 2: "이", 3: "삼", 4: "사", 5: "오", 6: "육", 7: "칠", 8: "팔", 9: "구"}


def ko_native(n):
    if n in NATIVE_DET:
        return NATIVE_DET[n]
    tens = {1: "열", 2: "스물"}[n // 10]
    return tens + NATIVE_UNITS[n % 10]


def ko_sino(n):
    tens, units = divmod(n, 10)
    text = ("" if tens == 0 else ("십" if tens == 1 else SINO[tens] + "십"))
    return text + (SINO[units] if units else "")


class Ko:
    code = "ko"

    def __init__(self, dims, latin_final=None):
        self.d = dims
        self.latin_final = latin_final or {}

    # -- sounds -----------------------------------------------------------
    def batchim(self, word):
        ch = word[-1]
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28 != 0
        if word in self.latin_final:
            return self.latin_final[word]
        return ch.lower() not in "aeiouy"

    def rieul(self, word):
        ch = word[-1]
        return "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 == 8

    def p(self, word, pair):
        return word + (pair[0] if self.batchim(word) else pair[1])

    def top(self, w):
        return self.p(w, ("은", "는"))

    def subj(self, w):
        return self.p(w, ("이", "가"))

    def obj(self, w):
        return self.p(w, ("을", "를"))

    def conj(self, w):
        return self.p(w, ("과", "와"))

    def name(self, n):
        """A given name as said: consonant-final Hangul names take 이 in casual speech."""
        if self.d["name_suffix"] == "suffixed" and self.d["register"] == "banmal" and "가" <= n[-1] <= "힣" \
                and self.batchim(n):
            return n + "이"
        return n

    def dat(self, n):
        return self.name(n) + ("한테" if self.d["register"] in ("banmal", "haeyo") else "에게")

    def src(self, n):
        return self.name(n) + ("한테서" if self.d["register"] in ("banmal", "haeyo") else "에게서")

    # -- amounts ----------------------------------------------------------
    def counter(self, item):
        return item["counter"] if self.d["counter"] == "specific" else "개"

    def amount(self, n, item):
        c = self.counter(item)
        form = self.d["numeral_form"]
        if form == "digits":
            return "%d%s" % (n, c)
        if form == "digits_spaced":
            return "%d %s" % (n, c)
        if form == "sino" and n >= 3:
            return "%s %s" % (ko_sino(n), c)
        return "%s %s" % (ko_native(n), c)

    def amount_obj(self, n, item):
        return self.obj(self.amount(n, item))

    # -- endings ----------------------------------------------------------
    ENDINGS = {
        "있": {"banmal": "있어", "plain": "있다", "haeyo": "있어요", "hapsyo": "있습니다"},
        "있었": {"banmal": "있었어", "plain": "있었다", "haeyo": "있었어요", "hapsyo": "있었습니다"},
        "줬": {"banmal": "줬어", "plain": "주었다", "haeyo": "줬어요", "hapsyo": "주었습니다"},
        "건넸": {"banmal": "건넸어", "plain": "건넸다", "haeyo": "건넸어요", "hapsyo": "건넸습니다"},
        "빌려줬": {"banmal": "빌려줬어", "plain": "빌려주었다", "haeyo": "빌려줬어요", "hapsyo": "빌려주었습니다"},
        "넘겨줬": {"banmal": "넘겨줬어", "plain": "넘겨주었다", "haeyo": "넘겨줬어요", "hapsyo": "넘겨주었습니다"},
        "받았": {"banmal": "받았어", "plain": "받았다", "haeyo": "받았어요", "hapsyo": "받았습니다"},
        "먹었": {"banmal": "먹었어", "plain": "먹었다", "haeyo": "먹었어요", "hapsyo": "먹었습니다"},
        "썼": {"banmal": "썼어", "plain": "썼다", "haeyo": "썼어요", "hapsyo": "썼습니다"},
        "잃어버렸": {"banmal": "잃어버렸어", "plain": "잃어버렸다", "haeyo": "잃어버렸어요", "hapsyo": "잃어버렸습니다"},
        "야": {"banmal": "야", "plain": "이다", "haeyo": "예요", "hapsyo": "입니다"},
        "가지고있": {"banmal": "가지고 있어", "plain": "가지고 있다", "haeyo": "가지고 있어요", "hapsyo": "가지고 있습니다"},
    }
    Q = {"있": {"banmal": "있어", "plain": "있니", "haeyo": "있어요", "hapsyo": "있습니까"},
         "야": {"banmal": "야", "plain": "지", "haeyo": "예요", "hapsyo": "입니까"},
         "남았": {"banmal": "남았어", "plain": "남았니", "haeyo": "남았어요", "hapsyo": "남았습니까"},
         "가지고있": {"banmal": "가지고 있어", "plain": "가지고 있니", "haeyo": "가지고 있어요",
                  "hapsyo": "가지고 있습니까"}}

    def end(self, key):
        return self.ENDINGS[key][self.d["register"]]

    def q(self, key):
        return self.Q[key][self.d["register"]]

    def copula(self, word):
        """Nominal predicate: 세 자루야 / 세 개야 / 3개예요 / 일곱 개이다."""
        reg = self.d["register"]
        if reg == "banmal":
            return word + ("이야" if self.batchim(word) else "야")
        if reg == "plain":
            return word + ("이다" if self.batchim(word) else "다")
        if reg == "haeyo":
            return word + ("이에요" if self.batchim(word) else "예요")
        return word + "입니다"

    def q_copula(self, word):
        reg = self.d["register"]
        if reg == "banmal":
            return word + ("이야" if self.batchim(word) else "야")
        if reg == "plain":
            return word + ("이지" if self.batchim(word) else "지")
        if reg == "haeyo":
            return word + ("이에요" if self.batchim(word) else "예요")
        return word + "입니까"

    # -- sentences --------------------------------------------------------
    def has_clause(self, name, n, item, frame=None, last=True):
        frame = frame or self.d["possession_frame"]
        w = item["word"]
        amt = self.amount(n, item)
        if frame == "existential":
            body = "%s %s %s" % (self.top(self.name(name)), self.subj(w), amt)
            return body + " " + (self.end("있") if last else "있고")
        if frame == "possessive_verb":
            body = "%s %s %s" % (self.top(self.name(name)), w, amt + ("을" if self.batchim(amt) else "를"))
            return body + " " + (self.end("가지고있") if last else "가지고 있고")
        if frame == "dative_existential":
            body = "%s %s %s" % (self.dat(name) + "는", self.subj(w), amt)
            return body + " " + (self.end("있") if last else "있고")
        # copula: 서연의 연필은 세 자루야
        body = "%s의 %s" % (self.name(name), self.top(w))
        return body + " " + (self.copula(amt) if last else amt + "이고")

    def sentence(self, text):
        return text + "."

    def has(self, rows, item):
        split = self.d["split"]
        if len(rows) == 1:
            return self.sentence(self.has_clause(rows[0][0], rows[0][1], item))
        if split == "two_facts_one_turn":
            first = self.has_clause(rows[0][0], rows[0][1], item, last=False)
            if self.d["possession_frame"] == "copula":
                return self.sentence("%s, %s" % (first, self.has_clause(rows[1][0], rows[1][1], item)))
            # the second conjunct leaves the item to the first (ellipsis)
            second_name = self.top(self.name(rows[1][0]))
            return self.sentence("%s, %s %s %s" % (first, second_name, self.amount(rows[1][1], item),
                                                   self.end("있")))
        return " ".join(self.sentence(self.has_clause(h, n, item)) for h, n in rows)

    def transfer_verb(self):
        return {"give": "줬", "hand": "건넸", "lend": "빌려줬", "pass_on": "넘겨줬"}[self.d["transfer_verb"]]

    def give(self, a, b, n, item):
        w, amt = item["word"], self.amount(n, item)
        order = self.d["word_order"]
        verb = self.end(self.transfer_verb())
        if order == "receiver_subject":
            return self.sentence("%s %s %s %s %s" % (self.subj(self.name(b)), self.src(a), w,
                                                     self.obj(amt), self.end("받았")))
        if order == "object_first":
            return self.sentence("%s %s %s %s %s" % (w, self.obj(amt), self.subj(self.name(a)), self.dat(b), verb))
        if order == "recipient_first":
            return self.sentence("%s %s %s %s %s" % (self.dat(b), self.subj(self.name(a)), w, self.obj(amt), verb))
        return self.sentence("%s %s %s %s %s" % (self.subj(self.name(a)), self.dat(b), w, self.obj(amt), verb))

    def use(self, a, n, item, verb):
        v = {"eat": "먹었", "use": "썼", "lose": "잃어버렸"}[verb]
        return self.sentence("%s %s %s %s" % (self.subj(self.name(a)), item["word"], self.obj(self.amount(n, item)),
                                              self.end(v)))

    def ask(self, who, item, form=None):
        form = form or self.d["question_form"]
        w, c = item["word"], self.counter(item)
        nm = self.name(who)
        if form == "exist":
            return "%s %s 몇 %s %s?" % (self.top(nm), self.subj(w), c, self.q("있"))
        if form == "now":
            return "%s 지금 %s 몇 %s?" % (self.top(nm), w, self.q_copula(c))
        if form == "left":
            return "%s %s 몇 %s %s?" % (self.dat(who), self.subj(w), c, self.q("남았"))
        if form == "have":
            return "%s %s 몇 %s %s?" % (self.top(nm), self.obj(w), c, self.q("가지고있"))
        return "%s 가진 %s 몇 %s?" % (self.subj(nm), self.top(w), self.q_copula(c))

    def ask_short(self, who, item):
        return "%s 몇 %s?" % (self.top(self.name(who)), self.q_copula(self.counter(item)))

    def follow(self, who):
        reg = self.d["register"]
        head = "그럼 " if reg in ("banmal", "haeyo") else ""
        tail = "요" if reg in ("haeyo", "hapsyo") else ""
        return head + self.top(self.name(who)) + tail + "?"

    def ask_total(self, a, b, item):
        c = self.counter(item)
        if self.d["split"] == "two_facts_one_turn":
            return "두 사람 합치면 %s 몇 %s?" % (item["word"], self.q_copula(c))
        return "%s %s %s 모두 몇 %s?" % (self.conj(self.name(a)), self.top(self.name(b)), self.subj(item["word"]),
                                     self.q_copula(c))

    def ask_more(self, a, b, item):
        reg = self.d["register"]
        end = {"banmal": "많아", "plain": "많니", "haeyo": "많아요", "hapsyo": "많습니까"}[reg]
        return "%s %s 중 누가 %s 더 %s?" % (self.conj(self.name(a)), self.name(b), self.subj(item["word"]), end)

    def why(self, who, item):
        reg = self.d["register"]
        tail = {"banmal": "있는 거야", "plain": "있는 거지", "haeyo": "있는 거예요", "hapsyo": "있는 겁니까"}[reg]
        return "%s 왜 %s 그만큼 %s?" % (self.top(self.name(who)), self.subj(item["word"]), tail)

    def pronoun(self, item):
        reg = self.d["register"]
        word = "걔는" if reg == "banmal" else "그 사람은"
        return "%s 지금 %s 몇 %s %s?" % (word, item["word"], self.counter(item), self.q("있"))

    def ask_location(self, who, item):
        reg = self.d["register"]
        end = {"banmal": "있어", "plain": "있니", "haeyo": "있어요", "hapsyo": "있습니까"}[reg]
        return "%s %s 어디에 %s?" % (self.name(who) + "의", self.top(item["word"]), end)

    def correct(self, old, new, item, style, event=None):
        """style: contrast | restate | named."""
        reg = self.d["register"]
        if style == "restate":
            head = {"banmal": "잘못 말했어", "plain": "잘못 말했다", "haeyo": "잘못 말했어요",
                    "hapsyo": "잘못 말했습니다"}[reg]
            verb = "받았" if self.d["word_order"] == "receiver_subject" else self.transfer_verb()
            return "%s, %s %s." % (head, self.amount_obj(new, item), self.end(verb))
        was = {"banmal": "었어", "plain": "었다", "haeyo": "었어요", "hapsyo": "었습니다"}[reg]
        new_amt = self.amount(new, item)
        new_said = new_amt + ("이" + was if self.batchim(new_amt) else "였" + was[1:])
        old_amt = self.subj(self.amount(old, item))
        if style == "named":
            return "아, %s %s 아니라 %s." % (item["word"], old_amt, new_said)
        return "아니, %s 아니라 %s." % (old_amt, new_said)

    def decline(self, who, kind):
        reg = self.d["register"]
        please = {"banmal": "줘", "plain": "줘", "haeyo": "주세요", "hapsyo": "주십시오"}[reg]
        if kind == 0:
            return "%s 문자 좀 보내 %s." % (self.dat(who), please)
        if kind == 1:
            return "내일 아침에 %s 일 다시 알려 %s." % (self.name(who) + "의", please)
        return "%s 전화 좀 걸어 %s." % (self.dat(who), please)


class En:
    code = "en"
    WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
             "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]

    def __init__(self, dims):
        self.d = dims

    def num(self, n):
        return str(n) if self.d["numeral_form"] == "digits" else self.WORDS[n]

    def amount(self, n, item):
        return "%s %s" % (self.num(n), item["one"] if n == 1 else item["word"])

    def cap(self, text):
        return text[0].upper() + text[1:]

    def has_clause(self, name, n, item, frame=None):
        frame = frame or self.d["possession_frame"]
        amt = self.amount(n, item)
        if frame == "had":
            return "%s had %s" % (name, amt)
        if frame == "owns":
            return "%s owns %s" % (name, amt)
        if frame == "got":
            return "%s's got %s" % (name, amt)
        if frame == "holding":
            return "%s is holding %s" % (name, amt)
        return "%s has %s" % (name, amt)

    def has(self, rows, item):
        split = self.d["split"]
        if len(rows) == 1:
            return self.has_clause(rows[0][0], rows[0][1], item) + "."
        if split == "two_facts_one_turn":
            verb = {"had": "had", "owns": "owns", "got": "'s got", "holding": "is holding"}.get(
                self.d["possession_frame"], "has")
            second = "%s%s%s %s" % (rows[1][0], "" if verb.startswith("'") else " ", verb, self.num(rows[1][1]))
            return "%s and %s." % (self.has_clause(rows[0][0], rows[0][1], item), second)
        return " ".join(self.has_clause(h, n, item) + "." for h, n in rows)

    def verb(self):
        return {"give": "gave", "hand": "handed", "pass": "passed", "lend": "lent"}[self.d["transfer_verb"]]

    def give(self, a, b, n, item):
        amt = self.amount(n, item)
        order = self.d["word_order"]
        if order == "prepositional":
            return "%s %s %s to %s." % (a, self.verb(), amt, b)
        if order == "receiver_subject":
            verb = {"give": "got", "hand": "received", "pass": "took", "lend": "borrowed"}[self.d["transfer_verb"]]
            return "%s %s %s from %s." % (b, verb, amt, a)
        if order == "passive":
            be = "was" if n == 1 else "were"
            return "%s %s %s to %s by %s." % (self.cap(amt), be, {"gave": "given", "handed": "handed",
                                                                 "passed": "passed", "lent": "lent"}[self.verb()], b, a)
        return "%s %s %s %s." % (a, self.verb(), b, amt)

    def use(self, a, n, item, verb):
        v = {"eat": "ate", "use": "used", "lose": "lost"}[verb]
        return "%s %s %s." % (a, v, self.amount(n, item))

    def ask(self, who, item, form=None):
        form = form or self.d["question_form"]
        w = item["word"]
        if form == "have":
            return "How many %s does %s have?" % (w, who)
        if form == "now":
            return "How many %s does %s have now?" % (w, who)
        if form == "got":
            return "How many %s has %s got?" % (w, who)
        if form == "left":
            return "How many %s does %s have left?" % (w, who)
        return "How many does %s have now?" % who

    def follow(self, who):
        return {"neutral": "And %s?", "casual": "What about %s?", "formal": "And how about %s?"}[
            self.d["register"]] % who

    def ask_total(self, a, b, item):
        if self.d["register"] == "casual":
            return "How many %s do %s and %s have altogether?" % (item["word"], a, b)
        return "How many %s do %s and %s have together?" % (item["word"], a, b)

    def ask_more(self, a, b, item):
        return "Who has more %s now, %s or %s?" % (item["word"], a, b)

    def why(self, who, item):
        return {"neutral": "Why does %s have that many %s?", "casual": "How come %s has that many %s?",
                "formal": "Why does %s have that many %s now?"}[self.d["register"]] % (who, item["word"])

    def pronoun(self, item, she=True):
        return "How many %s does %s have now?" % (item["word"], "she" if she else "he")

    def ask_location(self, who, item):
        return "Where does %s keep the %s?" % (who, item["word"])

    def correct(self, old, new, item, style, event=None):
        a, b = event["from"], event["to"]
        if style == "restate":
            return "Sorry, I misspoke: %s gave %s %s." % (a, b, self.num(new))
        if style == "named":
            return "Actually, %s gave %s %s, not %s." % (a, b, self.amount(new, item), self.num(old))
        return "No, it was %s, not %s." % (self.amount(new, item), self.num(old))

    def decline(self, who, kind):
        return ["Can you text %s for me?", "Please remind %s about this tomorrow.",
                "Could you call %s for me?"][kind] % who


# ---------------------------------------------------------------------------
# plans
# ---------------------------------------------------------------------------
# Each plan is a list of abstract turns over people A, B, C and one item.
PLANS = {
    "give_ask_follow_why": [("has", "A"), ("has", "B"), ("give", "A", "B"), ("ask", "B"), ("follow", "A"),
                            ("why", "A")],
    "joined_give_total": [("has2", "A", "B"), ("give", "A", "B"), ("ask", "A"), ("total", "A", "B")],
    "early_correction": [("has", "A"), ("has", "B"), ("give", "A", "B"), ("correct", -1), ("ask", "B"),
                         ("follow", "A")],
    "late_correction_why": [("has", "A"), ("has", "B"), ("give", "A", "B"), ("ask", "B"), ("correct", 3),
                            ("ask", "B"), ("why", "B")],
    "use_then_more": [("has", "A"), ("use", "A"), ("has", "B"), ("give", "B", "A"), ("ask", "A"), ("more", "A", "B")],
    "ambiguous_pronoun": [("has", "A"), ("has", "B"), ("give", "A", "B"), ("pronoun", "A", "B"), ("follow", "B"),
                          ("ask", "A")],
    "question_before_statement": [("has", "A"), ("missing", "C"), ("has", "C"), ("give", "A", "C"), ("ask", "C"),
                                  ("ask", "A")],
    "restart": [("has", "A"), ("has", "B"), ("give", "B", "A"), ("restart_ask", "A"), ("ask", "B"),
                ("total", "A", "B")],
    "cross_language": [("has", "A"), ("has", "B"), ("give", "A", "B"), ("cross_ask", "B"), ("ask", "A"),
                       ("why", "A")],
    "decline_and_ask": [("has", "A"), ("has", "B"), ("give", "B", "A"), ("ask", "A"), ("decline", "B"),
                        ("ask", "B")],
    "two_transfers": [("has", "A"), ("has", "B"), ("has", "C"), ("give", "A", "B"), ("give", "B", "C"),
                      ("ask", "C"), ("ask", "B"), ("more", "A", "C")],
    "location_hold": [("has2", "A", "B"), ("give", "B", "A"), ("location", "A"), ("ask", "A"), ("follow", "B")],
}
PLAN_NAMES = list(PLANS)


def pick_names(lang, dims, rng, used):
    if lang == "ko":
        pool = list(KO_LATIN_NAMES) if dims["name_script"] == "other" else KO_NAMES
    else:
        pool = EN_OTHER_NAMES if dims["name_script"] == "other" else EN_NAMES
    fresh = [n for n in pool if n not in used]
    rng.shuffle(fresh)
    seen = [n for n in pool if n in used]
    rng.shuffle(seen)
    return (fresh + seen)[:3]


def pick_item(lang, dims, rng):
    if lang == "ko":
        pool = KO_LATIN_ITEMS if dims["item_script"] == "other" else KO_ITEMS
        word, counter, domain, gloss, gloss_one = rng.choice(pool)
        return {"word": word, "counter": counter, "domain": domain, "gloss": gloss, "gloss_one": gloss_one}
    pool = EN_MEASURES if dims["counter"] == "measure" else EN_ITEMS
    word, one, domain, gloss = rng.choice(pool)
    return {"word": word, "one": one, "domain": domain, "gloss": gloss}


def build_dialogue(lang, index, plan_name, dims, rng, used_names):
    grammar = Ko(dims, {**KO_LATIN_NAMES, **KO_LATIN_FINALS}) if lang == "ko" else En(dims)
    names = pick_names(lang, dims, rng, used_names)
    if lang == "en" and plan_name == "ambiguous_pronoun" and dims["name_script"] == "native":
        group = [n for n in EN_NAMES if (n in EN_SHE) == (names[0] in EN_SHE) and n not in used_names
                 and n != names[0]] or [n for n in EN_NAMES if (n in EN_SHE) == (names[0] in EN_SHE) and n != names[0]]
        names[1] = group[0]
    used_names.update(names)
    people = dict(zip("ABC", names))
    item = pick_item(lang, dims, rng)
    plan = list(PLANS[plan_name])
    if dims["split"] != "one_fact_per_turn":
        merged = []
        for step in plan:
            if step[0] == "has" and merged and merged[-1][0] == "has":
                merged[-1] = ("has2", merged[-1][1], step[1])
            else:
                merged.append(step)
        plan = merged
    if dims["question_position"] == "before" and plan_name not in ("question_before_statement",):
        # ask about B before B's count is stated: held, then the statement, then the same question.
        if ("has", "B") in plan:
            at = plan.index(("has", "B"))
            plan = plan[:at] + [("missing", "B")] + plan[at:]
    # amounts: distinct starting counts, transfers smaller than what the giver holds
    while True:
        start = {p: rng.randint(3, 12) for p in "ABC"}
        amounts = [rng.randint(1, 4) for _ in plan]
        if len(set(start.values())) == 3:
            break
    state, turns, events_by_turn, clash = {}, [], {}, []
    touched = {}          # person -> turns whose events touch them
    last_answer = None    # (person) of the last count answer
    correction_done = False
    pending_follow = None
    she = {p for p in people.values() if p in EN_SHE}

    def record(n, say, events, tags):
        for ev in events:
            apply(state, ev)
            for key in ("holder", "from", "to"):
                if key in ev:
                    touched.setdefault(ev[key], []).append(n)
        events_by_turn[n] = events
        rows = []
        for ev in events:
            for key in ("holder", "from", "to"):
                if key in ev and ev[key] not in [r["entity"] for r in rows]:
                    rows.append({"entity": ev[key], "item": item_key, "quantity": state.get(ev[key])})
        turns.append({"n": n, "say": say, "label": "hold", "tags": tags,
                      "expect": {"act": "record", "entity": None, "quantity": None, "relation": None,
                                 "evidence": {"turns": [n]}, "events": events, "state": rows}})

    def evidence(person):
        return sorted(set(touched.get(person, [])))

    item_key = item["word"]
    for step_index, step in enumerate(plan):
        n = len(turns) + 1
        kind = step[0]
        amount = amounts[step_index]
        if kind == "has":
            p = people[step[1]]
            events = [{"type": "has", "holder": p, "item": item_key, "quantity": start[step[1]]}]
            record(n, grammar.has([(p, start[step[1]])], item), events, ["ownership"])
        elif kind == "has2":
            a, b = people[step[1]], people[step[2]]
            rows = [(a, start[step[1]]), (b, start[step[2]])]
            events = [{"type": "has", "holder": h, "item": item_key, "quantity": q} for h, q in rows]
            if dims["split"] == "one_fact_per_turn":
                record(n, grammar.has(rows[:1], item), events[:1], ["ownership"])
                record(n + 1, grammar.has(rows[1:], item), events[1:], ["ownership"])
            else:
                record(n, grammar.has(rows, item), events, ["ownership"])
        elif kind == "give":
            a, b = people[step[1]], people[step[2]]
            k = min(amount, max(1, state[a] - 1))
            events = [{"type": "transfer", "from": a, "to": b, "item": item_key, "quantity": k}]
            record(n, grammar.give(a, b, k, item), events, ["transfer"])
        elif kind == "use":
            a = people[step[1]]
            k = min(amount, max(1, state[a] - 1))
            verb = rng.choice(["eat", "use", "lose"]) if item["domain"] in ("fruit", "snacks", "kitchen") \
                else rng.choice(["use", "lose"])
            events = [{"type": "use", "holder": a, "item": item_key, "quantity": k}]
            record(n, grammar.use(a, k, item, verb), events, ["transfer"])
        elif kind in ("ask", "restart_ask", "follow", "cross_ask"):
            p = people[step[1]]
            tags = ["transfer"] if any(e["type"] != "has" for t in touched.get(p, []) for e in events_by_turn[t]) \
                else ["ownership"]
            turn = {"n": n, "label": "answerable", "tags": tags,
                    "expect": {"act": "answer", "entity": p, "quantity": state[p], "relation": "count",
                               "evidence": {"turns": evidence(p)}, "item": item_key}}
            if correction_done and correction_target in touched.get(p, []):
                turn["tags"] = sorted(set(turn["tags"]) | {"correction"})
                retracted, reexecuted = alternatives(p)
                if retracted is not None and retracted != state[p]:
                    turn["expect"]["retracted_quantity"] = retracted
                if reexecuted is not None and reexecuted not in (state[p], retracted):
                    turn["expect"]["reexecuted_quantity"] = reexecuted
            if kind == "follow":
                turn["say"] = grammar.follow(p)
                turn["tags"] = sorted(set(turn["tags"]) | {"follow_up"})
                if turns and turns[-1]["expect"]["act"] == "clarify":
                    turn["tags"] = sorted(set(turn["tags"]) | {"ambiguous_referent"})
            elif kind == "restart_ask":
                turn["say"] = grammar.ask(p, item)
                turn["restart_before"] = True
                turn["tags"] = sorted(set(turn["tags"]) | {"restart"})
            elif kind == "cross_ask":
                other = "en" if lang == "ko" else "ko"
                turn["lang"] = other
                turn["say"] = cross_question(lang, p, item, dims)
                turn["tags"] = sorted(set(turn["tags"]) | {"cross_language"})
            elif step_index > 0 and plan[step_index - 1][0] == "ask" and (index + step_index) % 2 == 0:
                turn["say"] = grammar.ask_short(p, item) if lang == "ko" else grammar.ask(p, item, "short")
                turn["tags"] = sorted(set(turn["tags"]) | {"follow_up"})
            else:
                turn["say"] = grammar.ask(p, item)
            last_answer = p
            if any(value == state[p] for holder, value in state.items() if holder != p):
                clash.append(n)
            turns.append(turn)
        elif kind == "total":
            a, b = people[step[1]], people[step[2]]
            turns.append({"n": n, "say": grammar.ask_total(a, b, item), "label": "answerable",
                          "tags": ["transfer"],
                          "expect": {"act": "answer", "entity": [a, b], "quantity": state[a] + state[b],
                                     "relation": "total", "evidence": {"turns": sorted(set(evidence(a) + evidence(b)))},
                                     "item": item_key}})
        elif kind == "more":
            a, b = people[step[1]], people[step[2]]
            if state[a] == state[b]:
                continue
            winner = a if state[a] > state[b] else b
            turns.append({"n": n, "say": grammar.ask_more(a, b, item), "label": "answerable",
                          "tags": ["transfer"],
                          "expect": {"act": "answer", "entity": winner, "quantity": None, "relation": "more",
                                     "candidates": [a, b], "evidence": {"turns": sorted(set(evidence(a) + evidence(b)))},
                                     "item": item_key}})
        elif kind == "why":
            p = people[step[1]]
            turns.append({"n": n, "say": grammar.why(p, item), "label": "why", "tags": ["why"],
                          "expect": {"act": "explain", "entity": p, "quantity": state[p], "relation": "count",
                                     "evidence": {"turns": evidence(p)}, "item": item_key}})
        elif kind == "pronoun":
            a, b = people[step[1]], people[step[2]]
            if lang == "en":
                both_male = a in EN_NAMES and b in EN_NAMES and a not in she and b not in she
                say = grammar.pronoun(item, she=not both_male)
            else:
                say = grammar.pronoun(item)
            turns.append({"n": n, "say": say, "label": "ambiguous", "tags": ["ambiguous_referent"],
                          "expect": {"act": "clarify", "entity": None, "quantity": None, "relation": None,
                                     "evidence": {"turns": [n]}, "candidates": [a, b]}})
        elif kind == "missing":
            p = people[step[1]]
            turns.append({"n": n, "say": grammar.ask(p, item), "label": "hold", "tags": ["missing_premise"],
                          "expect": {"act": "hold", "entity": p, "quantity": None, "relation": "count",
                                     "evidence": {"turns": [n]}, "item": item_key}})
        elif kind == "location":
            p = people[step[1]]
            turns.append({"n": n, "say": grammar.ask_location(p, item), "label": "hold",
                          "tags": ["missing_premise"],
                          "expect": {"act": "hold", "entity": p, "quantity": None, "relation": "location",
                                     "evidence": {"turns": [n]}, "item": item_key}})
        elif kind == "decline":
            p = people[step[1]]
            turns.append({"n": n, "say": grammar.decline(p, index % 3), "label": "unsupported", "tags": [],
                          "expect": {"act": "decline", "entity": None, "quantity": None, "relation": None,
                                     "evidence": {"turns": [n]}}})
        elif kind == "correct":
            # the transfer to correct: the last one (-1) or the one at plan position step[1]
            target = max(t for t, evs in events_by_turn.items() if evs[0]["type"] == "transfer")
            old_event = events_by_turn[target][0]
            old = old_event["quantity"]
            giver_start = state[old_event["from"]] + old
            choices = [q for q in range(1, giver_start) if q != old]
            new = rng.choice(choices)
            style = ["contrast", "restate", "named"][index % 3]
            say = grammar.correct(old, new, item, style, old_event)
            new_event = dict(old_event, quantity=new)
            # undo the old event, apply the new one
            state[old_event["from"]] += old - new
            state[old_event["to"]] -= old - new
            events_by_turn[target] = [new_event]
            correction_target = target
            correction_old = old
            correction_new = new
            correction_done = True
            for key in ("from", "to"):
                touched.setdefault(old_event[key], []).append(n)
            turns.append({"n": n, "say": say, "label": "correction", "tags": ["correction"],
                          "expect": {"act": "revise", "entity": None, "quantity": None, "relation": None,
                                     "evidence": {"turns": [target, n]}, "target_turn": target,
                                     "replaces": [old_event], "with": [new_event],
                                     "state": [{"entity": old_event["from"], "item": item_key,
                                                "quantity": state[old_event["from"]]},
                                               {"entity": old_event["to"], "item": item_key,
                                                "quantity": state[old_event["to"]]}]}})

            def alternatives(person, old=old, new=new, ev=old_event):
                if person == ev["to"]:
                    return state[person] - new + old, state[person] + old
                if person == ev["from"]:
                    return state[person] + new - old, state[person] - old
                return None, None
        if len(turns) >= 10:
            break
    variation = {"word_order": dims["word_order"], "register": dims["register"], "split": dims["split"],
                 "correction_position": ("early" if plan_name == "early_correction" else
                                         "late" if plan_name == "late_correction_why" else "none"),
                 "roles": "giver_first_mentioned" if dims["word_order"] != "receiver_subject" else "receiver_subject",
                 "initial_values": {people[k]: start[k] for k in "ABC" if people[k] in touched},
                 "plan": plan_name}
    variation.update({key: dims[key] for key in DIMENSIONS[lang] if key not in variation})
    if clash:
        return None      # an answer equal to another holder's count could not be told apart
    return {"schema": SCHEMA, "id": "dev2_%s_%02d" % (lang, index + 1), "language": lang,
            "domain": item["domain"], "categories": sorted({t for turn in turns for t in turn["tags"]}),
            "variation": variation, "turns": turns}


def apply(state, event):
    if event["type"] == "has":
        state[event["holder"]] = event["quantity"]
    elif event["type"] == "use":
        state[event["holder"]] -= event["quantity"]
    else:
        state[event["from"]] -= event["quantity"]
        state[event["to"]] = state.get(event["to"], 0) + event["quantity"]


def cross_question(lang, person, item, dims):
    """The same count question asked in the other language: names and items carried across."""
    if lang == "ko":
        name = KO_ROMAN.get(person, person)
        return "How many %s does %s have now?" % (item["gloss"], name)
    name = EN_HANGUL.get(person, person)
    return "%s 지금 %s 몇 개 있어?" % (Ko(dims).top(name), item["gloss"])


def dimension_table(lang):
    """Balanced assignment: every value of a dimension is used equally often (a value
    listed twice, twice as often), each dimension shuffled on its own by the seed."""
    table = [{} for _ in range(PER_LANGUAGE)]
    for key, values in DIMENSIONS[lang].items():
        column = (values * (PER_LANGUAGE // len(values) + 1))[:PER_LANGUAGE]
        random.Random("%d/%s/%s" % (SEED, lang, key)).shuffle(column)
        for row, value in zip(table, column):
            row[key] = value
    return table


def generate():
    rng = random.Random(SEED)
    dialogues = []
    for lang in ("ko", "en"):
        used = set()
        table = dimension_table(lang)
        for index in range(PER_LANGUAGE):
            plan = PLAN_NAMES[index % len(PLAN_NAMES)]
            dims = table[index]
            dialogue = None
            while dialogue is None:
                dialogue = build_dialogue(lang, index, plan, dims, rng, used)
            dialogues.append(dialogue)
    return dialogues


def split(dialogues):
    rng = random.Random(SEED)
    build, check = [], []
    for lang in ("ko", "en"):
        ids = [d["id"] for d in dialogues if d["language"] == lang]
        rng.shuffle(ids)
        cut = len(ids) * 2 // 3
        build += sorted(ids[:cut])
        check += sorted(ids[cut:])
    return {"seed": SEED, "build": build, "check": check}


def main():
    dialogues = generate()
    for path in HERE.glob("dev2_*.json"):
        path.unlink()
    for d in dialogues:
        (HERE / (d["id"] + ".json")).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    parts = split(dialogues)
    lines = ["seed %d" % parts["seed"], "build " + " ".join(parts["build"]), "check " + " ".join(parts["check"])]
    (HERE / "split.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("dialogues %d  build %d  check %d" % (len(dialogues), len(parts["build"]), len(parts["check"])))


if __name__ == "__main__":
    main()
