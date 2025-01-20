import requests
from django.conf import settings
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class EPlusClient:
    BASE_URL = "https://api.eplus.jp/v1"
    
    def __init__(self):
        self.api_key = settings.EPLUS_API_KEY
        
    def search_events(self, artist_name=None, prefecture=None, from_date=None):
        """イベントを検索"""
        if not from_date:
            from_date = datetime.now().strftime('%Y-%m-%d')
            
        params = {
            "apikey": self.api_key,
            "keyword": artist_name,
            "from_date": from_date,
            "limit": 10,
            "sort": "date_asc"
        }
        
        if prefecture:
            params["prefecture"] = prefecture
            
        try:
            response = requests.get(
                f"{self.BASE_URL}/events",
                params=params,
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"e+ APIエラー: {str(e)}")
            return None
            
    def get_event_detail(self, event_id):
        """イベントの詳細情報を取得"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/events/{event_id}",
                params={"apikey": self.api_key},
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"イベント詳細取得エラー: {str(e)}")
            return None 