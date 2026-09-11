"""
autocomplete.py: Terminal-grade inline predictive autocomplete engine (ble.sh / fish style).
Provides sub-millisecond prefix trie matching and vocabulary extraction.
"""

import re
from typing import Optional, List, Set

COMMON_KEYWORDS = [
    # Python
    "import", "from", "return", "def", "class", "async", "await", "lambda",
    "except", "finally", "raise", "assert", "global", "nonlocal", "yield",
    "continue", "break", "print", "range", "enumerate", "isinstance",
    "classmethod", "staticmethod", "property", "__init__", "__main__",
    # Bash & Linux
    "sudo", "systemctl", "journalctl", "apt", "install", "update", "upgrade",
    "git", "clone", "commit", "push", "pull", "checkout", "status", "branch",
    "chmod", "chown", "mkdir", "touch", "export", "source", "echo", "grep",
    "find", "curl", "wget", "which", "python3", "pip", "kill", "ps", "top",
    # JavaScript / TypeScript / Web
    "function", "const", "let", "var", "document", "window", "console", "log",
    "addEventListener", "querySelector", "getElementById", "innerHTML",
    # Markdown
    "### Notes", "## Overview", "> [!NOTE]", "> [!IMPORTANT]", "> [!TIP]",
    "> [!WARNING]", "- [ ] ", "- [x] ",
    # General vocabulary
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


class AutocompleteEngine:
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

    def get_suggestion(self, prefix: str) -> Optional[str]:
        """
        Returns the single best completion suffix matching the given prefix.
        Exact ble.sh behavior: returns suffix to render inline as ghost text.
        """
        if not prefix or len(prefix) < 2:
            return None

        p_low = prefix.lower()

        # Priority 1: Exact matches in current document words
        candidates = [w for w in self.doc_words if w.startswith(p_low) and len(w) > len(p_low)]
        if candidates:
            # Sort by shortest match first for natural typing
            candidates.sort(key=lambda w: (len(w), w))
            match = candidates[0]
            # Match case of original prefix
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

        return None
