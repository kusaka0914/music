from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('profile/<str:username>/', views.profile, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('music-taste/edit/', views.edit_music_taste, name='edit_music_taste'),
    path('logout/', views.logout_view, name='logout'),
    path('post/create/', views.create_post, name='create_post'),
    path('post/<int:pk>/', views.post_detail, name='post_detail'),
    path('post/<int:pk>/edit/', views.edit_post, name='edit_post'),
    path('post/<int:pk>/delete/', views.delete_post, name='delete_post'),
    path('post/<int:pk>/like/', views.like_post, name='like_post'),
    path('post/<int:pk>/comment/', views.add_comment, name='add_comment'),
    path('story/create/', views.create_story, name='create_story'),
    path('story/<int:pk>/', views.story_detail, name='story_detail'),
    path('story/<int:pk>/delete/', views.delete_story, name='delete_story'),
    path('story/<int:pk>/view/', views.view_story, name='view_story'),
    path('following-posts/', views.following_posts, name='following_posts'),
    path('follow/<str:username>/', views.follow_user, name='follow_user'),
    path('playlist/create/', views.create_playlist, name='create_playlist'),
    path('playlist/<int:pk>/', views.playlist_detail, name='playlist_detail'),
    path('playlist/<int:pk>/edit/', views.edit_playlist, name='edit_playlist'),
    path('playlist/<int:pk>/delete/', views.delete_playlist, name='delete_playlist'),
    path('post/<int:post_pk>/add-to-playlist/<int:playlist_pk>/', views.add_to_playlist, name='add_to_playlist'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('search/', views.search, name='search'),
    path('spotify/connect/', views.spotify_connect, name='spotify_connect'),
    path('spotify/callback/', views.spotify_callback, name='spotify_callback'),
    path('spotify/disconnect/', views.spotify_disconnect, name='spotify_disconnect'),
    path('spotify/search/', views.spotify_search, name='spotify_search'),
    path('spotify/search-track/', views.search_track, name='search_track'),
    path('spotify/search-track-for-story/', views.search_track_for_story, name='search_track_for_story'),
    path('music-compatibility/', views.music_compatibility, name='music_compatibility'),
] 