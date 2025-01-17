from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Q, Count, Case, When, F
from django.contrib import messages
from django.contrib.auth.models import User
from django.conf import settings
from .models import (
    MusicPost, MusicStory, Comment, Profile, MusicTaste,
    Playlist, Notification, PlaylistComment, Music, PlaylistMusic
)
from .forms import MusicPostForm, MusicStoryForm, CommentForm, MusicTasteForm, ProfileEditForm, MusicStoryForm,UserLoginForm,UserRegisterForm,PlaylistForm
from .spotify_utils import get_spotify_client
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import json
import logging
from django.contrib.auth import login, logout
from django.core.paginator import Paginator

logger = logging.getLogger(__name__)


def home(request):
    # 通常の投稿を取得（ユーザー名が存在するものだけ）
    posts = MusicPost.objects.select_related('user', 'user__profile').prefetch_related('likes', 'comments').filter(
        user__isnull=False,
        user__username__isnull=False
    ).order_by('-created_at')
    
    # アクティブなストーリーを取得（24時間以内）
    active_stories = MusicStory.objects.filter(
        expires_at__gt=timezone.now(),
        user__isnull=False,
        user__username__isnull=False
    ).select_related('user', 'user__profile').order_by('-created_at')
    
    # ストーリーをユーザーごとにグループ化
    stories_by_user = {}
    for story in active_stories:
        if story.user and story.user.username:  # ユーザーとユーザー名の存在を確認
            if story.user not in stories_by_user:
                stories_by_user[story.user] = {
                    'user': {
                        'username': story.user.username,
                        'avatar_url': story.user.profile.avatar.url if story.user.profile.avatar else '/static/images/default-avatar.svg',
                    },
                    'stories': [],
                    'has_unviewed': False
                }
            
            story_info = {
                'id': story.id,
                'track_name': story.track_name or '',
                'artist_name': story.artist_name or '',
                'album_image_url': story.album_image_url or '',
                'mood': story.mood or '',
                'mood_emoji': story.mood_emoji or '',
                'comment': story.comment or '',
                'created_at': story.created_at.isoformat(),
                'viewed': request.user.is_authenticated and request.user in story.viewers.all()
            }
            stories_by_user[story.user]['stories'].append(story_info)
            
            if request.user.is_authenticated and not story_info['viewed']:
                stories_by_user[story.user]['has_unviewed'] = True
    
    # stories_by_userをリスト形式に変換
    stories_by_user_list = [data for data in stories_by_user.values() if data['user']['username']]
    
    # トレンド投稿を取得（過去7日間で最もエンゲージメントの高い投稿）
    week_ago = timezone.now() - timezone.timedelta(days=7)
    trending_posts = MusicPost.objects.filter(
        created_at__gte=week_ago,
        user__isnull=False  # ユーザーが存在するものだけを取得
    ).annotate(
        engagement=Count('likes') + Count('comments')
    ).order_by('-engagement')[:5]
    
    # おすすめユーザーを取得
    recommended_users = []
    if request.user.is_authenticated:
        # 自分以外のユーザーを取得
        other_users = Profile.objects.exclude(
            user=request.user
        ).select_related('user').filter(
            user__isnull=False  # ユーザーが存在するものだけを取得
        )[:5]
        
        for profile in other_users:
            if profile.user and profile.user.username:  # ユーザーとユーザー名が存在する場合のみ処理
                compatibility = calculate_music_compatibility(request.user.profile, profile)
                recommended_users.append({
                    'user': profile.user,
                    'compatibility_score': int(compatibility)
                })
        
        # 互換性スコアで降順ソート
        recommended_users.sort(key=lambda x: x['compatibility_score'], reverse=True)
    
    # おすすめのプレイリストを取得
    recommended_playlists = get_recommended_playlists()
    
    context = {
        'posts': posts,
        'stories_by_user': stories_by_user_list,
        'trending_posts': trending_posts,
        'recommended_users': recommended_users[:3],  # 上位3人のみ表示
        'recommended_playlists': recommended_playlists  # おすすめのプレイリストを追加
    }
    
    return render(request, 'core/home.html', context)

def calculate_music_compatibility(user_profile1, user_profile2):
    """
    2つのユーザープロフィール間の音楽の相性を計算する
    """
    score = 0
    
    # 好きなジャンルの比較
    if user_profile1.favorite_genres and user_profile2.favorite_genres:
        user1_genres = set(user_profile1.favorite_genres)
        user2_genres = set(user_profile2.favorite_genres)
        common_genres = user1_genres.intersection(user2_genres)
        score += len(common_genres) * 20  # 共通ジャンルごとに20ポイント

    # 好きなアーティストの比較
    if user_profile1.favorite_artists and user_profile2.favorite_artists:
        user1_artists = set(user_profile1.favorite_artists)
        user2_artists = set(user_profile2.favorite_artists)
        common_artists = user1_artists.intersection(user2_artists)
        score += len(common_artists) * 30  # 共通アーティストごとに30ポイント

    # Spotifyの再生履歴の比較（もし利用可能な場合）
    if user_profile1.spotify_connected and user_profile2.spotify_connected:
        try:
            # Spotifyクライアントの取得
            client1 = get_spotify_client(user_profile1.user)
            client2 = get_spotify_client(user_profile2.user)
            
            if client1 and client2:
                # 最近再生した曲のアーティストを比較
                recent1 = {track['track']['artists'][0]['name'] for track in client1.current_user_recently_played(limit=20)['items']}
                recent2 = {track['track']['artists'][0]['name'] for track in client2.current_user_recently_played(limit=20)['items']}
                common_recent = recent1.intersection(recent2)
                score += len(common_recent) * 10  # 共通の最近聴いたアーティストごとに10ポイント
        
        except Exception as e:
            logger.error(f"Spotify再生履歴の比較中にエラー: {str(e)}")

    # スコアを0-100の範囲に正規化
    normalized_score = min(100, score)
    
    return normalized_score

