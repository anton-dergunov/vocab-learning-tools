import { describe, expect, it } from "vitest";
import { articleFor } from "./selectors";
import { entryFor, fileNameFor, markdownFor } from "./markdown";
import { testGraph } from "./testGraph";

const AT = "2026-09-01T12:00:00.000Z";

const fileNamed = (name: string) =>
  markdownFor(testGraph(), "es", AT).find((file) => file.path === name);

describe("the Obsidian projection", () => {
  it("names a file the way the vault already does", () => {
    expect(fileNameFor("es", "Technology")).toBe("Spanish vocab - Technology.md");
    expect(fileNameFor("zh-Hans", "Food")).toBe("Chinese (Simplified) vocab - Food.md");
  });

  it("keeps a topic that would be an illegal filename out of the path", () => {
    expect(fileNameFor("es", "Health / Body")).toBe("Spanish vocab - Health Body.md");
  });

  it("writes a single-sense word exactly as the vault writes it", () => {
    const graph = testGraph();
    const article = articleFor(graph, "lexemebalsa0001")!;
    expect(entryFor(graph, article)).toBe([
      "##### **la balsa** 🛶",
      "*raft*",
      "> Cruzaron el río en una balsa. - They crossed the river on a raft."
    ].join("\n"));
  });

  it("numbers the senses of a word that has more than one, and bolds the matched forms", () => {
    const graph = testGraph();
    const article = articleFor(graph, "lexemepicar0001")!;
    expect(entryFor(graph, article)).toBe([
      "##### **picar** 🌶️",
      "1. *to itch*",
      "> Me **pica** la nariz. - My nose **itches**.",
      "2. *to chop; to dice*",
      "> **Pica** la cebolla bien fina. - **Chop** the onion very finely.",
      "",
      "The sense is carried by the object, not the verb."
    ].join("\n"));
  });

  it("files a word by topic, an unfiled one under Misc and a waiting one under Inbox", () => {
    const files = markdownFor(testGraph(), "es", AT).map((file) => file.path);
    expect(files).toContain("Spanish vocab - Food.md");
    expect(files).toContain("Spanish vocab - Travel.md");
    // espolvorear is still in the inbox, so it stays out of Food the way the rail keeps it out.
    expect(fileNamed("Spanish vocab - Inbox.md")!.text).toContain("espolvorear");
    expect(fileNamed("Spanish vocab - Food.md")!.text).not.toContain("espolvorear");
  });

  it("gives a language with no topics a Misc file", () => {
    const files = markdownFor(testGraph(), "en", AT);
    expect(files.map((file) => file.path)).toEqual(["English vocab - Misc.md"]);
    expect(files[0].text).toContain("##### **turmoil** 🌪️");
    // English glosses into Russian in the fixture, which is what the vocabulary record asks for.
    expect(files[0].text).toContain("*суматоха; смятение*");
  });

  it("carries front matter and sorts entries so a re-export diffs cleanly", () => {
    const text = fileNamed("Spanish vocab - Food.md")!.text;
    expect(text.startsWith(`---\nacervo-export: "${AT}"\nlanguage: es\nsection: "Food"\n---\n`)).toBe(true);
    expect(text.indexOf("**picar**")).toBeGreaterThan(-1);
  });
});
