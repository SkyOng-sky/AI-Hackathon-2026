import streamlit as st
import streamlit.components.v1 as components
import json
import asyncio
import aiohttp

# ==========================================
# ⚙️  CONFIG & CATALOG
# ==========================================
TARGET_MODEL = "google/gemma-4-31B-turbo-TEE"
CHUTES_API_TOKEN = "cpk_f3f3bc6a793d4d03a599f5ee3358f430.929d18a651835cafa634cf7fd8550553.5qpiVBymo0TmZLOOfH62fPFx8zK9lTxj"
BASE_API_URL = "https://llm.chutes.ai/v1/chat/completions"

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
        {"id": "PSU-1000", "name": "Corsair RM1000x 1000W Gold", "cost": 220, "w": 1000},
        {"id": "PSU-750", "name": "Seasonic Focus 750W Gold", "cost": 180, "w": 750},
        {"id": "PSU-550", "name": "Cooler Master MWE 550W Bronze", "cost": 100, "w": 550},
    ],
    "motherboards": [
        {"id": "MB-HI", "name": "ASUS ROG Strix Z790-E Gaming WiFi", "cost": 1500, "tier": "high-end"},
        {"id": "MB-MI", "name": "MSI MAG B760M Mortar WiFi", "cost": 650, "tier": "mid-range"},
        {"id": "MB-LO", "name": "Gigabyte B450M DS3H", "cost": 280, "tier": "budget"},
    ],
}

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

TIER_THRESHOLDS = {"high-end": 6000, "mid-range": 3000}
BLANK_SPECS = {"use_case": "None", "performance_tier": "None", "max_budget": 0, "location": "None"}

EXAMPLE_PROMPTS = [
    "High-end gaming PC for 1440p, budget RM8000, KL",
    "Budget office PC for email and Excel, max RM2500, Penang",
    "Video editing workstation, RM12000, Sarawak",
    "Change to mid-range tier, keep everything else",
]

# ==========================================
# 📝  SYSTEM PROMPTS
# ==========================================
UNIFIED_ANALYSIS_PROMPT = """You are the brain of a PC sales engine at ByteForge, a Malaysian computer shop.
Inspect the latest customer message and full conversation history, then output a single JSON object.

=== CURRENT SAVED CONFIGURATION ===
{current_specs}

=== FULL CATALOG ===
{catalog}

=== RULES ===
1. "intent": "technical" if the message touches hardware, budget, location, use-case, or build changes.
   "intent": "chitchat" for pure greetings/small-talk with no PC content.
2. "extracted_specs": ONLY update fields the customer explicitly mentioned. Copy all other fields verbatim from CURRENT SAVED CONFIGURATION.
3. use_case must be one of: "gaming" | "workstation" | "content-creation" | "office" | "None"
4. performance_tier: if not named, infer from budget — <RM3000→"budget", RM3000-5999→"mid-range", RM6000+→"high-end", office builds→"office".
5. location: normalise Malaysian city/region names to "Kuala Lumpur", "Penang", or "Sarawak".
6. "needs_clarification": list any of ["use_case","location"] that are still missing (value is "None" or 0 after update).
7. "can_build": true only when use_case, location, AND max_budget are all known and non-zero.

Output ONLY valid JSON matching this exact schema (no markdown, no extra keys):
{{
  "intent": "technical" | "chitchat",
  "extracted_specs": {{
    "use_case": "string",
    "performance_tier": "string",
    "max_budget": integer,
    "location": "string"
  }},
  "needs_clarification": ["field", ...],
  "can_build": true | false
}}"""

COMPONENT_PICKER_PROMPT = """You are a PC hardware expert. Select the best possible components from the catalog for this customer.

CUSTOMER REQUIREMENTS:
{criteria}

FULL CATALOG:
{catalog}

SHIPPING FEES (MYR): Kuala Lumpur=20, Penang=30, Sarawak=80, elsewhere=50

HARD CONSTRAINTS (violations = invalid build):
1. Total hardware cost + shipping fee MUST be ≤ max_budget.
2. PSU wattage MUST exceed (CPU tdp + GPU tdp) × 1.6.
3. For use_case "office": use CPU-OFC and GPU-NONE only.
4. All selected IDs must exist exactly as shown in the catalog.

OPTIMISATION GOALS (in priority order):
1. Meet the performance_tier target as closely as possible.
2. Maximise value: if budget allows upgrading a component without breaching the cap, upgrade it.
3. Prefer components that match the use_case (e.g. workstation → more RAM; gaming → stronger GPU; content-creation → fast storage + GPU).

Output ONLY valid JSON (no markdown, no extra keys):
{{
  "cpu_id": "...",
  "gpu_id": "...",
  "ram_id": "...",
  "storage_id": "...",
  "psu_id": "...",
  "mb_id": "...",
  "reasoning": "one sentence explaining key trade-offs made"
}}"""

