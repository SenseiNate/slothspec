"""Write the redline: a self-contained HTML page plus a CSV for the RVTM crowd."""
from __future__ import annotations

import csv
import html
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from .rules import SEV_WEIGHT, score


def _highlight(text: str, findings) -> str:
    out = html.escape(text)
    seen = set()
    for f in sorted(findings, key=lambda x: -len(x.match)):
        m = f.match.strip()
        if not m or m.lower() in seen or f.rule in ("compound requirement", "long statement"):
            continue
        seen.add(m.lower())
        esc = html.escape(m)
        out = re.sub(rf"(?<![\w>])({re.escape(esc)})(?![\w<])", rf'<mark class="{f.severity}" title="{html.escape(f.rule)}">\1</mark>', out, count=1, flags=re.I)
    return out


def write_csv(reqs, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ID", "Requirement", "Score", "Rule findings", "Model verdict", "Verifiable", "Singular",
                    "Model issues", "Verification method", "How to verify", "Suggested rewrite", "Rewritten by"])
        for r in reqs:
            m = r.llm or {}
            w.writerow([
                r.rid, r.text, score(r.findings),
                "; ".join(f"{f.rule}: {f.match}" for f in r.findings),
                m.get("verdict", ""), m.get("verifiable", ""), m.get("singular", ""),
                "; ".join(m.get("issues", [])), m.get("verification_method", ""),
                m.get("how_to_verify", ""), m.get("rewrite", ""), m.get("editor", ""),
            ])


def _high_confidence(r) -> bool:
    """The model flagged it AND a medium/high pattern check fired. On the NASA doc these were
    the comments worth sending; model-only flags were pickier."""
    return bool(r.llm) and r.llm.get("verdict") != "good" and any(f.severity in ("high", "med") for f in r.findings)


def write_html(reqs, path: Path, source: str, model: str | None, seconds: float,
               timing: dict | None = None, cached: int = 0) -> None:
    total = len(reqs)
    ran_model = any(r.llm for r in reqs)
    clean = sum(1 for r in reqs if not r.findings and (not r.llm or r.llm.get("verdict") == "good"))
    flagged = total - clean
    model_flagged = sum(1 for r in reqs if r.llm and r.llm.get("verdict") != "good")
    confident = sum(1 for r in reqs if _high_confidence(r))
    rules = Counter(f.rule for r in reqs for f in r.findings)
    methods = Counter((r.llm or {}).get("verification_method") for r in reqs if r.llm)
    high = sum(1 for r in reqs if any(f.severity == "high" for f in r.findings))

    rows = []
    for r in sorted(reqs, key=lambda x: (not _high_confidence(x), -score(x.findings))):
        m = r.llm or {}
        sev = "high" if any(f.severity == "high" for f in r.findings) else ("med" if r.findings else "ok")
        if m.get("verdict") == "rewrite":
            sev = "high"
        chips = "".join(
            f'<li><span class="chip {f.severity}">{html.escape(f.rule)}</span> {html.escape(f.why)}</li>'
            for f in sorted(r.findings, key=lambda f: -SEV_WEIGHT[f.severity])
        )
        model_block = ""
        if m:
            issues = "".join(f"<li>{html.escape(i)}</li>" for i in m.get("issues", []))
            rewrite = "<br>".join(html.escape(x) for x in m.get("rewrite", "").splitlines() if x.strip())
            model_block = f"""
            <div class="model">
              <div class="mhead"><span class="verdict v-{m.get('verdict','').replace(' ','-')}">{html.escape(m.get('verdict',''))}</span>
              <span class="vm">{html.escape(m.get('verification_method',''))}</span>{f'<span class="vm">rewrite: {html.escape(m["editor"])}</span>' if m.get('editor') else ''}</div>
              {f'<ul class="issues">{issues}</ul>' if issues else ''}
              <p class="howto"><b>Verify by:</b> {html.escape(m.get('how_to_verify',''))}</p>
              <div class="rewrite"><b>Suggested rewrite</b><p>{rewrite}</p></div>
            </div>"""
        rows.append(f"""
        <article class="req {sev}" data-sev="{sev}" data-conf="{'1' if _high_confidence(r) else '0'}">
          <header><code>{html.escape(r.rid)}</code>{'<span class="conf">high confidence</span>' if _high_confidence(r) else ''}<span class="score">score {score(r.findings)}</span></header>
          <p class="text">{_highlight(r.text, r.findings)}</p>
          {f'<ul class="findings">{chips}</ul>' if chips else '<p class="okline">No pattern hits.</p>'}
          {model_block}
        </article>""")

    if ran_model:
        stats = [(total, "requirements found"), (model_flagged, "flagged by the model"),
                 (confident, "high confidence: pattern check and model agree"),
                 (total - model_flagged, "model says good")]
    else:
        stats = [(total, "requirements found"), (flagged, "with a pattern hit"),
                 (high, "with a high-severity hit"), (clean, "look clean")]
    stats_html = "".join(f'  <div class="stat"><b>{n}</b><span>{html.escape(label)}</span></div>\n' for n, label in stats)
    run_note = f"{seconds:.0f}s" + ((" (" + ", ".join(f"{k} {v:.0f}s" for k, v in timing.items()) + ")") if timing else "")
    if cached:
        run_note += f"; {cached} model answers reused from an earlier run's cache"
    top = "".join(f"<li><span>{html.escape(k)}</span><b>{v}</b></li>" for k, v in rules.most_common(8))
    meth = "".join(f"<li><span>{html.escape(k)}</span><b>{v}</b></li>" for k, v in methods.most_common() if k)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SlothSpec Redline</title>
