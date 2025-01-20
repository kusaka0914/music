# Spotify設定
SPOTIFY_CLIENT_ID = 'あなたのクライアントID'  # ここを実際のClient IDに置き換えてください
SPOTIFY_CLIENT_SECRET = 'あなたのクライアントシークレット'  # ここを実際のClient Secretに置き換えてください
SPOTIFY_REDIRECT_URI = 'http://localhost:8001/spotify/callback/' 

# ログインURL
LOGIN_URL = 'core:login' 

# LiveFan API設定
LIVEFAN_API_KEY = env('LIVEFAN_API_KEY', default=None) 

# Songkick API設定
SONGKICK_API_KEY = env('SONGKICK_API_KEY', default=None) 

# e+ API設定
EPLUS_API_KEY = env('EPLUS_API_KEY', default=None) 

# ぴあAPI設定
PIA_API_KEY = env('PIA_API_KEY', default=None)
PIA_CLIENT_ID = env('PIA_CLIENT_ID', default=None) 