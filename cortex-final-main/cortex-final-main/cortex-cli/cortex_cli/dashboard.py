"""cortex dashboard -- generate a self-contained GitLab Pages HTML dashboard."""

from __future__ import annotations

import html
import os
import re
from datetime import datetime, date
from typing import Any


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _field(m: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = m.get(k, "")
        if v:
            return str(v)
    return default


def _is_org_memory(m: dict) -> bool:
    scope = _field(m, "scope", "Scope").upper()
    return scope in ("ORGANISATION", "ORGANIZATION")


def _parse_carbon(raw: str) -> tuple[float, float]:
    if not raw or raw.strip().upper() == "N/A":
        return 0.0, 0.0
    m = re.search(r"[~+]?\s*(\d+(?:\.\d+)?)", raw)
    if m is None:
        return 0.0, 0.0
    value = float(m.group(1))
    if "cost" in raw.lower():
        return 0.0, value
    return value, 0.0


def _extract_ids(raw: str) -> list[int]:
    return [int(x) for x in re.findall(r"#(\d+)", raw)]


def _age_days(date_str: str) -> int:
    try:
        d = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, AttributeError):
        return -1


_CO2_FACTOR = 0.4
_KG_PER_TREE_YEAR = 22.0


def generate_dashboard(
    memories: list[dict],
    patterns: list[dict],
    output_path: str = "public/index.html",
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    org_mems = [m for m in memories if _is_org_memory(m)]
    project_mems = [m for m in memories if not _is_org_memory(m)]

    total = len(memories)
    org_count = len(org_mems)
    project_count = len(project_mems)

    active = sum(1 for m in memories if _field(m, "status", "Status").lower() == "active")
    superseded = sum(1 for m in memories if _field(m, "status", "Status").lower() == "superseded")
    overridden = sum(1 for m in memories if _field(m, "status", "Status").lower() == "overridden")
    security_count = sum(
        1 for m in memories
        if _field(m, "Security relevant", "security_relevant").lower() in ("yes", "true")
    )

    org_sources: set[str] = set()
    for m in org_mems:
        sp = _field(m, "source_project", "Source project")
        if sp:
            org_sources.add(sp)
    org_source_count = len(org_sources)

    file_map: dict[str, list[int]] = {}
    for m in memories:
        for fp in re.split(r"[,;\s]+", _field(m, "Governs files", "governs_files")):
            fp = fp.strip()
            if fp:
                file_map.setdefault(fp, []).append(m["id"])
    files_governed = len(file_map)

    total_savings = 0.0
    total_cost = 0.0
    for m in memories:
        s, c = _parse_carbon(_field(m, "Carbon impact", "carbon_impact"))
        total_savings += s
        total_cost += c
    net_kwh = total_savings - total_cost
    co2_kg = net_kwh * _CO2_FACTOR
    trees_year = (co2_kg * 12) / _KG_PER_TREE_YEAR if _KG_PER_TREE_YEAR else 0

    pattern_count = len(patterns)

    sections: list[str] = []
    sections.append(_section_summary_cards(
        total, project_count, org_count, active, superseded, overridden,
        security_count, files_governed, net_kwh, pattern_count,
    ))
    sections.append(_section_hero_moments(org_source_count))
    sections.append(_section_mermaid_graph(memories))
    if org_mems:
        sections.append(_section_org_registry(org_mems))
    sections.append(_section_carbon_table(memories, total_savings, total_cost, net_kwh, co2_kg, trees_year))
    sections.append(_section_file_coverage(file_map, memories))
    sections.append(_section_security_inventory(memories))
    sections.append(_section_pattern_rules(patterns))
    sections.append(_section_memory_details(memories))

    body = "\n".join(sections)
    page = _wrap_page(body, now, org_source_count)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(page)

    return os.path.abspath(output_path)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _panel(cmd: str, sub: str, inner: str, extra_class: str = "") -> str:
    cls = f'panel {extra_class}'.strip()
    return (
        f'<section class="{cls}">'
        f'<div class="panel-header">'
        f'<span class="cmd">{cmd}</span>'
        f'<span class="cmd-sep">::</span>'
        f'<span class="cmd-sub">{sub}</span>'
        f'</div>'
        f'{inner}'
        f'</section>'
    )


def _section_summary_cards(
    total: int, project_count: int, org_count: int,
    active: int, superseded: int, overridden: int,
    security: int, files: int, net_kwh: float, patterns: int,
) -> str:
    def _card(label: str, value: str | int, accent: str = "green", pulse: bool = False) -> str:
        dot = '<span class="led pulse"></span>' if pulse else f'<span class="led led-{accent}"></span>'
        return (
            f'<div class="stat-cell accent-{accent}">'
            f'<div class="stat-label">{dot}{label}</div>'
            f'<div class="stat-value">{value}</div>'
            f'</div>'
        )

    cards = [
        _card("MEMORIES", total, "green"),
        _card("ACTIVE", active, "green", pulse=True),
        _card("EVOLVED", superseded, "yellow"),
        _card("ORG_SHARED", org_count, "cyan"),
        _card("SECURITY", security, "red"),
    ]
    inner = '<div class="stat-grid">' + "".join(cards) + '</div>'
    return _panel("cortex", "intelligence_summary", inner)


def _section_hero_moments(org_source_count: int) -> str:
    org_line = ""
    if org_source_count > 0:
        org_line = (
            f'<div class="sys-line">'
            f'SYS &gt; org_monitor.active &mdash; '
            f'tracking <strong>{org_source_count}</strong> '
            f'upstream project{"s" if org_source_count != 1 else ""}'
            f'</div>'
        )

    lc_nodes = [
        ("lc-default", "DECISION", "recorded"),
        ("lc-conflict", "CONFLICT", "detected"),
        ("lc-default", "REVIEW", "human"),
        ("lc-intent", "OVERRIDE", "intentional"),
        ("lc-default", "NEW_MEM", "written"),
        ("lc-org", "ORG_PROMOTE", "shared"),
    ]
    lc_html = ""
    for i, (cls, label, sub) in enumerate(lc_nodes):
        lc_html += f'<div class="lc-node {cls}">{label}<br><span class="lc-sub">{sub}</span></div>'
        if i < len(lc_nodes) - 1:
            lc_html += '<div class="lc-arrow">&#8594;</div>'

    inner = (
        f'<div class="tagline">// Every engineering activity strengthens the next engineering decision.</div>'
        f'{org_line}'
        f'<div class="lifecycle">{lc_html}</div>'
    )
    return _panel("cortex", "system_overview", inner, "hero-panel")


def _section_mermaid_graph(memories: list[dict]) -> str:
    if not memories:
        return _panel("cortex", "knowledge_graph", '<p class="nil">// no memories to graph</p>')

    import json as _json

    nodes = []
    links = []
    id_set = {m["id"] for m in memories}

    for m in memories:
        mid = m["id"]
        status = _field(m, "Status", "status").lower()
        is_org = _is_org_memory(m)
        is_security = _field(m, "Security relevant", "security_relevant").lower() in ("yes", "true")
        is_superseded = status == "superseded"
        decision = _field(m, "Decision", "decision", default="?")
        source_proj = _field(m, "source_project", "Source project")
        label = f"#{mid:03d}: {decision[:48]}"
        if is_org and source_proj:
            label += f" [{source_proj}]"
        node_type = "org" if is_org else ("security" if is_security else ("superseded" if is_superseded else "active"))
        nodes.append({"id": mid, "label": label, "type": node_type, "full": decision})

    for m in memories:
        mid = m["id"]
        for dep_id in _extract_ids(_field(m, "Depends on", "depends_on")):
            if dep_id in id_set:
                links.append({"source": dep_id, "target": mid, "kind": "depends"})
        for blk_id in _extract_ids(_field(m, "Blocks", "blocks")):
            if blk_id in id_set:
                links.append({"source": mid, "target": blk_id, "kind": "blocks"})

    graph_data = _json.dumps({"nodes": nodes, "links": links})

    legend = (
        '<div class="graph-legend">'
        '<span class="legend-item"><span class="legend-dot" style="background:#00ff88"></span> active</span>'
        '<span class="legend-item"><span class="legend-dot" style="background:#00fff2"></span> org</span>'
        '<span class="legend-item"><span class="legend-dot" style="background:#ff2d55"></span> security</span>'
        '<span class="legend-item"><span class="legend-dot" style="background:#50506a"></span> superseded</span>'
        '<span class="legend-item" style="gap:0.3rem"><span style="border-top:2px dashed #50506a;width:18px;display:inline-block"></span> blocks</span>'
        '</div>'
    )

    inner = f'''{legend}
<div class="kg-wrap">
  <canvas id="kg-canvas"></canvas>
  <div id="kg-tooltip"></div>
</div>
<script>
(function() {{
  var RAW = {graph_data};
  var canvas = document.getElementById('kg-canvas');
  var tooltip = document.getElementById('kg-tooltip');
  var ctx = canvas.getContext('2d');

  var COLOR = {{
    active:     '#00ff88',
    org:        '#00fff2',
    security:   '#ff2d55',
    superseded: '#50506a',
    bg:         '#07070f',
    surface:    '#0d0d1a',
    border:     '#1a1a2e',
    text:       '#c8c8d8',
    depends:    '#b060ff',
    blocks:     '#ff2d55',
  }};

  function resize() {{
    var wrap = canvas.parentElement;
    canvas.width  = wrap.clientWidth  || 900;
    canvas.height = Math.max(420, Math.min(600, window.innerHeight * 0.55));
  }}
  resize();
  window.addEventListener('resize', function() {{ resize(); sim(); }});

  /* --- build node/link objects --- */
  var nodes = RAW.nodes.map(function(n) {{
    return Object.assign({{}}, n, {{
      x: canvas.width  * 0.1 + Math.random() * canvas.width  * 0.8,
      y: canvas.height * 0.1 + Math.random() * canvas.height * 0.8,
      vx: 0, vy: 0, r: n.type === 'org' ? 14 : 11,
    }});
  }});
  var nodeMap = {{}};
  nodes.forEach(function(n) {{ nodeMap[n.id] = n; }});

  var links = RAW.links.map(function(l) {{
    return {{ source: nodeMap[l.source], target: nodeMap[l.target], kind: l.kind }};
  }}).filter(function(l) {{ return l.source && l.target; }});

  /* --- force simulation --- */
  var REPEL = 4800, ATTRACT = 0.012, DAMP = 0.82, LINK_LEN = 160, CENTER = 0.008;
  var running = true;

  function tick() {{
    var W = canvas.width, H = canvas.height;
    nodes.forEach(function(a) {{
      /* repulsion */
      nodes.forEach(function(b) {{
        if (a === b) return;
        var dx = a.x - b.x, dy = a.y - b.y;
        var d2 = dx*dx + dy*dy + 1;
        var f = REPEL / d2;
        a.vx += f * dx / Math.sqrt(d2);
        a.vy += f * dy / Math.sqrt(d2);
      }});
      /* center gravity */
      a.vx += (W/2 - a.x) * CENTER;
      a.vy += (H/2 - a.y) * CENTER;
    }});
    /* link spring */
    links.forEach(function(l) {{
      var dx = l.target.x - l.source.x, dy = l.target.y - l.source.y;
      var d = Math.sqrt(dx*dx + dy*dy) || 1;
      var f = (d - LINK_LEN) * ATTRACT;
      var fx = f * dx/d, fy = f * dy/d;
      l.source.vx += fx; l.source.vy += fy;
      l.target.vx -= fx; l.target.vy -= fy;
    }});
    /* integrate + clamp */
    nodes.forEach(function(n) {{
      n.vx *= DAMP; n.vy *= DAMP;
      n.x = Math.max(n.r + 4, Math.min(W - n.r - 4, n.x + n.vx));
      n.y = Math.max(n.r + 4, Math.min(H - n.r - 4, n.y + n.vy));
    }});
  }}

  /* --- glow helper --- */
  function glow(color, blur) {{
    ctx.shadowColor = color;
    ctx.shadowBlur  = blur;
  }}

  /* --- draw --- */
  var _frame = 0;
  function draw() {{
    var W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = COLOR.bg;
    ctx.fillRect(0, 0, W, H);

    /* links */
    links.forEach(function(l) {{
      var sx = l.source.x, sy = l.source.y, tx = l.target.x, ty = l.target.y;
      var isBlocks = l.kind === 'blocks';
      ctx.save();
      ctx.beginPath();
      if (isBlocks) {{ ctx.setLineDash([5,4]); }}
      ctx.strokeStyle = isBlocks ? COLOR.blocks : COLOR.depends;
      ctx.lineWidth = 1.5;
      glow(isBlocks ? COLOR.blocks : COLOR.depends, 6);
      ctx.moveTo(sx, sy);
      ctx.lineTo(tx, ty);
      ctx.stroke();
      /* arrowhead */
      var angle = Math.atan2(ty - sy, tx - sx);
      var tr = l.target.r + 3;
      var ax = tx - tr * Math.cos(angle), ay = ty - tr * Math.sin(angle);
      ctx.beginPath();
      ctx.setLineDash([]);
      ctx.fillStyle = isBlocks ? COLOR.blocks : COLOR.depends;
      ctx.moveTo(ax, ay);
      ctx.lineTo(ax - 9*Math.cos(angle-0.4), ay - 9*Math.sin(angle-0.4));
      ctx.lineTo(ax - 9*Math.cos(angle+0.4), ay - 9*Math.sin(angle+0.4));
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }});

    /* nodes */
    var pulse = 0.5 + 0.5 * Math.sin(_frame * 0.06);
    nodes.forEach(function(n) {{
      var c = COLOR[n.type] || COLOR.active;
      var isActive = n.type === 'active';
      var glowR = isActive ? 8 + pulse * 6 : 8;

      /* outer glow ring for org */
      if (n.type === 'org') {{
        ctx.save();
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r + 5, 0, Math.PI*2);
        ctx.strokeStyle = COLOR.org;
        ctx.lineWidth = 1;
        glow(COLOR.org, 12);
        ctx.stroke();
        ctx.restore();
      }}

      /* node circle */
      ctx.save();
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI*2);
      ctx.fillStyle = COLOR.surface;
      ctx.strokeStyle = c;
      ctx.lineWidth = n === _hover ? 3 : 2;
      glow(c, n === _hover ? 20 : glowR);
      ctx.fill();
      ctx.stroke();
      ctx.restore();

      /* superseded: dashed stroke overlay */
      if (n.type === 'superseded') {{
        ctx.save();
        ctx.beginPath();
        ctx.setLineDash([4,3]);
        ctx.arc(n.x, n.y, n.r + 3, 0, Math.PI*2);
        ctx.strokeStyle = COLOR.superseded;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.restore();
      }}

      /* id label inside node */
      ctx.save();
      ctx.fillStyle = c;
      ctx.font = 'bold 9px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      glow(c, 4);
      ctx.fillText('#' + String(n.id).padStart(3,'0'), n.x, n.y);
      ctx.restore();
    }});

    _frame++;
  }}

  function sim() {{
    if (!running) return;
    tick(); tick(); tick();
    draw();
    requestAnimationFrame(sim);
  }}
  sim();

  /* --- interaction --- */
  var _hover = null, _drag = null, _dragOffX = 0, _dragOffY = 0;

  function getPos(e) {{
    var r = canvas.getBoundingClientRect();
    var src = e.touches ? e.touches[0] : e;
    return {{ x: src.clientX - r.left, y: src.clientY - r.top }};
  }}
  function hitNode(x, y) {{
    for (var i = nodes.length-1; i >= 0; i--) {{
      var n = nodes[i];
      var dx = x-n.x, dy = y-n.y;
      if (dx*dx + dy*dy < (n.r+6)*(n.r+6)) return n;
    }}
    return null;
  }}

  canvas.addEventListener('mousemove', function(e) {{
    var p = getPos(e);
    if (_drag) {{
      _drag.x = p.x + _dragOffX;
      _drag.y = p.y + _dragOffY;
      _drag.vx = 0; _drag.vy = 0;
      return;
    }}
    var n = hitNode(p.x, p.y);
    _hover = n;
    canvas.style.cursor = n ? 'grab' : 'default';
    if (n) {{
      tooltip.style.display = 'block';
      tooltip.style.left = (p.x + 14) + 'px';
      tooltip.style.top  = (p.y - 10) + 'px';
      tooltip.textContent = n.full;
    }} else {{
      tooltip.style.display = 'none';
    }}
  }});
  canvas.addEventListener('mouseleave', function() {{
    _hover = null;
    _drag  = null;
    tooltip.style.display = 'none';
    canvas.style.cursor = 'default';
  }});
  canvas.addEventListener('mousedown', function(e) {{
    var p = getPos(e);
    var n = hitNode(p.x, p.y);
    if (n) {{
      _drag = n;
      _dragOffX = n.x - p.x;
      _dragOffY = n.y - p.y;
      canvas.style.cursor = 'grabbing';
    }}
  }});
  canvas.addEventListener('mouseup', function() {{
    _drag = null;
    canvas.style.cursor = _hover ? 'grab' : 'default';
  }});
}})();
</script>'''

    return _panel("cortex", "knowledge_graph", inner)


def _section_org_registry(org_mems: list[dict]) -> str:
    rows: list[str] = []
    for m in sorted(org_mems, key=lambda x: x.get("id", 0)):
        mid = m["id"]
        decision = _esc(_field(m, "Decision", "decision", default="N/A"))
        source_proj = _esc(_field(m, "source_project", "Source project"))
        promoted_by = _esc(_field(m, "promoted_by", "Promoted by"))
        status = _field(m, "status", "Status", default="Unknown")
        date_val = _field(m, "date", "Date")
        age = _age_days(date_val)
        age_str = f"{age}d" if age >= 0 else "?"
        stale = ' <span class="tag tag-yellow">STALE</span>' if age > 180 else ""
        sec = ' <span class="tag tag-red">SEC</span>' if _field(m, "Security relevant", "security_relevant").lower() in ("yes", "true") else ""
        rows.append(
            f'<tr>'
            f'<td class="mono">#{mid:03d}</td>'
            f'<td>{decision}</td>'
            f'<td><span class="tag tag-cyan">{source_proj or "—"}</span></td>'
            f'<td>{promoted_by or "—"}</td>'
            f'<td><span class="tag tag-{status.lower()}">{_esc(status)}</span>{sec}</td>'
            f'<td class="mono">{age_str}{stale}</td>'
            f'</tr>'
        )

    desc = '<div class="section-desc">// decisions promoted from individual projects into shared organisational knowledge</div>'
    table = (
        '<table><thead><tr>'
        '<th>ID</th><th>Decision</th><th>Source Project</th>'
        '<th>Promoted By</th><th>Status</th><th>Age</th>'
        '</tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody></table>'
    )
    return _panel("cortex", "org_registry", desc + table, "panel-org")


def _section_carbon_table(
    memories: list[dict],
    total_savings: float, total_cost: float,
    net_kwh: float, co2_kg: float, trees_year: float,
) -> str:
    rows: list[str] = []
    for m in memories:
        carbon_raw = _field(m, "Carbon impact", "carbon_impact")
        s, c = _parse_carbon(carbon_raw)
        if s == 0 and c == 0:
            continue
        cls = "val-green" if s > 0 else "val-red"
        rows.append(
            f'<tr>'
            f'<td class="mono">#{m["id"]:03d}</td>'
            f'<td>{_esc(_field(m, "Decision", "decision", default="N/A"))}</td>'
            f'<td class="{cls}">{_esc(carbon_raw)}</td>'
            f'</tr>'
        )
    if not rows:
        return _panel("cortex", "carbon_impact", '<p class="nil">// no carbon data recorded</p>')

    summary = (
        f'<tr class="summary-row">'
        f'<td colspan="2">TOTALS</td>'
        f'<td>'
        f'<span class="val-green">savings: {total_savings:.0f} kWh</span>'
        f'<span class="sep">|</span>'
        f'<span class="val-red">cost: {total_cost:.0f} kWh</span>'
        f'<span class="sep">|</span>'
        f'net: {net_kwh:+.0f} kWh'
        f'<span class="sep">|</span>'
        f'CO2: {co2_kg:.1f} kg/mo'
        f'<span class="sep">|</span>'
        f'trees: {trees_year:.1f}/yr'
        f'</td></tr>'
    )
    table = (
        '<table><thead><tr><th>ID</th><th>Decision</th><th>Impact</th></tr></thead>'
        '<tbody>' + "".join(rows) + summary + '</tbody></table>'
    )
    return _panel("cortex", "carbon_impact", table)


def _section_file_coverage(file_map: dict[str, list[int]], memories: list[dict]) -> str:
    if not file_map:
        return _panel("cortex", "file_coverage", '<p class="nil">// no governed files</p>')

    mem_lookup = {m["id"]: m for m in memories}
    rows: list[str] = []
    for fp in sorted(file_map):
        ids = file_map[fp]
        ids_str = " ".join(f'<span class="mem-ref">#{mid:03d}</span>' for mid in sorted(ids))
        has_security = any(
            _field(mem_lookup.get(mid, {}), "Security relevant", "security_relevant").lower() in ("yes", "true")
            for mid in ids
        )
        has_org = any(_is_org_memory(mem_lookup.get(mid, {})) for mid in ids)
        statuses = set(_field(mem_lookup.get(mid, {}), "Status", "status", default="?") for mid in ids)
        tier = '<span class="tag tag-cyan">ORG</span>' if has_org else '<span class="tag tag-purple">PROJECT</span>'
        sec = '<span class="tag tag-red">SEC</span>' if has_security else ""
        rows.append(
            f'<tr>'
            f'<td class="mono file-path">{_esc(fp)}</td>'
            f'<td>{ids_str}</td>'
            f'<td>{tier}</td>'
            f'<td>{sec}</td>'
            f'<td>{", ".join(sorted(statuses))}</td>'
            f'</tr>'
        )

    table = (
        '<table><thead><tr>'
        '<th>File Path</th><th>Governing Memories</th><th>Tier</th><th>Security</th><th>Status</th>'
        '</tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody></table>'
    )
    return _panel("cortex", "file_coverage", table)


def _section_security_inventory(memories: list[dict]) -> str:
    sec_mems = [
        m for m in memories
        if _field(m, "Security relevant", "security_relevant").lower() in ("yes", "true")
    ]
    if not sec_mems:
        return _panel("cortex", "security_inventory", '<p class="nil">// no security-relevant memories</p>')

    rows: list[str] = []
    for m in sec_mems:
        date_val = _field(m, "Date", "date")
        age = _age_days(date_val)
        age_str = f"{age}d" if age >= 0 else "?"
        stale = ' <span class="tag tag-yellow">STALE</span>' if age > 180 else ""
        status = _field(m, "Status", "status", default="N/A")
        is_org = _is_org_memory(m)
        scope = '<span class="tag tag-cyan">ORG</span>' if is_org else '<span class="tag tag-purple">PROJECT</span>'
        rows.append(
            f'<tr>'
            f'<td class="mono">#{m["id"]:03d}</td>'
            f'<td>{_esc(_field(m, "Decision", "decision", default="N/A"))}</td>'
            f'<td>{_esc(_field(m, "Decided by", "decided_by", default="N/A"))}</td>'
            f'<td class="mono">{_esc(date_val) if date_val else "N/A"}</td>'
            f'<td class="mono">{age_str}{stale}</td>'
            f'<td>{_esc(status)}</td>'
            f'<td>{scope}</td>'
            f'</tr>'
        )
    table = (
        '<table><thead><tr>'
        '<th>ID</th><th>Decision</th><th>Decided By</th>'
        '<th>Date</th><th>Age</th><th>Status</th><th>Scope</th>'
        '</tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody></table>'
    )
    return _panel("cortex", "security_inventory", table)


def _section_pattern_rules(patterns: list[dict]) -> str:
    if not patterns:
        return _panel("cortex", "pattern_rules", '<p class="nil">// no pattern rules defined</p>')

    rows: list[str] = []
    for p in patterns:
        examples = p.get("Examples", "")
        ex_html = f'<pre class="code-block">{_esc(examples)}</pre>' if examples else ""
        rows.append(
            f'<tr>'
            f'<td class="mono">P#{p["id"]:03d}</td>'
            f'<td>{_esc(p.get("Rule", "N/A"))}</td>'
            f'<td class="mono anti">{_esc(p.get("Anti-pattern", "N/A"))}</td>'
            f'<td>{_esc(p.get("Language", "N/A"))}</td>'
            f'<td>{_esc(p.get("Established by", "N/A"))}</td>'
            f'</tr>'
            f'<tr class="ex-row"><td colspan="5">{ex_html}</td></tr>'
        )
    table = (
        '<table><thead><tr>'
        '<th>ID</th><th>Rule</th><th>Anti-pattern</th><th>Language</th><th>Established By</th>'
        '</tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody></table>'
    )
    return _panel("cortex", "pattern_rules", table)


def _section_memory_details(memories: list[dict]) -> str:
    if not memories:
        return _panel("cortex", "memory_details", '<p class="nil">// no memories</p>')

    def sort_key(m: dict) -> tuple:
        order = {"active": 0, "superseded": 1}
        return (order.get(_field(m, "Status", "status").lower(), 2), 0 if _is_org_memory(m) else 1)

    cards: list[str] = []
    for m in sorted(memories, key=sort_key):
        mid = m["id"]
        status = _field(m, "Status", "status", default="Unknown")
        sc = status.lower().replace(" ", "-")
        decision = _esc(_field(m, "Decision", "decision", default="N/A"))
        is_org = _is_org_memory(m)

        org_badge = '<span class="tag tag-cyan" style="margin-left:0.5rem">ORG</span>' if is_org else ""
        extra = " mem-org" if is_org else ""

        org_fields = ""
        if is_org:
            for fk, fv_keys in [("source_project", ("source_project", "Source project")),
                                  ("promoted_by", ("promoted_by", "Promoted by")),
                                  ("scope", ("scope", "Scope"))]:
                val = _field(m, *fv_keys)
                if val:
                    org_fields += (
                        f'<div class="mem-field org-field">'
                        f'<span class="fk">{fk}:</span> {_esc(val)}'
                        f'</div>'
                    )

        skip = {"id", "scope", "source_project", "promoted_by", "Scope", "Source project", "Promoted by"}
        fields = "".join(
            f'<div class="mem-field"><span class="fk">{_esc(k)}:</span> {_esc(v)}</div>'
            for k, v in m.items() if k not in skip
        )

        cards.append(
            f'<details class="mem-card {sc}{extra}">'
            f'<summary>'
            f'<span class="mem-id">#{mid:03d}</span>'
            f' &mdash; {decision} '
            f'<span class="tag tag-{sc}">{_esc(status)}</span>'
            f'{org_badge}'
            f'</summary>'
            f'<div class="mem-body">{org_fields}{fields}</div>'
            f'</details>'
        )

    return _panel("cortex", "memory_details", "".join(cards))


# ---------------------------------------------------------------------------
# Page wrapper + CSS
# ---------------------------------------------------------------------------

def _wrap_page(body: str, timestamp: str, org_source_count: int = 0) -> str:
    org_header = ""
    if org_source_count > 0:
        org_header = (
            f'<div class="hdr-org">'
            f'ORG_MONITOR &gt; active &mdash; '
            f'{org_source_count} upstream project{"s" if org_source_count != 1 else ""} connected'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CORTEX &mdash; Institutional Memory</title>
<style>
/* ── reset + base ─────────────────────────────────────────── */
:root {{
  --bg:        #07070f;
  --surface:   #0d0d1a;
  --border:    #1a1a2e;
  --green:     #00ff88;
  --cyan:      #00fff2;
  --purple:    #b060ff;
  --yellow:    #ffe066;
  --red:       #ff2d55;
  --text:      #c8c8d8;
  --muted:     #50506a;
  --hdr-h:     64px;
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas", monospace;
  font-size: 14px;
  line-height: 1.65;
  min-height: 100vh;
  /* scanline overlay */
  background-image: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0,0,0,0.08) 2px,
    rgba(0,0,0,0.08) 4px
  );
}}

