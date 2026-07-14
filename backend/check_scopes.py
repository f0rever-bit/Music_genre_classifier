from app.database import SessionLocal
from app.models.spotify_auth import SpotifyAuth
db = SessionLocal()
auth = db.query(SpotifyAuth).first()
if auth:
    print(f"User ID: {auth.user_id}")
    print(f"Scopes: {auth.scope}")
else:
    print("No auth found")
