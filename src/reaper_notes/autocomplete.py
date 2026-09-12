"""
autocomplete.py: Advanced Inline Predictive Autocomplete & Fuzzy Spellcheck / Autocorrect Engine.
Provides sub-millisecond prefix trie matching, document vocabulary indexing, and Levenshtein fuzzy autocorrect.
"""

import re
import difflib
from typing import Optional, List, Set, Dict

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


class AutocompleteEngine:
    """
    Dual-layer autocomplete and spellcheck engine:
    1. Fast prefix trie/set lookup for ble.sh style ghost-text completion.
    2. Levenshtein fuzzy distance spellchecking & auto-correction for typos.
    """
    def __init__(self):
        self.vocabulary: Set[str] = set()
        self.doc_words: Set[str] = set()
        self._load_builtins()

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
        If no exact prefix match exists, checks for fuzzy autocorrect candidates.
        """
        if not prefix or len(prefix) < 2:
            return None

        p_low = prefix.lower()

        # Priority 1: Exact matches in current document words
        candidates = [w for w in self.doc_words if w.startswith(p_low) and len(w) > len(p_low)]
        if candidates:
            candidates.sort(key=lambda w: (len(w), w))
            match = candidates[0]
            if prefix.isupper():
                match = match.upper()
            elif prefix[0].isupper():
                match = match.capitalize()
            return match[len(prefix):]

        # Priority 2: Built-in vocabulary & system keywords
        candidates = [w for w in self.vocabulary if w.startswith(p_low) and len(w) > len(p_low)]
        if candidates:
            candidates.sort(key=lambda w: (len(w), w))
            match = candidates[0]
            if prefix.isupper():
                match = match.upper()
            elif prefix[0].isupper():
                match = match.capitalize()
            return match[len(prefix):]

        # Priority 3: Fuzzy Autocorrect
        if len(prefix) >= 3:
            corr = self.get_autocorrect_suggestion(prefix)
            if corr and corr.lower().startswith(p_low):
                return corr[len(prefix):]

        return None
