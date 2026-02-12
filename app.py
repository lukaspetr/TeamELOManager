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
    # Důležité: 'weights' podporují modely jako PlackettLuce
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
        
        # Init hráčů, co nejsou v DB
        for p in t_a + t_b:
            if p not in elo_db: elo_db[p] = model.rating(name=p, mu=1200, sigma=400)
            
        r_a = [elo_db[p] for p in t_a]
        r_b = [elo_db[p] for p in t_b]
        
        # --- LOGIKA VÁH PRO STŘÍDÁNÍ ---
        # Defaultně má každý váhu 1.0 (hraje celý zápas / hrají všichni)
        w_a = [1.0] * len(t_a)
        w_b = [1.0] * len(t_b)
        
        # Pokud je v zápisu uvedeno, že se střídalo ("rotation": true)
        if match.get("rotation", False):
            len_a = len(t_a)
            len_b = len(t_b)
            
            # Zjistíme, kolik lidí bylo maximálně na hřišti (velikost menšího týmu)
            field_size = min(len_a, len_b)
            
            # Pokud má tým A víc lidí než je field_size, snížíme jim váhu
            # Příklad: Hrají 6 lidí na 5 míst. Váha každého je 5/6 (0.83)
            if len_a > field_size:
                factor = field_size / len_a
                w_a = [factor] * len_a
                
            # To samé pro tým B
            if len_b > field_size:
                factor = field_size / len_b
                w_b = [factor] * len_b

        # Výpočet s vahami
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
    # Defaultně False = Střídá se (chceme férové týmy N vs N)
    play_all = st.checkbox("Hrají všichni v poli (bez střídání)", value=False, help="Pokud je zaškrtnuto, vytvoří se týmy např. 5 proti 6. Tým s více hráči bude mít ELO výhodu.")
    
    if st.button("Navrhnout") and len(selected) >= 2:
        # Příprava dat
        pool = []
        for n in selected:
            r = elo_db[n].mu if n in elo_db else roster.get(n,{}).get("initial_elo",1200)
            try: age = float(roster.get(n,{}).get("age",30))
            except: age = 30
            pool.append({"n":n, "r":r, "age":age})
        
        # Seřadit podle ELO (jen pomocné, kombinace to nepotřebují, ale je to dobré pro přehled)
        pool.sort(key=lambda x: x['r'], reverse=True)
        
        # LOGIKA ROZDĚLENÍ
        extra_player = None
        main_pool = pool
        
        # Pokud je lichý počet A NIKDO NESTŘÍDÁ (Play All = True) -> Necháme všechny ve hře
        # Pokud je lichý počet A STŘÍDÁ SE (Play All = False) -> Jednoho vyhodíme
        
        if len(pool) % 2 != 0 and not play_all:
            extra_player = pool[-1] # Nejslabší hráč (nebo náhodný) jde střídat
            main_pool = pool[:-1]
        
        # Generování kombinací
        # itertools.combinations vybere polovinu hráčů do Týmu A, zbytek je Tým B
        # Pokud je main_pool lichý (jen v režimu play_all), split bude např. 5 vs 6
        team_size = len(main_pool) // 2
        combs = list(itertools.combinations(main_pool, team_size))
        
        # Omezíme počet iterací pro rychlost
        if len(combs) > 5000: combs = combs[:5000]
        
        best = (None, float('inf'))
        
        for ta in combs:
            ta_names = {x['n'] for x in ta}
            # Tým B je zbytek z main_pool
            tb = [x for x in main_pool if x['n'] not in ta_names]
            
            # Kritický bod: Porovnáváme Součet ELO
            sum_a = sum(x['r'] for x in ta)
            sum_b = sum(x['r'] for x in tb)
            diff = abs(sum_a - sum_b)
            
            if diff < best[1]: 
                best = ((list(ta), list(tb)), diff)
                
        if best[0]:
            (ta, tb), diff = best
            
            # Pokud se střídá, vypíšeme extra hráče
            msg = ""
            if extra_player and not play_all:
                 msg = f"ℹ️ **Lichý počet (střídání):** Hráč **{format_name_func(extra_player['n'])}** začíná na střídačce."

            c1, c2 = st.columns(2)
            
            def show_team_list(lst):
                for p in lst:
                    fname = roster.get(p['n'], {}).get("full_name", p['n'])
                    st.write(f"**{fname}** ({int(p['r'])})")

            with c1:
                st.info(f"Tým A ({int(sum(x['r'] for x in ta))})")
                show_team_list(ta)
            with c2:
                # Barva podle toho, jestli je to přesilovka
                is_powerplay = len(tb) > len(ta)
                header_text = f"Tým B ({int(sum(x['r'] for x in tb))})"
                if is_powerplay:
                     st.error(f"{header_text} - PŘESILOVKA (+1 hráč)")
                else:
                     st.warning(header_text)
                show_team_list(tb)
                
            if msg: st.write(msg)
            
            # Informace o ELO dopadu
            if play_all and len(pool) % 2 != 0:
                st.caption("⚠️ Protože hrají všichni (lichý počet), Tým B má výhodu jednoho hráče. ELO systém s tím počítá (očekává jejich výhru).")
            else:
                st.success(f"Rozdíl ELO: {int(diff)}")

with tab3:
    st.header("Generátor JSON")
    
    curr_a = st.session_state.get("ta",[])
    curr_b = st.session_state.get("tb",[])
    opt_a = sorted([p for p in all_players if p not in curr_b])
    opt_b = sorted([p for p in all_players if p not in curr_a])
    
    c1,c2 = st.columns(2)
    with c1: 
        ta = st.multiselect("Tým A", opt_a, key="ta", format_func=format_name_func)
        sa = st.number_input("Skóre A",step=1)
    with c2: 
        tb = st.multiselect("Tým B", opt_b, key="tb", format_func=format_name_func)
        sb = st.number_input("Skóre B",step=1)
    
    col_date, col_rot = st.columns(2)
    with col_date:
        d = st.text_input("Datum", value="2026-02-12")
    with col_rot:
        # Checkbox pro typ zápasu
        st.write("") # Spacer
        st.write("")
        is_rotation = st.checkbox("Bylo to se střídáním?", value=True, help="Pokud je zaškrtnuto, počítá se ELO jako by byl počet hráčů na hřišti vyrovnaný (vážený průměr). Pokud ne, počítá se jako přesilovka (součet).")
    
    if st.button("Generovat"):
        if not ta or not tb: 
            st.error("Chybí týmy")
        else:
            j = {
                "date": d,
                "team_a": ta,
                "team_b": tb,
                "score_a": int(sa),
                "score_b": int(sb),
                "rotation": is_rotation  # Nový parametr
            }
            st.code(json.dumps(j, indent=2, ensure_ascii=False)+",", language="json")
