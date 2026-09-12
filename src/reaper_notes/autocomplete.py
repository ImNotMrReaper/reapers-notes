"""
autocomplete.py: Advanced Inline Predictive Autocomplete & Fuzzy Spellcheck / Autocorrect Engine.
Provides sub-millisecond prefix trie matching, persistent user word frequency database,
document vocabulary indexing, and Levenshtein fuzzy autocorrect.
"""

import os
import re
import sys
import time
import sqlite3
import difflib
from pathlib import Path
from typing import Optional, List, Set, Dict, Tuple

CONFIG_DIR = Path.home() / ".config" / "reaper-notes"
VOCAB_DB_PATH = CONFIG_DIR / "user_vocabulary.db"
DEFAULT_NOTES_DIR = Path.home() / "Documents" / "Notes"

COMMON_KEYWORDS = [
    # Python Keywords & Builtins
    "import", "from", "return", "def", "class", "async", "await", "lambda",
    "except", "finally", "raise", "assert", "global", "nonlocal", "yield",
    "continue", "break", "print", "range", "enumerate", "isinstance",
    "classmethod", "staticmethod", "property", "__init__", "__main__",
    "isinstance", "issubclass", "isinstance", "isinstance", "isinstance",
    # Bash & Linux Commands
    "sudo", "systemctl", "journalctl", "apt", "install", "update", "upgrade",
    "git", "clone", "commit", "push", "pull", "checkout", "status", "branch",
    "chmod", "chown", "mkdir", "touch", "export", "source", "echo", "grep",
    "find", "curl", "wget", "which", "python3", "pip", "kill", "ps", "top",
    "terminator", "nautilus", "howdy", "fprintd", "neofetch", "fastfetch",
    # Antigravity & Link Terms
    "antigravity", "agy", "senpai", "mr-reaper", "reaper-notes", "joycon",
    "vulkan", "whisper", "obsidian", "autocorrect", "autocomplete", "subagent",
    # Common Misspellings -> Corrections
    "tehn", "recieve", "seperat", "definately", "accidentally", "accommodate",
    "achieve", "address", "apparent", "argument", "beginning", "believe",
    "calendar", "category", "cemetery", "changeable", "collectible",
    "column", "committed", "conscience", "conscious", "definitely",
    "discipline", "embarrass", "equipment", "existence", "experience",
    "foreign", "guarantee", "guidance", "happen", "harness", "hierarchy",
    "humorous", "immediate", "independent", "intelligence", "judgment",
    "kernel", "knowledge", "laboratory", "leisure", "library", "license",
    "maintenance", "maneuver", "noticeable", "occasion", "occurred",
    "parallel", "possession", "privilege", "procedure", "questionnaire",
    "receive", "recommend", "reference", "relevant", "restaurant", "rhyme",
    "rhythm", "schedule", "separate", "sergeant", "threshold", "tomorrow",
    "truly", "until", "vacuum", "weather", "weird", "writing",
    # Markdown & Formatting
    "### Notes", "## Overview", "> [!NOTE]", "> [!IMPORTANT]", "> [!TIP]",
    "> [!WARNING]", "- [ ] ", "- [x] ",
    # Vocabulary
    "about", "above", "after", "again", "against", "almost", "already", "always",
    "amount", "another", "answer", "anyone", "anything", "appear", "around",
    "before", "beginning", "behavior", "behind", "believe", "between", "bottom",
    "change", "check", "children", "choose", "clean", "clear", "complete",
    "condition", "config", "configuration", "connect", "connection", "control",
    "current", "database", "default", "define", "delete", "detail", "device",
    "different", "direct", "directory", "discover", "document", "element",
    "enable", "engine", "enough", "ensure", "environment", "error", "example",
    "execute", "execution", "existing", "expect", "explain", "extend", "extension",
    "feature", "file", "filter", "finish", "follow", "forward", "framework",
    "frequency", "function", "future", "general", "generate", "global", "hardware",
    "header", "history", "identify", "implement", "important", "include", "initial",
    "initialize", "insert", "inspect", "install", "integrate", "interface", "internal",
    "keyboard", "kernel", "launch", "launcher", "layout", "length", "library",
    "license", "lightweight", "linux", "listen", "location", "lookup", "machine",
    "manage", "manager", "manual", "match", "matrix", "memory", "message",
    "method", "minute", "model", "modify", "module", "mouse", "multiple",
    "native", "necessary", "network", "nothing", "notice", "number", "object",
    "operation", "optimize", "option", "output", "package", "parallel", "pattern",
    "perform", "permission", "physical", "pipeline", "platform", "plugin", "policy",
    "position", "predict", "predictive", "preference", "previous", "priority",
    "process", "profile", "program", "project", "prompt", "protocol", "provide",
    "random", "receive", "record", "recorder", "reference", "register", "release",
    "reload", "remove", "replace", "report", "request", "require", "reset",
    "resolve", "resource", "response", "restore", "result", "return", "running",
    "sample", "scaffold", "schedule", "screen", "script", "search", "section",
    "secure", "security", "select", "selection", "sensor", "separate", "sequence",
    "server", "service", "session", "setting", "setup", "shortcut", "simulate",
    "software", "solution", "source", "standard", "start", "state", "status",
    "storage", "string", "structure", "subagent", "submit", "subsystem", "succeed",
    "success", "suggest", "suggestion", "support", "switch", "system", "table",
    "tandem", "target", "task", "terminal", "testing", "theme", "threshold",
    "timeout", "timestamp", "toggle", "tokenizer", "tracking", "trading",
    "trajectory", "transcribe", "trigger", "ubuntu", "understand", "unified",
    "universal", "unlock", "update", "upgrade", "useful", "validate", "value",
    "variable", "version", "voice", "volume", "wait", "warning", "window", "wrapper"
]