def login_view(request):
    if request.method == 'POST':
        form = UserLoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, 'ログインしました。')
            return redirect('core:home')
    else:
        form = UserLoginForm()
    return render(request, 'core/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.success(request, 'ログアウトしました。')
    return redirect('core:home')

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                # プロフィールが存在しない場合のみ作成
                Profile.objects.get_or_create(user=user)
                messages.success(request, '登録が完了しました。ログインしてください。')
                return redirect('core:login')
            except Exception as e:
                messages.error(request, '登録中にエラーが発生しました。')
                return redirect('core:register')
    else:
        form = UserRegisterForm()
    return render(request, 'core/register.html', {'form': form})

@login_required
def create_post(request):
    if request.method == 'POST':
        try:
            # フォームデータの取得
            spotify_track_id = request.POST.get('spotify_track_id')
            title = request.POST.get('title')
            artist = request.POST.get('artist')
            description = request.POST.get('description')
            scene = request.POST.get('scene')
            album_image = request.POST.get('album_image')

            # バリデーション
            if not all([spotify_track_id, title, artist, scene]):
                messages.error(request, '必須項目が入力されていません。')
                return redirect('core:create_post')

            # 投稿の作成
            post = MusicPost.objects.create(
                user=request.user,
                title=title,
                artist=artist,
                spotify_link=spotify_track_id,  # トラックIDのみを保存
                description=description,
                mood=scene,
                image=album_image
            )

            messages.success(request, '投稿が作成されました！')
            return redirect('core:post_detail', post_id=post.id)

        except Exception as e:
            logger.error(f"投稿作成中にエラーが発生: {str(e)}")
            messages.error(request, '投稿の作成中にエラーが発生しました。')
            return redirect('core:create_post')

    return render(request, 'core/post_form.html')

@login_required
def post_detail(request, post_id):
    post = get_object_or_404(MusicPost, id=post_id)
    comments = post.comments.select_related('user').order_by('-created_at')
    
    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.user = request.user
            comment.post = post
            comment.save()
            return redirect('core:post_detail', post_id=post.id)
    else:
        comment_form = CommentForm()
    
    similar_posts = MusicPost.objects.filter(
        Q(artist=post.artist) |
        Q(tags__overlap=post.tags) |
        Q(mood=post.mood)
    ).exclude(id=post.id)[:5]
    
    context = {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'similar_posts': similar_posts,
    }
    
    return render(request, 'core/post_detail.html', context)

@login_required
def edit_post(request, pk):
    post = get_object_or_404(MusicPost, pk=pk, user=request.user)
    if request.method == 'POST':
        form = MusicPostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, '投稿が更新されました。')
            return redirect('core:post_detail', pk=post.pk)
    else:
        form = MusicPostForm(instance=post)
    return render(request, 'core/post_form.html', {'form': form, 'title': '投稿を編集'})

@login_required
def delete_post(request, pk):
    post = get_object_or_404(MusicPost, pk=pk, user=request.user)
    if request.method == 'POST':
        post.delete()
        messages.success(request, '投稿が削除されました。')
        return redirect('core:home')
    return render(request, 'core/post_confirm_delete.html', {'post': post})

@login_required
def like_post(request, post_id):
    """投稿のいいね処理"""
    try:
        post = get_object_or_404(MusicPost, id=post_id)
        
        if request.user in post.likes.all():
            post.likes.remove(request.user)
            liked = False
        else:
            post.likes.add(request.user)
            liked = True
        
        return JsonResponse({
            'status': 'success',
            'liked': liked,
            'like_count': post.likes.count()
        })
    except Exception as e:
        logger.error(f"いいね処理中にエラーが発生: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'いいねの処理中にエラーが発生しました'
        }, status=500)

@login_required
def add_comment(request, pk):
    post = get_object_or_404(MusicPost, pk=pk)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.post = post
            comment.save()
            if request.user != post.user:
                Notification.objects.create(
                    recipient=post.user,
                    sender=request.user,
                    notification_type='comment',
                    post=post,
                    comment=comment
                )
            messages.success(request, 'コメントが投稿されました。')
            return redirect('core:post_detail', pk=post.pk)
    return redirect('core:post_detail', pk=post.pk)

def profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    posts = MusicPost.objects.filter(user=profile_user).order_by('-created_at')
    
    # MusicTasteを取得または作成
    music_taste, created = MusicTaste.objects.get_or_create(user=profile_user)
    
    # Spotifyのデータを取得
    recently_played = []
    top_tracks = []
    if profile_user.profile.spotify_connected:  # Spotifyと連携している場合
        logger.info(f"Spotifyデータ取得開始: user={profile_user.username}")
        try:
            spotify_client = get_spotify_client(profile_user)
            if spotify_client:
                logger.info("Spotifyクライアント取得成功")
                recently_played = get_recently_played_tracks(spotify_client)
                top_tracks = get_top_tracks(spotify_client)
                logger.info(f"Spotifyデータ取得完了: recently_played={len(recently_played)}件, top_tracks={len(top_tracks)}件")
            else:
                logger.warning("Spotifyクライアントの取得に失敗")
        except Exception as e:
            logger.error(f"Spotifyデータの取得に失敗: {str(e)}")
    else:
        logger.info(f"Spotify未連携: user={profile_user.username}")
    
    # バッジを取得
    badges = profile_user.profile.get_achievement_badges()
    
    # おすすめユーザーを取得（プロフィールの所有者の場合のみ）
    recommended_users = []
    if request.user == profile_user:
        recommended_users = profile_user.profile.get_recommended_users()
    
    # 音楽の相性スコアと共通の趣味を計算
    compatibility_score = None
    common_interests = None
    
    if request.user.is_authenticated and request.user != profile_user:
        compatibility_score = request.user.profile.get_music_compatibility_score(profile_user)
        common_interests = request.user.profile.get_common_music_interests(profile_user)
    
    return render(request, 'core/profile.html', {
        'profile_user': profile_user,
        'posts': posts,
        'recently_played': recently_played,
        'top_tracks': top_tracks,
        'badges': badges,
        'recommended_users': recommended_users,
        'compatibility_score': compatibility_score,
        'common_interests': common_interests,
    })

@login_required
def follow_user(request, username):
    user_to_follow = get_object_or_404(User, username=username)
    if request.user != user_to_follow:
        if request.user in user_to_follow.profile.followers.all():
            user_to_follow.profile.followers.remove(request.user)
            is_following = False
        else:
            user_to_follow.profile.followers.add(request.user)
            is_following = True
            Notification.objects.create(
                recipient=user_to_follow,
                sender=request.user,
                notification_type='follow'
            )
        return JsonResponse({
            'is_following': is_following,
            'followers_count': user_to_follow.profile.followers.count()
        })
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def create_playlist(request):
    if request.method == 'POST':
        try:
            title = request.POST.get('title')
            description = request.POST.get('description')
            is_public = request.POST.get('is_public') == 'on'
            track_ids_str = request.POST.get('track_ids', '[]')
            
            try:
                track_ids = json.loads(track_ids_str)
            except json.JSONDecodeError:
                logger.error(f"track_idsのJSONデコードに失敗: {track_ids_str}")
                track_ids = []

            if not title:
                messages.error(request, 'プレイリスト名を入力してください。')
                return redirect('core:create_playlist')

            if not track_ids:
                messages.error(request, '少なくとも1曲は追加してください。')
                return redirect('core:create_playlist')

            # プレイリストの作成
            playlist = Playlist.objects.create(
                user=request.user,
                title=title,
                description=description,
                is_public=is_public
            )

            # 選択された曲をプレイリストに追加
            spotify = get_spotify_client()
            
            for order, track_id in enumerate(track_ids):
                try:
                    # 既存の楽曲を探す
                    music = Music.objects.filter(spotify_id=track_id).first()
                    if not music:
                        # Spotifyから曲の情報を取得して新しい楽曲を作成
                        track_info = spotify.track(track_id)
                        music = Music.objects.create(
                            title=track_info['name'],
                            artist=track_info['artists'][0]['name'],
                            spotify_id=track_id,
                            album_art=track_info['album']['images'][0]['url'] if track_info['album']['images'] else None,
                            preview_url=track_info.get('preview_url'),
                            duration_ms=track_info.get('duration_ms', 0)
                        )

                    # プレイリストと楽曲を関連付け
                    PlaylistMusic.objects.create(
                        playlist=playlist,
                        music=music,
                        order=order
                    )

                except Exception as e:
                    logger.error(f"楽曲の追加中にエラー: {str(e)}")
                    continue

            messages.success(request, 'プレイリストを作成しました。')
            return redirect('core:playlist_detail', pk=playlist.pk)

        except Exception as e:
            logger.error(f"プレイリスト作成エラー: {str(e)}")
            messages.error(request, 'プレイリストの作成中にエラーが発生しました。')
            return redirect('core:create_playlist')

    return render(request, 'core/create_playlist.html')

def playlist_detail(request, pk):
    playlist = get_object_or_404(Playlist, pk=pk)
    
    # プレイリストの曲を取得（順序を保持）
    playlist_tracks = PlaylistMusic.objects.filter(
        playlist=playlist
    ).select_related('music').order_by('order')
    
    # おすすめプレイリストを取得
    recommended_playlists = Playlist.objects.filter(
        is_public=True
    ).exclude(
        pk=pk
    ).annotate(
        engagement=Count('likes') + Count('playlist_comments')
    ).order_by('-engagement')[:5]

    # Spotifyから人気の曲を取得
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # 日本の人気曲を検索（より多くの曲を取得してからランダムに選択）
        results = spotify.search(
            q='year:2024',
            type='track',
            market='JP',
            limit=20  # より多くの曲を取得
        )
        
        import random
        trending_tracks = []
        if 'tracks' in results and 'items' in results['tracks']:
            # ランダムに5曲を選択
            tracks = random.sample(results['tracks']['items'], min(5, len(results['tracks']['items'])))
            for track in tracks:
                track_data = {
                    'title': track['name'],
                    'artist': track['artists'][0]['name'] if track['artists'] else 'Unknown Artist',
                    'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'spotify_id': track['id']
                }
                trending_tracks.append(track_data)
            
    except Exception as e:
        logger.error(f"Spotifyからの人気曲取得エラー: {str(e)}")
        trending_tracks = []

    context = {
        'playlist': playlist,
        'playlist_tracks': playlist_tracks,
        'recommended_playlists': recommended_playlists,
        'trending_tracks': trending_tracks,
    }
    
    return render(request, 'core/playlist_detail.html', context)

