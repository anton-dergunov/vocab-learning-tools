import { describe, expect, it } from "vitest";
import { accentedPinyin, accentedPinyinInText, isNumberedPinyin } from "./pinyin";

describe("accentedPinyin", () => {
  it("marks the tone where the rule puts it", () => {
    expect(accentedPinyin("han4 zi4")).toBe("hàn zì");
    expect(accentedPinyin("Fang1 shan1 Xian4")).toBe("Fāng shān Xiàn");
    expect(accentedPinyin("ni2 jiang1")).toBe("ní jiāng");
    // `a` and `e` win wherever they are; `ou` marks the o; otherwise the last vowel takes it.
    expect(accentedPinyin("hao3")).toBe("hǎo");
    expect(accentedPinyin("gou3")).toBe("gǒu");
    expect(accentedPinyin("hui4")).toBe("huì");
    expect(accentedPinyin("xie4")).toBe("xiè");
  });

  it("writes ü for both spellings an ASCII format uses", () => {
    expect(accentedPinyin("Lu:3 liang2")).toBe("Lǚ liáng");
    expect(accentedPinyin("nv3")).toBe("nǚ");
  });

  it("drops the digit for a neutral tone rather than marking it", () => {
    expect(accentedPinyin("ma5")).toBe("ma");
    expect(accentedPinyin("de0")).toBe("de");
  });

  it("leaves alone anything that is not numbered pinyin", () => {
    expect(accentedPinyin("hàn zì")).toBe("hàn zì");
    expect(accentedPinyin("てあらいき")).toBe("てあらいき");
    expect(accentedPinyin("/maloˈɡɾaɾ/")).toBe("/maloˈɡɾaɾ/");
    expect(isNumberedPinyin("case study")).toBe(false);
  });

  it("marks the cross-references CC-CEDICT writes inside a definition", () => {
    expect(accentedPinyinInText("a county in Lüliang City 呂梁市|吕梁市[Lu:3 liang2 Shi4], Shanxi"))
      .toBe("a county in Lüliang City 呂梁市|吕梁市[Lǚ liáng Shì], Shanxi");
    // Some builds space out the `u:` that stands for `ü`; closing it up is what makes them read.
    expect(accentedPinyinInText("City 呂梁市|吕梁市[Lu : 3 liang2 Shi4], Shanxi"))
      .toBe("City 呂梁市|吕梁市[Lǚ liáng Shì], Shanxi");
    // An IPA transcription in brackets is not a reading and must survive untouched.
    expect(accentedPinyinInText("noise [bʲɪɡlʲɪˈt͡sax]")).toBe("noise [bʲɪɡlʲɪˈt͡sax]");
  });
});
