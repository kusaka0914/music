import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def get_spotify_client():
    try:
        client_credentials_manager = SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        )
        return spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    except Exception as e:
        logger.error(f"Spotifyクライアントの初期化に失敗: {str(e)}")
        return None

def get_artist_image(artist_name):
    """
    アーティスト名から画像URLを取得
    """
    try:
        sp = get_spotify_client()
        if not sp:
            return None

        # アーティストを検索
        results = sp.search(q=artist_name, type='artist', limit=1)
        
        if not results['artists']['items']:
            return None
            
        artist = results['artists']['items'][0]
        
        # 画像がある場合は最大サイズの画像を返す
        if artist['images']:
            return artist['images'][0]['url']
            
    except Exception as e:
        logger.error(f"アーティスト画像の取得に失敗: {str(e)}")
        
    return None

def update_artist_images(profile):
    """
    プロフィールの全アーティストの画像を更新
    """
    if not profile.favorite_artists:
        return
        
    artists_data = profile.favorite_artists.get('artists', [])
    updated_artists = []
    
    for artist in artists_data:
        artist_name = artist.get('name', artist) if isinstance(artist, dict) else artist
        image_url = get_artist_image(artist_name)
        
        artist_data = {
            'name': artist_name,
            'image': image_url
        }
        updated_artists.append(artist_data)
    
    profile.favorite_artists['artists'] = updated_artists
    profile.save() 