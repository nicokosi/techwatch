// TechWatch: read the daily digests and start a new run, without leaving Herdr.
// Opened as a dialog by mod.open:techwatch (ctrl-shift-d). Starting a run opens Claude on
// /veille in a tab, from the given date on and with the given focus if any; Claude asks
// whether to keep it. 👍/👎 under each item go to reactions.jsonl, which /profil reads.

import { View, div } from "gpui-kit";
import { v_flex, h_flex, InputState, Input, TextView } from "gpui-base";
import { run, props, closeOverlay, theme, exec, appHome, readTextFile, spaces } from "herdr";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const ITEM_RE = /^## \d+\. \[(.+)\]\((\S+)\)\s*$/m; // URLs hold no space, but may hold parentheses

// The digest cut at its `## ` headings: items carry their title and URL, so they can be voted on.
const sectionsOf = (text) => text.split(/\n(?=## )/).map((part) => {
  const m = part.match(ITEM_RE);
  return { text: part, title: m?.[1], url: m?.[2] };
});

// reactions.jsonl: one vote per line, the last one on a URL counts (see techwatch/reactions.py).
const votesOf = (text) => {
  const votes = {};
  for (const line of (text ?? "").split("\n")) {
    try { const e = JSON.parse(line); votes[e.url] = e.vote; } catch { /* a blank or hand-broken line costs one vote, not the dialog */ }
  }
  return votes;
};

export default class TechWatch extends View {
  init(_props, cx) {
    this.dates = [];
    this.selected = null;
    this.content = "";
    this.error = null;
    this.input = InputState.new({ placeholder: "Depuis le (AAAA-MM-JJ), vide : dernier digest" });
    this.input.on("change", (_e, cx) => { this.error = null; cx.notify(); });
    this.input.on("submit", (_e, cx) => this.launch(cx));
    this.focus = InputState.new({ placeholder: "Orientation, optionnelle : regarde en particulier le monitoring Java" });
    this.focus.on("submit", (_e, cx) => this.launch(cx));
    this.repo = null;
    this.votes = {};
    cx.spawn(async (cx) => {
      // `mise run install-herdr-mod` links this folder from the clone: the link leads back to it.
      const link = await exec("readlink", ["-f", `${appHome()}/mods/techwatch`]);
      this.repo = link.stdout.trim().replace(/\/herdr\/techwatch$/, "");
      this.votes = votesOf(await readTextFile(`${this.repo}/reactions.jsonl`).catch(() => null));
      const r = await exec("ls", [`${this.repo}/digests`]);
      this.dates = r.stdout.split("\n").filter((f) => /^\d{4}-\d{2}-\d{2}(-\d{4})?\.md$/.test(f)).map((f) => f.slice(0, -3)).sort().reverse();
      if (r.code !== 0) this.error = `Pas de digests dans ${this.repo}/digests`;
      cx.notify();
      if (this.dates.length) await this.open(this.dates[0], cx);
    });
  }

  async open(date, cx) {
    this.selected = date;
    this.content = await readTextFile(`${this.repo}/digests/${date}.md`).catch((e) => `Lecture impossible : ${e}`);
    cx.notify();
  }

  vote(section, vote, cx) {
    const before = this.votes[section.url];
    const next = before === vote ? 0 : vote; // a second click takes the vote back
    this.votes[section.url] = next;
    cx.notify();
    cx.spawn(async (cx) => {
      // --title=… in one element: a title starting with "-" would read as an option.
      const r = await exec("uv", ["run", "--project", this.repo, "techwatch-react", String(next), section.url,
        `--title=${section.title}`, `--file=${this.repo}/reactions.jsonl`], { cwd: this.repo })
        .catch((e) => ({ code: -1, stderr: String(e) }));
      if (r.code !== 0) {
        this.votes[section.url] = before;
        this.error = `Vote non enregistré : ${(r.stderr || r.stdout || "").trim().split("\n").pop()}`;
        cx.notify();
      }
    });
  }