/* ── layout ───────────────────────────────────────────────── */
.hdr {{
  background: #050510;
  border-bottom: 1px solid var(--green);
  box-shadow: 0 0 24px rgba(0,255,136,0.15);
  padding: 0 2rem;
  height: var(--hdr-h);
  display: flex;
  align-items: center;
  gap: 2rem;
  position: sticky;
  top: 0;
  z-index: 100;
}}
.hdr-logo {{
  font-size: 1.5rem;
  font-weight: 900;
  letter-spacing: 0.15em;
  color: var(--green);
  text-shadow: 0 0 12px var(--green);
}}
.hdr-sub {{
  color: var(--muted);
  font-size: 0.78rem;
  letter-spacing: 0.05em;
}}
.hdr-ts {{
  margin-left: auto;
  color: var(--muted);
  font-size: 0.75rem;
}}
.hdr-org {{
  color: var(--cyan);
  font-size: 0.78rem;
  text-shadow: 0 0 8px var(--cyan);
}}
.main {{ max-width: 1280px; margin: 0 auto; padding: 2rem 1.5rem; }}

/* ── panels ───────────────────────────────────────────────── */
.panel {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-top: 2px solid var(--green);
  margin-bottom: 2rem;
  padding: 0;
  overflow: hidden;
}}
.panel-org {{ border-top-color: var(--cyan); }}
.panel-org .panel-header .cmd-sub {{ color: var(--cyan); }}
.panel-header {{
  display: flex;
  align-items: center;
  gap: 0;
  background: #0a0a18;
  border-bottom: 1px solid var(--border);
  padding: 0.55rem 1.25rem;
  font-size: 0.8rem;
  letter-spacing: 0.06em;
}}
.cmd      {{ color: var(--green); text-shadow: 0 0 8px var(--green); }}
.cmd-sep  {{ color: var(--muted); margin: 0 0.15rem; }}
.cmd-sub  {{ color: var(--text); }}
.panel > *:not(.panel-header) {{ padding: 1.25rem 1.5rem; }}
.panel > .stat-grid,
.panel > .moment-grid,
.panel > .lifecycle,
.panel > table,
.panel > .tagline,
.panel > .sys-line,
.panel > .mem-card,
.panel > .nil,
.panel > .graph-legend,
.panel > .kg-wrap,
.panel > .section-desc {{
  padding: 0; /* handled by parent padding below */
}}