@login_required
def edit_playlist(request, pk):
    playlist = get_object_or_404(Playlist, pk=pk, user=request.user)
    if request.method == 'POST':
        form = PlaylistForm(request.POST, instance=playlist)
        if form.is_valid():
            form.save()
            messages.success(request, 'プレイリストが更新されました。')
            return redirect('core:playlist_detail', pk=playlist.pk)
    else:
        form = PlaylistForm(instance=playlist)
    return render(request, 'core/playlist_form.html', {'form': form, 'title': 'プレイリストを編集'})

@login_required
def delete_playlist(request, pk):
    playlist = get_object_or_404(Playlist, pk=pk, user=request.user)
    if request.method == 'POST':
        playlist.delete()
        messages.success(request, 'プレイリストが削除されました。')
        return redirect('core:home')
    return render(request, 'core/playlist_confirm_delete.html', {'playlist': playlist})

@login_required
def add_to_playlist(request, post_pk, playlist_pk):
    post = get_object_or_404(MusicPost, pk=post_pk)
    playlist = get_object_or_404(Playlist, pk=playlist_pk, user=request.user)
    if post in playlist.posts.all():
        playlist.posts.remove(post)
        messages.success(request, f'「{post.title}」がプレイリストから削除されました。')
    else:
        playlist.posts.add(post)
        messages.success(request, f'「{post.title}」がプレイリストに追加されました。')
    return redirect('core:post_detail', pk=post_pk)

@login_required
def notifications(request):
    notifications = request.user.notifications_received.all().order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()
    return render(request, 'core/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count
    })

@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save()
    return redirect('core:notifications')

@login_required
def following_posts(request):
    following_users = request.user.profile.following.all().values_list('user', flat=True)
    posts = MusicPost.objects.filter(user__in=following_users).select_related('user', 'user__profile').prefetch_related('likes', 'comments').order_by('-created_at')
    return render(request, 'core/following_posts.html', {'posts': posts})

def search(request):
    query = request.GET.get('q', '')
    posts = []
    if query:
        posts = MusicPost.objects.filter(
            Q(title__icontains=query) |
            Q(artist__icontains=query) |
            Q(description__icontains=query) |
            Q(user__username__icontains=query)
        ).order_by('-created_at')
    return render(request, 'core/search.html', {
        'query': query,
        'posts': posts
    })

@login_required
def profile_edit(request):
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user.profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'プロフィールを更新しました。')
            return redirect('core:profile', username=request.user.username)
    else:
        form = ProfileEditForm(instance=request.user.profile, user=request.user)
    
    return render(request, 'core/profile_edit.html', {
        'form': form
    })

@login_required
def edit_music_taste(request):
    music_taste, created = MusicTaste.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # AJAXリクエストの場合
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                data = json.loads(request.body)
                action = data.get('action')
                
                if action == 'add_artist':
                    artist_name = data.get('artist')
                    artist_image = data.get('image')
                    artist_id = data.get('id')
                    
                    # favorite_artistsが未初期化の場合は空のリストを作成
                    if not music_taste.favorite_artists:
                        music_taste.favorite_artists = []
                    
                    # アーティストデータを作成
                    artist_data = {
                        'name': artist_name,
                        'image': artist_image,
                        'id': artist_id
                    }
                    
                    # IDで重複チェック
                    if not any(artist.get('id') == artist_id for artist in music_taste.favorite_artists):
                        music_taste.favorite_artists.append(artist_data)
                        music_taste.save()
                    
                    return JsonResponse({
                        'status': 'success',
                        'message': 'アーティストを追加しました'
                    })
                
                elif action == 'update_genres':
                    genres = data.get('genres', [])
                    music_taste.genres = genres
                    music_taste.save()
                    return JsonResponse({'status': 'success'})
                
                elif action == 'update_moods':
                    moods = data.get('moods', [])
                    music_taste.moods = moods
                    music_taste.save()
                    return JsonResponse({'status': 'success'})
                
                return JsonResponse({'status': 'error', 'message': '不明なアクション'})
            
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': '無効なJSONデータ'}, status=400)
            except Exception as e:
                logger.error(f"音楽の好み更新中にエラー: {str(e)}")
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        
        # 通常のフォーム送信の場合
        else:
            form = MusicTasteForm(request.POST, instance=music_taste)
            if form.is_valid():
                form.save()
                messages.success(request, '音楽の好みを更新しました。')
                return redirect('core:profile', username=request.user.username)
    else:
        form = MusicTasteForm(instance=music_taste)
    
    # 利用可能なジャンルとムードのリスト
    available_genres = [
        'j-pop', 'j-rock', 'anime', 'pop', 'rock', 'hip-hop', 'r&b', 'jazz',
        'classical', 'electronic', 'dance', 'alternative', 'indie', 'metal',
        'folk', 'blues', 'reggae', 'soul', 'punk', 'country'
    ]
    
    available_moods = [
        'morning', 'night', 'rainy', 'workout', 'study', 'party',
        'relax', 'sad', 'happy', 'energetic', 'romantic', 'focus'
    ]
    
    # 現在の選択状態を取得
    current_genres = music_taste.genres if music_taste.genres else []
    current_moods = music_taste.moods if music_taste.moods else []
    current_artists = music_taste.favorite_artists if music_taste.favorite_artists else []
    
    # 人気のアーティストを取得
    try:
        logger.info("人気アーティストの取得を開始")
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # J-POPアーティストの検索
        results = spotify.search(q='genre:j-pop year:2024', type='artist', market='JP', limit=10)
        popular_artists = []
        
        for artist in results['artists']['items']:
            artist_data = {
                'name': artist['name'],
                'id': artist['id'],
                'image': artist['images'][0]['url'] if artist['images'] else None,
                'genres': artist['genres'][:3] if artist['genres'] else []
            }
            popular_artists.append(artist_data)
            logger.info(f"アーティスト取得: {artist_data['name']}")
        
        logger.info(f"人気アーティスト取得完了: {len(popular_artists)}件")
    except Exception as e:
        logger.error(f"人気アーティストの取得に失敗: {str(e)}")
        popular_artists = []
    
    context = {
        'form': form,
        'available_genres': available_genres,
        'available_moods': available_moods,
        'current_genres': current_genres,
        'current_moods': current_moods,
        'current_artists': current_artists,
        'popular_artists': popular_artists
    }
    
    return render(request, 'core/edit_music_taste.html', context)

