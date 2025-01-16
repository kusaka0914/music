from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/<str:username>/', views.profile, name='profile'),
    path('post/create/', views.create_post, name='create_post'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/<int:post_id>/like/', views.like_post, name='like_post'),
    path('post/<int:post_id>/comment/', views.add_comment, name='add_comment'),
    path('story/create/', views.create_story, name='create_story'),
    path('story/<int:story_id>/view/', views.view_story, name='view_story'),
    path('story/<int:story_id>/reaction/', views.story_reaction, name='story_reaction'),
    path('search/track/', views.search_track, name='search_track'),
    path('filter-posts/', views.filter_posts, name='filter_posts'),
    path('following/posts/', views.following_posts, name='following_posts'),
    path('search/', views.search, name='search'),
    path('music-compatibility/', views.music_compatibility, name='music_compatibility'),
    path('playlist/create/', views.create_playlist, name='create_playlist'),
    path('playlist/<int:pk>/', views.playlist_detail, name='playlist_detail'),
    path('playlist/<int:pk>/edit/', views.edit_playlist, name='edit_playlist'),
    path('playlist/<int:pk>/delete/', views.delete_playlist, name='delete_playlist'),
    path('post/<int:post_pk>/add-to-playlist/<int:playlist_pk>/', views.add_to_playlist, name='add_to_playlist'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('edit-music-taste/', views.edit_music_taste, name='edit_music_taste'),
    path('spotify/connect/', views.spotify_connect, name='spotify_connect'),
    path('spotify/callback/', views.spotify_callback, name='spotify_callback'),
    path('spotify/disconnect/', views.spotify_disconnect, name='spotify_disconnect'),
    path('spotify/search-track/', views.search_track, name='search_track'),
] 