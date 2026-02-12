import streamlit as st
import json
import os
import itertools
from openskill.models import PlackettLuce

# --- KONFIGURACE ---
st.set_page_config(page_title="Football ELO", layout="centered")

DATA_DIR = "data"
MATCHES_FILE = os.path.join(DATA_DIR, "matches.json")
PLAYERS_FILE = os.path.join(DATA_DIR, "players.json")

# --- NAČÍTÁNÍ DAT ---
def load_data():
    if not os.path.exists(MATCHES_FILE): return []
    try:
        with open(MATCHES_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def load_roster():
    if not os.path.exists(PLAYERS_FILE): return {}
    try:
        with open(PLAYERS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

# --- VÝPOČET ELO ---
def calculate_elo(matches, roster):
    model = PlackettLuce(mu=1200, sigma=400)
    elo_db = {}
    
    # 1. Startovní pozice
    for name, meta in roster.items():
        start_mu = meta.get("initial_elo", 1200)
        elo_db[name] = model.rating(name=name, mu=start_mu, sigma=400)
    
    # 2. Historie zápasů
    for match in matches:
        t_a = match['team_a']
        t_b = match['team_b']
        for p in t_a + t_b:
            if p not in elo_db: elo_db[p] = model.rating(name=p, mu=1200, sigma=400)
            
        r_a = [elo_db[p] for p in t_a]
        r_b = [elo_db[p] for p in t_b]
        res = model.rate([r_a, r_b], scores=[match['score_a'], match['score_b']])
        
        for i, p in enumerate(t_a): elo_db[p] = res[0][i]
        for i, p in enumerate(t_b): elo_db[p] = res[1][i]
        
    return elo_db

# --- UI APLIKACE ---
st.title("⚽ Football ELO Manager")

matches = load_data()
roster = load_roster()
elo_db = calculate_elo(matches, roster)

all_players = sorted(list(set(elo_db.keys()) | set(roster.keys())))

# PŘÍPRAVA ŽEBŘÍČKU
leaderboard = []
for name, rating in elo_db.items():
    meta = roster.get(name, {})
    games = sum(1 for m in matches if name in m['team_a'] or name in m['team_b'])
    leaderboard.append({
        "Rank": 0,
        "Jméno": name,
        "ELO": int(rating.mu),
        "Zápasů": games,
        "Věk": meta.get("age", "-")
    })
    
leaderboard.sort(key=lambda x: x['ELO'], reverse=True)
for i, p in enumerate(leaderboard): p['Rank'] = i + 1

# --- ZÁLOŽKY ---
tab1, tab2, tab3 = st.tabs(["📊 Žebříček", "⚖️ Týmy", "📝 Zadat zápas"])

with tab1:
    # --- UPRAVENÁ TABULKA ---
    # height=800 zajistí, že bude dostatečně vysoká
    # use_container_width=True ji roztáhne do šířky
    st.dataframe(
        leaderboard,
        column_order=("Rank", "Jméno", "ELO", "Zápasů", "Věk"),
        hide_index=True,
        use_container_width=True,
        height=800 
    )

with tab2:
    st.header("Generátor týmů")
    selected = st.multiselect("Kdo hraje?", all_players)
    if st.button("Navrhnout") and len(selected) >= 2:
        # Data pro generátor
        pool = []
        for n in selected:
            r = elo_db[n].mu if n in elo_db else roster.get(n,{}).get("initial_elo",1200)
            try: age = float(roster.get(n,{}).get("age",30))
            except: age = 30
            pool.append({"n":n, "r":r, "age":age})
        pool.sort(key=lambda x: x['r'], reverse=True)
        
        # Sudý/Lichý
        if len(pool) % 2 != 0:
            main = pool[:-1]
            extra = pool[-1]
        else:
            main = pool
            extra = None
            
        # Kombinace
        combs = list(itertools.combinations(main, len(main)//2))
        if len(combs)>3000: combs=combs[:3000]
        
        best = (None, float('inf'))
        for ta in combs:
            ta_names = {x['n'] for x in ta}
            tb = [x for x in main if x['n'] not in ta_names]
            diff = abs(sum(x['r'] for x in ta) - sum(x['r'] for x in tb))
            if diff < best[1]: best = ((list(ta), list(tb)), diff)
            
        if best[0]:
            (ta, tb), diff = best
            
            # Lichý hráč logika
            msg = ""
            if extra:
                aa = sum(x['age'] for x in ta)/len(ta) if ta else 0
                ab = sum(x['age'] for x in tb)/len(tb) if tb else 0
                if aa > ab: ta.append(extra); t="A"
                else: tb.append(extra); t="B"
                msg = f"ℹ️ {extra['n']} přidán k týmu {t} (starší)."
                
            c1, c2 = st.columns(2)
            with c1:
                st.info(f"Tým A ({int(sum(x['r'] for x in ta))})")
                for p in ta: st.write(f"**{p['n']}** ({int(p['r'])}){' ➕' if extra and p==extra else ''}")
            with c2:
                st.warning(f"Tým B ({int(sum(x['r'] for x in tb))})")
                for p in tb: st.write(f"**{p['n']}** ({int(p['r'])}){' ➕' if extra and p==extra else ''}")
            if msg: st.write(msg)
            st.success(f"Rozdíl ELO: {int(diff)}")

with tab3:
    st.header("Generátor JSON")
    
    # Chytré filtrování (Co je v A, není v B)
    curr_a = st.session_state.get("ta",[])
    curr_b = st.session_state.get("tb",[])
    opt_a = sorted([p for p in all_players if p not in curr_b])
    opt_b = sorted([p for p in all_players if p not in curr_a])
    
    c1,c2 = st.columns(2)
    with c1: ta = st.multiselect("Tým A", opt_a, key="ta"); sa = st.number_input("Skóre A",step=1)
    with c2: tb = st.multiselect("Tým B", opt_b, key="tb"); sb = st.number_input("Skóre B",step=1)
    
    d = st.text_input("Datum", value="2026-02-12")
    
    if st.button("Generovat"):
        if not ta or not tb: st.error("Chybí týmy")
        else:
            j = {"date":d,"team_a":ta,"team_b":tb,"score_a":int(sa),"score_b":int(sb)}
            st.code(json.dumps(j, indent=2, ensure_ascii=False)+",", language="json")
