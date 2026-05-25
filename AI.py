import streamlit as st
import streamlit.components.v1 as components
import json
import ollama

# ==========================================
# ⚙️  CONFIG & CATALOG
# ==========================================
TARGET_MODEL = "llama3.2:latest"

CATALOG = {
    "cpus": [
        {"id": "CPU-I9", "name": "Intel Core i9-14900K", "cost": 2200, "tier": "high-end", "tdp": 125},
        {"id": "CPU-I5", "name": "Intel Core i5-14600K", "cost": 1100, "tier": "mid-range", "tdp": 125},
        {"id": "CPU-R5", "name": "AMD Ryzen 5 7600", "cost": 880, "tier": "mid-range", "tdp": 65},
        {"id": "CPU-R3", "name": "AMD Ryzen 3 4100", "cost": 370, "tier": "budget", "tdp": 65},
        {"id": "CPU-OFC", "name": "Intel Core i5-13400 (iGPU)", "cost": 920, "tier": "office", "tdp": 65},
    ],
    "gpus": [
        {"id": "GPU-4090", "name": "NVIDIA GeForce RTX 4090 24GB", "cost": 7500, "tier": "high-end", "tdp": 450},
        {"id": "GPU-4070", "name": "NVIDIA GeForce RTX 4070 12GB", "cost": 2500, "tier": "mid-range", "tdp": 200},
        {"id": "GPU-4060", "name": "NVIDIA GeForce RTX 4060 8GB", "cost": 1300, "tier": "budget", "tdp": 115},
        {"id": "GPU-NONE", "name": "Integrated Graphics (iGPU)", "cost": 0, "tier": "office", "tdp": 0},
    ],
    "rams": [
        {"id": "RAM-64", "name": "64GB DDR5-5600 (2×32GB)", "cost": 820, "gb": 64},
        {"id": "RAM-32", "name": "32GB DDR5-5200 (2×16GB)", "cost": 420, "gb": 32},
        {"id": "RAM-16", "name": "16GB DDR4-3200 (2×8GB)", "cost": 180, "gb": 16},
        {"id": "RAM-8", "name": "8GB DDR4-3200 (1×8GB)", "cost": 100, "gb": 8},
    ],
    "storages": [
        {"id": "SSD-2T", "name": "2TB WD Black NVMe Gen4", "cost": 450, "size": "2TB"},
        {"id": "SSD-1T", "name": "1TB Samsung 980 Pro NVMe", "cost": 240, "size": "1TB"},
        {"id": "SSD-512", "name": "512GB Kingston NV2 NVMe", "cost": 140, "size": "512GB"},
    ],
    "psus": [
        {"id": "PSU-1000", "name": "Corsair RM1000x 1000W Gold", "cost": 620, "w": 1000},
        {"id": "PSU-750", "name": "Seasonic Focus 750W Gold", "cost": 380, "w": 750},
        {"id": "PSU-550", "name": "Cooler Master MWE 550W Bronze", "cost": 200, "w": 550},
    ],
    "motherboards": [
        {"id": "MB-HI", "name": "ASUS ROG Strix Z790-E Gaming WiFi", "cost": 1500, "tier": "high-end"},
        {"id": "MB-MI", "name": "MSI MAG B760M Mortar WiFi", "cost": 650, "tier": "mid-range"},
        {"id": "MB-LO", "name": "Gigabyte B450M DS3H", "cost": 280, "tier": "budget"},
    ],
}

TIER_THRESHOLDS = {"high-end": 6000, "mid-range": 3000}

LOCATION_ALIASES: dict[str, str] = {
    "kuala lumpur": "Kuala Lumpur", "kl": "Kuala Lumpur", "klcc": "Kuala Lumpur",
    "pj": "Kuala Lumpur", "petaling jaya": "Kuala Lumpur", "subang": "Kuala Lumpur",
    "shah alam": "Kuala Lumpur", "kepong": "Kuala Lumpur", "cheras": "Kuala Lumpur",
    "penang": "Penang", "george town": "Penang", "butterworth": "Penang", "pg": "Penang",
    "sarawak": "Sarawak", "kuching": "Sarawak", "miri": "Sarawak",
    "sibu": "Sarawak", "bintulu": "Sarawak", "east malaysia": "Sarawak", "borneo": "Sarawak",
}

SHIPPING_REGIONS = {
    "Kuala Lumpur": {"base_fee": 20},
    "Penang": {"base_fee": 30},
    "Sarawak": {"base_fee": 80},
}

DEFAULT_SHIPPING = {"base_fee": 50}

BLANK_SPECS = {"use_case": "None", "performance_tier": "None", "max_budget": 0, "location": "None"}