<style>
:root{{--bg:#f6f4ef;--card:#fff;--ink:#1f1d1a;--mute:#6b665d;--line:#e3ded3;--high:#c2410c;--med:#b45309;--low:#64748b;--ok:#3f7d4e;--acc:#5b4636}}
@media (prefers-color-scheme:dark){{:root{{--bg:#171512;--card:#211e1a;--ink:#ece7de;--mute:#a39b8e;--line:#36312a;--high:#fb923c;--med:#fbbf24;--low:#94a3b8;--ok:#7fc28f;--acc:#d6b89a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}}
.wrap{{max-width:980px;margin:0 auto;padding:28px 16px 60px}}
h1{{font-size:26px;margin:0 0 4px}}.sub{{color:var(--mute);margin:0 0 22px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:18px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}.stat b{{display:block;font-size:24px}}.stat span{{color:var(--mute);font-size:13px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:18px}}@media(max-width:640px){{.two{{grid-template-columns:1fr}}}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}.box h3{{margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--mute)}}
.box ul{{list-style:none;margin:0;padding:0}}.box li{{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px dashed var(--line)}}
.filters{{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 14px}}.filters button{{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:5px 12px;cursor:pointer;font:inherit;font-size:13px}}.filters button.on{{background:var(--acc);color:var(--bg);border-color:var(--acc)}}
.req{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--ok);border-radius:10px;padding:14px 16px;margin-bottom:10px}}
.req.high{{border-left-color:var(--high)}}.req.med{{border-left-color:var(--med)}}
.req header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}}.req code{{font-weight:600}}.conf{{margin-left:8px;margin-right:auto;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--ok);border:1px solid var(--ok);border-radius:999px;padding:1px 7px}}.score{{color:var(--mute);font-size:12px}}
.text{{margin:0 0 8px;font-size:16px}}mark{{background:transparent;border-bottom:2px solid;padding:0 1px;color:inherit}}mark.high{{border-color:var(--high)}}mark.med{{border-color:var(--med)}}mark.low{{border-color:var(--low)}}
.findings{{margin:0;padding:0;list-style:none;font-size:13.5px;color:var(--mute)}}.findings li{{margin:3px 0}}
.chip{{display:inline-block;font-size:11.5px;font-weight:600;padding:1px 7px;border-radius:999px;margin-right:4px;border:1px solid}}.chip.high{{color:var(--high)}}.chip.med{{color:var(--med)}}.chip.low{{color:var(--low)}}
.okline{{color:var(--ok);margin:0;font-size:13.5px}}
.model{{margin-top:10px;border-top:1px solid var(--line);padding-top:10px}}.mhead{{display:flex;gap:8px;align-items:center}}
.verdict{{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}}.v-good{{color:var(--ok)}}.v-needs-work{{color:var(--med)}}.v-rewrite{{color:var(--high)}}
.vm{{font-size:12px;border:1px solid var(--line);border-radius:6px;padding:0 6px;color:var(--mute)}}
.issues{{margin:6px 0;padding-left:18px;font-size:13.5px}}.howto{{font-size:13.5px;margin:4px 0;color:var(--mute)}}
.rewrite{{background:var(--bg);border-radius:8px;padding:8px 10px;margin-top:6px;font-size:14px}}.rewrite p{{margin:4px 0 0}}
footer{{color:var(--mute);font-size:12.5px;margin-top:24px}}
</style></head><body><div class="wrap">
<h1>🦥 SlothSpec redline</h1>
<p class="sub">{html.escape(source)} · {datetime.now():%b %d %Y %H:%M} · {html.escape(model or 'rules only')} · {html.escape(run_note)}, all local</p>
<div class="stats">
{stats_html}
</div>
<div class="two"><div class="box"><h3>Most common problems</h3><ul>{top or '<li>none</li>'}</ul></div>
<div class="box"><h3>Verification methods (model)</h3><ul>{meth or '<li>run with the model to fill this in</li>'}</ul></div></div>
<div class="filters"><button class="on" data-f="all">All</button>{'<button data-f="conf">High confidence</button>' if confident else ''}<button data-f="high">High</button><button data-f="med">Medium</button><button data-f="ok">Clean</button></div>
{''.join(rows)}
<footer>High-confidence findings first, then worst first by pattern-check score. Pattern checks are deterministic; model notes are suggestions, not gospel. Nothing in this report left this machine.</footer>
</div><script>
document.querySelectorAll('.filters button').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.filters button').forEach(x=>x.classList.remove('on'));b.classList.add('on');const f=b.dataset.f;document.querySelectorAll('.req').forEach(r=>r.style.display=(f==='all'||(f==='conf'?r.dataset.conf==='1':r.dataset.sev===f))?'':'none')}});
</script></body></html>"""
    path.write_text(doc, encoding="utf-8")
