import httpx
import json
from app.database import SessionLocal
from app.models.spotify_auth import SpotifyAuth

def test_spotify():
    db = SessionLocal()
    auth = db.query(SpotifyAuth).filter(SpotifyAuth.user_id == 4).first()
    if not auth:
        print("No auth found")
        return
    token = auth.access_token
    
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