  launch(cx) {
    if (!this.repo) return;
    const date = this.input.value().trim();
    if (date && !DATE_RE.test(date)) {
      this.error = "Date attendue au format AAAA-MM-JJ";
      cx.notify();
      return;
    }
    const focus = this.focus.value().trim();
    const argv = ["claude", ["/veille", date, focus].filter(Boolean).join(" ")];
    const tab = date ? `veille depuis ${date}` : "veille";
    closeOverlay(props().overlay);
    const space = spaces().find((s) => s.folder === this.repo);
    if (space) run("tab.new", { space: space.id, name: tab, folder: this.repo, argv });
    else run("space.new", { name: "TechWatch", folder: this.repo, tab, argv });
  }

  render(_cx) {
    const t = theme();
    const button = (id, text, action) => h_flex().id(id).h(32).px(14).items_center().rounded(8)
      .bg(t.solid).text_color(t.solid_foreground).text_size(12.5).font_medium().cursor_pointer()
      .hover((s) => s.opacity(0.88)).on_click(action).child(text);
    const row = (date) => h_flex().id(`tw-${date}`).px(10).py(6).rounded(6).cursor_pointer()
      .bg(date === this.selected ? t.selected : t.popover).hover((s) => s.bg(t.hover))
      .text_size(12.5).text_color(date === this.selected ? t.foreground : t.muted)
      .on_click((_e, cx) => cx.spawn(async (cx) => this.open(date, cx)))
      .child(date.replace(/-(\d{2})(\d{2})$/, " $1:$2"));
    return v_flex().size_full().overflow_hidden().p(18).gap(14).bg(t.popover).text_color(t.foreground)
      .child(h_flex().items_center()
        .child(div().flex_1().text_size(15).font_semibold().child("Veille"))
        .child(div().text_size(11).text_color(t.dim).child("Esc")))
      .child(h_flex().gap(8).items_center()
        .child(Input.new(this.input).w(300).flex_none().h(34).px(10).rounded(8).border_1().border_color(t.input).bg(t.background).text_size(12.5))
        .child(Input.new(this.focus).flex_1().h(34).px(10).rounded(8).border_1().border_color(t.input).bg(t.background).text_size(12.5))
        .child(button("tw-run", "Lancer la veille", (_e, cx) => this.launch(cx))))
      .child(div().text_size(11.5).text_color(this.error ? t.blocked : t.dim).child(this.error ??
        "Claude écrit un nouveau digest dans un onglet, puis te demande s'il faut le garder (commit et push). Avec une date : les articles depuis ce jour ; avec une orientation : ceux-là d'abord."))
      .child(h_flex().flex_1().min_h(0).items_stretch().gap(14) // h_flex centers its items: the columns must fill the height
        .child(v_flex().id("tw-list").w(130).flex_none().min_h(0).gap(2).overflow_y_scroll()
          .children(this.dates.length ? this.dates.map(row) : [div().text_size(12).text_color(t.dim).child("Aucun digest")]))
        .child(v_flex().id("tw-digest").flex_1().min_w(0).min_h(0).px(16).py(12).gap(16).rounded(8).bg(t.background).overflow_y_scroll()
          .text_size(13).children(sectionsOf(this.content).map((section, i) => this.section(section, i, t)))));
  }

  section(section, i, t) {
    const chip = (vote, glyph, color) => {
      const on = this.votes[section.url] === vote;
      return h_flex().id(`tw-vote-${this.selected}-${i}-${vote}`).h(24).px(8).items_center().rounded(6).cursor_pointer()
        .border_1().border_color(on ? t[color] : t.border).bg(on ? t[color] + "26" : t.background)
        .hover((s) => s.bg(t.hover)).on_click((_e, cx) => this.vote(section, vote, cx)).child(glyph);
    };
    return v_flex().gap(4)
      .child(TextView.markdown(`tw-md-${this.selected}-${i}`, section.text).selectable(true))
      .when(Boolean(section.url), (el) => el.child(h_flex().gap(6)
        .child(chip(1, "👍", "done"))
        .child(chip(-1, "👎", "blocked"))));
  }
}