RESPONDER_SYSTEM_PROMPT = """You are a friendly expert PC sales engineer at ByteForge, a Malaysian computer shop.
You remember the full conversation. Reference earlier context naturally.
Be conversational and warm. Keep replies to 2–4 sentences. No bullet points."""

CHITCHAT_SYSTEM_PROMPT = """You are a friendly PC sales engineer at ByteForge, a Malaysian computer shop.
Reply naturally to greetings and small talk in 1–3 sentences. You remember the full conversation."""

MEMORY_TURNS = 6

# ==========================================
# 🎨  CSS
# ==========================================
APP_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;600;700&display=swap');

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

[data-testid="stHorizontalBlock"] {
    height: calc(100vh - 90px) !important;
    align-items: stretch !important; gap: 1.5rem !important;
}
[data-testid="stColumn"]:first-child > div[data-testid="stVerticalBlock"] {
    height: 100% !important; overflow-y: auto !important;
    overflow-x: hidden !important; padding-right: 6px;
    scrollbar-width: thin; scrollbar-color: #555 transparent;
}
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px !important; border: 1px solid #e8eaed !important;
}
[data-testid="stMetricValue"] { font-size: 1.1rem !important; font-weight: 600; color: #1a73e8 !important; }
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; text-transform: uppercase; letter-spacing: 0.7px; opacity: 0.55; }

.msg-user { display: flex; justify-content: flex-end; margin: 24px 0 24px 0; }
.bubble-user {
    background: #e8f0fe; color: #1f1f1f;
    padding: 12px 18px; border-radius: 22px 22px 4px 22px;
    font-size: 0.97rem; max-width: 74%; line-height: 1.55; word-wrap: break-word;
}
.msg-bot { display: flex; align-items: flex-start; gap: 12px; margin: 0 0 32px 0; padding-bottom: 4px; }
.bot-avatar {
    width: 32px; height: 32px; border-radius: 50%;
    background: transparent; display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; margin-top: 3px; color: inherit;
}
.bot-avatar svg { width: 32px; height: 32px; }
.bot-text { font-size: 0.97rem; line-height: 1.65; color: inherit; flex: 1; }

.typing-wrap { display: flex; align-items: center; gap: 5px; padding: 6px 0; }
.typing-wrap span {
    width: 8px; height: 8px; border-radius: 50%;
    background: #555; display: inline-block;
    animation: tdot 1.3s infinite ease-in-out;
}
.typing-wrap span:nth-child(2) { animation-delay: 0.18s; }
.typing-wrap span:nth-child(3) { animation-delay: 0.36s; }
@keyframes tdot { 0%,80%,100%{transform:translateY(0);opacity:.3} 40%{transform:translateY(-7px);opacity:1} }

