import streamlit as st
import json
import os
import itertools
from openskill.models import PlackettLuce

# --- CONFIGURATION ---
st.set_page_config(page_title="Football ELO", layout="centered")

DATA_DIR = "data"
MATCHES_FILE = os.path.join(DATA_DIR, "matches.json")
PLAYERS_FILE = os.path.join(DATA_DIR, "players.json")

# --- DATA LOADING ---
def load_data():
    # Load matches
    if not os.path.exists(MATCHES_FILE):
        st.error(f"File not found: {MATCHES_FILE}")
        return []
    with open(MATCHES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_roster():
    # Load player details (Age, Full Name)
    if not os.path.exists(PLAYERS_FILE):
        return {}
    with open(PLAYERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- ELO CALCULATION ---
def calculate_elo(matches):
    # We recalculate history from scratch every time
    model = PlackettLuce(mu=1200, sigma=400)
    elo_db = {}
    
    for match in matches:
        team_a = match['team_a']
        team_b = match['team_b']
        
        # Initialize players if new
        for p in team_a + team_b:
            if p not in elo_db: elo_db[p] = model.rating(name=p)
            
        # Get current ratings
        team_a_ratings = [elo_db[p] for p in team_a]
        team_b_ratings = [elo_db[p] for p in team_b]
        
        # Calculate result
        res = model.rate([team_a_ratings, team_b_ratings], scores=[match['score_a'], match['score_b']])
        
        # Update DB
        for i, p in enumerate(team_a): elo_db[p] = res[0][i]
        for i, p in enumerate(team_b): elo_db[p] = res[1][i]
        
    return elo_db

# --- APP LOGIC ---
st.title("⚽ Football ELO Manager")

# Load and Calculate
matches = load_data()
roster = load_roster()
elo_db = calculate_elo(matches)

# Get list of all players seen in history + roster
all_players_set = set(elo_db.keys()) | set(roster.keys())
all_players = sorted(list(all_players_set))

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["🏆 Leaderboard", "⚖️ Teams", "📝 Add Match"])

# TAB 1: LEADERBOARD
with tab1:
    st.header("Current Standings")
    
    leaderboard = []
    for name, rating in elo_db.items():
        meta = roster.get(name, {})
        full_name = meta.get("full_name", "")
        age = meta.get("age", "")
        
        # Count matches played
        games_played = sum(1 for m in matches if name in m['team_a'] or name in m['team_b'])
        
        leaderboard.append({
            "Rank": 0, # Placeholder
            "Name": name,
            "Full Name": full_name,
            "ELO": int(rating.mu),
            "Games": games_played
        })
    
    # Sort and Rank
    leaderboard.sort(key=lambda x: x['ELO'], reverse=True)
    for i, p in enumerate(leaderboard):
        p['Rank'] = i + 1
        
    st.dataframe(
        leaderboard, 
        column_order=("Rank", "Name", "ELO", "Games", "Full Name"),
        use_container_width=True, 
        hide_index=True
    )

# TAB 2: TEAM GENERATOR
with tab2:
    st.header("Fair Team Generator")
    selected = st.multiselect("Who is playing today?", all_players)
    
    if st.button("Generate Teams") and len(selected) >= 2:
        # Prepare stats
        p_stats = [{"n": p, "r": elo_db[p].mu if p in elo_db else 1200} for p in selected]
        
        best_diff = float('inf')
        best_split = None
        
        # Combinations logic
        combs = list(itertools.combinations(p_stats, len(p_stats)//2))
        # Cap combinations for performance if too many players
        if len(combs) > 3000: combs = combs[:3000]
        
        for ta in combs:
            ta_names = {x['n'] for x in ta}
            tb = [x for x in p_stats if x['n'] not in ta_names]
            
            sa = sum(x['r'] for x in ta)
            sb = sum(x['r'] for x in tb)
            
            if abs(sa - sb) < best_diff:
                best_diff = abs(sa - sb)
                best_split = (ta, tb, sa, sb)
        
        # Display
        ta, tb, sa, sb = best_split
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader(f"Team A ({int(sa)})")
            for p in ta: st.write(f"**{p['n']}** ({int(p['r'])})")
        with c2:
            st.subheader(f"Team B ({int(sb)})")
            for p in tb: st.write(f"**{p['n']}** ({int(p['r'])})")
            
        st.success(f"Difference: {int(best_diff)} points")

# TAB 3: JSON GENERATOR (Helper for manual update)
with tab3:
    st.header("Generate Match JSON")
    st.info("Use this to generate the text for matches.json")
    
    c1, c2 = st.columns(2)
    with c1:
        ta_in = st.multiselect("Team A", all_players, key="ta_in")
        sa_in = st.number_input("Score A", min_value=0, step=1)
    with c2:
        tb_in = st.multiselect("Team B", all_players, key="tb_in")
        sb_in = st.number_input("Score B", min_value=0, step=1)
        
    date_in = st.text_input("Date (Optional)", value="2025-MM-DD")
        
    if st.button("Create JSON Snippet"):
        if not ta_in or not tb_in:
            st.error("Select players first.")
        else:
            new_match = {
                "date": date_in,
                "team_a": ta_in,
                "team_b": tb_in,
                "score_a": int(sa_in),
                "score_b": int(sb_in)
            }
            # Print as formatted JSON string
            json_str = json.dumps(new_match, indent=2, ensure_ascii=False)
            st.code(json_str + ",", language="json")
            st.caption("Copy the text above and paste it at the bottom of data/matches.json")
