import pandas as pd
import requests
from datetime import datetime
import io

# --- 1. CONFIG: THE 2025-26 PREMIER LEAGUE TEAMS ---
TEAM_QIDS = [
    "Q9617", "Q965", "Q7156", "Q19571", "Q19422", "Q7141", "Q19424",
    "Q5794", "Q18755", "Q19651", "Q8100", "Q1130849", "Q50602", "Q18656",
    "Q18716", "Q19490", "Q18048", "Q18724", "Q18747", "Q5330"
]


def get_wikidata_birthdays():
    print("🌍 Querying Wikidata (SPARQL) for birthdays...")
    team_values = " ".join([f"wd:{qid}" for qid in TEAM_QIDS])

    query = f"""
    SELECT ?playerLabel ?dob WHERE {{
      VALUES ?team {{ {team_values} }}
      ?player wdt:P54 ?team ; wdt:P569 ?dob .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }}
    }}
    """

    try:
        url = "https://query.wikidata.org/sparql"
        response = requests.get(url, params={'format': 'json', 'query': query})
        data = response.json()

        dob_map = {}
        for item in data['results']['bindings']:
            try:
                name = item['playerLabel']['value']
                dob_str = item['dob']['value']
                key = name.lower().strip()
                dob_date = pd.to_datetime(dob_str).date()
                dob_map[key] = dob_date
            except:
                continue
        print(f"✅ Wikidata returned {len(dob_map)} player records.")
        return dob_map
    except Exception as e:
        print(f"❌ Wikidata Query Failed: {e}")
        return {}


def get_data():
    headers = {"User-Agent": "Mozilla/5.0"}

    # 1. FETCH LIVE ROSTER
    try:
        print("Fetching Active FPL Roster...")
        response = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", headers=headers)
        response.raise_for_status()
        data = response.json()

        teams = {t['id']: t['name'] for t in data['teams']}
        players = pd.DataFrame(data['elements'])
        players['full_name'] = (players['first_name'] + " " + players['second_name'])
        players['match_key'] = players['full_name'].str.lower().str.strip()
        players['Team Name'] = players['team'].map(teams)
    except Exception as e:
        print(f"❌ Error fetching Live Data: {e}")
        return pd.DataFrame()

    # 2. FETCH BIRTHDAYS
    dob_map = get_wikidata_birthdays()
    if not dob_map: return pd.DataFrame()

    # 3. MATCHING LOGIC
    print("Matching Active Players to Birthdays...")
    matches_found = []

    try:
        fix_resp = requests.get("https://fantasy.premierleague.com/api/fixtures/", headers=headers).json()
        fixtures = pd.DataFrame(fix_resp)
        fixtures['kickoff_time'] = pd.to_datetime(fixtures['kickoff_time']).dt.date
        fixtures = fixtures.dropna(subset=['kickoff_time'])
        fixtures['Home'] = fixtures['team_h'].map(teams)
        fixtures['Away'] = fixtures['team_a'].map(teams)
    except:
        return pd.DataFrame()

    today = datetime.now().date()

    for _, p in players.iterrows():
        p_key = p['match_key']
        p_team = p['Team Name']

        p_dob = dob_map.get(p_key)
        if not p_dob:
            web_key = p['web_name'].lower().strip()
            p_dob = dob_map.get(web_key)

        if p_dob:
            p_dob = pd.to_datetime(p_dob).date()
            team_fix = fixtures[(fixtures['Home'] == p_team) | (fixtures['Away'] == p_team)]

            for _, m in team_fix.iterrows():
                m_date = m['kickoff_time']

                # EXACT BIRTHDAY MATCH
                if m_date.month == p_dob.month and m_date.day == p_dob.day:
                    venue = "vs" if p_team == m['Home'] else "@"
                    opponent = m['Away'] if p_team == m['Home'] else m['Home']
                    status = "✅ PLAYED" if m_date < today else "🔜 UPCOMING"
                    css_class = "played" if m_date < today else "upcoming"

                    matches_found.append({
                        "Date": m_date,
                        "Status": status,
                        "CssClass": css_class,
                        "Player": p['full_name'],
                        "Team": p_team,
                        "Turning Age": m_date.year - p_dob.year,
                        "Opponent": f"{venue} {opponent}"
                    })

    return pd.DataFrame(matches_found).sort_values('Date')


# --- 4. GENERATE HTML ---
print("\n--- STARTING ---")
df = get_data()

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>PL Birthday Matches (Full Season)</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 2rem auto; padding: 1rem; background: #f0f2f5; }}
        h1 {{ text-align: center; color: #38003c; }}
        .summary {{ text-align: center; margin-bottom: 2rem; color: #555; }}
        .card {{ background: white; padding: 1.2rem; margin-bottom: 1rem; border-radius: 8px; display: flex; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}

        /* Different borders for Past vs Future */
        .played {{ border-left: 5px solid #aaa; opacity: 0.8; }}
        .upcoming {{ border-left: 5px solid #00ff85; }}

        .date-col {{ width: 80px; text-align: center; margin-right: 1rem; }}
        .day {{ font-size: 1.4rem; font-weight: 800; color: #333; }}
        .month {{ font-size: 0.8rem; text-transform: uppercase; font-weight: 700; color: #777; }}

        .info-col {{ flex-grow: 1; }}
        .player {{ font-size: 1.2rem; font-weight: 700; }}
        .details {{ color: #555; }}

        .status-tag {{ font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; vertical-align: middle; margin-left: 10px; }}
        .played .status-tag {{ background: #eee; color: #555; }}
        .upcoming .status-tag {{ background: #00ff85; color: #38003c; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>📅 Full Season Birthday Matches</h1>
    <div class="summary">Found {len(df)} matches for the 2025-26 Season</div>
"""

if not df.empty:
    print(f"\n✅ Success! Found {len(df)} matches across the whole season.")
    for _, row in df.iterrows():
        html_content += f"""
        <div class="card {row['CssClass']}">
            <div class="date-col">
                <div class="day">{row['Date'].day}</div>
                <div class="month">{row['Date'].strftime('%b')}</div>
            </div>
            <div class="info-col">
                <div class="player">{row['Player']} <span class="status-tag">{row['Status']}</span></div>
                <div class="details">Turn {row['Turning Age']} • <b>{row['Team']}</b> {row['Opponent']}</div>
            </div>
        </div>
        """
else:
    print("\n⚠️ No matches found.")
    html_content += "<p style='text-align:center'>No matches found.</p>"

html_content += f"</body></html>"

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("Done. Created index.html")