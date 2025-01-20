import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from django.conf import settings
import logging
from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)

def get_spotify_client(user=None):
    """
    ユーザーのSpotifyクライアントを取得
    """
    try:
        if user and user.profile.spotify_connected and user.profile.spotify_refresh_token:
            logger.info(f"Spotifyクライアント取得開始: user={user.username}, refresh_token={user.profile.spotify_refresh_token[:10]}...")
            
            auth_manager = SpotifyOAuth(
                client_id=settings.SPOTIFY_CLIENT_ID,
                client_secret=settings.SPOTIFY_CLIENT_SECRET,
                redirect_uri=settings.SPOTIFY_REDIRECT_URI,
                scope='user-read-recently-played user-top-read',
                cache_handler=None
            )
            
            try:
                token_info = auth_manager.refresh_access_token(user.profile.spotify_refresh_token)
                logger.info("アクセストークンの更新に成功しました")
                spotify_client = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Spotifyクライアント取得成功")
                return spotify_client
            except Exception as token_error:
                logger.error(f"アクセストークンの更新に失敗: {str(token_error)}")
                # トークンが無効な場合はSpotify連携を解除
                user.profile.spotify_connected = False
                user.profile.spotify_refresh_token = None
                user.profile.save()
                return None
                
        logger.warning(f"Spotify連携の条件を満たしていません: user={user.username if user else None}, connected={user.profile.spotify_connected if user else None}")
        return None
    except Exception as e:
        logger.error(f"Spotifyクライアントの取得に失敗: {str(e)}")
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

def get_recently_played_tracks(spotify_client, limit=10):
    """最近再生した曲を取得"""
    try:
        logger.info("最近再生した曲の取得開始")
        results = spotify_client.current_user_recently_played(limit=limit)
        tracks = []
        for item in results['items']:
            track = item['track']
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'played_at': item['played_at'],
                'spotify_url': track['external_urls']['spotify'],
                'spotify_id': track['id']
            })
        logger.info(f"最近再生した曲を{len(tracks)}件取得しました")
        return tracks
    except Exception as e:
        logger.error(f"最近再生した曲の取得に失敗: {str(e)}")
        return []

def get_top_tracks(spotify_client, limit=10, time_range='short_term'):
    """お気に入りの曲を取得（short_term: 4週間, medium_term: 6ヶ月, long_term: 全期間）"""
    try:
        results = spotify_client.current_user_top_tracks(limit=limit, time_range=time_range)
        tracks = []
        for track in results['items']:
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'spotify_url': track['external_urls']['spotify'],
                'spotify_id': track['id']
            })
        return tracks
    except Exception as e:
        print(f"Error getting top tracks: {e}")
        return [] 