/* inner spacing wrapper for hero */
.hero-panel > *:not(.panel-header) {{ padding: 0 1.5rem; }}
.hero-panel > .moment-grid {{ padding: 0 1.5rem; }}
.hero-panel > .lifecycle {{ padding: 1rem 1.5rem 1.5rem; }}
.hero-panel > .tagline {{ padding-top: 1.25rem; }}

/* ── stat grid (summary cards) ────────────────────────────── */
.stat-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1px;
  background: var(--border);
  padding: 0;
  margin: 0;
}}
.stat-cell {{
  background: var(--surface);
  padding: 1.1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  border-left: 3px solid transparent;
  transition: background 0.15s;
}}
.stat-cell:hover {{ background: #111124; }}
.accent-green  {{ border-left-color: var(--green); }}
.accent-cyan   {{ border-left-color: var(--cyan); }}
.accent-purple {{ border-left-color: var(--purple); }}
.accent-yellow {{ border-left-color: var(--yellow); }}
.accent-red    {{ border-left-color: var(--red); }}
.stat-label {{
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  color: var(--muted);
}}
.stat-value {{
  font-size: 1.75rem;
  font-weight: 900;
  color: #fff;
  line-height: 1;
  letter-spacing: -0.02em;
}}

/* ── LED dots ─────────────────────────────────────────────── */
.led {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--muted);
}}
.led-green  {{ background: var(--green);  box-shadow: 0 0 6px var(--green); }}
.led-cyan   {{ background: var(--cyan);   box-shadow: 0 0 6px var(--cyan); }}
.led-purple {{ background: var(--purple); box-shadow: 0 0 6px var(--purple); }}
.led-yellow {{ background: var(--yellow); box-shadow: 0 0 6px var(--yellow); }}
.led-red    {{ background: var(--red);    box-shadow: 0 0 6px var(--red); }}
@keyframes pulse {{
  0%, 100% {{ opacity: 1; box-shadow: 0 0 6px var(--green); }}
  50%       {{ opacity: 0.3; box-shadow: 0 0 2px var(--green); }}
}}
.pulse {{
  background: var(--green);
  box-shadow: 0 0 6px var(--green);
  animation: pulse 1.6s ease-in-out infinite;
}}

