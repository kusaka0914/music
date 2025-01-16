from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('edit-music-taste/', views.edit_music_taste, name='edit_music_taste'),
    path('register/', views.register, name='register'),
    path('create-post/', views.create_post, name='create_post'),
    path('post/<int:pk>/', views.post_detail, name='post_detail'),
    path('post/<int:pk>/edit/', views.edit_post, name='edit_post'),
    path('post/<int:pk>/delete/', views.delete_post, name='delete_post'),
    path('post/<int:pk>/like/', views.like_post, name='like_post'),
    path('post/<int:pk>/comment/', views.add_comment, name='add_comment'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/<str:username>/', views.profile, name='profile'),
    path('follow/<str:username>/', views.follow_user, name='follow_user'),
    path('create-playlist/', views.create_playlist, name='create_playlist'),
    path('playlist/<int:pk>/', views.playlist_detail, name='playlist_detail'),
    path('playlist/<int:pk>/edit/', views.edit_playlist, name='edit_playlist'),
    path('playlist/<int:pk>/delete/', views.delete_playlist, name='delete_playlist'),
    path('add-to-playlist/<int:post_pk>/<int:playlist_pk>/', views.add_to_playlist, name='add_to_playlist'),
    path('notifications/', views.notifications, name='notifications'),
    path('notification/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('following-posts/', views.following_posts, name='following_posts'),
    path('search/', views.search, name='search'),
    path('music-taste/edit/', views.edit_music_taste, name='edit_music_taste'),
    path('music-compatibility/', views.music_compatibility, name='music_compatibility'),
    path('search-artists/', views.search_artists, name='search_artists'),
    path('popular-artists/', views.popular_artists, name='popular_artists'),
    path('recommended-artists/', views.recommended_artists, name='recommended_artists'),
] 