EXAMPLE_PROMPTS = [
    "High-end gaming PC for 1440p, budget RM8000, KL",
    "Budget office PC for email and Excel, max RM2500, Penang",
    "Video editing workstation, RM12000, Sarawak",
    "Change to mid-range tier, keep everything else",
]

PARSER_SYSTEM_PROMPT = f"""You are a PC sales requirements extraction engine.
Read the full conversation and latest message, then output UPDATED build requirements as JSON.
=== CATALOG ===
{json.dumps(CATALOG, indent=2)}
=== RULES ===
1. CRITICAL: Preserve every field the user did NOT mention. Only update what changed.
2. use_case → "gaming" | "workstation" | "content-creation" | "office"
3. performance_tier inference:
   - If user explicitly names a tier ("budget", "mid-range", "high-end") → use that.
   - If user only mentions a budget amount, infer tier from budget:
       RM6000+ → "high-end", RM3000–RM5999 → "mid-range", under RM3000 → "budget"
   - If user raises budget (e.g. "increase budget to RM4000"), also reconsider the tier.
4. max_budget → any RM/MYR amount as integer.
5. location → map any Malaysian city to: Kuala Lumpur, Penang, or Sarawak.
MEMORY: Previous values are in conversation history. "Change X" means preserve all others exactly.
Output ONLY raw JSON with keys: use_case, performance_tier, max_budget, location."""

RESPONDER_SYSTEM_PROMPT = """You are a friendly expert PC sales engineer at ByteForge, a Malaysian computer shop.
You remember the full conversation. Reference earlier context naturally.
Be conversational, warm, 2–4 sentences. No bullet points."""

CHITCHAT_SYSTEM_PROMPT = """You are a friendly PC sales engineer at ByteForge, a Malaysian computer shop.
Reply naturally to greetings and small talk in 1–3 sentences. You remember the full conversation."""

# ==========================================
# 🎨  CSS
# ==========================================
APP_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;600;700&display=swap');

/* ── No outer scroll ───────────────────────────────── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], section.main {
    overflow: hidden !important; height: 100vh !important;
}
.block-container {
    overflow: hidden !important; height: 100vh !important;
    padding: 0.6rem 1.5rem 0 1.5rem !important;
    max-width: 100% !important;
    font-family: 'Google Sans', system-ui, sans-serif;
}
header, footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }

/* ── Column layout ─────────────────────────────────── */
[data-testid="stHorizontalBlock"] {
    height: calc(100vh - 90px) !important;
    align-items: stretch !important; gap: 1.5rem !important;
}
[data-testid="stColumn"]:first-child > div[data-testid="stVerticalBlock"] {
    height: 100% !important; overflow-y: auto !important;
    overflow-x: hidden !important; padding-right: 6px;
    scrollbar-width: thin; scrollbar-color: #555 transparent;
}

/* ── Left panel card ───────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px !important; border: 1px solid #e8eaed !important;
}
[data-testid="stMetricValue"] { font-size: 1.1rem !important; font-weight: 600; color: #1a73e8 !important; }
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; text-transform: uppercase; letter-spacing: 0.7px; opacity: 0.55; }

/* ── Chat bubbles ──────────────────────────────────── */
.msg-user {
    display: flex; justify-content: flex-end;
    margin: 24px 0 24px 0;
}
.bubble-user {
    background: #e8f0fe; color: #1f1f1f;
    padding: 12px 18px; border-radius: 22px 22px 4px 22px;
    font-size: 0.97rem; max-width: 74%; line-height: 1.55; word-wrap: break-word;
}
.msg-bot {
    display: flex; align-items: flex-start; gap: 12px;
    margin: 0 0 32px 0;
    padding-bottom: 4px;
}

/* ── Sparkling AI Avatar Profile Badge ─────────────── */
.bot-avatar {
    width: 32px; height: 32px; border-radius: 50%;
    background: transparent; display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; margin-top: 3px; color: inherit;
}
.bot-avatar svg { width: 32px; height: 32px; }
.bot-text { font-size: 0.97rem; line-height: 1.65; color: inherit; flex: 1; }

/* ── Typing dots ───────────────────────────────────── */
.typing-wrap { display: flex; align-items: center; gap: 5px; padding: 6px 0; }
.typing-wrap span {
    width: 8px; height: 8px; border-radius: 50%;
    background: #555; display: inline-block;
    animation: tdot 1.3s infinite ease-in-out;
}
.typing-wrap span:nth-child(2) { animation-delay: 0.18s; }
.typing-wrap span:nth-child(3) { animation-delay: 0.36s; }
@keyframes tdot { 0%,80%,100%{transform:translateY(0);opacity:.3} 40%{transform:translateY(-7px);opacity:1} }