/* ── hero panel ───────────────────────────────────────────── */
.tagline {{
  color: var(--muted);
  font-size: 0.82rem;
  padding-bottom: 0.5rem;
}}
.sys-line {{
  color: var(--cyan);
  font-size: 0.78rem;
  padding-bottom: 0.75rem;
  text-shadow: 0 0 6px var(--cyan);
}}
.moment-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 1px;
  background: var(--border);
  margin-bottom: 1px;
}}
.moment {{
  background: var(--surface);
  padding: 1.1rem 1.25rem;
  border-top: 2px solid transparent;
}}
.moment-green  {{ border-top-color: var(--green); }}
.moment-red    {{ border-top-color: var(--red); }}
.moment-cyan   {{ border-top-color: var(--cyan); }}
.moment-purple {{ border-top-color: var(--purple); }}
.moment-glyph {{
  font-size: 0.7rem;
  letter-spacing: 0.1em;
  color: var(--muted);
  margin-bottom: 0.3rem;
}}
.moment-name {{
  font-size: 0.9rem;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.08em;
  margin-bottom: 0.4rem;
}}
.moment-body {{ font-size: 0.78rem; color: var(--muted); line-height: 1.55; }}

/* ── lifecycle bar ────────────────────────────────────────── */
.lifecycle {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  background: #050510;
  border-top: 1px solid var(--border);
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  text-align: center;
}}
.lc-node {{
  background: var(--border);
  padding: 0.45rem 0.75rem;
  color: var(--text);
  white-space: nowrap;
  line-height: 1.3;
}}
.lc-conflict {{ background: rgba(255,45,85,0.15);  border: 1px solid var(--red);    color: var(--red); }}
.lc-intent   {{ background: rgba(255,224,102,0.1); border: 1px solid var(--yellow); color: var(--yellow); }}
.lc-org      {{ background: rgba(0,255,242,0.08);  border: 1px solid var(--cyan);   color: var(--cyan); }}
.lc-default  {{ border: 1px solid var(--border); }}
.lc-sub      {{ color: var(--muted); font-size: 0.65rem; }}
.lc-arrow    {{ color: var(--muted); }}

