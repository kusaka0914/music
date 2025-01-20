import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class LiveFanClient:
    BASE_URL = "https://api.livefan.jp/api/v1"
    
    def __init__(self):
        self.api_key = settings.LIVEFAN_API_KEY
        
    def _make_request(self, endpoint, params=None):
        """APIリクエストを実行"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/{endpoint}",
                headers=headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"LiveFan APIエラー: {str(e)}")
            return None
            
    def search_events(self, artist_name=None, venue=None, from_date=None, to_date=None):
        """イベントを検索"""
        params = {
            "artist": artist_name,
            "venue": venue,
            "from": from_date,
            "to": to_date
        }
        return self._make_request("events/search", params)
    
    def get_artist_events(self, artist_id):
        """アーティストの今後のイベントを取得"""
        return self._make_request(f"artists/{artist_id}/events")
    
    def get_venue_events(self, venue_id):
        """会場の今後のイベントを取得"""
        return self._make_request(f"venues/{venue_id}/events") 