/* ── Theme-Safe BOM Table ──────────────────────────── */
.bom-wrap {
    margin-top: 14px; margin-bottom: 8px;
    border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 12px; overflow: hidden;
}
.bom-table { width: 100%; border-collapse: collapse; font-size: 0.87rem; }
.bom-table thead tr { background: rgba(128, 128, 128, 0.1); }
.bom-table th { padding: 9px 14px; text-align: left; font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.6px; font-weight: 600; opacity: 0.7; border-bottom: 1px solid rgba(128, 128, 128, 0.2); color: inherit; }
.bom-table td { padding: 10px 14px; border-bottom: 1px solid rgba(128, 128, 128, 0.1); color: inherit; }
.bom-table tr:last-child td { border-bottom: none; }
.td-r { text-align: right; }
.td-bold { font-weight: 700; color: #1a73e8; }
.bom-table tr:hover td { background: rgba(26, 115, 232, 0.05); }

/* ── Theme-Safe Financials Card Overlays ────────────── */
.fin-row { display: flex; gap: 10px; margin: 10px 0 12px; }
.fin-card { flex: 1; background: rgba(128, 128, 128, 0.08); border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 10px; padding: 10px 14px; color: inherit; }
.fc-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.6px; opacity: 0.5; margin-bottom: 3px; }
.fc-value { font-size: 1.05rem; font-weight: 700; }
.fc-delta { font-size: 0.78rem; color: #34a853; margin-top: 2px; }

/* ── Budget bar ────────────────────────────────────── */
.budget-bar-wrap { margin: 10px 0 14px; }
.budget-bar-label { font-size: 0.82rem; font-weight: 600; opacity: 0.65; margin-bottom: 5px; }
.budget-bar-bg { height: 8px; background: rgba(128, 128, 128, 0.2); border-radius: 8px; overflow: hidden; }
.budget-bar-fill { height: 100%; border-radius: 8px; background: linear-gradient(90deg, #4285f4, #34a853); transition: width 0.5s ease; }

/* ── High-Contrast Prompt Pills ───────────────────── */
div.pill-wrap div[data-testid="stButton"] > button {
    text-align: left !important; justify-content: flex-start !important;
    border-radius: 10px !important; border: 1px solid rgba(128, 128, 128, 0.4) !important;
    background: transparent !important; font-size: 0.83rem !important;
    font-weight: 400 !important; padding: 9px 13px !important;
    white-space: normal !important; line-height: 1.4 !important;
    height: auto !important; min-height: 40px !important; width: 100% !important;
    color: inherit !important;
    transition: background 0.15s, color 0.15s, border-color 0.15s !important;
}
div.pill-wrap div[data-testid="stButton"] > button:hover {
    background: rgba(26, 115, 232, 0.15) !important;
    border-color: #1a73e8 !important;
    color: #1a73e8 !important;
}

/* ── Clear button ──────────────────────────────────── */
.stButton > button { border-radius: 22px; border: 1px solid rgba(128, 128, 128, 0.4); background: transparent; font-weight: 500; transition: all 0.18s; }
.stButton > button:hover { background: rgba(26, 115, 232, 0.15) !important; border-color: #1a73e8 !important; color: #1a73e8 !important; }

/* ── Catalogue ─────────────────────────────────────── */
.cat-wrap { border: 1px solid rgba(128, 128, 128, 0.3); border-radius: 12px; padding: 12px; margin-top: 12px; }
.cat-wrap summary { font-size: 0.83rem; font-weight: 600; cursor: pointer; list-style: none; display: flex; align-items: center; gap: 7px; outline: none; opacity: 0.7; }
.cat-wrap summary::-webkit-details-marker { display: none; }
.cat-body { padding-top: 10px; font-size: 0.75rem; font-family: monospace; white-space: pre-wrap; opacity: 0.75; max-height: 260px; overflow-y: auto; }

/* ── Misc ──────────────────────────────────────────── */
[data-testid="stChatInput"] textarea { border-radius: 26px !important; font-size: 0.97rem !important; }
[data-testid="stChatMessage"] { display: none !important; }
.section-label { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; opacity: 0.4; margin: 14px 0 6px; }
.turn-divider { height: 1px; background: transparent; margin: 4px 0 20px 42px; }
</style>"""

# ── Sparkling Gemini Avatar SVG ──────────────────────
BOT_AVATAR_HTML = """<div class="bot-avatar">
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path fill="currentColor" d="M12 2c5.523 0 10 4.477 10 10a9.97 9.97 0 0 1-2.83 6.97A9.97 9.97 0 0 1 12 22a9.97 9.97 0 0 1-7.17-3.03A9.97 9.97 0 0 1 2 12C2 6.477 6.477 2 12 2m0 14a6.98 6.98 0 0 0-5.075 2.182A7.96 7.96 0 0 0 12 20a7.96 7.96 0 0 0 5.074-1.818A6.98 6.98 0 0 0 12 16m0-12a8 8 0 0 0-6.452 12.73A8.97 8.97 0 0 1 12 14a8.97 8.97 0 0 1 6.451 2.73A8 8 0 0 0 12 4m-.47 1.32a.506.506 0 0 1 .94 0l.254.61a4.37 4.37 0 0 0 2.25 2.327l.718.318c.41.183.41.781 0 .964l-.76.338a4.36 4.36 0 0 0-2.218 2.25l-.247.566a.506.506 0 0 1-.934 0l-.246-.565a4.36 4.36 0 0 0-2.22-2.251l-.76-.338a.531.531 0 0 1 0-.964l.718-.318a4.37 4.37 0 0 0 2.251-2.326z"/></svg>
</div>"""

TYPING_BUBBLE = f"""<div class="msg-bot">
  {BOT_AVATAR_HTML}
  <div class="bot-text">
    <div class="typing-wrap"><span></span><span></span><span></span></div>
  </div>
</div>"""

# ── Iconify Custom Layout SVGs ──────────────────────
MONITOR_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1.2em" height="1.2em" viewBox="0 0 24 24" style="vertical-align:text-bottom;margin-right:6px;"><path fill="currentColor" d="M20 18c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2H0v2h24v-2h-4zM4 6h16v10H4V6z"/></svg>'
GRAPH_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" style="vertical-align:text-bottom;margin-right:4px;"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path d="M3.5 4v13.5a3 3 0 0 0 3 3H20"/><path d="m6.5 15 4.5-4.5 3.5 3.5L20 8.5"/></g></svg>'
PROD_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" style="vertical-align:text-bottom;margin-right:4px;"><rect x="2" y="3" width="20" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 21h8M12 17v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'


# ==========================================
# 🖼️  RENDERERS
# ==========================================
def _bom_html(bom: list) -> str:
    rows = "".join(f"""
    <tr>
      <td>{i['name']}</td>
      <td class="td-r">{i['qty']}×</td>
      <td class="td-r">MYR {i['unit_cost']:}</td>
      <td class="td-r td-bold">MYR {i['qty'] * i['unit_cost']:}</td>
    </tr>""" for i in bom)

    return f"""<div class="bom-wrap">
  <table class="bom-table">
    <thead><tr>
      <th>Component</th><th class="td-r">Qty</th>
      <th class="td-r">Unit</th><th class="td-r">Total</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def show_message(role: str, content: str, result=None, max_budget: int = 0) -> None:
    if role == "user":
        st.markdown(f'<div class="msg-user"><div class="bubble-user">{content}</div></div>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div class="msg-bot">{BOT_AVATAR_HTML}<div class="bot-text">{content}</div></div>',
            unsafe_allow_html=True,
        )
        if result:
            _render_result(result, max_budget)
        st.markdown('<div class="turn-divider"></div>', unsafe_allow_html=True)


def _render_result(result: dict, max_budget: int) -> None:
    if result["status"] == "Approved":
        fin = result["financials"]
        pct = fin["budget_pct"]
        bgt = max_budget or st.session_state.current_specs.get("max_budget", 0)
        rem = bgt - fin["grand_total"]

        if bgt > 0:
            st.markdown(f"""
            <div class="budget-bar-wrap">
              <div class="budget-bar-label">Budget utilisation: {pct}%</div>
              <div class="budget-bar-bg"><div class="budget-bar-fill" style="width:{min(pct, 100)}%"></div></div>
            </div>""", unsafe_allow_html=True)

        delta = f'<div class="fc-delta">▲ MYR {rem:} remaining</div>' if bgt and rem > 0 else ""

        st.markdown(f"""
        <div class="fin-row">
          <div class="fin-card"><div class="fc-label">Components</div><div class="fc-value">MYR {fin['hw_total']:}</div></div>
          <div class="fin-card"><div class="fc-label">Shipping</div><div class="fc-value">MYR {fin['shipping']:}</div></div>
          <div class="fin-card"><div class="fc-label">Grand Total</div><div class="fc-value">MYR {fin['grand_total']:}</div>{delta}</div>
        </div>""", unsafe_allow_html=True)

        st.markdown(_bom_html(result["bom"]), unsafe_allow_html=True)
    else:
        for r in result.get("reasons", ["Unknown failure."]):
            st.warning(r)


def inject_js() -> None:
    components.html("""
    <script>
    (function(){
        var p=window.parent, d=p.document;
        function lock(){
            d.documentElement.style.overflow='hidden';
            d.body.style.overflow='hidden';
            var m=d.querySelector('[data-testid="stMain"]');
            if(m) m.style.overflow='hidden';
        }
        function getChat(){
            var best=null;
            d.querySelectorAll('div').forEach(function(el){
                var ov=p.getComputedStyle(el).overflowY;
                if((ov==='auto'||ov==='scroll')&&el.offsetHeight>100) best=el;
            });
            return best;
        }
        function fitChat(){
            var c=getChat(); if(!c) return;
            var top=c.getBoundingClientRect().top;
            var ib=d.querySelector('[data-testid="stBottom"]')||d.querySelector('[data-testid="stChatInputContainer"]');
            var bot=ib?(p.innerHeight-ib.getBoundingClientRect().top+4):80;
            var h=p.innerHeight-top-bot;
            if(h>60){c.style.height=h+'px';c.style.maxHeight=h+'px';}
        }
        function scrollBot(){
            var a=d.getElementById('chat-end');
            if(a){a.scrollIntoView({behavior:'instant',block:'end'});return;}
            var c=getChat();
            if(c) c.scrollTop=c.scrollHeight+9999;
        }
        function run(){ lock(); fitChat(); scrollBot(); }
        run(); setTimeout(run,80);
        setTimeout(scrollBot,250); setTimeout(scrollBot,600); setTimeout(scrollBot,1200);
        var chat=getChat();
        if(chat){
            new MutationObserver(function(){ setTimeout(scrollBot,40); })
                .observe(chat,{childList:true,subtree:true});
        }
        p.addEventListener('resize',function(){ setTimeout(run,80); });
    })();
    </script>
    """, height=0, scrolling=False)


# ==========================================
# 🤖  AGENTS
# ==========================================
def _budget_to_tier(budget: int) -> str:
    if budget >= TIER_THRESHOLDS["high-end"]:  return "high-end"
    if budget >= TIER_THRESHOLDS["mid-range"]: return "mid-range"
    return "budget"


class SalesEngineerAgent:
    def classify_intent(self, msg: str) -> str:
        try:
            r = ollama.chat(
                model=TARGET_MODEL,
                messages=[
                    {"role": "system", "content":
                        "Reply 'technical' if the message mentions PC parts, CPU, GPU, RAM, storage, budget, "
                        "location, use case, performance tier, OR any change/update/upgrade/switch/keep instruction. "
                        "Reply 'chitchat' ONLY for pure greetings with zero product content. ONE word only."},
                    {"role": "user", "content": msg},
                ],
                options={"temperature": 0.0},
            )
            return "technical" if "technical" in r["message"]["content"].lower() else "chitchat"
        except Exception:
            return "technical"

    def handle_chitchat(self, msg: str) -> str:
        history = st.session_state.chat_memory[-8:]
        msgs = [{"role": "system", "content": CHITCHAT_SYSTEM_PROMPT}] + history + [{"role": "user", "content": msg}]
        try:
            r = ollama.chat(model=TARGET_MODEL, messages=msgs, options={"temperature": 0.8})
            return r["message"]["content"].strip()
        except Exception:
            return "Hey! Tell me what kind of PC you're looking to build."

    def parse_requirements(self, msg: str) -> tuple[dict, str | None]:
        current = json.dumps(st.session_state.current_specs)
        reminder = {"role": "user",
                    "content": f"[SYSTEM: current specs={current}. Preserve unchanged fields. Output ONLY JSON.]"}
        history = st.session_state.parser_history + [reminder, {"role": "user", "content": msg}]
        old_budget = st.session_state.current_specs.get("max_budget", 0)

        try:
            r = ollama.chat(model=TARGET_MODEL, messages=history, options={"temperature": 0.0})
            raw = r["message"]["content"].strip()

            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()

            parsed: dict = json.loads(raw)
            base = st.session_state.current_specs.copy()

            # ── performance_tier ──────────────────────────────
            pt = str(parsed.get("performance_tier", "")).lower()
            if any(k in pt for k in ["high", "end"]):
                base["performance_tier"] = "high-end"
            elif any(k in pt for k in ["mid", "balanced"]):
                base["performance_tier"] = "mid-range"
            elif any(k in pt for k in ["bud", "cheap"]):
                base["performance_tier"] = "budget"
            elif any(k in pt for k in ["office", "work"]):
                base["performance_tier"] = "office"

            # ── use_case ──────────────────────────────────────
            uc = str(parsed.get("use_case", "")).lower()
            if any(k in uc for k in ["gam", "game"]):
                base["use_case"] = "gaming"
            elif any(k in uc for k in ["work", "render", "3d", "cad"]):
                base["use_case"] = "workstation"
            elif any(k in uc for k in ["edit", "video", "content", "creat"]):
                base["use_case"] = "content-creation"
            elif any(k in uc for k in ["office", "word", "excel", "email"]):
                base["use_case"] = "office"

            # ── location ──────────────────────────────────────
            loc = str(parsed.get("location", "")).title()
            if loc and loc not in ("None", ""):
                base["location"] = LOCATION_ALIASES.get(loc.lower(), loc)

            # ── max_budget ────────────────────────────────────
            braw = "".join(c for c in str(parsed.get("max_budget", "0")) if c.isdigit())
            new_budget = int(braw) if braw else 0
            if new_budget > 0:
                base["max_budget"] = new_budget

            # ✅ State Injection & Hierarchy Adjustments
            new_budget = base["max_budget"]

            # If we have a budget but no tier yet, force an inference
            if base.get("performance_tier", "None") == "None" and new_budget > 0:
                base["performance_tier"] = _budget_to_tier(new_budget)
            # If budget increased, potentially upgrade the tier
            elif new_budget > old_budget and new_budget > 0:
                inferred_tier = _budget_to_tier(new_budget)
                current_tier = base["performance_tier"]
                tier_rank = {"budget": 0, "mid-range": 1, "high-end": 2, "None": -1}
                if tier_rank.get(inferred_tier, 0) > tier_rank.get(current_tier, 0):
                    base["performance_tier"] = inferred_tier

            st.session_state.parser_history.append({"role": "user", "content": msg})
            st.session_state.parser_history.append({"role": "assistant", "content": raw})
            st.session_state.current_specs = base

            return base, None

        except Exception as e:
            return st.session_state.current_specs, str(e)

    def check_missing_info(self, criteria: dict) -> list[str]:
        missing = []
        # Check if critical fields are missing or still set to the default "None"
        if str(criteria.get("use_case", "None")).lower() == "none":
            missing.append("use case (gaming, workstation, office, etc.)")
        if str(criteria.get("location", "None")).lower() == "none":
            missing.append("shipping location (e.g., KL, Penang, Sarawak)")
        return missing

    def ask_for_clarification(self, user_msg: str, missing: list[str]) -> str:
        ctx = (f"Customer said: '{user_msg}'\n"
               f"I need to know their: {', '.join(missing)} before I can recommend a build. "
               f"Ask them warmly in 1-2 sentences.")

        history = st.session_state.chat_memory[-8:]
        msgs = [{"role": "system", "content": RESPONDER_SYSTEM_PROMPT}] + history + [{"role": "user", "content": ctx}]

        try:
            r = ollama.chat(model=TARGET_MODEL, messages=msgs, options={"temperature": 0.7})
            return r["message"]["content"].strip()
        except Exception:
            # Fallback if the LLM fails
            clean_missing = [m.split(' (')[0] for m in missing]
            return f"I'd love to put a parts list together! Could you let me know your {', and '.join(clean_missing)}?"

    def build_solution(self, criteria: dict, downgrade: bool = False) -> dict:
        TIER_DOWN = {"high-end": "mid-range", "mid-range": "budget", "budget": "budget"}
        tier = TIER_DOWN.get(criteria.get("performance_tier", "mid-range"), "budget") if downgrade else criteria.get(
            "performance_tier", "mid-range")
        uc = criteria.get("use_case", "gaming")
        C = CATALOG

        cpu_id = {"high-end": "CPU-I9", "mid-range": "CPU-I5", "budget": "CPU-R3"}.get(tier, "CPU-R3")
        if uc == "office" or tier == "office": cpu_id = "CPU-OFC"
        cpu = next(c for c in C["cpus"] if c["id"] == cpu_id)

        gpu_id = {"high-end": "GPU-4090", "mid-range": "GPU-4070", "budget": "GPU-4060"}.get(tier, "GPU-4060")
        if uc == "office" or tier == "office": gpu_id = "GPU-NONE"
        gpu = next(g for g in C["gpus"] if g["id"] == gpu_id)

        ram_gb = {"high-end": 64, "mid-range": 32, "budget": 16}.get(tier, 16)
        if uc == "workstation":        ram_gb = max(ram_gb, 64)
        if uc == "content-creation":   ram_gb = max(ram_gb, 32)
        if uc == "office" or tier == "office": ram_gb = min(ram_gb, 8)
        ram = next(r for r in C["rams"] if r["gb"] == ram_gb)

        ssd_id = {"high-end": "SSD-2T", "mid-range": "SSD-1T", "budget": "SSD-512"}.get(tier, "SSD-512")
        if uc in ("workstation", "content-creation"): ssd_id = "SSD-2T"
        ssd = next(s for s in C["storages"] if s["id"] == ssd_id)

        min_w = (cpu.get("tdp", 65) + gpu.get("tdp", 0)) * 1.6
        psu = next((p for p in sorted(C["psus"], key=lambda x: x["w"]) if p["w"] >= min_w), C["psus"][0])

        mb_tier = tier if tier in ("high-end", "mid-range", "budget") else "budget"
        mb = next(m for m in C["motherboards"] if m["tier"] == mb_tier)

        return {
            "bom": [
                {"item_id": cpu["id"], "name": cpu["name"], "qty": 1, "unit_cost": cpu["cost"]},
                {"item_id": mb["id"], "name": mb["name"], "qty": 1, "unit_cost": mb["cost"]},
                {"item_id": ram["id"], "name": ram["name"], "qty": 1, "unit_cost": ram["cost"]},
                {"item_id": ssd["id"], "name": ssd["name"], "qty": 1, "unit_cost": ssd["cost"]},
                {"item_id": gpu["id"], "name": gpu["name"], "qty": 1, "unit_cost": gpu["cost"]},
                {"item_id": psu["id"], "name": psu["name"], "qty": 1, "unit_cost": psu["cost"]},
            ],
            "tier_used": tier, "use_case": uc,
            "location": criteria.get("location", "Kuala Lumpur"),
            "max_budget": int(criteria.get("max_budget", 0)),
        }

    def validate_and_quote(self, draft: dict) -> dict:
        bom, budget = draft["bom"], draft["max_budget"]
        canonical = LOCATION_ALIASES.get(draft["location"].lower().strip(), draft["location"])
        rules = SHIPPING_REGIONS.get(canonical, DEFAULT_SHIPPING)

        hw = sum(i["qty"] * i["unit_cost"] for i in bom)
        ship = rules["base_fee"]
        total = hw + ship
        pct = round(total / budget * 100, 1) if budget else 0

        if budget > 0 and total > budget:
            return {"status": "Rejected",
                    "reasons": [f"Over budget by MYR {total - budget:} (build MYR {total:} vs cap MYR {budget:})."],
                    "can_retry": draft["tier_used"] != "budget"}

        return {"status": "Approved", "tier": draft["tier_used"], "use_case": draft["use_case"],
                "location": canonical, "bom": bom,
                "financials": {"hw_total": hw, "shipping": ship, "grand_total": total, "budget_pct": pct}}

    def generate_response(self, user_msg: str, result: dict, criteria: dict) -> str:
        if result["status"] == "Approved":
            fin = result["financials"]
            ctx = (f"Customer said: '{user_msg}'\n"
                   f"Build approved. Use case: {result['use_case']}, tier: {result['tier']}, location: {result['location']}.\n"
                   f"Total MYR {fin['grand_total']:} (parts MYR {fin['hw_total']:} + ship MYR {fin['shipping']:}). "
                   f"Budget: MYR {criteria.get('max_budget', 0):,}, utilisation {fin['budget_pct']}%.\n"
                   f"Write a warm 2-sentence confirmation. Mention use case, tier, total, and budget remaining.")
        else:
            ctx = (f"Customer: '{user_msg}'\nBuild rejected: {' | '.join(result.get('reasons', []))}\n"
                   f"2-sentence warm explanation. Suggest raising budget or switching to a lower tier.")

        history = st.session_state.chat_memory[-8:]
        msgs = [{"role": "system", "content": RESPONDER_SYSTEM_PROMPT}] + history + [{"role": "user", "content": ctx}]

        try:
            r = ollama.chat(model=TARGET_MODEL, messages=msgs, options={"temperature": 0.7})
            return r["message"]["content"].strip()
        except Exception:
            if result["status"] == "Approved":
                return f"Your **{result['tier']} {result['use_case']}** build is confirmed for {result['location']} — MYR {result['financials']['grand_total']:} total."
            return "That build exceeded the budget. Try bumping the limit or switching to a lower tier."


# ==========================================
# 🚀  UI
# ==========================================
st.set_page_config(page_title="ByteForge PC Builder", layout="wide", page_icon="🖥️")
st.markdown(APP_CSS, unsafe_allow_html=True)

defaults = {
    "parser_history": [{"role": "system", "content": PARSER_SYSTEM_PROMPT}],
    "current_specs": BLANK_SPECS.copy(),
    "display_history": [],
    "chat_memory": [],
    "pill_input": None,
    "processing": False,
    "pending_input": None,
}

for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

agent = SalesEngineerAgent()

# ── Header Configuration with Iconify Desktop SVG ─────────────────
st.markdown(f"""<div style="display:flex;align-items:center;gap:12px;padding-top:4px;margin-bottom:4px;">
  <div style="color:inherit; display:flex; align-items:center; justify-content:center; flex-shrink:0;">
    {MONITOR_SVG}
  </div>
  <div>
    <div style="font-size:1.1rem;font-weight:700;line-height:1.2;">ByteForge PC Builder</div>
    <div style="font-size:0.72rem;opacity:0.4;letter-spacing:0.3px;">AI Sales Engineer · Powered by Ollama</div>
  </div>
</div>
<hr style="margin:6px 0 8px;border:none;border-top:1px solid rgba(128,128,128,0.2);">""", unsafe_allow_html=True)

col_left, col_right = st.columns([1, 2], gap="large")

# ── LEFT PANEL ─────────────────────────────────────────────
with col_left:
    with st.container(border=True):
        st.markdown(f"<div class='section-label'>{GRAPH_SVG} Build Configuration</div>", unsafe_allow_html=True)
        s = st.session_state.current_specs
        c1, c2 = st.columns(2)
        c1.metric("Use Case", str(s.get("use_case", "—")).replace("-", " ").title())
        c2.metric("Tier", str(s.get("performance_tier", "—")).title())
        c1.metric("Budget", f"MYR {s.get('max_budget', 0):,}")
        c2.metric("Location", str(s.get("location", "—")))

    st.markdown("<div class='section-label'>Try asking</div>", unsafe_allow_html=True)

    for i, pt in enumerate(EXAMPLE_PROMPTS):
        st.markdown('<div class="pill-wrap">', unsafe_allow_html=True)
        if st.button(pt, key=f"pill_{i}", use_container_width=True):
            st.session_state.pill_input = pt
        st.markdown('</div>', unsafe_allow_html=True)

    cat_json = json.dumps(CATALOG, indent=2)
    st.markdown(
        f'<details class="cat-wrap"><summary>{PROD_SVG} Full Catalogue</summary><div class="cat-body">{cat_json}</div></details>',
        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Clear Session", use_container_width=True):
        for k in defaults: st.session_state.pop(k, None)
        st.rerun()

# ── RIGHT PANEL ────────────────────────────────────────────
with col_right:
    st.markdown("<div class='section-label'>Consultation</div>", unsafe_allow_html=True)
    chat_box = st.container(height=600, border=False)

    with chat_box:
        if not st.session_state.display_history:
            st.markdown(
                "<div style='opacity:0.4;text-align:center;padding-top:32%;font-size:1.05rem;'>What kind of PC are we building today?</div>",
                unsafe_allow_html=True)
        for msg in st.session_state.display_history:
            show_message(msg["role"], msg["content"], msg.get("result"), msg.get("max_budget", 0))

        typing_slot = st.empty()
        if st.session_state.processing:
            typing_slot.markdown(TYPING_BUBBLE, unsafe_allow_html=True)

        st.markdown('<div id="chat-end" style="height:1px;"></div>', unsafe_allow_html=True)

    inject_js()

    typed = st.chat_input("Describe your PC needs in plain English…")
    user_input = typed or st.session_state.pill_input

    # Phase 1: show user bubble immediately
    if user_input and not st.session_state.processing:
        st.session_state.pill_input = None
        st.session_state.pending_input = user_input
        st.session_state.processing = True
        st.session_state.display_history.append({"role": "user", "content": user_input})
        st.session_state.chat_memory.append({"role": "user", "content": user_input})
        st.rerun()

    # Phase 2: AI pipeline (typing dots visible while this runs)
    if st.session_state.processing and st.session_state.pending_input:
        user_msg = st.session_state.pending_input
        intent = agent.classify_intent(user_msg)

        if intent == "chitchat":
            reply = agent.handle_chitchat(user_msg)
            entry = {"role": "assistant", "content": reply}
        else:
            criteria, err = agent.parse_requirements(user_msg)
            missing_info = agent.check_missing_info(criteria)

            if missing_info:
                # Intercept! Ask for missing details before building
                reply = agent.ask_for_clarification(user_msg, missing_info)
                entry = {"role": "assistant", "content": reply}
            else:
                # All critical specs are present, proceed with build
                draft = agent.build_solution(criteria)
                result = agent.validate_and_quote(draft)

                if result["status"] == "Rejected" and result.get("can_retry"):
                    draft = agent.build_solution(criteria, downgrade=True)
                    result = agent.validate_and_quote(draft)

                reply = agent.generate_response(user_msg, result, criteria)
                if err: reply = f"*(Note: kept previous specs.)*\n\n{reply}"
                entry = {"role": "assistant", "content": reply, "result": result,
                         "max_budget": criteria.get("max_budget", 0)}

        st.session_state.display_history.append(entry)
        st.session_state.chat_memory.append({"role": "assistant", "content": reply})
        st.session_state.processing = False
        st.session_state.pending_input = None
        st.rerun()