def search_artists(request):
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'artists': []})
    
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        results = spotify.search(q=query, type='artist', limit=5)
        artists = [{
            'name': artist['name'],
            'id': artist['id'],
            'image': artist['images'][0]['url'] if artist['images'] else None
        } for artist in results['artists']['items']]
        
        return JsonResponse({'artists': artists})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def music_compatibility(request):
    # 自分のmusic_tasteを取得または作成
    my_music_taste, _ = MusicTaste.objects.get_or_create(user=request.user)
    
    # 自分以外のユーザーを取得
    other_users = User.objects.exclude(id=request.user.id)
    
    # 音楽の相性を計算
    compatibility_scores = []
    for other_user in other_users:
        # 他のユーザーのmusic_tasteを取得または作成
        other_music_taste, _ = MusicTaste.objects.get_or_create(user=other_user)
        
        score = request.user.profile.get_music_compatibility(other_user.profile)
        compatibility_scores.append({
            'user': other_user,
            'score': score,
            'common_genres': set(my_music_taste.top_genres.keys()) & 
                           set(other_music_taste.top_genres.keys()),
            'common_moods': set(my_music_taste.top_moods.keys()) & 
                           set(other_music_taste.top_moods.keys()),
        })
    
    # スコアの高い順にソート
    compatibility_scores.sort(key=lambda x: x['score'], reverse=True)
    
    return render(request, 'core/music_compatibility.html', {
        'compatibility_scores': compatibility_scores[:10]  # 上位10人を表示
    })