/* ── tables ───────────────────────────────────────────────── */
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}}
th, td {{ padding: 0.55rem 0.85rem; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ background: #0a0a18; color: var(--muted); font-size: 0.7rem; letter-spacing: 0.08em; text-transform: uppercase; }}
tr:hover td {{ background: rgba(255,255,255,0.02); }}
.summary-row td {{ background: #0a0a18; color: var(--text); font-size: 0.78rem; }}
.val-green {{ color: var(--green); }}
.val-red   {{ color: var(--red); }}
.sep {{ color: var(--muted); margin: 0 0.5rem; }}
.mono {{ font-family: inherit; letter-spacing: 0.04em; }}
.file-path {{ color: var(--cyan); font-size: 0.78rem; }}
.anti {{ color: var(--red); font-size: 0.78rem; }}
.mem-ref {{
  display: inline-block;
  background: rgba(176,96,255,0.15);
  border: 1px solid var(--purple);
  color: var(--purple);
  padding: 0.05em 0.4em;
  font-size: 0.72rem;
  margin-right: 0.2rem;
}}
.ex-row td {{ padding: 0 0.85rem 0.75rem; }}
.code-block {{
  background: #050510;
  border-left: 2px solid var(--purple);
  padding: 0.7rem 1rem;
  font-size: 0.78rem;
  overflow-x: auto;
  color: var(--muted);
}}

/* ── tags / badges ────────────────────────────────────────── */
.tag {{
  display: inline-block;
  padding: 0.1em 0.5em;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border: 1px solid currentColor;
}}
.tag-green   {{ color: var(--green); }}
.tag-cyan    {{ color: var(--cyan); }}
.tag-purple  {{ color: var(--purple); }}
.tag-yellow  {{ color: var(--yellow); }}
.tag-red     {{ color: var(--red); }}
.tag-active     {{ color: var(--green); }}
.tag-superseded {{ color: var(--yellow); }}
.tag-overridden {{ color: var(--red); }}
.tag-unknown    {{ color: var(--muted); border-color: var(--muted); }}

/* ── knowledge graph ──────────────────────────────────────── */
.graph-legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 1.2rem;
  font-size: 0.75rem;
  color: var(--muted);
  padding: 1rem 1.5rem 0.6rem;
  border-bottom: 1px solid var(--border);
}}
.legend-item {{ display: flex; align-items: center; gap: 0.4rem; }}
.legend-dot  {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
.kg-wrap {{
  position: relative;
  width: 100%;
  background: #050510;
  border-top: 1px solid var(--border);
}}
#kg-canvas {{
  display: block;
  width: 100%;
}}
#kg-tooltip {{
  display: none;
  position: absolute;
  background: #0a0a18;
  border: 1px solid var(--border);
  color: var(--text);
  font-size: 0.75rem;
  padding: 0.4rem 0.7rem;
  pointer-events: none;
  max-width: 320px;
  white-space: normal;
  line-height: 1.4;
  z-index: 10;
}}