.bom-wrap { margin-top: 14px; margin-bottom: 8px; border: 1px solid rgba(128,128,128,0.2); border-radius: 12px; overflow: hidden; }
.bom-table { width: 100%; border-collapse: collapse; font-size: 0.87rem; }
.bom-table thead tr { background: rgba(128,128,128,0.1); }
.bom-table th { padding: 9px 14px; text-align: left; font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.6px; font-weight: 600; opacity: 0.7; border-bottom: 1px solid rgba(128,128,128,0.2); color: inherit; }
.bom-table td { padding: 10px 14px; border-bottom: 1px solid rgba(128,128,128,0.1); color: inherit; }
.bom-table tr:last-child td { border-bottom: none; }
.td-r { text-align: right; }
.td-bold { font-weight: 700; color: #1a73e8; }
.bom-table tr:hover td { background: rgba(26, 115, 232, 0.05); }
.ai-reasoning { font-size: 0.78rem; opacity: 0.5; font-style: italic; margin: 6px 0 2px 2px; }

.fin-row { display: flex; gap: 10px; margin: 10px 0 12px; }
.fin-card { flex: 1; background: rgba(128, 128, 128, 0.08); border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 10px; padding: 10px 14px; color: inherit; }
.fc-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.6px; opacity: 0.5; margin-bottom: 3px; }
.fc-value { font-size: 1.05rem; font-weight: 700; }
.fc-delta { font-size: 0.78rem; color: #34a853; margin-top: 2px; }

.budget-bar-wrap { margin: 10px 0 14px; }
.budget-bar-label { font-size: 0.82rem; font-weight: 600; opacity: 0.65; margin-bottom: 5px; }
.budget-bar-bg { height: 8px; background: rgba(128, 128, 128, 0.2); border-radius: 8px; overflow: hidden; }
.budget-bar-fill { height: 100%; border-radius: 8px; background: linear-gradient(90deg, #4285f4, #34a853); transition: width 0.5s ease; }

div.pill-wrap div[data-testid="stButton"] > button {
    text-align: left !important; justify-content: flex-start !important;
    border-radius: 10px !important; border: 1px solid rgba(128,128,128,0.4) !important;
    background: transparent !important; font-size: 0.83rem !important;
    font-weight: 400 !important; padding: 9px 13px !important;
    white-space: normal !important; line-height: 1.4 !important;
    height: auto !important; min-height: 40px !important; width: 100% !important;
    color: inherit !important;
    transition: background 0.15s, color 0.15s, border-color 0.15s !important;
}
div.pill-wrap div[data-testid="stButton"] > button:hover {
    background: rgba(26, 115, 232, 0.15) !important; border-color: #1a73e8 !important; color: #1a73e8 !important;
}
.stButton > button { border-radius: 22px; border: 1px solid rgba(128,128,128,0.4); background: transparent; font-weight: 500; transition: all 0.18s; }
.stButton > button:hover { background: rgba(26, 115, 232, 0.15) !important; border-color: #1a73e8 !important; color: #1a73e8 !important; }

.cat-wrap { border: 1px solid rgba(128,128,128,0.3); border-radius: 12px; padding: 12px; margin-top: 12px; }
.cat-wrap summary { font-size: 0.83rem; font-weight: 600; cursor: pointer; list-style: none; display: flex; align-items: center; gap: 7px; outline: none; opacity: 0.7; }
.cat-wrap summary::-webkit-details-marker { display: none; }
.cat-body { padding-top: 10px; font-size: 0.75rem; font-family: monospace; white-space: pre-wrap; opacity: 0.75; max-height: 260px; overflow-y: auto; }

[data-testid="stChatInput"] textarea { border-radius: 26px !important; font-size: 0.97rem !important; }
[data-testid="stChatMessage"] { display: none !important; }
.section-label { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; opacity: 0.4; margin: 14px 0 6px; }
.turn-divider { height: 1px; background: transparent; margin: 4px 0 20px 42px; }
</style>"""

BOT_AVATAR_HTML = """<div class="bot-avatar">
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="none"/><path fill="currentColor" d="M12 2c5.523 0 10 4.477 10 10a9.97 9.97 0 0 1-2.83 6.97A9.97 9.97 0 0 1 12 22a9.97 9.97 0 0 1-7.17-3.03A9.97 9.97 0 0 1 2 12C2 6.477 6.477 2 12 2m0 14a6.98 6.98 0 0 0-5.075 2.182A7.96 7.96 0 0 0 12 20a7.96 7.96 0 0 0 5.074-1.818A6.98 6.98 0 0 0 12 16m0-12a8 8 0 0 0-6.452 12.73A8.97 8.97 0 0 1 12 14a8.97 8.97 0 0 1 6.451 2.73A8 8 0 0 0 12 4m-.47 1.32a.506.506 0 0 1 .94 0l.254.61a4.37 4.37 0 0 0 2.25 2.327l.718.318c.41.183.41.781 0 .964l-.76.338a4.36 4.36 0 0 0-2.218 2.25l-.247.566a.506.506 0 0 1-.934 0l-.246-.565a4.36 4.36 0 0 0-2.22-2.251l-.76-.338a.531.531 0 0 1 0-.964l.718-.318a4.37 4.37 0 0 0 2.251-2.326z"/></svg>
</div>"""

TYPING_BUBBLE = f"""<div class="msg-bot">
  {BOT_AVATAR_HTML}
  <div class="bot-text">
    <div class="typing-wrap"><span></span><span></span><span></span></div>
  </div>
</div>"""

MONITOR_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1.2em" height="1.2em" viewBox="0 0 24 24" style="vertical-align:text-bottom;margin-right:6px;"><path fill="currentColor" d="M20 18c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2H0v2h24v-2h-4zM4 6h16v10H4V6z"/></svg>'
GRAPH_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" style="vertical-align:text-bottom;margin-right:4px;"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path d="M3.5 4v13.5a3 3 0 0 0 3 3H20"/><path d="m6.5 15 4.5-4.5 3.5 3.5L20 8.5"/></g></svg>'
PROD_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" style="vertical-align:text-bottom;margin-right:4px;"><rect x="2" y="3" width="20" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 21h8M12 17v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'


# ==========================================
# 🖼️  RENDERERS
# ==========================================
def _bom_html(bom: list, reasoning: str = "") -> str:
    rows = "".join(f"""
    <tr>
      <td>{i['name']}</td>
      <td class="td-r">{i['qty']}×</td>
      <td class="td-r">MYR {i['unit_cost']:,}</td>
      <td class="td-r td-bold">MYR {i['qty'] * i['unit_cost']:,}</td>
    </tr>""" for i in bom)

    reasoning_html = f'<div class="ai-reasoning">💡 {reasoning}</div>' if reasoning else ""

    return f"""{reasoning_html}<div class="bom-wrap">
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

        delta = f'<div class="fc-delta">▲ MYR {rem:,} remaining</div>' if bgt and rem > 0 else ""

        st.markdown(f"""
        <div class="fin-row">
          <div class="fin-card"><div class="fc-label">Components</div><div class="fc-value">MYR {fin['hw_total']:,}</div></div>
          <div class="fin-card"><div class="fc-label">Shipping</div><div class="fc-value">MYR {fin['shipping']:,}</div></div>
          <div class="fin-card"><div class="fc-label">Grand Total</div><div class="fc-value">MYR {fin['grand_total']:,}</div>{delta}</div>
        </div>""", unsafe_allow_html=True)

        st.markdown(_bom_html(result["bom"], result.get("reasoning", "")), unsafe_allow_html=True)
    else:
        for r in result.get("reasons", ["Unknown failure."]):
            st.warning(r)


# 🌟 DEFINITION PLACEMENT ERROR REPAIRED HERE 🌟
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
# 🤖  AGENT MECHANICS (DIRECT ENDPOINT PIPELINE)
# ==========================================
def _trim_memory(history: list, max_turns: int = MEMORY_TURNS) -> list:
    pairs = []
    i = len(history) - 1
    while i >= 1 and len(pairs) < max_turns:
        if history[i]["role"] == "assistant" and history[i - 1]["role"] == "user":
            pairs.insert(0, history[i - 1])
            pairs.insert(1, history[i])
            i -= 2
        else:
            i -= 1
    return pairs


class SalesEngineerAgent:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {CHUTES_API_TOKEN}",
            "Content-Type": "application/json"
        }

    async def _post(self, payload: dict) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.post(BASE_API_URL, headers=self.headers, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"HTTP {response.status}: {text}")
                res_json = await response.json()
                return res_json["choices"][0]["message"]["content"].strip()

    async def analyse(self, msg: str) -> dict:
        system = (
            UNIFIED_ANALYSIS_PROMPT
            .replace("{current_specs}", json.dumps(st.session_state.current_specs, indent=2))
            .replace("{catalog}", json.dumps(CATALOG, indent=2))
        )
        history = _trim_memory(st.session_state.chat_memory)
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": msg}]

        payload = {
            "model": TARGET_MODEL,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        try:
            raw_text = await self._post(payload)
            return json.loads(raw_text)
        except Exception as e:
            st.toast(f"analyse() communication error: {e}", icon="🔴")
            return {
                "intent": "technical",
                "extracted_specs": st.session_state.current_specs,
                "needs_clarification": [],
                "can_build": False,
            }

    async def build_solution_ai(self, criteria: dict) -> dict | None:
        prompt = (
            COMPONENT_PICKER_PROMPT
            .replace("{criteria}", json.dumps(criteria, indent=2))
            .replace("{catalog}", json.dumps(CATALOG, indent=2))
        )
        payload = {
            "model": TARGET_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        try:
            raw_text = await self._post(payload)
            sel = json.loads(raw_text)

            lookup = {
                "cpus": {c["id"]: c for c in CATALOG["cpus"]},
                "gpus": {g["id"]: g for g in CATALOG["gpus"]},
                "rams": {r["id"]: r for r in CATALOG["rams"]},
                "storages": {s["id"]: s for s in CATALOG["storages"]},
                "psus": {p["id"]: p for p in CATALOG["psus"]},
                "motherboards": {m["id"]: m for m in CATALOG["motherboards"]},
            }
            cpu = lookup["cpus"][sel["cpu_id"]]
            gpu = lookup["gpus"][sel["gpu_id"]]
            ram = lookup["rams"][sel["ram_id"]]
            ssd = lookup["storages"][sel["storage_id"]]
            psu = lookup["psus"][sel["psu_id"]]
            mb = lookup["motherboards"][sel["mb_id"]]

            return {
                "bom": [
                    {"item_id": cpu["id"], "name": cpu["name"], "qty": 1, "unit_cost": cpu["cost"]},
                    {"item_id": mb["id"], "name": mb["name"], "qty": 1, "unit_cost": mb["cost"]},
                    {"item_id": ram["id"], "name": ram["name"], "qty": 1, "unit_cost": ram["cost"]},
                    {"item_id": ssd["id"], "name": ssd["name"], "qty": 1, "unit_cost": ssd["cost"]},
                    {"item_id": gpu["id"], "name": gpu["name"], "qty": 1, "unit_cost": gpu["cost"]},
                    {"item_id": psu["id"], "name": psu["name"], "qty": 1, "unit_cost": psu["cost"]},
                ],
                "tier_used": criteria.get("performance_tier", "mid-range"),
                "use_case": criteria.get("use_case", "gaming"),
                "location": criteria.get("location", "Kuala Lumpur"),
                "max_budget": int(criteria.get("max_budget", 0)),
                "reasoning": sel.get("reasoning", ""),
            }
        except Exception:
            return None

    def build_solution_rules(self, criteria: dict, downgrade: bool = False) -> dict:
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
        if uc == "workstation":      ram_gb = max(ram_gb, 64)
        if uc == "content-creation": ram_gb = max(ram_gb, 32)
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
            "reasoning": "Determined via custom shop layout fallback constraints.",
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
            return {
                "status": "Rejected",
                "reasons": [f"Over budget by MYR {total - budget:,} (build MYR {total:,} vs cap MYR {budget:,})."],
                "can_retry": draft["tier_used"] != "budget",
            }

        return {
            "status": "Approved",
            "tier": draft["tier_used"],
            "use_case": draft["use_case"],
            "location": canonical,
            "bom": bom,
            "reasoning": draft.get("reasoning", ""),
            "financials": {"hw_total": hw, "shipping": ship, "grand_total": total, "budget_pct": pct},
        }

    async def _stream_pipeline(self, messages: list, stream_slot) -> str:
        payload = {
            "model": TARGET_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "stream": True
        }
        full_text = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(BASE_API_URL, headers=self.headers, json=payload) as response:
                    async for line in response.content:
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data: "):
                            data_chunk = line_str[6:].strip()
                            if data_chunk == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_chunk)
                                delta = chunk_json["choices"][0]["delta"].get("content", "")
                                full_text += delta
                                stream_slot.markdown(
                                    f'<div class="msg-bot">{BOT_AVATAR_HTML}<div class="bot-text">{full_text}▌</div></div>',
                                    unsafe_allow_html=True
                                )
                            except Exception:
                                continue
            stream_slot.markdown(f'<div class="msg-bot">{BOT_AVATAR_HTML}<div class="bot-text">{full_text}</div></div>',
                                 unsafe_allow_html=True)
            return full_text
        except Exception:
            return ""

    async def generate_response_streamed(self, user_msg: str, result: dict, criteria: dict, stream_slot) -> str:
        if result["status"] == "Approved":
            fin = result["financials"]
            ctx = (
                f"Customer said: '{user_msg}'\n"
                f"Build approved. Use case: {result['use_case']}, tier: {result['tier']}, location: {result['location']}.\n"
                f"Total MYR {fin['grand_total']:,} (parts MYR {fin['hw_total']:,} + ship MYR {fin['shipping']:,}). "
                f"Budget: MYR {criteria.get('max_budget', 0):,}, utilisation {fin['budget_pct']}%.\n"
                f"Write a warm 2-sentence confirmation. Mention use case, tier, total, and budget remaining."
            )
        else:
            ctx = (
                f"Customer: '{user_msg}'\n"
                f"Build rejected: {' | '.join(result.get('reasons', []))}\n"
                f"2-sentence warm explanation. Suggest raising budget or switching to a lower tier."
            )

        history = _trim_memory(st.session_state.chat_memory)
        messages = [{"role": "system", "content": RESPONDER_SYSTEM_PROMPT}] + history + [
            {"role": "user", "content": ctx}]

        reply = await self._stream_pipeline(messages, stream_slot)
        if not reply:
            reply = f"Your **{result.get('tier', '?')} {result.get('use_case', '?')}** build is confirmed — MYR {result['financials']['grand_total']:,} total." if \
            result["status"] == "Approved" else "That build exceeded the budget parameters. Try raising the cap limit."
            stream_slot.markdown(f'<div class="msg-bot">{BOT_AVATAR_HTML}<div class="bot-text">{reply}</div></div>',
                                 unsafe_allow_html=True)
        return reply

    async def handle_chitchat_streamed(self, msg: str, stream_slot) -> str:
        history = _trim_memory(st.session_state.chat_memory)
        messages = [{"role": "system", "content": CHITCHAT_SYSTEM_PROMPT}] + history + [
            {"role": "user", "content": msg}]
        reply = await self._stream_pipeline(messages, stream_slot)
        if not reply:
            reply = "Hello! Tell me what sort of custom system we are putting together today."
            stream_slot.markdown(f'<div class="msg-bot">{BOT_AVATAR_HTML}<div class="bot-text">{reply}</div></div>',
                                 unsafe_allow_html=True)
        return reply

    async def ask_for_clarification_streamed(self, user_msg: str, missing: list[str], stream_slot) -> str:
        ctx = f"Customer said: '{user_msg}'\nI need: {', '.join(missing)} before I can recommend a build.\nAsk warmly in 1-2 sentences."
        history = _trim_memory(st.session_state.chat_memory)
        messages = [{"role": "system", "content": RESPONDER_SYSTEM_PROMPT}] + history + [
            {"role": "user", "content": ctx}]
        reply = await self._stream_pipeline(messages, stream_slot)
        if not reply:
            reply = "I would love to help configure that setup! Could you share your missing use case or shipping location context?"
            stream_slot.markdown(f'<div class="msg-bot">{BOT_AVATAR_HTML}<div class="bot-text">{reply}</div></div>',
                                 unsafe_allow_html=True)
        return reply


# ==========================================
# ⚖️  UI & INTERACTION ENGINE
# ==========================================
st.set_page_config(page_title="ByteForge PC Builder", layout="wide", page_icon="🖥️")
st.markdown(APP_CSS, unsafe_allow_html=True)

defaults = {
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

st.markdown(f"""<div style="display:flex;align-items:center;gap:12px;padding-top:4px;margin-bottom:4px;">
  <div style="color:inherit;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
    {MONITOR_SVG}
  </div>
  <div>
    <div style="font-size:1.1rem;font-weight:700;line-height:1.2;">ByteForge PC Builder</div>
    <div style="font-size:0.72rem;opacity:0.4;letter-spacing:0.3px;">AI Sales Engineer · Powered by Chutes</div>
  </div>
</div>
<hr style="margin:6px 0 8px;border:none;border-top:1px solid rgba(128,128,128,0.2);">""", unsafe_allow_html=True)

col_left, col_right = st.columns([1, 2], gap="large")

# ── LEFT SIDE CONFIGURATION CARD ────────────────────────────────────
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

    st.markdown(
        f'<details class="cat-wrap"><summary>{PROD_SVG} Full Catalogue</summary>'
        f'<div class="cat-body">{json.dumps(CATALOG, indent=2)}</div></details>',
        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Clear Session", use_container_width=True):
        for k in defaults: st.session_state.pop(k, None)
        st.rerun()

# ── RIGHT SIDE CONSULTATION CHATBOX CONTAINER ───────────────────────
with col_right:
    st.markdown("<div class='section-label'>Consultation</div>", unsafe_allow_html=True)
    chat_box = st.container(height=600, border=False)

    with chat_box:
        if not st.session_state.display_history:
            st.markdown(
                "<div style='opacity:0.4;text-align:center;padding-top:32%;font-size:1.05rem;'>"
                "What kind of PC are we building today?</div>",
                unsafe_allow_html=True)

        for msg in st.session_state.display_history:
            show_message(msg["role"], msg["content"], msg.get("result"), msg.get("max_budget", 0))

        # Dynamic Streaming Placeholders
        stream_slot = st.empty()
        typing_slot = st.empty()

        # Kept active here during background processing loops
        if st.session_state.processing:
            typing_slot.markdown(TYPING_BUBBLE, unsafe_allow_html=True)

        st.markdown('<div id="chat-end" style="height:1px;"></div>', unsafe_allow_html=True)

    inject_js()

    typed = st.chat_input("Describe your PC needs in plain English…")
    user_input = typed or st.session_state.pill_input

    # ── Input Router Trigger ────────────────────────────────────────
    if user_input and not st.session_state.processing:
        st.session_state.pill_input = None
        st.session_state.pending_input = user_input
        st.session_state.processing = True
        st.session_state.display_history.append({"role": "user", "content": user_input})
        st.session_state.chat_memory.append({"role": "user", "content": user_input})
        st.rerun()

    # ── Active Live Async Pipeline Processing ────────────────────────
    if st.session_state.processing and st.session_state.pending_input:
        user_msg = st.session_state.pending_input

        # Step 1: Execute concurrent analysis mapping extraction logic
        analysis = asyncio.run(agent.analyse(user_msg))
        intent = analysis.get("intent", "technical")
        criteria = analysis.get("extracted_specs", st.session_state.current_specs)
        missing = analysis.get("needs_clarification", [])
        can_build = analysis.get("can_build", False)

        if intent == "chitchat":
            typing_slot.empty()  # Wipe out the typing dots right before the text streaming block starts
            reply = asyncio.run(agent.handle_chitchat_streamed(user_msg, stream_slot))
            entry = {"role": "assistant", "content": reply}

        elif missing or not can_build:
            st.session_state.current_specs = criteria
            typing_slot.empty()  # Wipe out the typing dots right before the text streaming block starts
            reply = asyncio.run(
                agent.ask_for_clarification_streamed(user_msg, missing or ["use case and shipping location"],
                                                     stream_slot))
            entry = {"role": "assistant", "content": reply}

        else:
            st.session_state.current_specs = criteria

            # Step 2: Execute build matching optimization loops
            draft = asyncio.run(agent.build_solution_ai(criteria)) or agent.build_solution_rules(criteria)
            result = agent.validate_and_quote(draft)

            # Downgrade Fallback Logic
            if result["status"] == "Rejected" and result.get("can_retry"):
                tier_down = {"high-end": "mid-range", "mid-range": "budget", "budget": "budget"}
                fallback = dict(criteria)
                fallback["performance_tier"] = tier_down.get(criteria.get("performance_tier", "budget"), "budget")
                draft2 = asyncio.run(agent.build_solution_ai(fallback)) or agent.build_solution_rules(fallback)
                result2 = agent.validate_and_quote(draft2)
                if result2["status"] == "Approved":
                    result = result2

            # Step 3: Stream response text output
            typing_slot.empty()  # Clear typing animation bubble container the exact millisecond streaming tokens hit the screen
            reply = asyncio.run(agent.generate_response_streamed(user_msg, result, criteria, stream_slot))
            entry = {
                "role": "assistant",
                "content": reply,
                "result": result,
                "max_budget": criteria.get("max_budget", 0),
            }

        # Save turns to memory configurations
        st.session_state.display_history.append(entry)
        st.session_state.chat_memory.append({"role": "assistant", "content": reply})
        st.session_state.chat_memory = _trim_memory(st.session_state.chat_memory, MEMORY_TURNS)

        st.session_state.processing = False
        st.session_state.pending_input = None
        st.rerun()