import csv
import json
import networkx as nx
from pyvis.network import Network

CSV_PATH = 'custom_school_comparisons_2023.csv'
OUTPUT_PATH = 'school_network.html'

# Parse CSV
source_schools = set()
all_schools = {}
edges = []

with open(CSV_PATH, newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        cells = [c.strip() for c in row if c.strip()]
        if not cells:
            continue
        parts = cells[0].split(':', 1)
        if len(parts) != 2:
            continue
        src_id, src_name = parts
        src_name = src_name.replace('&amp;', '&')
        source_schools.add(src_id)
        all_schools[src_id] = src_name

        for cell in cells[1:]:
            parts = cell.split(':', 1)
            if len(parts) != 2:
                continue
            tgt_id, tgt_name = parts
            tgt_name = tgt_name.replace('&amp;', '&')
            all_schools[tgt_id] = tgt_name
            edges.append((src_id, tgt_id))

print(f"Schools: {len(all_schools)}, Source schools: {len(source_schools)}, Edges: {len(edges)}")

# Build edge set for bidirectional lookup
edge_set = set(edges)

# Find nodes that participate in at least one bidirectional edge
nodes_with_bidir = set()
for src, tgt in edges:
    if (tgt, src) in edge_set:
        nodes_with_bidir.add(src)
        nodes_with_bidir.add(tgt)

# Compute spread-out starting positions with networkx
print("Computing layout (this may take a moment)...")
G = nx.DiGraph()
for uid in all_schools:
    G.add_node(uid)
for src, tgt in edges:
    G.add_edge(src, tgt)

init_pos = nx.circular_layout(G)
pos = nx.spring_layout(G, k=6.0, seed=42, iterations=120, pos=init_pos)

SCALE = 4000  # pixels — vis.js uses these as starting positions for physics

net = Network(
    height='960px',
    width='100%',
    directed=True,
    bgcolor='#ffffff',
    font_color='#222222',
)

# Add nodes — physics=True so vis.js can push overlapping nodes apart
for uid, name in all_schools.items():
    x, y = pos[uid]
    if uid in source_schools:
        color = '#2171b5' if uid in nodes_with_bidir else '#add8e6'
    else:
        color = '#d3d3d3'
    net.add_node(
        uid,
        label=name,
        color=color,
        size=8,
        x=float(x * SCALE),
        y=float(y * SCALE),
    )

# Add edges
seen_bidir = set()
for src, tgt in edges:
    if (tgt, src) in edge_set:
        norm = (min(src, tgt), max(src, tgt))
        if norm in seen_bidir:
            continue
        seen_bidir.add(norm)
        net.add_edge(src, tgt, color='red', width=1.5,
                     arrows={'to': {'enabled': True, 'scaleFactor': 0.3},
                             'from': {'enabled': True, 'scaleFactor': 0.3}},
                     smooth={'enabled': False})
    else:
        net.add_edge(src, tgt, color='black', width=0.5,
                     arrows={'to': {'enabled': True, 'scaleFactor': 0.3}},
                     smooth={'enabled': False})

# Physics: repulsion-only pass to resolve overlaps, then freezes itself
net.set_options("""
{
  "nodes": {
    "font": { "size": 9, "face": "Arial", "background": "rgba(255,255,255,0.3)" },
    "borderWidth": 1
  },
  "edges": {
    "smooth": { "enabled": false }
  },
  "physics": {
    "enabled": true,
    "solver": "repulsion",
    "repulsion": {
      "nodeDistance": 120,
      "centralGravity": 0.0,
      "springLength": 200,
      "springConstant": 0.0,
      "damping": 0.5
    },
    "stabilization": {
      "enabled": true,
      "iterations": 300,
      "updateInterval": 25,
      "fit": true
    }
  },
  "interaction": {
    "hover": true,
    "tooltipDelay": 999999,
    "navigationButtons": true,
    "keyboard": true,
    "zoomView": true,
    "dragView": true
  }
}
""")

net.write_html(OUTPUT_PATH)

# ── Data for JS filters ───────────────────────────────────────────────────────
# nodes_with_bidir already built above
nodes_with_outbound = set(src for src, tgt in edges)   # has at least one outbound edge

bidir_json    = json.dumps(list(nodes_with_bidir))
outbound_json = json.dumps(list(nodes_with_outbound))

# ── Post-process HTML: inject controls + loading overlay + zoom handler ───────
extra_js = f"""
<style>
#loadingOverlay {{
    position: fixed; inset: 0;
    background: rgba(255,255,255,0.85);
    display: flex; align-items: center; justify-content: center;
    font: 18px Arial, sans-serif; color: #333; z-index: 9999;
}}
#filterPanel {{
    position: fixed; top: 12px; left: 12px;
    background: #fff; border: 1px solid #bbb; border-radius: 6px;
    padding: 10px 14px; font: 13px Arial, sans-serif;
    box-shadow: 0 2px 6px rgba(0,0,0,0.15); z-index: 1000;
    display: flex; flex-direction: column; gap: 6px;
}}
#filterPanel label {{ cursor: pointer; display: flex; align-items: center; gap: 6px; }}
</style>

<div id="loadingOverlay">Resolving node overlaps&hellip;</div>

<div id="filterPanel">
  <strong style="margin-bottom:2px">Filters</strong>
  <label><input type="checkbox" id="cb_bidir"> Show only schools with bidirectional links</label>
  <label><input type="checkbox" id="cb_outbound"> Omit schools with zero outbound links</label>
  <label><input type="checkbox" id="cb_bidir_net"> Only show network held together by bidirectional links</label>
</div>

<script>
(function waitForNetwork() {{
    if (typeof network === 'undefined' || typeof edges === 'undefined' || typeof nodes === 'undefined') {{
        setTimeout(waitForNetwork, 50);
        return;
    }}

    // ── Filter sets (embedded from Python) ───────────────────────────────────
    var bidirSet    = new Set({bidir_json});
    var outboundSet = new Set({outbound_json});

    // ── Apply all checkboxes ─────────────────────────────────────────────────
    function applyFilters() {{
        var onlyBidir      = document.getElementById('cb_bidir').checked;
        var omitNoOutbound = document.getElementById('cb_outbound').checked;
        var onlyBidirNet   = document.getElementById('cb_bidir_net').checked;

        // Node visibility
        var nodeUpdates = [];
        nodes.forEach(function(node) {{
            var visible = true;
            if ((onlyBidir || onlyBidirNet) && !bidirSet.has(node.id))    visible = false;
            if (omitNoOutbound              && !outboundSet.has(node.id)) visible = false;
            nodeUpdates.push({{ id: node.id, hidden: !visible }});
        }});
        nodes.update(nodeUpdates);

        // Edge visibility: cb_bidir_net hides all one-way (black) edges
        var edgeUpdates = [];
        edges.forEach(function(edge) {{
            var isBidir = baseEdgeData[edge.id] && baseEdgeData[edge.id].fromEnabled;
            edgeUpdates.push({{ id: edge.id, hidden: onlyBidirNet && !isBidir }});
        }});
        edges.update(edgeUpdates);
    }}

    document.getElementById('cb_bidir').addEventListener('change', applyFilters);
    document.getElementById('cb_outbound').addEventListener('change', applyFilters);
    document.getElementById('cb_bidir_net').addEventListener('change', applyFilters);

    // ── Disable physics after stabilisation ──────────────────────────────────
    network.on("stabilized", function() {{
        network.setOptions({{ physics: {{ enabled: false }} }});
        var overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.remove();
    }});

    // ── Custom tooltip ───────────────────────────────────────────────────────
    var tipEl = document.createElement('div');
    tipEl.style.cssText = [
        'position:fixed',
        'background:#fff',
        'border:1px solid #aaa',
        'border-radius:5px',
        'padding:8px 10px',
        'font:12px Arial,sans-serif',
        'line-height:1.7',
        'width:230px',
        'max-height:500px',
        'overflow-y:auto',
        'z-index:10000',
        'display:none',
        'box-shadow:0 3px 10px rgba(0,0,0,0.18)',
        'pointer-events:none',
        'white-space:nowrap'
    ].join(';');
    document.body.appendChild(tipEl);

    function buildTipHTML(nodeId) {{
        var nid = String(nodeId);
        var outSet = new Set(), inSet = new Set();
        edges.forEach(function(e) {{
            if (String(e.from) === nid) outSet.add(String(e.to));
            if (String(e.to)   === nid) inSet.add(String(e.from));
        }});
        var all = new Set([...outSet, ...inSet]);
        var items = [];
        all.forEach(function(otherId) {{
            var n = nodes.get(otherId);
            var nm = n ? n.label : otherId;
            var isOut = outSet.has(otherId), isIn = inSet.has(otherId);
            var pfx = (isOut && isIn) ? 'X' : (isOut ? '<' : '>');
            items.push({{ pfx: pfx, nm: nm, bidir: isOut && isIn }});
        }});
        items.sort(function(a, b) {{ return a.nm.localeCompare(b.nm); }});
        return items.map(function(i) {{
            var line = i.pfx + '\u00a0' + i.nm;
            return i.bidir ? '<b>' + line + '</b>' : line;
        }}).join('<br>');
    }}

    var mX = 0, mY = 0;
    document.addEventListener('mousemove', function(e) {{
        mX = e.clientX; mY = e.clientY;
        if (tipEl.style.display !== 'none') {{
            tipEl.style.left = (mX + 18) + 'px';
            tipEl.style.top  = Math.min(mY - 10, window.innerHeight - tipEl.offsetHeight - 10) + 'px';
        }}
    }});
    network.on('hoverNode', function(p) {{
        var html = buildTipHTML(p.node);
        if (html) {{
            tipEl.innerHTML = html;
            tipEl.style.display = 'block';
            tipEl.style.left = (mX + 18) + 'px';
            tipEl.style.top  = (mY - 10) + 'px';
        }}
    }});
    network.on('blurNode', function() {{ tipEl.style.display = 'none'; }});

    // ── Zoom handler: shrink edges and arrows as you zoom in ─────────────────
    var baseEdgeData = {{}};
    edges.forEach(function(edge) {{
        var toScale     = (edge.arrows && edge.arrows.to  && edge.arrows.to.scaleFactor  != null) ? edge.arrows.to.scaleFactor  : 0.3;
        var fromEnabled = !!(edge.arrows && edge.arrows.from && edge.arrows.from.enabled);
        baseEdgeData[edge.id] = {{
            width:       edge.width != null ? edge.width : 1,
            toScale:     toScale,
            fromEnabled: fromEnabled
        }};
    }});

    network.on("zoom", function(params) {{
        var scale   = params.scale;
        var updates = [];
        edges.forEach(function(edge) {{
            var base = baseEdgeData[edge.id];
            if (!base) return;
            var w  = Math.max(0.05, base.width   / scale);
            var as = Math.max(0.02, base.toScale / scale);
            var upd = {{ id: edge.id, width: w, arrows: {{ to: {{ enabled: true, scaleFactor: as }} }} }};
            if (base.fromEnabled) upd.arrows.from = {{ enabled: true, scaleFactor: as }};
            updates.push(upd);
        }});
        if (updates.length) edges.update(updates);
    }});
}})();
</script>
"""

with open(OUTPUT_PATH, 'r') as f:
    html = f.read()
html = html.replace('</body>', extra_js + '\n</body>')
with open(OUTPUT_PATH, 'w') as f:
    f.write(html)

print(f"Graph written to {OUTPUT_PATH}")
