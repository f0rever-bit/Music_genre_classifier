import httpx
import json

# Assuming we have the token for user_id=4 from DB
def test_spotify():
    import psycopg2
    conn = psycopg2.connect("dbname=music_recommender_db user=postgres host=127.0.0.1 port=5432")
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM spotify_auth WHERE user_id = 4;")
    row = cur.fetchone()
    if not row:
        print("No token")
        return
    token = row[0]
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    me_r = httpx.get("https://api.spotify.com/v1/me", headers=headers)
    print("ME STATUS:", me_r.status_code)
    me_data = me_r.json()
    user_id = me_data["id"]
    print("USER ID:", user_id)
    
    playlist_data = {
        "name": "Test Export Playlist",
        "public": False,
        "description": "Created from Music Classifier App"
    }
    
    c_r = httpx.post(f"https://api.spotify.com/v1/users/{user_id}/playlists", headers=headers, json=playlist_data)
    print("CREATE STATUS:", c_r.status_code)
    print("CREATE RESPONSE:", c_r.text)

if __name__ == "__main__":
    test_spotify()
