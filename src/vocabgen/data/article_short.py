from __future__ import annotations
from dataclasses import dataclass
import re
from typing import List, Optional


# TODO Move to the ArticleShort class (inside this class)
@dataclass
class Example:
    passage: str  # TODO Can have a better name?
    translation: Optional[str] = None


@dataclass
class ArticleShort:
    """
    Represents a short vocabulary article in markdown like:

    ##### **la balsa** 🛶
    *raft*
    > Example spanish - English
    > Another example...

    Use parse_from_markdown to create an instance.
    """
    # TODO Why HEADING_RE, etc are per-class while
    headword: str
    emoji: Optional[str]
    translation: str
    examples: List[Example]
    raw_markdown: str

    HEADING_RE = re.compile(r"^#####\s+\*\*(?P<headword>.+?)\*\*(?:\s+(?P<emoji>.+))?\s*$", re.M)
    TRANSLATION_RE = re.compile(r"^\*(?P<translation>.+?)\*\s*$")
    EXAMPLE_RE = re.compile(r"^>\s*(?P<content>.+)$")

    @classmethod
    def parse_from_markdown(cls, text: str) -> ArticleShort:
        """
        Parse a single article block and return the article or raise ValueError with explanation.
        """
        original = text
        lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip() != ""]
        if not lines:
            raise ValueError("Empty article")

        # heading = first non-empty line
        m = cls.HEADING_RE.match(lines[0])
        if not m:
            raise ValueError(f"Invalid heading line. Expected '##### **word** [emoji]'. Got: {lines[0]!r}")
        headword = m.group("headword").strip()
        emoji = m.group("emoji").strip() if m.group("emoji") else None

        # translation is expected to be the next line
        if len(lines) < 2:
            raise ValueError("Missing translation line (expected '*translation*').")
        m2 = cls.TRANSLATION_RE.match(lines[1])
        if not m2:
            raise ValueError(f"Invalid translation line. Expected '*translation*'. Got: {lines[1]!r}")
        translation = m2.group("translation").strip()

        examples: List[Example] = []
        for ln in lines[2:]:
            m3 = cls.EXAMPLE_RE.match(ln)
            if not m3:
                # allow non-example lines but warn / validation error
                raise ValueError(f"Invalid example line (must start with '>'): {ln!r}")
            content = m3.group("content").strip()
            # Try to split into "Spanish - English" based on first " - " occurrence
            if " - " in content:
                spanish, english = content.split(" - ", 1)
                examples.append(Example(passage=spanish.strip(), translation=english.strip()))
            else:
                # Only Spanish example provided
                examples.append(Example(passage=content, translation=None))
        return cls(headword=headword, emoji=emoji, translation=translation, examples=examples, raw_markdown=original.strip())

    def to_markdown(self) -> str:
        lines = []
        lines.append(f"##### **{self.headword}**" + (f" {self.emoji}" if self.emoji else ""))
        lines.append(f"*{self.translation}*")
        for ex in self.examples:
            if ex.translation:
                lines.append(f"> {ex.passage} - {ex.translation}")
            else:
                lines.append(f"> {ex.passage}")
        return "\n".join(lines) + "\n"


    def validate(self) -> None:
        """
        Additional checks (raise ValueError on failure). Already checked by parser,
        but call if you constructed the object manually.
        """
        if not self.headword:
            raise ValueError("Empty headword")
        if not self.translation:
            raise ValueError("Empty translation")