/* ── memory detail cards ──────────────────────────────────── */
.mem-card {{
  border-bottom: 1px solid var(--border);
  border-left: 3px solid var(--border);
  overflow: hidden;
}}
.mem-card.active     {{ border-left-color: var(--green); }}
.mem-card.superseded {{ border-left-color: var(--yellow); }}
.mem-card.overridden {{ border-left-color: var(--red); }}
.mem-card.mem-org    {{ border-left-color: var(--cyan); }}
.mem-card summary {{
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  padding: 0.75rem 1.5rem;
  font-size: 0.82rem;
}}
.mem-card summary::-webkit-details-marker {{ display: none; }}
.mem-card summary::before {{
  content: "\\25B6";
  font-size: 0.6rem;
  color: var(--muted);
  transition: transform 0.2s;
  flex-shrink: 0;
}}
.mem-card[open] summary::before {{ transform: rotate(90deg); }}
.mem-card[open] summary {{ background: #0a0a18; }}
.mem-id {{ color: var(--muted); font-size: 0.75rem; }}
.mem-body {{ padding: 0.5rem 1.5rem 1rem; background: #050510; font-size: 0.8rem; }}
.mem-field {{ padding: 0.18rem 0; }}
.fk {{ color: var(--cyan); }}
.org-field {{
  background: rgba(0,255,242,0.04);
  border-left: 2px solid var(--cyan);
  padding: 0.25rem 0.6rem;
  margin-bottom: 0.2rem;
}}

/* ── misc ─────────────────────────────────────────────────── */
.nil {{ color: var(--muted); font-size: 0.8rem; font-style: italic; padding: 1.25rem 1.5rem; }}
.section-desc {{ color: var(--muted); font-size: 0.78rem; padding: 0.75rem 1.5rem 0; }}

@media (max-width: 640px) {{
  .hdr {{ flex-wrap: wrap; height: auto; padding: 0.75rem 1rem; gap: 0.5rem; }}
  .hdr-ts {{ margin-left: 0; }}
  .stat-grid {{ grid-template-columns: repeat(2, 1fr); }}
  .moment-grid {{ grid-template-columns: 1fr; }}
  .lifecycle {{ flex-direction: column; align-items: flex-start; }}
  .main {{ padding: 1rem; }}
}}
</style>
</head>
<body>
<header class="hdr">
  <div class="hdr-logo">CORTEX</div>
  <div class="hdr-sub">living organisational record engine</div>
  {org_header}
  <div class="hdr-ts">generated {_esc(timestamp)}</div>
</header>
<main class="main">
{body}
</main>
</body>
</html>"""
