import { describe, expect, it } from "vitest";
import { articleFor } from "./selectors";
import { testGraph } from "./testGraph";
import { yamlFor } from "./yaml";

describe("YAML projection", () => {
  it("projects a multi-sense entry with its lineage and schedule", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemepicar0001")!);
    expect(document).toContain("# picar — Spanish");
    expect(document).toContain("id: lexemepicar0001");
    expect(document).toContain(String.raw`ipa: "/piˈkaɾ/"`);
    expect(document).toContain("topics: [Food]");
    expect(document).toContain("shortGloss: to itch; to chop");
    expect(document.match(/^ {2}- order: /gm)).toHaveLength(2);
    expect(document).toContain("      - { lang: en, terms: [to chop, to dice] }");
    expect(document).toContain("        videoTitle: Comiendo en un mercado");
    expect(document).toContain("        videoStart: 461");
    expect(document).toContain("        approved: false");
    expect(document).toContain("attestations:");
    expect(document).toContain("  system: anki");
  });

  it("marks a derived short form rather than inventing one", () => {
    const document = yamlFor(articleFor(testGraph(), "lexemebalsa0001")!);
    expect(document).toContain("shortGloss: null");
    expect(document).toContain("gender: feminine");
    expect(document).not.toContain("ipa:");
  });

  it("quotes anything that would not survive as a plain YAML scalar", () => {
    const graph = testGraph();
    graph.lexemes[1].headword = "yes: really";
    const document = yamlFor(articleFor(graph, "lexemebalsa0001")!);
    expect(document).toContain('headword: "yes: really"');
  });
});