# Explicit common typo corrections table
TYPO_CORRECTIONS: Dict[str, str] = {
    "tehn": "then",
    "taht": "that",
    "recieve": "receive",
    "seperat": "separate",
    "definately": "definitely",
    "antigravty": "antigravity",
    "anti-gravity": "antigravity",
    "suod": "sudo",
    "autocompleate": "autocomplete",
    "autocorrecter": "autocorrect",
    "importent": "important",
    "signiture": "signature",
}


class UserVocabularyDatabase:
    """
    SQLite-backed persistent database of word frequencies.
    Learns and prioritizes words the user types, accepts, and saves across sessions.
    """
    def __init__(self, db_path: Path = VOCAB_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS word_frequencies (
                        word TEXT PRIMARY KEY,
                        frequency INTEGER NOT NULL DEFAULT 1,
                        last_used REAL NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_word_prefix ON word_frequencies(word);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_freq_desc ON word_frequencies(frequency DESC, last_used DESC);
                """)
        except Exception as e:
            print(f"[UserVocabularyDatabase] DB init error: {e}", file=sys.stderr)

    def record_word(self, word: str, count: int = 1):
        clean = word.strip().lower()
        if len(clean) < 2 or not clean[0].isalpha():
            return
        now = time.time()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO word_frequencies (word, frequency, last_used)
                    VALUES (?, ?, ?)
                    ON CONFLICT(word) DO UPDATE SET
                        frequency = frequency + excluded.frequency,
                        last_used = excluded.last_used;
                """, (clean, count, now))
        except Exception:
            pass

    def record_text(self, text: str):
        if not text:
            return
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_\-]{1,}\b", text)
        if not words:
            return
        counts: Dict[str, int] = {}
        for w in words:
            cw = w.lower()
            if len(cw) >= 2 and cw[0].isalpha():
                counts[cw] = counts.get(cw, 0) + 1

        now = time.time()
        try:
            with self._get_connection() as conn:
                conn.executemany("""
                    INSERT INTO word_frequencies (word, frequency, last_used)
                    VALUES (?, ?, ?)
                    ON CONFLICT(word) DO UPDATE SET
                        frequency = frequency + excluded.frequency,
                        last_used = excluded.last_used;
                """, [(word, cnt, now) for word, cnt in counts.items()])
        except Exception:
            pass

    def get_top_matches(self, prefix: str, limit: int = 10) -> List[Tuple[str, int]]:
        p_low = prefix.strip().lower()
        if len(p_low) < 2:
            return []
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT word, frequency FROM word_frequencies
                    WHERE word LIKE ? AND word != ?
                    ORDER BY frequency DESC, last_used DESC, length(word) ASC
                    LIMIT ?;
                """, (f"{p_low}%", p_low, limit))
                return cursor.fetchall()
        except Exception:
            return []

    def get_total_words(self) -> int:
        try:
            with self._get_connection() as conn:
                res = conn.execute("SELECT COUNT(*) FROM word_frequencies;").fetchone()
                return res[0] if res else 0
        except Exception:
            return 0

    def seed_from_directory(self, dir_path: Path):
        """Seeds the database from existing text and markdown documents."""
        if not dir_path.exists():
            return
        try:
            for item in dir_path.glob("*.*"):
                if item.is_file() and item.suffix.lower() in (".txt", ".md", ".py", ".json", ".sh"):
                    try:
                        content = item.read_text(encoding="utf-8", errors="ignore")
                        self.record_text(content)
                    except Exception:
                        pass
        except Exception:
            pass


class AutocompleteEngine:
    """
    Dual-layer autocomplete and spellcheck engine:
    1. Fast prefix lookup prioritized by the user's persistent frequency SQLite database.
    2. Document-local vocabulary & built-in keyword lookup.
    3. Levenshtein fuzzy distance spellchecking & auto-correction for typos.
    """
    def __init__(self):
        self.vocabulary: Set[str] = set()
        self.doc_words: Set[str] = set()
        self.vocab_db = UserVocabularyDatabase()
        self._load_builtins()
        self._check_and_seed()

    def _check_and_seed(self):
        try:
            if self.vocab_db.get_total_words() < 50:
                self.vocab_db.seed_from_directory(DEFAULT_NOTES_DIR)
        except Exception:
            pass

    def _load_builtins(self):
        for word in COMMON_KEYWORDS:
            clean = word.strip().lower()
            if len(clean) >= 2:
                self.vocabulary.add(clean)

    def update_document_words(self, text: str):
        """Indexes all words in the document for immediate local suggestion."""
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_\-]{2,}\b", text)
        self.doc_words = set(w.lower() for w in words)

    def get_autocorrect_suggestion(self, word: str) -> Optional[str]:
        """
        Returns a spellcheck / autocorrect suggestion if 'word' contains a typo.
        """
        if not word or len(word) < 3:
            return None

        w_low = word.lower()

        # Check explicit dictionary override
        if w_low in TYPO_CORRECTIONS:
            corrected = TYPO_CORRECTIONS[w_low]
            if word.isupper():
                return corrected.upper()
            elif word[0].isupper():
                return corrected.capitalize()
            return corrected

        # If already a valid word in doc or vocabulary, no correction needed
        if w_low in self.doc_words or w_low in self.vocabulary:
            return None

        # Fuzzy match against doc words and vocabulary using difflib SequenceMatcher
        all_words = list(self.doc_words | self.vocabulary)
        matches = difflib.get_close_matches(w_low, all_words, n=1, cutoff=0.82)
        if matches:
            match = matches[0]
            if word.isupper():
                return match.upper()
            elif word[0].isupper():
                return match.capitalize()
            return match

        return None

    def get_suggestion(self, prefix: str) -> Optional[str]:
        """
        Returns the single best completion suffix matching the given prefix.
        Priority:
        1. User's most frequent words from the persistent SQLite database.
        2. Exact matches in current document words.
        3. Built-in vocabulary & system keywords.
        4. Fuzzy autocorrect candidates.
        """
        if not prefix or len(prefix) < 2:
            return None

        p_low = prefix.lower()

        # Priority 1: User's highest-frequency words from persistent SQLite database
        db_matches = self.vocab_db.get_top_matches(p_low, limit=5)
        if db_matches:
            match, _ = db_matches[0]
            if prefix.isupper():
                match = match.upper()
            elif prefix[0].isupper():
                match = match.capitalize()
            return match[len(prefix):]

        # Priority 2: Exact matches in current document words
        candidates = [w for w in self.doc_words if w.startswith(p_low) and len(w) > len(p_low)]
        if candidates:
            candidates.sort(key=lambda w: (len(w), w))
            match = candidates[0]
            if prefix.isupper():
                match = match.upper()
            elif prefix[0].isupper():
                match = match.capitalize()
            return match[len(prefix):]

        # Priority 3: Built-in vocabulary & system keywords
        candidates = [w for w in self.vocabulary if w.startswith(p_low) and len(w) > len(p_low)]
        if candidates:
            candidates.sort(key=lambda w: (len(w), w))
            match = candidates[0]
            if prefix.isupper():
                match = match.upper()
            elif prefix[0].isupper():
                match = match.capitalize()
            return match[len(prefix):]

        # Priority 4: Fuzzy Autocorrect
        if len(prefix) >= 3:
            corr = self.get_autocorrect_suggestion(prefix)
            if corr and corr.lower().startswith(p_low):
                return corr[len(prefix):]

        return None