def search_artists(request):
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'artists': []})
    
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        results = spotify.search(q=query, type='artist', limit=5)
        artists = [{
            'name': artist['name'],
            'id': artist['id'],
            'image': artist['images'][0]['url'] if artist['images'] else None
        } for artist in results['artists']['items']]
        
        return JsonResponse({'artists': artists})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def popular_artists(request):
    """人気のアーティストを取得するエンドポイント"""
    try:
        page = int(request.GET.get('page', 1))
        per_page = 10
        offset = (page - 1) * per_page
        
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # 日本の人気アーティストを取得（オフセットを使用して新しいアーティストを取得）
        results = spotify.search(
            q='genre:j-pop', 
            type='artist', 
            market='JP', 
            limit=per_page,
            offset=offset
        )
        
        artists = [{
            'name': artist['name'],
            'id': artist['id'],
            'image': artist['images'][0]['url'] if artist['images'] else None,
            'popularity': artist['popularity']
        } for artist in results['artists']['items']]
        
        # 人気度でソート
        artists.sort(key=lambda x: x['popularity'], reverse=True)
        
        return JsonResponse({
            'artists': artists,
            'has_more': len(artists) == per_page  # 取得件数が per_page と同じなら、まだデータがある
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def recommended_artists(request):
    """ユーザーにおすすめのアーティストを取得するエンドポイント"""
    try:
        page = int(request.GET.get('page', 1))
        per_page = 10
        offset = (page - 1) * per_page
        
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # ユーザーの好みのジャンルを取得
        user_genres = list(request.user.music_taste.top_genres.keys()) if hasattr(request.user, 'music_taste') else []
        
        if user_genres:
            # ユーザーのジャンルに基づいて検索
            genre = user_genres[offset % len(user_genres)]  # ジャンルを循環させる
            results = spotify.search(
                q=f'genre:{genre}', 
                type='artist', 
                limit=per_page,
                offset=offset
            )
        else:
            # ジャンルがない場合は一般的な人気アーティストを検索
            results = spotify.search(
                q='year:2024', 
                type='artist', 
                limit=per_page,
                offset=offset
            )
        
        artists = [{
            'name': artist['name'],
            'id': artist['id'],
            'image': artist['images'][0]['url'] if artist['images'] else None
        } for artist in results['artists']['items']]
        
        return JsonResponse({
            'artists': artists,
            'has_more': len(artists) == per_page  # 取得件数が per_page と同じなら、まだデータがある
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def spotify_connect(request):
    """Spotifyとの連携を開始"""
    sp_oauth = SpotifyOAuth(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        scope='user-read-recently-played user-top-read'
    )
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@login_required
def spotify_callback(request):
    """Spotifyからのコールバックを処理"""
    code = request.GET.get('code')
    if not code:
        messages.error(request, 'Spotify連携に失敗しました。認証コードが見つかりません。')
        return redirect('core:profile', username=request.user.username)

    try:
        logger.info(f"Spotifyコールバック処理開始: user={request.user.username}")
        sp_oauth = SpotifyOAuth(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET,
            redirect_uri=settings.SPOTIFY_REDIRECT_URI,
            scope='user-read-recently-played user-top-read'
        )
        
        # アクセストークンを取得
        token_info = sp_oauth.get_access_token(code, check_cache=False)
        if not token_info or 'refresh_token' not in token_info:
            logger.error("リフレッシュトークンの取得に失敗しました")
            messages.error(request, 'Spotify連携に失敗しました。リフレッシュトークンを取得できませんでした。')
            return redirect('core:profile', username=request.user.username)
            
        # リフレッシュトークンを保存
        request.user.profile.spotify_refresh_token = token_info['refresh_token']
        request.user.profile.spotify_connected = True
        request.user.profile.save()
        
        logger.info(f"Spotify連携成功: user={request.user.username}")
        messages.success(request, 'Spotifyと連携しました！')
        
    except Exception as e:
        logger.error(f"Spotify連携処理でエラーが発生: {str(e)}")
        messages.error(request, f'Spotify連携に失敗しました: {str(e)}')
    
    return redirect('core:profile', username=request.user.username)

@login_required
def spotify_disconnect(request):
    """Spotifyとの連携を解除"""
    request.user.profile.spotify_refresh_token = None
    request.user.profile.spotify_connected = False
    request.user.profile.save()
    messages.success(request, 'Spotifyとの連携を解除しました。')
    return redirect('core:profile', username=request.user.username)

@login_required
def filter_posts(request):
    """投稿のフィルタリング処理"""
    filter_type = request.GET.get('filter', 'all')
    
    try:
        if filter_type == 'following':
            # フォローしているユーザーの投稿を取得
            following_users = request.user.profile.following.all()
            posts = MusicPost.objects.filter(user__in=following_users)
        elif filter_type == 'popular':
            # いいねの多い順に投稿を取得（過去7日間）
            seven_days_ago = timezone.now() - timezone.timedelta(days=7)
            posts = MusicPost.objects.annotate(
                like_count=Count('likes')
            ).filter(
                created_at__gte=seven_days_ago
            ).order_by('-like_count', '-created_at')
        else:  # all
            # すべての投稿を取得（新しい順）
            posts = MusicPost.objects.all().order_by('-created_at')

        # 投稿を10件ずつ表示
        paginator = Paginator(posts, 10)
        page = request.GET.get('page')
        posts = paginator.get_page(page)

        html = render_to_string('core/includes/post_list.html', {
            'posts': posts,
            'user': request.user
        }, request=request)

        return JsonResponse({
            'status': 'success',
            'html': html
        })

    except Exception as e:
        logger.error(f"フィルタリング中にエラーが発生: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'フィルタリングに失敗しました'
        }, status=500)

@login_required
def create_story(request):
    """ストーリー作成エンドポイント"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info(f"ストーリー作成リクエスト: {data}")  # デバッグログ
            
            # 必須フィールドの確認
            if not data.get('spotify_track_id'):
                return JsonResponse({'status': 'error', 'message': '曲の選択は必須です'}, status=400)
            if not data.get('mood'):
                return JsonResponse({'status': 'error', 'message': '気分の選択は必須です'}, status=400)
            
            # Spotifyから曲の情報を取得
            spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
                client_id=settings.SPOTIFY_CLIENT_ID,
                client_secret=settings.SPOTIFY_CLIENT_SECRET
            ))
            track_info = spotify.track(data['spotify_track_id'])
            
            # 気分に応じたテキストを設定
            mood_text = {
                'happy': 'ハッピー',
                'chill': 'リラックス',
                'energetic': 'エネルギッシュ',
                'sad': 'メランコリー',
                'love': 'ラブ'
            }.get(data['mood'], '')
            
            # ストーリーの作成
            story = MusicStory.objects.create(
                user=request.user,
                spotify_track_id=data['spotify_track_id'],
                mood=data['mood'],
                mood_emoji=mood_text,
                comment=data.get('comment', ''),
                expires_at=timezone.now() + timezone.timedelta(hours=24)
            )
            
            logger.info(f"ストーリー作成成功: id={story.id}")  # デバッグログ
            return JsonResponse({'status': 'success', 'story_id': story.id})
            
        except json.JSONDecodeError:
            logger.error("JSONデコードエラー")
            return JsonResponse({'status': 'error', 'message': '無効なJSONデータです'}, status=400)
        except Exception as e:
            logger.error(f"ストーリー作成エラー: {str(e)}")
            return JsonResponse({'status': 'error', 'message': 'ストーリーの作成中にエラーが発生しました'}, status=500)
    
    return JsonResponse({'status': 'error', 'message': '無効なリクエストです'}, status=400)

@login_required
def story_reaction(request, story_id):
    if request.method == 'POST':
        story = get_object_or_404(MusicStory, id=story_id)
        data = json.loads(request.body)
        emoji = data.get('emoji')
        
        if emoji:
            reactions = story.quick_reactions
            reactions[emoji] = reactions.get(emoji, 0) + 1
            story.quick_reactions = reactions
            story.save()
            
            return JsonResponse({
                'status': 'success',
                'reactions': story.quick_reactions
            })
    
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def view_story(request, story_id):
    story = get_object_or_404(MusicStory, id=story_id)
    if request.user not in story.viewers.all():
        story.viewers.add(request.user)
    return JsonResponse({'status': 'success'})

@login_required
def search_track(request):
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'tracks': []})
    
    try:
        spotify = get_spotify_client(request.user)
        if not spotify:
            return JsonResponse({'error': 'Spotifyクライアントの取得に失敗しました。'}, status=400)
        
        results = spotify.search(q=query, type='track', limit=5)
        tracks = results['tracks']['items']
        
        formatted_tracks = []
        for track in tracks:
            track_data = {
                'id': track['id'],
                'title': track['name'],
                'artist': track['artists'][0]['name'],
                'imageUrl': track['album']['images'][0]['url'] if track['album']['images'] else '',
            }
            formatted_tracks.append(track_data)
        
        return JsonResponse({'tracks': formatted_tracks})
    
    except Exception as e:
        logger.error(f"楽曲検索中にエラーが発生: {str(e)}")
        return JsonResponse({'error': '楽曲の検索中にエラーが発生しました。'}, status=500)

def get_recently_played_tracks(spotify_client):
    """
    ユーザーの最近再生した曲を取得する
    """
    try:
        results = spotify_client.current_user_recently_played(limit=10)
        tracks = []
        for item in results['items']:
            track = item['track']
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'spotify_url': track['external_urls']['spotify'],
                'played_at': item['played_at']
            })
        return tracks
    except Exception as e:
        logger.error(f"最近再生した曲の取得に失敗: {str(e)}")
        return []

def get_top_tracks(spotify_client):
    """
    ユーザーのトップトラックを取得する
    """
    try:
        results = spotify_client.current_user_top_tracks(limit=10, time_range='short_term')
        tracks = []
        for track in results['items']:
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'spotify_url': track['external_urls']['spotify']
            })
        return tracks
    except Exception as e:
        logger.error(f"トップトラックの取得に失敗: {str(e)}")
        return []

@login_required
def search_track_for_story(request):
    """ストーリー作成用の曲検索エンドポイント"""
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'tracks': []})
    
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        results = spotify.search(q=query, type='track', limit=5)
        tracks = results['tracks']['items']
        
        formatted_tracks = []
        for track in tracks:
            track_data = {
                'id': track['id'],
                'title': track['name'],
                'artist': track['artists'][0]['name'],
                'imageUrl': track['album']['images'][0]['url'] if track['album']['images'] else '',
            }
            formatted_tracks.append(track_data)
        
        return JsonResponse({'tracks': formatted_tracks})
    
    except Exception as e:
        logger.error(f"楽曲検索中にエラーが発生: {str(e)}")
        return JsonResponse({'error': '楽曲の検索中にエラーが発生しました。'}, status=500)

@login_required
def get_story_details(request, story_id):
    """ストーリーの詳細情報を取得するエンドポイント"""
    try:
        story = get_object_or_404(MusicStory, id=story_id)
        
        # ストーリーを閲覧済みとしてマーク
        if request.user not in story.viewers.all():
            story.viewers.add(request.user)
        
        # 前後のストーリーを取得
        user_stories = MusicStory.objects.filter(
            user=story.user,
            expires_at__gt=timezone.now()
        ).order_by('created_at')
        
        story_ids = list(user_stories.values_list('id', flat=True))
        current_index = story_ids.index(story.id)
        
        prev_story_id = story_ids[current_index - 1] if current_index > 0 else None
        next_story_id = story_ids[current_index + 1] if current_index < len(story_ids) - 1 else None
        
        # レスポンスデータの作成
        data = {
            'id': story.id,
            'user': {
                'username': story.user.username,
                'avatar_url': story.user.profile.avatar.url if story.user.profile.avatar else '/static/images/default-avatar.svg',
            },
            'track_name': story.track_name or '',
            'artist_name': story.artist_name or '',
            'album_image_url': story.album_image_url or '',
            'spotify_track_id': story.spotify_track_id or '',
            'mood': story.mood or '',
            'mood_emoji': story.mood_emoji or '',
            'comment': story.comment or '',
            'created_at': story.created_at.isoformat(),
            'expires_at': story.expires_at.isoformat(),
            'viewers_count': story.viewers.count(),
            'prev_story_id': prev_story_id,
            'next_story_id': next_story_id,
            'is_own_story': 'true' if request.user == story.user else 'false'  # JavaScriptのブーリアン値として文字列を使用
        }
        
        return JsonResponse({'status': 'success', 'story': data})
        
    except Exception as e:
        logger.error(f"ストーリー詳細の取得に失敗: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'ストーリーの取得に失敗しました'}, status=500)

@login_required
def spotify_search(request):
    """楽曲検索エンドポイント"""
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'tracks': []})

    try:
        # SpotifyClientCredentialsを直接使用
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # 日本市場での検索
        jp_results = spotify.search(q=query, type='track', market='JP', limit=5)
        jp_tracks = jp_results['tracks']['items']
        
        # グローバル市場での検索（日本で見つからない場合のバックアップ）
        if not jp_tracks:
            global_results = spotify.search(q=query, type='track', limit=5)
            tracks = global_results['tracks']['items']
        else:
            tracks = jp_tracks

        # 検索結果を整形
        formatted_tracks = []
        seen_ids = set()
        
        for track in tracks:
            track_id = track['id']
            if track_id not in seen_ids:
                seen_ids.add(track_id)
                # 既存の楽曲を検索
                music = Music.objects.filter(spotify_id=track_id).first()
                if not music:
                    # 新しい楽曲をデータベースに保存
                    music = Music.objects.create(
                        title=track['name'],
                        artist=track['artists'][0]['name'],
                        spotify_id=track_id,
                        album_art=track['album']['images'][0]['url'] if track['album']['images'] else None,
                        preview_url=track['preview_url'],
                        duration_ms=track['duration_ms']
                    )
                
                formatted_tracks.append({
                    'id': track_id,
                    'title': track['name'],
                    'artist': track['artists'][0]['name'],
                    'imageUrl': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'preview_url': track['preview_url']
                })

        return JsonResponse({'tracks': formatted_tracks[:5]})  # 最大5曲まで返す

    except Exception as e:
        logger.error(f"Spotify検索エラー: {str(e)}")
        return JsonResponse({'error': 'Spotifyの検索中にエラーが発生しました。'}, status=500)

@login_required
def story_detail(request, pk):
    """ストーリーの詳細を表示"""
    story = get_object_or_404(MusicStory, pk=pk)
    
    # ストーリーが期限切れの場合
    if story.is_expired:
        messages.error(request, 'このストーリーは期限切れです。')
        return redirect('core:home')
    
    # 非公開ストーリーの場合、作成者のみアクセス可能
    if not story.is_public and story.user != request.user:
        messages.error(request, 'このストーリーにはアクセスできません。')
        return redirect('core:home')
    
    # 閲覧履歴を記録
    if request.user not in story.viewers.all():
        story.viewers.add(request.user)
    
    # 前後のストーリーを取得
    user_stories = MusicStory.objects.filter(
        user=story.user,
        expires_at__gt=timezone.now()
    ).order_by('created_at')
    
    story_ids = list(user_stories.values_list('id', flat=True))
    current_index = story_ids.index(story.id)
    
    context = {
        'story': story,
        'prev_story_id': story_ids[current_index - 1] if current_index > 0 else None,
        'next_story_id': story_ids[current_index + 1] if current_index < len(story_ids) - 1 else None,
        'viewers_count': story.viewers.count(),
        'is_own_story': request.user == story.user
    }
    
    return render(request, 'core/story_detail.html', context)

@login_required
def delete_story(request, pk):
    """ストーリーの削除"""
    story = get_object_or_404(MusicStory, pk=pk, user=request.user)
    
    if request.method == 'POST':
        story.delete()
        messages.success(request, 'ストーリーを削除しました。')
        return redirect('core:home')
    
    return render(request, 'core/story_confirm_delete.html', {'story': story})

@login_required
def like_playlist(request, playlist_id):
    """プレイリストのいいね処理"""
    try:
        playlist = get_object_or_404(Playlist, id=playlist_id)
        
        if request.user in playlist.likes.all():
            playlist.likes.remove(request.user)
            liked = False
        else:
            playlist.likes.add(request.user)
            liked = True
            # 自分の投稿以外の場合は通知を作成
            if request.user != playlist.user:
                Notification.objects.create(
                    recipient=playlist.user,
                    sender=request.user,
                    notification_type='like',
                    playlist=playlist
                )
        
        return JsonResponse({
            'status': 'success',
            'liked': liked,
            'like_count': playlist.likes.count()
        })
    except Exception as e:
        logger.error(f"プレイリストのいいね処理中にエラーが発生: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'いいねの処理中にエラーが発生しました'
        }, status=500)

@login_required
def add_playlist_comment(request, playlist_id):
    """プレイリストへのコメント追加"""
    playlist = get_object_or_404(Playlist, id=playlist_id)
    
    if request.method == 'POST':
        try:
            content = request.POST.get('content')
            if not content:
                return JsonResponse({
                    'status': 'error',
                    'message': 'コメント内容を入力してください'
                }, status=400)
            
            comment = PlaylistComment.objects.create(
                playlist=playlist,
                user=request.user,
                content=content
            )
            
            # 自分の投稿以外の場合は通知を作成
            if request.user != playlist.user:
                Notification.objects.create(
                    recipient=playlist.user,
                    sender=request.user,
                    notification_type='comment',
                    playlist=playlist,
                    comment=comment
                )
            
            # コメントのHTMLをレンダリング
            html = render_to_string('core/includes/playlist_comment.html', {
                'comment': comment
            }, request=request)
            
            return JsonResponse({
                'status': 'success',
                'html': html,
                'comment_count': playlist.playlist_comments.count()
            })
            
        except Exception as e:
            logger.error(f"プレイリストへのコメント追加中にエラーが発生: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'コメントの追加中にエラーが発生しました'
            }, status=500)
    
    return JsonResponse({'status': 'error', 'message': '無効なリクエストです'}, status=400)

def get_recommended_playlists():
    """おすすめのプレイリストを取得"""
    # 過去1週間の人気プレイリストを取得
    week_ago = timezone.now() - timezone.timedelta(days=7)
    popular_playlists = Playlist.objects.filter(
        is_public=True,
        created_at__gte=week_ago
    ).annotate(
        engagement_score=Count('likes') + Count('playlist_comments') * 2
    ).order_by('-engagement_score')[:5]
    
    return popular_playlists
