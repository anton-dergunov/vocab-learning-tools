from __future__ import annotations
from dataclasses import dataclass
import re
from typing import List, Optional


@dataclass
class ArticleShort:
    """
    Represents a short vocabulary article in markdown like:

    ##### **la balsa** 🛶
    *raft*
    > El río tenía una **balsa**. - The river had a raft.
    > Usamos la **balsa** para cruzar el lago.

    Use parse_from_markdown() to create an instance.
    """

    @dataclass
    class Example:
        """
        Represents one example line within the article.
        Example:
          > El perro corre rápido. - The dog runs fast.
        """
        spanish_text: str
        translation: Optional[str] = None

    headword: str
    emoji: Optional[str]
    translation: str
    examples: List[Example]
    raw_markdown: str

    # Regex constants
    HEADING_RE = re.compile(
        r"^#####\s+\*\*(?P<headword>.+?)\*\*(?:\s+(?P<emoji>.+))?\s*$",
        re.M,
    )
    TRANSLATION_RE = re.compile(r"^\*(?P<translation>.+?)\*\s*$")
    EXAMPLE_RE = re.compile(r"^>\s*(?P<content>.+)$")

    # --- Factory method --------------------------------------------------

    @classmethod
    def parse_from_markdown(cls, text: str) -> ArticleShort:
        """
        Parse a single article block and return the ArticleShort.
        Raises ValueError on structural or formatting errors.
        """
        original = text
        lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
        if not lines:
            raise ValueError("Empty article")

        # Heading
        m = cls.HEADING_RE.match(lines[0])
        if not m:
            raise ValueError(
                f"Invalid heading line. Expected '##### **word** [emoji]'. Got: {lines[0]!r}"
            )
        headword = m.group("headword").strip()
        emoji = m.group("emoji").strip() if m.group("emoji") else None

        # Translation line
        if len(lines) < 2:
            raise ValueError("Missing translation line (expected '*translation*').")
        m2 = cls.TRANSLATION_RE.match(lines[1])
        if not m2:
            raise ValueError(
                f"Invalid translation line. Expected '*translation*'. Got: {lines[1]!r}"
            )
        translation = m2.group("translation").strip()

        # Examples
        examples: List[ArticleShort.Example] = []
        for ln in lines[2:]:
            m3 = cls.EXAMPLE_RE.match(ln)
            if not m3:
                raise ValueError(f"Invalid example line (must start with '>'): {ln!r}")
            content = m3.group("content").strip()
            if " - " in content:
                spanish, english = content.split(" - ", 1)
                examples.append(
                    cls.Example(spanish_text=spanish.strip(), translation=english.strip())
                )
            else:
                examples.append(cls.Example(spanish_text=content, translation=None))

        return cls(
            headword=headword,
            emoji=emoji,
            translation=translation,
            examples=examples,
            raw_markdown=original.strip(),
        )

    # --- Serialization ---------------------------------------------------

    def to_markdown(self) -> str:
        """
        Convert back to the standardized markdown format.
        """
        lines = [f"##### **{self.headword}**" + (f" {self.emoji}" if self.emoji else "")]
        lines.append(f"*{self.translation}*")
        for ex in self.examples:
            if ex.translation:
                lines.append(f"> {ex.spanish_text} - {ex.translation}")
            else:
                lines.append(f"> {ex.spanish_text}")
        return "\n".join(lines) + "\n"

    # --- Validation ------------------------------------------------------

    def validate(self) -> None:
        """
        Additional validation for manually constructed instances.
        Raises ValueError if any field is missing or invalid.
        """
        if not self.headword.strip():
            raise ValueError("Empty headword")
        if not self.translation.strip():
            raise ValueError("Empty translation")
        for ex in self.examples:
            if not ex.spanish_text.strip():
                raise ValueError("Empty example text")
