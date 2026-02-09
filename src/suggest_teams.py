import json
import os
import argparse
import itertools

# --- CONFIGURATION ---
DATA_DIR = "data"
ROSTER_FILE = os.path.join(DATA_DIR, "players.json")     # Manual info
ELO_FILE = os.path.join(DATA_DIR, "elo_state.json")      # Generated ELO

def load_data():
    if not os.path.exists(ELO_FILE):
        print("Error: Run main.py first to generate ELO ratings.")
        return {}, {}
    
    with open(ELO_FILE, 'r') as f:
        elo_data = json.load(f)
        
    roster_data = {}
    if os.path.exists(ROSTER_FILE):
        with open(ROSTER_FILE, 'r') as f:
            roster_data = json.load(f)
            
    return elo_data, roster_data

def get_player_stats(name, elo_db, roster_db):
    """Combines ELO and Roster data into one object."""
    elo = elo_db[name]['mu'] if name in elo_db else 1200.0
    meta = roster_db.get(name, {})
    
    return {
        "name": name,
        "elo": elo,
        "full_name": meta.get("full_name", ""),
        "age": meta.get("age", "?")
    }

def balance_teams(names):
    elo_db, roster_db = load_data()
    
    # 1. Build list of player objects
    players = []
    for name in names:
        p_stats = get_player_stats(name, elo_db, roster_db)
        players.append(p_stats)

    # 2. Brute force balance (Same logic as before)
    team_size = len(players) // 2
    combinations = itertools.combinations(players, team_size)
    
    best_diff = float('inf')
    best_matchup = None

    for team_a in combinations:
        team_a_ids = {p['name'] for p in team_a}
        team_b = [p for p in players if p['name'] not in team_a_ids]
        
        sum_a = sum(p['elo'] for p in team_a)
        sum_b = sum(p['elo'] for p in team_b)
        
        diff = abs(sum_a - sum_b)
        
        if diff < best_diff:
            best_diff = diff
            best_matchup = (team_a, team_b, sum_a, sum_b)

    # 3. Display Result with Metadata
    team_a, team_b, sum_a, sum_b = best_matchup

    def print_team(label, team_list, total_elo):
        avg_elo = total_elo / len(team_list)
        # Calculate average age (filtering out '?')
        ages = [p['age'] for p in team_list if isinstance(p['age'], int)]
        avg_age = sum(ages)/len(ages) if ages else 0
        
        print(f"{label} (Avg Elo: {int(avg_elo)}, Avg Age: {avg_age:.1f})")
        print("-" * 50)
        
        # Sort by ELO for display
        sorted_team = sorted(team_list, key=lambda x: x['elo'], reverse=True)
        
        for p in sorted_team:
            # Format: "Alex (1200) - Alex Ferguson [29]"
            details = []
            if p['full_name']: details.append(p['full_name'])
            if p['age'] != "?": details.append(f"{p['age']}y")
            
            detail_str = f" | {', '.join(details)}" if details else ""
            print(f"  {p['name']:<10} {int(p['elo']):<5}{detail_str}")
        print("")

    print("\n" + "="*50)
    print(f"BALANCED TEAMS (Diff: {int(abs(sum_a - sum_b))})")
    print("="*50)
    
    print_team("TEAM A", team_a, sum_a)
    print_team("TEAM B", team_b, sum_b)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('players', nargs='+')
    args = parser.parse_args()
    balance_teams(args.players)
