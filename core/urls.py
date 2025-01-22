from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/<str:username>/', views.profile, name='profile'),
    path('music-taste/edit/', views.edit_music_taste, name='edit_music_taste'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('post/create/', views.create_post, name='create_post'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/<int:post_id>/edit/', views.edit_post, name='edit_post'),
    path('post/<int:post_id>/delete/', views.delete_post, name='delete_post'),
    path('post/<int:post_id>/like/', views.like_post, name='like_post'),
    path('post/<int:post_id>/comment/', views.add_comment, name='add_comment'),
    path('story/create/', views.create_story, name='create_story'),
    path('story/<int:post_id>/', views.story_detail, name='story_detail'),
    path('story/<int:post_id>/delete/', views.delete_story, name='delete_story'),
    path('story/<int:post_id>/view/', views.view_story, name='view_story'),
    path('following-posts/', views.following_posts, name='following_posts'),
    path('follow/<str:username>/', views.follow_user, name='follow_user'),
    path('playlist/create/', views.create_playlist, name='create_playlist'),
    path('playlist/<int:pk>/', views.playlist_detail, name='playlist_detail'),
    path('playlist/<int:pk>/edit/', views.edit_playlist, name='edit_playlist'),
    path('playlist/<int:pk>/delete/', views.delete_playlist, name='delete_playlist'),
    path('post/<int:post_pk>/add-to-playlist/<int:playlist_pk>/', views.add_to_playlist, name='add_to_playlist'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/count/', views.get_unread_notification_count, name='get_unread_notification_count'),
    path('notifications/<int:notification_id>/redirect/', views.notification_redirect, name='notification_redirect'),
    path('search/', views.search, name='search'),
    path('spotify/connect/', views.spotify_connect, name='spotify_connect'),
    path('spotify/callback/', views.spotify_callback, name='spotify_callback'),
    path('spotify/disconnect/', views.spotify_disconnect, name='spotify_disconnect'),
    path('spotify/search/', views.spotify_search, name='spotify_search'),
    path('spotify/search-track/', views.search_track, name='search_track'),
    path('spotify/search-track-for-story/', views.search_track_for_story, name='search_track_for_story'),
    path('music-compatibility/', views.music_compatibility, name='music_compatibility'),
    path('playlist/<int:playlist_id>/like/', views.like_playlist, name='like_playlist'),
    path('post/<int:post_id>/like/', views.like_post, name='like_post'),
    path('post/<int:post_id>/comment/', views.add_comment, name='add_comment'),
    path('filter_posts/', views.filter_posts, name='filter_posts'),
    path('api/artist-analysis/', views.get_artist_analysis, name='artist_analysis'),
    path('api/mood-recommendations/<str:mood_id>/', views.get_mood_recommendations, name='mood_recommendations'),
    path('create-story-modal/', views.create_story_modal, name='create_story_modal'),
    
    # メッセージ機能のURL
    path('messages/', views.messages_view, name='messages'),
    path('messages/<int:conversation_id>/', views.conversation_detail, name='conversation_detail'),
    path('messages/new/<str:username>/', views.new_conversation, name='new_conversation'),
    path('api/messages/send/', views.send_message, name='send_message'),
    path('api/messages/unread-count/', views.get_unread_messages_count, name='get_unread_messages_count'),
    path('api/toggle-follow/<str:username>/', views.toggle_follow, name='toggle_follow'),
    
    # 通知関連のURL
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:notification_id>/redirect/', views.notification_redirect, name='notification_redirect'),
    path('api/notifications/unread-count/', views.get_unread_notification_count, name='get_unread_notification_count'),
    path('api/posts/<int:post_id>/likes/', views.get_post_likes, name='get_post_likes'),
    path('spotify/search/<str:search_type>/', views.spotify_search, name='spotify_search'),
    path('api/posts/<int:post_id>/comments/', views.get_post_comments, name='get_post_comments'),

    path('popular-artists/', views.popular_artists, name='popular_artists'),
    path('recommended-artists/', views.recommended_artists, name='recommended_artists'),
    path('edit-music-taste/', views.edit_music_taste, name='edit_music_taste'),
    path('search-artists/', views.search_artists, name='search_artists'),
    
] 
