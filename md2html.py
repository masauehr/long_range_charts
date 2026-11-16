"""GUIDE.md を、公開サイト用の1ページ（guide.html）に変換する小さな変換器（外部ライブラリなし）。

対応する書き方: ![説明](画像パス)・# ## ### 見出し・段落・- と 1. の箇条書き・| 表 |・> 引用・``` コードブロック・---（区切り線）・**太字**・`コード`・[文字](URL)。
GUIDE.md はこの範囲で書くこと（それ以外の Markdown は正しく変換されない）。
使い方: python md2html.py GUIDE.md out.html
"""
import html
import re
import sys

STYLE = """
:root { --bg:#f7f7f5; --fg:#1d1f21; --muted:#6a6f76; --card:#fff; --line:#d9dbde; --accent:#1f5fa8; --note:#e8f0fa; --code:#eef0f2; }
@media (prefers-color-scheme: dark) { :root { --bg:#17191c; --fg:#e8e9ea; --muted:#9aa0a6; --card:#202327; --line:#363a40; --accent:#6aa7ea; --note:#1c2a3a; --code:#262a30; } }
* { box-sizing: border-box; }
body { margin:0; padding:0 16px 40px; background:var(--bg); color:var(--fg); font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif; line-height:1.8; }
main { max-width: 900px; margin: 0 auto; }
nav.top { max-width: 900px; margin: 12px auto 0; font-size: .9rem; }
a { color: var(--accent); }
h1 { font-size: 1.5rem; margin: 18px 0 8px; }
h2 { font-size: 1.25rem; margin: 32px 0 8px; padding-bottom: 4px; border-bottom: 2px solid var(--line); }
h3 { font-size: 1.05rem; margin: 22px 0 6px; }
blockquote { margin: 12px 0; padding: 8px 14px; background: var(--note); border-left: 4px solid var(--accent); border-radius: 4px; }
blockquote p { margin: 4px 0; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: .92rem; display: block; overflow-x: auto; }
th, td { border: 1px solid var(--line); padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: var(--card); }
pre { background: var(--code); padding: 10px 14px; border-radius: 6px; overflow-x: auto; line-height: 1.5; font-size: .88rem; }
code { background: var(--code); padding: 1px 5px; border-radius: 4px; font-size: .9em; }
pre code { background: none; padding: 0; }
hr { border: none; border-top: 1px solid var(--line); margin: 28px 0; }
li { margin: 3px 0; }
footer { max-width: 900px; margin: 30px auto 0; color: var(--muted); font-size: .8rem; border-top: 1px solid var(--line); padding-top: 8px; }
"""


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


def convert(md, title="ガイド", back_href="index.html", back_text="← 図のビューアへ戻る"):
    lines = md.split("\n")
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):                                   # コードブロック
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j])
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            i = j + 1
        elif re.match(r"^#{1,3} ", ln):
            n = len(ln) - len(ln.lstrip("#"))
            out.append(f"<h{n}>{inline(ln[n + 1:])}</h{n}>")
            i += 1
        elif re.match(r"^!\[[^\]]*\]\([^)]+\)\s*$", ln):                # 画像（1行）
            m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", ln)
            out.append(f'<figure><img src="{html.escape(m.group(2))}" alt="{html.escape(m.group(1))}" style="max-width:100%;height:auto;border:1px solid var(--line);border-radius:4px;background:#fff"><figcaption style="font-size:.85rem;color:var(--muted)">{html.escape(m.group(1))}</figcaption></figure>')
            i += 1
        elif ln.strip() == "---":
            out.append("<hr>")
            i += 1
        elif ln.startswith(">"):                                   # 引用（連続する行をまとめる）
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i][1:].strip())
                i += 1
            items = [b for b in buf if b]
            ul = [b[2:] for b in items if b.startswith("- ")]
            body = "".join(f"<p>{inline(b)}</p>" for b in items if not b.startswith("- "))
            if ul:
                body += "<ul>" + "".join(f"<li>{inline(u)}</li>" for u in ul) + "</ul>"
            out.append(f"<blockquote>{body}</blockquote>")
        elif ln.startswith("|"):                                   # 表
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[2:]]
            t = "<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
            for r in body:
                t += "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
            out.append(t + "</tbody></table>")
        elif re.match(r"^(- |\d+\. )", ln):                       # 箇条書き（- と 1.）
            ordered = bool(re.match(r"^\d+\. ", ln))
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines) and re.match(r"^(- |\d+\. )", lines[i]):
                items.append(re.sub(r"^(- |\d+\. )", "", lines[i]))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
        elif ln.strip() == "":
            i += 1
        else:                                                      # 段落（空行までの連続行）
            buf = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,3} |```|\||>|- |\d+\. |---$|!\[)", lines[i]):
                buf.append(lines[i].strip())
                i += 1
            if not buf:                                            # どれにも当てはまらない行は1行の段落として進める
                buf = [ln.strip()]
                i += 1
            out.append("<p>" + inline("<br>".join(buf).replace("<br>", "\n")).replace("\n", "<br>") + "</p>")
    body = "\n".join(out)
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{STYLE}</style>
</head>
<body>
<nav class="top"><a href="{back_href}">{back_text}</a></nav>
<main>
{body}
</main>
<footer>これは気象庁の公式予報ではありません。データ・ライセンスの詳細は NOTICE.md を参照してください。</footer>
</body>
</html>
"""


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    t = convert(open(src, encoding="utf-8").read(), title="長期予報の図 かんたんガイド")
    open(dst, "w", encoding="utf-8").write(t)
    print(f"{src} → {dst}")
