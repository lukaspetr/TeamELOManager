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
    # Model PlackettLuce (mu=1200, sigma=400)
    model = PlackettLuce(mu=1200, sigma=400)
    elo_db = {}
    
    # 1. Startovní pozice (Seeding)
    for name, meta in roster.items():
        start_mu = meta.get("initial_elo", 1200)
        elo_db[name] = model.rating(name=name, mu=start_mu, sigma=400)
    
    # 2. Historie zápasů
    for match in matches:
        t_a = match['team_a']
        t_b = match['team_b']
        
        # Inicializace nováčků
        for p in t_a + t_b:
            if p not in elo_db: elo_db[p] = model.rating(name=p, mu=1200, sigma=400)
            
        r_a = [elo_db[p] for p in t_a]
        r_b = [elo_db[p] for p in t_b]
        
        # --- LOGIKA VÁH PRO STŘÍDÁNÍ ---
        w_a = [1.0] * len(t_a)
        w_b = [1.0] * len(t_b)
        
        # Pokud se střídalo ("rotation": true), snížíme váhu početnějšího týmu
        if match.get("rotation", False):
            len_a = len(t_a)
            len_b = len(t_b)
            field_size = min(len_a, len_b) # Kolik lidí reálně hraje (např. 5)
            
            # Pokud má tým A 6 lidí na 5 míst -> váha každého je 5/6
            if len_a > field_size:
                factor = field_size / len_a
                w_a = [factor] * len_a
                
            if len_b > field_size:
                factor = field_size / len_b
                w_b = [factor] * len_b

        # Výpočet
        res = model.rate([r_a, r_b], scores=[match['score_a'], match['score_b']], weights=[w_a, w_b])
        
        for i, p in enumerate(t_a): elo_db[p] = res[0][i]
        for i, p in enumerate(t_b): elo_db[p] = res[1][i]
        
    return elo_db

# --- HELPER PRO JMÉNA ---
def format_name_func(player_id):
    meta = roster.get(player_id, {})
    full_name = meta.get("full_name", "")
    if full_name:
        return f"{player_id} ({full_name})"
    return player_id

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
    full_name = meta.get("full_name", name)
    games = sum(1 for m in matches if name in m['team_a'] or name in m['team_b'])
    
    leaderboard.append({
        "Rank": 0,
        "Hráč": full_name,
        "ELO": int(rating.mu),
        "Zápasů": games,
        "Věk": meta.get("age", "-")
    })
    
leaderboard.sort(key=lambda x: x['ELO'], reverse=True)
for i, p in enumerate(leaderboard): p['Rank'] = i + 1

# --- ZÁLOŽKY ---
tab1, tab2, tab3 = st.tabs(["📊 Žebříček", "⚖️ Týmy", "📝 Zadat zápas"])

with tab1:
    st.dataframe(
        leaderboard,
        column_order=("Rank", "Hráč", "ELO", "Zápasů", "Věk"),
        hide_index=True,
        use_container_width=True,
        height=800 
    )

with tab2:
    st.header("Generátor týmů")
    
    # 1. Výběr hráčů
    selected = st.multiselect(
        "Kdo hraje?", 
        options=all_players, 
        format_func=format_name_func
    )
    
    # 2. Checkbox pro režim hry
    play_all = st.checkbox("Hrají všichni v poli (bez střídání)", value=False, help="Zaškrtni, pokud hrajete přesilovku (např. 5 na 6). Pokud je odškrtnuto, jeden hráč bude střídat.")
    
    if st.button("Navrhnout") and len(selected) >= 2:
        # Příprava dat
        pool = []
        for n in selected:
            r = elo_db[n].mu if n in elo_db else roster.get(n,{}).get("initial_elo",1200)
            try: age = float(roster.get(n,{}).get("age",30))
            except: age = 30
            pool.append({"n":n, "r":r, "age":age})
        
        # Seřadit podle ELO (nejslabší bude na konci)
        pool.sort(key=lambda x: x['r'], reverse=True)
        
        # --- LOGIKA LICHÉHO POČTU ---
        extra_player = None
        main_pool = pool
        
        # Pokud je lichý počet A NIKDO NESTŘÍDÁ (Play All = True) -> Necháme všechny v main_pool
        # Pokud je lichý počet A STŘÍDÁ SE (Play All = False) -> Vyřadíme posledního (nejslabšího)
        
        if len(pool) % 2 != 0 and not play_all:
            extra_player = pool[-1] # Nejslabší hráč jde "na čekačku"
            main_pool = pool[:-1]   # Zbytek rozdělíme férově
        
        # Generování kombinací z main_pool
        team_size = len(main_pool) // 2
        combs = list(itertools.combinations(main_pool, team_size))
        if len(combs) > 5000: combs = combs[:5000]
        
        best = (None, float('inf'))
        for ta in combs:
            ta_names = {x['n'] for x in ta}
            tb = [x for x in main_pool if x['n'] not in ta_names]
            
            sum_a = sum(x['r'] for x in ta)
            sum_b = sum(x['r'] for x in tb)
            diff = abs(sum_a - sum_b)
            
            if diff < best[1]: 
                best = ((list(ta), list(tb)), diff)
                
        if best[0]:
            (ta, tb), diff = best
            
            # --- PŘIŘAZENÍ EXTRA HRÁČE PODLE VĚKU ---
            msg_extra = ""
            if extra_player and not play_all:
                # Spočítáme průměrný věk týmů (základní sestavy)
                avg_a = sum(x['age'] for x in ta) / len(ta) if ta else 0
                avg_b = sum(x['age'] for x in tb) / len(tb) if tb else 0
                
                target_team_name = ""
                
                # Přidáme ho ke STARŠÍMU týmu
                if avg_a > avg_b:
                    ta.append(extra_player)
                    target_team_name = "A"
                else:
                    tb.append(extra_player)
                    target_team_name = "B"
                    
                full_n = roster.get(extra_player['n'], {}).get("full_name", extra_player['n'])
                msg_extra = f"ℹ️ **Lichý počet:** Nejnižší ELO má **{full_n}**. Byl přiřazen k týmu **{target_team_name}**, protože má vyšší věkový průměr."

            # Vykreslení
            c1, c2 = st.columns(2)
            
            # Funkce pro výpis týmu (zobrazuje ELO všech, ale počítá součet jen základu)
            def show_team_box(team_list, team_letter):
                # Zjistíme, kdo je v tomto týmu "navíc" (střídá)
                rotation_player = None
                active_players = []
                
                for p in team_list:
                    if extra_player and p['n'] == extra_player['n']:
                        rotation_player = p
                    else:
                        active_players.append(p)
                
                # Součet ELO jen pro aktivní hráče (pokud se střídá)
                # Pokud hrají všichni (přesilovka), počítáme všechny
                if not play_all and rotation_player:
                    team_elo_sum = sum(p['r'] for p in active_players)
                else:
                    team_elo_sum = sum(p['r'] for p in team_list)
                    
                team_avg_age = sum(p['age'] for p in team_list) / len(team_list) if team_list else 0

                # Barvičky
                header = f"Tým {team_letter} ({int(team_elo_sum)})"
                if team_letter == "A":
                    st.info(header)
                else:
                    # Tým B může být varování (pokud je silnější/přesilovka)
                    st.warning(header)

                st.caption(f"Ø Věk: {team_avg_age:.1f}")
                
                for p in team_list:
                    fname = roster.get(p['n'], {}).get("full_name", p['n'])
                    if p == rotation_player:
                        st.write(f
