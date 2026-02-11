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
    if not os.path.exists(MATCHES_FILE):
        return []
    try:
        with open(MATCHES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return [] # Ošetření pro případ, že je soubor prázdný nebo rozbitý

def load_roster():
    if not os.path.exists(PLAYERS_FILE):
        return {}
    try:
        with open(PLAYERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

# --- VÝPOČET ELO ---
def calculate_elo(matches, roster):
    model = PlackettLuce(mu=1200, sigma=400)
    elo_db = {}
    
    # 1. KROK: Inicializace všech hráčů ze soupisky
    # I když nejsou žádné zápasy, hráči se objeví v žebříčku se svým startovním ELO
    for name, meta in roster.items():
        start_mu = meta.get("initial_elo", 1200)
        elo_db[name] = model.rating(name=name, mu=start_mu, sigma=400)
    
    # 2. KROK: Přehrání historie zápasů
    for match in matches:
        team_a = match['team_a']
        team_b = match['team_b']
        
        # Pojistka pro hráče, kteří nejsou v soupisce, ale hráli zápas
        for p in team_a + team_b:
            if p not in elo_db:
                elo_db[p] = model.rating(name=p, mu=1200, sigma=400)
            
        team_a_ratings = [elo_db[p] for p in team_a]
        team_b_ratings = [elo_db[p] for p in team_b]
        
        res = model.rate([team_a_ratings, team_b_ratings], scores=[match['score_a'], match['score_b']])
        
        for i, p in enumerate(team_a): elo_db[p] = res[0][i]
        for i, p in enumerate(team_b): elo_db[p] = res[1][i]
        
    return elo_db

# --- UI APLIKACE ---
st.title("⚽ Football ELO Manager")

# Načtení dat
matches = load_data()
roster = load_roster()

# Pokud je soupiska prázdná, zobrazíme varování
if not roster:
    st.error("⚠️ Soubor `data/players.json` je prázdný nebo chybí! Žebříček se nemá z čeho načíst.")

elo_db = calculate_elo(matches, roster)

# Seznam všech hráčů pro výběry
all_players_set = set(elo_db.keys()) | set(roster.keys())
all_players = sorted(list(all_players_set))

# Záložky
tab1, tab2, tab3 = st.tabs(["🏆 Žebříček", "⚖️ Týmy", "📝 JSON Generátor"])

# TAB 1: ŽEBŘÍČEK
with tab1:
    st.header("Aktuální žebříček")
    
    leaderboard = []
    for name, rating in elo_db.items():
        meta = roster.get(name, {})
        full_name = meta.get("full_name", name)
        initial = meta.get("initial_elo", 1200)
        games_played = sum(1 for m in matches if name in m['team_a'] or name in m['team_b'])
        
        leaderboard.append({
            "Rank": 0,
            "Jméno": name,
            "Plné jméno": full_name,
            "ELO": int(rating.mu),
            "Start": initial,
            "Zápasů": games_played
        })
    
    # Seřadit podle ELO
    leaderboard.sort(key=lambda x: x['ELO'], reverse=True)
    for i, p in enumerate(leaderboard):
        p['Rank'] = i + 1
        
    st.dataframe(
        leaderboard, 
        column_order=("Rank", "Jméno", "ELO", "Zápasů", "Start", "Plné jméno"),
        use_container_width=True, 
        hide_index=True
    )

# TAB 2: GENERÁTOR TÝMŮ (SUDÝ/LICHÝ + VĚK)
with tab2:
    st.header("Generátor týmů")
    selected_names = st.multiselect("Kdo dnes hraje?", all_players)
    
    if st.button("Navrhnout týmy") and len(selected_names) >= 2:
        # Příprava dat
        players_pool = []
        for name in selected_names:
            if name in elo_db:
                r = elo_db[name].mu
            else:
                r = roster.get(name, {}).get("initial_elo", 1200)
            
            age_str = roster.get(name, {}).get("age", "30")
            try:
                age = float(age_str)
            except ValueError:
                age = 30.0
            players_pool.append({"n": name, "r": r, "age": age})

        # Seřadit podle ELO
        players_pool.sort(key=lambda x: x['r'], reverse=True)

        # Logika pro lichý počet
        count = len(players_pool)
        extra_player = None
        main_group = []

        if count % 2 != 0:
            main_group = players_pool[:-1] # Všichni kromě posledního
            extra_player = players_pool[-1] # Poslední (nejslabší)
        else:
            main_group = players_pool

        # Kombinace
        combs = list(itertools.combinations(main_group, len(main_group)//2))
        if len(combs) > 5000: combs = combs[:5000]
        
        best_diff = float('inf')
        best_split = None
        
        for ta in combs:
            ta_names = {x['n'] for x in ta}
            tb = [x for x in main_group if x['n'] not in ta_names]
            sa = sum(x['r'] for x in ta)
            sb = sum(x['r'] for x in tb)
            if abs(sa - sb) < best_diff:
                best_diff = abs(sa - sb)
                best_split = (list(ta), list(tb), sa, sb)
        
        team_a, team_b, sum_a, sum_b = best_split

        # Přidání lichého hráče
        msg_extra = ""
        if extra_player:
            avg_a = sum(p['age'] for p in team_a) / len(team_a) if team_a else 0
            avg_b = sum(p['age'] for p in team_b) / len(team_b) if team_b else 0
            
            if avg_a > avg_b:
                team_a.append(extra_player)
                target = "A"
                sum_a += extra_player['r']
            else:
                team_b.append(extra_player)
                target = "B"
                sum_b += extra_player['r']
            msg_extra = f"ℹ️ **Lichý počet:** {extra_player['n']} přidán k týmu {target} (starší průměr)."

        # Výpis
        c1, c2 = st.columns(2)
        def show_team(lst):
            if not lst: return
            avg = sum(p['age'] for p in lst)/len(lst)
            st.caption(f"Ø Věk: {avg:.1f}")
            for p in lst:
                mark = " ➕" if extra_player and p['n'] == extra_player['n'] else ""
                st.write(f"**{p['n']}** ({int(p['r'])}){mark}")

        with c1:
            st.subheader(f"Tým A ({int(sum_a)})")
            show_team(team_a)
        with c2:
            st.subheader(f"Tým B ({int(sum_b)})")
            show_team(team_b)
            
        if msg_extra: st.info(msg_extra)
        st.success(f"Rozdíl ELO (základ): {int(best_diff)}")

# TAB 3: JSON GENERÁTOR (S VALIDACÍ)
with tab3:
    st.header("Generátor JSON")
    
    # Chytré filtrování - co je v A, není v B
    curr_a = st.session_state.get("ta_in", [])
    curr_b = st.session_state.get("tb_in", [])
    
    opt_a = sorted([p for p in all_players if p not in curr_b])
    opt_b = sorted([p for p in all_players if p not in curr_a])
    
    c1, c2 = st.columns(2)
    with c1:
        ta_in = st.multiselect("Tým A", opt_a, key="ta_in")
        sa_in = st.number_input("Skóre A", min_value=0, step=1)
    with c2:
        tb_in = st.multiselect("Tým B", opt_b, key="tb_in")
        sb_in = st.number_input("Skóre B", min_value=0, step=1)
        
    date_in = st.text_input("Datum", value="2026-MM-DD")
    
    if st.button("Vytvořit JSON snippet"):
        if not ta_in or not tb_in:
            st.error("Vyber týmy.")
        else:
            new_match = {
                "date": date_in,
                "team_a": ta_in,
                "team_b": tb_in,
                "score_a": int(sa_in),
                "score_b": int(sb_in)
            }
            st.code(json.dumps(new_match, indent=2, ensure_ascii=False) + ",", language="json")
