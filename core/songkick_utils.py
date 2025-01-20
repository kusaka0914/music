import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class SongkickClient:
    BASE_URL = "https://api.songkick.com/api/3.0"
    
    def __init__(self):
        self.api_key = settings.SONGKICK_API_KEY
        
    def search_events(self, artist_name=None, location=None):
        """イベントを検索"""
        params = {
            "apikey": self.api_key,
            "per_page": 10
        }
        
        if artist_name:
            # まずアーティストIDを取得
            artist_id = self._get_artist_id(artist_name)
            if artist_id:
                return self._get_artist_events(artist_id)
        
        if location:
            params["location"] = f"geo:{location}"
            
        try:
            response = requests.get(
                f"{self.BASE_URL}/events.json",
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Songkick APIエラー: {str(e)}")
            return None
            
    def _get_artist_id(self, artist_name):
        """アーティスト名からIDを取得"""
        params = {
            "apikey": self.api_key,
            "query": artist_name
        }
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/search/artists.json",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("resultsPage", {}).get("results", {}).get("artist"):
                return data["resultsPage"]["results"]["artist"][0]["id"]
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"アーティストID取得エラー: {str(e)}")
            return None
            
    def _get_artist_events(self, artist_id):
        """アーティストの今後のイベントを取得"""
        params = {
            "apikey": self.api_key,
            "per_page": 10
        }
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/artists/{artist_id}/calendar.json",
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"アーティストイベント取得エラー: {str(e)}")
            return None 