from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Q, Count, Case, When, F, Model as models, Exists, OuterRef, IntegerField, Max, Min, BooleanField
from django.contrib import messages
from django.contrib.auth.models import User
from django.conf import settings
from .models import (
    MusicPost, MusicStory, Comment, Profile, MusicTaste,
    Playlist, Notification, PlaylistComment, Music, PlaylistMusic, Event,
    Conversation, Message, MessageAttachment
)
from .forms import MusicPostForm, MusicStoryForm, CommentForm, MusicTasteForm, ProfileEditForm, MusicStoryForm,UserLoginForm,UserRegisterForm,PlaylistForm
from .spotify_utils import get_spotify_client, get_recently_played_tracks, get_top_tracks, get_spotify_oauth
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import json
import logging
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
import random
from django.db import transaction
import pytz

logger = logging.getLogger(__name__)


def home(request):
    # 検索クエリの取得
    search_query = request.GET.get('q', '')
    
    # 特定の投稿IDが指定された場合、その投稿を取得
    featured_post_id = request.GET.get('featured')
    featured_post = None
    if featured_post_id:
        try:
            featured_post = MusicPost.objects.select_related('user', 'user__profile').prefetch_related('likes', 'comments').get(
                id=featured_post_id,
                user__isnull=False,
                user__username__isnull=False
            )
        except MusicPost.DoesNotExist:
            pass

    # 通常の投稿を取得（ユーザー名が存在するものだけ）
    posts = MusicPost.objects.select_related('user', 'user__profile').prefetch_related('likes', 'comments').filter(
        user__isnull=False,
        user__username__isnull=False
    )
    
    # 特定の投稿が指定されている場合、その投稿を除外して取得
    if featured_post:
        posts = posts.exclude(id=featured_post.id)
    
    # 投稿を作成日時の降順で並び替え
    posts = posts.order_by('-created_at')

    # 特定の投稿が存在する場合、リストの先頭に追加
    if featured_post:
        posts = list(posts)
        posts.insert(0, featured_post)
    
    # Ajaxリクエストの場合、投稿リストのみを返す
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('core/includes/post_list.html', {'posts': posts}, request=request)
        return JsonResponse({'html': html})
    
    # 通常のリクエストの場合は以下の処理を続行
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
    
    # トレンド投稿を取得（コメントの重みを3倍に設定）
    trending_posts = MusicPost.objects.select_related('user', 'user__profile').prefetch_related('likes', 'comments').filter(
        created_at__gte=timezone.now() - timezone.timedelta(days=7),
        user__isnull=False,
        user__username__isnull=False
    ).annotate(
        like_count=Count('likes'),
        comment_count=Count('comments'),
        engagement_score=Count('likes') + (Count('comments') * 3)  # コメントの重みを3倍に
    ).order_by('-engagement_score', '-created_at')[:5]
    
    # おすすめユーザーを取得
    recommended_users = []
    if request.user.is_authenticated:
        # フォロー中のユーザーのプロフィールIDを取得
        following_profile_ids = request.user.profile.following.values_list('id', flat=True)
        
        # 自分以外のユーザーを取得（フォロー中のユーザーを除外）
        other_users = Profile.objects.exclude(
            Q(user=request.user) |
            Q(id__in=following_profile_ids)
        ).select_related('user').filter(
            user__isnull=False  # ユーザーが存在するものだけを取得
        )
        
        # 各ユーザーとの音楽の相性を計算
        for profile in other_users:
            if profile.user and profile.user.username:  # ユーザーとユーザー名が存在する場合のみ処理
                compatibility = calculate_music_compatibility(request.user.profile, profile)
                # 音楽の相性が15%以上のユーザーのみを追加
                if compatibility['score'] >= 15:
                    recommended_users.append({
                        'user': profile.user,
                        'compatibility_score': compatibility['score']
                    })
        
        # 互換性スコアで降順ソート
        recommended_users.sort(key=lambda x: x['compatibility_score'], reverse=True)
        # 上位5人まで取得
        recommended_users = recommended_users[:5]
    
    # おすすめのプレイリストを取得
    recommended_playlists = Playlist.objects.filter(
        is_public=True
    ).annotate(
        track_count=Count('playlistmusic'),
        likes_count=Count('likes'),
        engagement_score=Count('likes') + Count('playlist_comments')
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'playlistmusic_set__music'
    ).order_by('-engagement_score', '-created_at')[:6]

    # プレイリストのカバー画像を設定
    for playlist in recommended_playlists:
        first_track = playlist.playlistmusic_set.first()
        if first_track and first_track.music:
            playlist.cover_image = first_track.music.album_art
        else:
            playlist.cover_image = None

    context = {
        'posts': posts,
        'stories_by_user': stories_by_user_list,
        'trending_posts': trending_posts,
        'recommended_users': recommended_users,  # 上位3人のみ表示
        'recommended_playlists': recommended_playlists  # おすすめのプレイリストを追加
    }
    
    return render(request, 'core/home.html', context)

def register_view(request):
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

def calculate_music_compatibility(profile1, profile2):
    """ユーザー間の音楽の相性スコアを計算"""
    try:
        score = 0
        common_artists = []
        
        # お気に入りアーティストを比較
        profile1_artists = [artist['name'] for artist in profile1.favorite_artists] if profile1.favorite_artists else []
        profile2_artists = [artist['name'] for artist in profile2.favorite_artists] if profile2.favorite_artists else []
    
        common_artists = [artist for artist in profile1_artists if artist in profile2_artists]
        score += len(common_artists) * 15  # 共通のアーティストごとに15ポイント
        
        # スコアを0-100の範囲に正規化
        normalized_score = min(100, score)
        
        return {
            'score': normalized_score,
            'common_artists': common_artists[:5],  # 上位5アーティストまで
        }
    except Exception as e:
        logger.error(f"音楽の相性スコア計算エラー: {str(e)}")
        return {
            'score': 0,
            'common_artists': [],
        }

def get_common_artists(user1, user2):
    """二人のユーザー間の共通のアーティストを取得"""
    try:
        # user1とuser2はProfileオブジェクトとして扱う
        user1_artists = [artist['name'] for artist in user1.favorite_artists] if user1.favorite_artists else []
        user2_artists = [artist['name'] for artist in user2.favorite_artists] if user2.favorite_artists else []
        
        # 共通のアーティストを返す
        return list(set(user1_artists) & set(user2_artists))
    except Exception as e:
        logger.error(f"共通アーティスト取得エラー: {str(e)}")
        return []

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
            post_type = request.POST.get('post_type')
            description = request.POST.get('description')
            
            # バリデーション
            if not all([post_type, description]):
                messages.error(request, '必須項目が入力されていません。')
                return redirect('core:create_post')

            # 投稿データの準備
            post_data = {
                'user': request.user,
                'description': description,
                'post_type': post_type,
            }

            # 投稿タイプに応じてデータを設定
            if 'spotify_track_id' in request.POST:
                spotify_track_id = request.POST.get('spotify_track_id')
                post_data.update({
                    'title': request.POST.get('title'),
                    'artist': request.POST.get('artist'),
                    'spotify_link': f"https://open.spotify.com/track/{spotify_track_id}",
                    'image': request.POST.get('image'),
                    'target_type': 'track'
                })
            elif 'spotify_artist_id' in request.POST:
                spotify_artist_id = request.POST.get('spotify_artist_id')
                artist_name = request.POST.get('artist_name')
                
                # アーティスト投稿の場合
                post_data.update({
                    'artist': artist_name,  # artist_nameをartistフィールドに保存
                    'spotify_link': f"https://open.spotify.com/artist/{spotify_artist_id}",
                    'image': request.POST.get('image'),
                    'target_type': 'artist'  # target_typeを明示的に設定
                })
            elif 'spotify_album_id' in request.POST:
                spotify_album_id = request.POST.get('spotify_album_id')
                post_data.update({
                    'title': request.POST.get('album_name'),
                    'artist': request.POST.get('album_artist'),
                    'spotify_link': f"https://open.spotify.com/album/{spotify_album_id}",
                    'image': request.POST.get('image'),
                    'target_type': 'album'  # target_typeを明示的に設定
                })

            # 投稿の作成
            post = MusicPost.objects.create(**post_data)

            messages.success(request, '投稿が作成されました！')
            return redirect('core:home')

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
    
    # 類似投稿を取得（同じアーティストまたは同じムードの投稿）
    similar_posts = MusicPost.objects.filter(
        Q(artist=post.artist) |
        Q(mood=post.mood)
    ).exclude(id=post.id).order_by('-created_at')[:5]
    
    context = {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'similar_posts': similar_posts,
    }
    
    return render(request, 'core/post_detail.html', context)

@login_required
def edit_post(request, post_id):
    post = get_object_or_404(MusicPost, id=post_id, user=request.user)
    
    if request.method == 'POST':
        try:
            # フォームデータの取得
            post_type = request.POST.get('post_type')
            description = request.POST.get('description')
            target_type = request.POST.get('target_type')
            # バリデーション
            if not all([post_type, description]):
                messages.error(request, '必須項目が入力されていません。')
                return redirect('core:edit_post', post_id=post_id)

            # 投稿データの更新
            post.post_type = post_type
            post.description = description
            post.save()

            messages.success(request, '投稿を更新しました。')
            return redirect('core:home')

        except Exception as e:
            logger.error(f"投稿更新エラー: {str(e)}")
            messages.error(request, '投稿の更新中にエラーが発生しました。')
            return redirect('core:edit_post', post_id=post_id)

    context = {
        'post': post,
    }
    
    return render(request, 'core/edit_post.html', context)

@login_required
def delete_post(request, post_id):
    post = get_object_or_404(MusicPost, pk=post_id, user=request.user)
    if request.method == 'POST':
        post.delete()
        messages.success(request, '投稿が削除されました。')
        return JsonResponse({'status': 'success'})
    return render(request, 'core/post_confirm_delete.html', {'post': post})

@login_required
def like_post(request, post_id):
    try:
        with transaction.atomic():
            post = MusicPost.objects.select_for_update().get(id=post_id)
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
    except MusicPost.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': '投稿が見つかりません。'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': 'エラーが発生しました。'
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

@login_required
def profile(request, username):
    try:
        profile_user = User.objects.get(username=username)
        profile = profile_user.profile
        posts = MusicPost.objects.filter(user=profile_user).order_by('-created_at')
        
        # フォロー中とフォロワーのユーザーを取得し、相性スコアを計算
        following_users = []
        for following_profile in profile.following.all():
            compatibility_score = request.user.profile.get_music_compatibility_score(following_profile.user)
            following_users.append({
                'user': following_profile.user,
                'compatibility_score': compatibility_score
            })
        
        follower_users = []
        for follower_profile in profile.followers.all():
            compatibility_score = request.user.profile.get_music_compatibility_score(follower_profile.user)
            follower_users.append({
                'user': follower_profile.user,
                'compatibility_score': compatibility_score
            })
        
        # プレイリストとその他の情報を取得
        playlists = Playlist.objects.filter(user=profile_user, is_public=True)
        
        # 音楽の相性スコアを計算（既存のユーザーの場合）
        compatibility_data = None
        if request.user != profile_user:
            # 共通のアーティストを取得（画像情報付き）
            common_artists = []
            if profile.favorite_artists and request.user.profile.favorite_artists:
                # アーティスト情報をIDまたは名前でマッピング
                user1_artists = {}
                for artist in request.user.profile.favorite_artists:
                    key = artist.get('id') or artist.get('name')
                    if key:
                        user1_artists[key] = artist

                user2_artists = {}
                for artist in profile.favorite_artists:
                    key = artist.get('id') or artist.get('name')
                    if key:
                        user2_artists[key] = artist
                
                # 共通のアーティストを見つける
                common_keys = set(user1_artists.keys()) & set(user2_artists.keys())
                
                # 共通のアーティスト情報を構築
                for key in common_keys:
                    artist_info = user1_artists[key]
                    common_artists.append({
                        'name': artist_info.get('name', ''),
                        'image': artist_info.get('image'),
                        'id': artist_info.get('id', '')
                    })
            
            # 相性スコアを計算
            score = calculate_music_compatibility(request.user.profile, profile)['score']
            
            compatibility_data = {
                'score': score,
                'common_artists': common_artists
            }
        
        # フォロー状態を確認
        is_following = request.user.profile.following.filter(id=profile.id).exists() if request.user.is_authenticated else False
        
        context = {
            'profile_user': profile_user,
            'posts': posts,
            'following_users': following_users,
            'follower_users': follower_users,
            'playlists': playlists,
            'compatibility_data': compatibility_data,
            'is_following': is_following,
        }
        return render(request, 'core/profile.html', context)
    except User.DoesNotExist:
        return redirect('core:home')

@login_required
def follow_user(request, username):
    """ユーザーをフォロー/アンフォローする"""
    user_to_follow = get_object_or_404(User, username=username)
    if request.user != user_to_follow:
        if user_to_follow.profile in request.user.profile.following.all():
            request.user.profile.following.remove(user_to_follow.profile)
            is_following = False
        else:
            request.user.profile.following.add(user_to_follow.profile)
            is_following = True
            # 通知を作成
            Notification.objects.create(
                recipient=user_to_follow,
                sender=request.user,
                notification_type='follow'
            )
        
        return JsonResponse({
            'status': 'success',
            'is_following': is_following
        })
    return JsonResponse({'status': 'error', 'message': '自分自身をフォローすることはできません'}, status=400)

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
            spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
                client_id=settings.SPOTIFY_CLIENT_ID,
                client_secret=settings.SPOTIFY_CLIENT_SECRET
            ))
            
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
        track_count=Count('playlistmusic'),
        likes_count=Count('likes'),
        engagement_score=Count('likes') + Count('playlist_comments')
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        'playlistmusic_set__music'
    ).order_by('-engagement_score', '-created_at')[:5]

    
    first_track = playlist.playlistmusic_set.first()
    if first_track and first_track.music:
        playlist.cover_image = first_track.music.album_art
    else:
        playlist.cover_image = None

    for playlist_music in recommended_playlists:
        first_track = playlist_music.playlistmusic_set.first()
        if first_track and first_track.music:
            playlist_music.cover_image = first_track.music.album_art
        else:
            playlist_music.cover_image = None

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
                return redirect('core:edit_playlist', pk=pk)

            if not track_ids:
                messages.error(request, '少なくとも1曲は追加してください。')
                return redirect('core:edit_playlist', pk=pk)

            # プレイリストの基本情報を更新
            playlist.title = title
            playlist.description = description
            playlist.is_public = is_public
            playlist.save()

            # 既存の曲を全て削除
            PlaylistMusic.objects.filter(playlist=playlist).delete()

            # 新しい曲を追加
            spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
                client_id=settings.SPOTIFY_CLIENT_ID,
                client_secret=settings.SPOTIFY_CLIENT_SECRET
            ))
            
            for order, track_id in enumerate(track_ids):
                try:
                    music = Music.objects.filter(spotify_id=track_id).first()
                    if not music:
                        track_info = spotify.track(track_id)
                        music = Music.objects.create(
                            title=track_info['name'],
                            artist=track_info['artists'][0]['name'],
                            spotify_id=track_id,
                            album_art=track_info['album']['images'][0]['url'] if track_info['album']['images'] else None,
                            preview_url=track_info.get('preview_url'),
                            duration_ms=track_info.get('duration_ms', 0)
                        )

                    PlaylistMusic.objects.create(
                        playlist=playlist,
                        music=music,
                        order=order
                    )

                except Exception as e:
                    logger.error(f"楽曲の追加中にエラー: {str(e)}")
                    continue

            messages.success(request, 'プレイリストを更新しました。')
            return redirect('core:playlist_detail', pk=playlist.pk)

        except Exception as e:
            logger.error(f"プレイリスト更新エラー: {str(e)}")
            messages.error(request, 'プレイリストの更新中にエラーが発生しました。')
            return redirect('core:edit_playlist', pk=pk)

    # プレイリストの曲を取得
    playlist_tracks = PlaylistMusic.objects.filter(
        playlist=playlist
    ).select_related('music').order_by('order')

    # 現在の曲のリストを作成
    current_tracks = [{
        'id': track.music.spotify_id,
        'title': track.music.title,
        'artist': track.music.artist,
        'imageUrl': track.music.album_art
    } for track in playlist_tracks]

    context = {
        'playlist': playlist,
        'current_tracks': json.dumps(current_tracks)
    }
    
    return render(request, 'core/edit_playlist.html', context)

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
    # 通知を種類ごとにグループ化して最新のものだけを取得
    notifications = (
        request.user.notifications.filter(
            recipient=request.user,
            sender__isnull=False  # 送信者が存在する通知のみ
        ).exclude(  # 必要なフィールドが空の通知を除外
            Q(notification_type='like_post') & Q(post__isnull=True) |
            Q(notification_type='comment_post') & Q(post__isnull=True) |
            Q(notification_type='like_playlist') & Q(playlist__isnull=True)
        ).values('sender', 'notification_type', 'post', 'playlist')
        .annotate(
            latest_id=Max('id'),
            created_at=Max('created_at'),
            is_read=Case(
                When(is_read=True, then=True),
                default=False,
                output_field=BooleanField()
            )
        )
        .order_by('-created_at')
    )
    
    # 通知の詳細情報を取得
    detailed_notifications = []
    for notif in notifications:
        try:
            notification = Notification.objects.select_related(
                'sender', 'sender__profile',  # sender__profileを追加
                'post', 'playlist', 'comment'
            ).get(id=notif['latest_id'])
            
            # フォロー状態を確認（sender__profileを使用）
            if notification.sender and notification.sender != request.user:
                notification.is_following = notification.sender.profile in request.user.profile.following.all()
            else:
                notification.is_following = False
            
            # 通知の種類に応じて必要なフィールドが存在することを確認
            if (notification.notification_type == 'like_post' and notification.post) or \
               (notification.notification_type == 'comment_post' and notification.post) or \
               (notification.notification_type == 'like_playlist' and notification.playlist) or \
               notification.notification_type == 'follow':
                detailed_notifications.append(notification)
        except Exception as e:
            logger.error(f"通知の取得エラー: {str(e)}")
            continue
    
    # 未読の通知を既読に更新
    request.user.notifications.filter(is_read=False).update(is_read=True)
    
    unread_count = sum(1 for n in notifications if not n['is_read'])
    
    return render(request, 'core/notifications.html', {
        'notifications': detailed_notifications,
        'unread_count': unread_count
    })

@login_required
def get_unread_notification_count(request):
    count = request.user.notifications.filter(is_read=False).count()
    return JsonResponse({'count': count})

@login_required
def notification_redirect(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id)
    notification.is_read = True
    notification.save()
    
    if notification.notification_type == 'follow':
        return redirect('core:profile', username=notification.sender.username)
    elif notification.notification_type in ['like_post', 'comment_post']:
        return redirect(f'/?featured={notification.post.id}')
    elif notification.notification_type == 'like_playlist':
        return redirect('core:playlist_detail', playlist_id=notification.playlist.id)
    
    return redirect('core:home')

@login_required
def following_posts(request):
    following_users = request.user.profile.following.values_list('user', flat=True)
    posts = MusicPost.objects.filter(user__in=following_users).select_related('user', 'user__profile').prefetch_related('likes', 'comments').order_by('-created_at')
    return render(request, 'core/following_posts.html', {'posts': posts})

def search(request):
    query = request.GET.get('q', '')
    search_type = request.GET.get('type', 'all')
    show_all = request.GET.get('show_all', False)  # 一覧表示モードのフラグ
    
    # 一覧表示モードまたは検索クエリがある場合
    if show_all or query:
        if search_type == 'users':
            # ユーザー検索
            users = User.objects.filter(
                Q(username__icontains=query) if query else Q()
            ).select_related('profile').distinct()

            # ログインユーザーの場合、各ユーザーとの相性スコアとフォロー状態を計算
            if request.user.is_authenticated:
                users_with_compatibility = []
                for user in users:
                    if user != request.user:  # 自分自身を除外
                        compatibility = calculate_music_compatibility(request.user.profile, user.profile)
                        user.compatibility_score = compatibility['score']
                        # フォロー状態を追加
                        user.is_following = user.profile in request.user.profile.following.all()
                        users_with_compatibility.append(user)
                users = users_with_compatibility
            
            context = {
                'query': query,
                'search_type': search_type,
                'users': users,
                'show_all': show_all
            }
            
        elif search_type == 'playlists':
            # プレイリスト検索
            playlists = Playlist.objects.filter(
                Q(title__icontains=query) | Q(description__icontains=query) if query else Q(),
                is_public=True
            ).select_related('user', 'user__profile').annotate(
                track_count=Count('playlistmusic'),
                likes_count=Count('likes')
            ).order_by('-created_at')
            
            context = {
                'query': query,
                'search_type': search_type,
                'playlists': playlists,
                'show_all': show_all
            }
            
        elif search_type == 'posts':
            # 投稿検索
            posts = MusicPost.objects.filter(
                Q(title__icontains=query) | Q(artist__icontains=query) |
                Q(description__icontains=query) | Q(mood__icontains=query) if query else Q()
            ).select_related('user', 'user__profile').prefetch_related(
                'likes', 'comments'
            ).order_by('-created_at')
            
            context = {
                'query': query,
                'search_type': search_type,
                'posts': posts,
                'show_all': show_all
            }
            
        else:  # all
            # 全体検索
            posts = MusicPost.objects.filter(
                Q(title__icontains=query) | Q(artist__icontains=query) |
                Q(description__icontains=query) if query else Q()
            ).select_related('user', 'user__profile').prefetch_related(
                'likes', 'comments'
            ).order_by('-created_at')
            
            users = User.objects.filter(
                Q(username__icontains=query) | Q(profile__bio__icontains=query) if query else Q()
            ).select_related('profile').distinct()
            
            # ログインユーザーの場合、各ユーザーとの相性スコアとフォロー状態を計算
            if request.user.is_authenticated:
                users_with_compatibility = []
                for user in users:
                    if user != request.user:  # 自分自身を除外
                        compatibility = calculate_music_compatibility(request.user.profile, user.profile)
                        user.compatibility_score = compatibility['score']
                        # フォロー状態を追加
                        user.is_following = user.profile in request.user.profile.following.all()
                        users_with_compatibility.append(user)
                users = users_with_compatibility
            
            playlists = Playlist.objects.filter(
                Q(title__icontains=query) | Q(description__icontains=query) if query else Q(),
                is_public=True
            ).select_related('user', 'user__profile').annotate(
                track_count=Count('playlistmusic'),
                likes_count=Count('likes')
            ).order_by('-created_at')

            for playlist in playlists:
                first_track = playlist.playlistmusic_set.first()
                if first_track and first_track.music:
                    playlist.cover_image = first_track.music.album_art
                else:
                    playlist.cover_image = None
            
            context = {
                'query': query,
                'search_type': search_type,
                'posts': posts,
                'users': users,
                'playlists': playlists,
                'show_all': show_all
            }
    else:
        context = {
            'query': '',
            'search_type': search_type,
            'show_all': show_all
        }
    
    return render(request, 'core/search.html', context)

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
    music_taste, created = Profile.objects.get_or_create(user=request.user)
    user = request.user
    
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
                    if not user.profile.favorite_artists:
                        user.profile.favorite_artists = []
                    
                    # アーティストデータを作成
                    artist_data = {
                        'name': artist_name,
                        'image': artist_image,
                        'id': artist_id
                    }
                    
                    # IDで重複チェック
                    if not any(artist.get('id') == artist_id for artist in user.profile.favorite_artists):
                        user.profile.favorite_artists.append(artist_data)
                        user.profile.save()
                    
                    return JsonResponse({
                        'status': 'success',
                        'message': 'アーティストを追加しました'
                    })
                
                elif action == 'update_genres':
                    genres = data.get('genres', [])
                    user.profile.favorite_genres = genres
                    user.profile.save()
                    return JsonResponse({'status': 'success'})
                
                elif action == 'update_moods':
                    moods = data.get('moods', [])
                    user.profile.music_mood_preferences = moods
                    user.profile.save()
                    return JsonResponse({'status': 'success'})
                
                return JsonResponse({'status': 'error', 'message': '不明なアクション'})
            
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': '無効なJSONデータ'}, status=400)
            except Exception as e:
                logger.error(f"音楽の好み更新中にエラー: {str(e)}")
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        
        # 通常のフォーム送信の場合
        else:
            form = MusicTasteForm(request.POST, instance=user.profile)
            if form.is_valid():
                form.save()
                messages.success(request, '音楽の好みを更新しました。')
                return redirect('core:profile', username=request.user.username)
    else:
        form = MusicTasteForm(instance=user.profile)
    
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
    current_genres = user.profile.favorite_genres if user.profile.favorite_genres else []
    current_moods = user.profile.music_mood_preferences if user.profile.music_mood_preferences else []
    current_artists = user.profile.favorite_artists if user.profile.favorite_artists else []
    
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
    if not request.user.is_authenticated:
        return redirect('core:login')
    
    # 1. 相性の良いユーザーを取得
    compatible_users = get_compatible_users(request.user)
    
    # 2. 今日のおすすめ曲を取得
    recommended_tracks = get_recommended_tracks(request.user)
    
    # 3. 平均相性を計算
    average_compatibility = calculate_average_compatibility(request.user)
    
    # 4. ジャンル分析
    genre_analysis = analyze_user_genres(request.user)
    
    context = {
        'compatible_users': compatible_users,
        'recommended_tracks': recommended_tracks,
        'average_compatibility': average_compatibility,
        'genre_analysis': genre_analysis,
    }
    
    return render(request, 'core/music_compatibility.html', context)

def get_compatible_users(user, limit=5):
    """相性の良いユーザーを取得"""
    try:
        # 自分以外のプロフィールを取得
        all_profiles = Profile.objects.exclude(user=user)
        compatible_users = []
        
        for profile in all_profiles:
            # 共通のアーティストを検出（user.profileとprofileを比較）
            common_artists = get_common_artists(user.profile, profile)
            # ジャンルの類似性を計算
            genre_similarity = calculate_genre_similarity(user.profile, profile)
            # 総合スコアを計算（アーティストとジャンルの重み付け）
            compatibility_score = (len(common_artists) * 0.6 + genre_similarity * 0.4) * 100
            
            if compatibility_score > 0:
                compatible_users.append({
                    'user': profile.user,
                    'profile': profile,  # プロフィール情報を追加
                    'score': int(compatibility_score),
                    'common_artists': common_artists[:3]  # Top 3 common artists
                })
        
        # スコアで降順ソート
        compatible_users.sort(key=lambda x: x['score'], reverse=True)
        return compatible_users[:limit]
    except Exception as e:
        logger.error(f"互換性のあるユーザーの取得に失敗: {str(e)}")
        return []

def get_recommended_tracks(user):
    """今日のおすすめ曲を取得"""
    try:
        recommended_tracks = []
        
        # 1. お気に入りアーティストの曲を取得
        if user.profile.favorite_artists:
            for artist in user.profile.favorite_artists[:3]:  # 上位3アーティスト
                artist_id = artist.get('id')
                if artist_id:
                    tracks = get_artist_top_tracks(artist_id)
                    recommended_tracks.extend(tracks)
        
        # 2. よく聴くジャンルの曲を追加
        if user.profile.favorite_genres:
            genre_tracks = get_tracks_by_genres(user.profile.favorite_genres)
            recommended_tracks.extend(genre_tracks)
        
        # 重複を除去してランダムに選択
        unique_tracks = []
        track_ids = set()
        
        for track in recommended_tracks:
            if track['id'] not in track_ids:
                track_ids.add(track['id'])
                unique_tracks.append(track)
        
        # ランダムに並び替えて上位10曲を返す
        random.shuffle(unique_tracks)
        return unique_tracks[:10]
        
    except Exception as e:
        logger.error(f"おすすめ曲の取得に失敗: {str(e)}")
        return []

def calculate_average_compatibility(user):
    """平均相性を計算"""
    all_profiles = Profile.objects.exclude(user=user)
    total_score = 0
    count = 0
    
    following_scores = []
    all_scores = []
    
    for profile in all_profiles:
        # calculate_music_compatibilityを使用してスコアを計算
        compatibility = calculate_music_compatibility(user.profile, profile)
        score = compatibility['score']
        all_scores.append(score)
        
        if profile in user.profile.following.all():
            following_scores.append(score)
            
        total_score += score
        count += 1
    
    return {
        'overall_average': int(total_score / count) if count > 0 else 0,
        'following_average': int(sum(following_scores) / len(following_scores)) if following_scores else 0,
        'score_distribution': analyze_score_distribution(all_scores),
    }

def analyze_user_genres(user):
    """ユーザーのジャンル分析を実行"""
    genres = {}
    
    # お気に入りアーティストからジャンルを収集
    if user.profile.favorite_artists:
        for artist in user.profile.favorite_artists:
            if 'genres' in artist:
                for genre in artist['genres']:
                    genres[genre] = genres.get(genre, 0) + 1
    
    # ジャンルを出現頻度でソート
    sorted_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)
    
    return {
        'top_genres': dict(sorted_genres[:5]),
        'genre_count': len(genres),
    }

def analyze_score_distribution(scores):
    """相性スコアの分布を分析"""
    ranges = {
        '0-20': 0,
        '21-40': 0,
        '41-60': 0,
        '61-80': 0,
        '81-100': 0
    }
    
    for score in scores:
        if score <= 20:
            ranges['0-20'] += 1
        elif score <= 40:
            ranges['21-40'] += 1
        elif score <= 60:
            ranges['41-60'] += 1
        elif score <= 80:
            ranges['61-80'] += 1
        else:
            ranges['81-100'] += 1
            
    return ranges

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
    try:
        sp_oauth = get_spotify_oauth()
        code = request.GET.get('code')
        if not code:
            messages.error(request, 'Spotifyの認証に失敗しました。')
            return redirect('core:home')

        # アクセストークンを取得
        token_info = sp_oauth.get_access_token(code, check_cache=False)
        if not token_info:
            messages.error(request, 'Spotifyのトークン取得に失敗しました。')
            return redirect('core:home')

        # プロフィールを取得または作成
        profile = Profile.objects.get_or_create(user=request.user)[0]
        profile.spotify_refresh_token = token_info['refresh_token']
        profile.spotify_connected = True  # この行を追加
        profile.save()

        # ログ出力を追加
        logger.info(f"Spotify連携成功: user={request.user.username}, refresh_token={profile.spotify_refresh_token[:10]}...")

        messages.success(request, 'Spotifyと連携しました。')
        return redirect('core:home')

    except Exception as e:
        logger.error(f"Spotify連携エラー: {str(e)}")
        messages.error(request, f'エラーが発生しました: {str(e)}')
        return redirect('core:home')

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
    """投稿をフィルタリングするビュー"""
    try:
        filter_type = request.GET.get('filter', 'all')
        sort_by = request.GET.get('sort', 'recommended')
        
        # 基本のクエリセット
        posts = MusicPost.objects.select_related('user', 'user__profile').prefetch_related('likes', 'comments').filter(
            user__isnull=False,
            user__username__isnull=False
        )
        
        # フィルタリング
        if filter_type == 'following' and request.user.is_authenticated:
            following_users = request.user.profile.following.values_list('user', flat=True)
            posts = posts.filter(user__in=following_users)
        
        if filter_type == 'today':
            japan_tz = pytz.timezone('Asia/Tokyo')
            today = timezone.now().astimezone(japan_tz).date()
            posts = posts.filter(created_at__date=today)
        
        # ソート
        if sort_by == 'newest':
            posts = posts.order_by('-created_at')
        elif sort_by == 'popular':
            posts = posts.annotate(
                like_count=Count('likes'),
                comment_count=Count('comments'),
                engagement_score=Count('likes') + (Count('comments') * 3)  # コメントの重みを3倍に
            ).order_by('-engagement_score', '-created_at')
        else:  # recommended
            if request.user.is_authenticated:
                posts = posts.annotate(
                    like_count=Count('likes'),
                    comment_count=Count('comments'),
                    is_followed=Exists(
                        Profile.objects.filter(
                            user=OuterRef('user'),
                            followers=request.user.profile
                        )
                    )
                ).annotate(
                    score=Case(
                        When(is_followed=True, then=10),
                        default=0,
                        output_field=IntegerField(),
                    ) + F('like_count') + (F('comment_count') * 3)  # コメントの重みを3倍に
                ).order_by('-score', '-created_at')
            else:
                posts = posts.annotate(
                    like_count=Count('likes'),
                    comment_count=Count('comments'),
                    engagement_score=Count('likes') + (Count('comments') * 3)  # コメントの重みを3倍に
                ).order_by('-engagement_score', '-created_at')

        # テンプレートをレンダリング
        html = render_to_string('core/includes/post_list.html', {'posts': posts}, request=request)
        return JsonResponse({
            'status': 'success',
            'html': html
        })
    except Exception as e:
        logger.error(f"投稿のフィルタリングエラー: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': '投稿の読み込みに失敗しました。'
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
    """曲を検索するAPI"""
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'tracks': []})
    
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        results = spotify.search(q=query, type='track', market='JP', limit=5)
        tracks = [{
            'id': track['id'],
            'name': track['name'],
            'artist': track['artists'][0]['name'],
            'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
            'preview_url': track['preview_url']
        } for track in results['tracks']['items']]
        
        return JsonResponse({'tracks': tracks})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_recently_played_tracks(spotify_client):
    """
    ユーザーの最近再生した曲を取得する
    """
    try:
        results = spotify_client.current_user_recently_played(limit=20)  # より多くの曲を取得
        tracks = []
        seen_ids = set()  # 重複チェック用のセット
        
        for item in results['items']:
            track = item['track']
            track_id = track['id']
            
            # まだ追加していない曲のみを追加
            if track_id not in seen_ids:
                seen_ids.add(track_id)
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'spotify_url': track['external_urls']['spotify'],
                    'played_at': item['played_at'],
                    'spotify_id': track_id
            })
                
            # 10曲集まったら終了
            if len(tracks) >= 10:
                break
                    
        return tracks
    except Exception as e:
        logger.error(f"最近再生した曲の取得に失敗: {str(e)}")
        return []

def get_top_tracks(spotify_client):
    """
    ユーザーのトップトラックを取得する
    """
    try:
        results = spotify_client.current_user_top_tracks(limit=20, time_range='short_term')  # より多くの曲を取得
        tracks = []
        seen_ids = set()  # 重複チェック用のセット
        
        for track in results['items']:
            track_id = track['id']
            
            # まだ追加していない曲のみを追加
            if track_id not in seen_ids:
                seen_ids.add(track_id)
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'spotify_url': track['external_urls']['spotify'],
                    'spotify_id': track_id
            })
                
                # 10曲集まったら終了
            if len(tracks) >= 10:
                break
                    
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
def spotify_search(request, search_type):
    """Spotifyで曲、アーティスト、アルバムを検索"""
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'error': '検索クエリが必要です'}, status=400)

    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))

        results = {}
        
        if search_type == 'track':
            # 曲検索
            track_results = spotify.search(q=query, type='track', limit=10, market='JP')
            results['tracks'] = [{
                'id': track['id'],
                'title': track['name'],
                'artist': track['artists'][0]['name'],
                'imageUrl': track['album']['images'][0]['url'] if track['album']['images'] else '',
                'preview_url': track['preview_url']
            } for track in track_results['tracks']['items']]

        elif search_type == 'artist':
            # アーティスト検索
            artist_results = spotify.search(q=query, type='artist', limit=10, market='JP')
            results['artists'] = []
            for artist in artist_results['artists']['items']:
                # アーティストのトップトラックを取得
                top_tracks = spotify.artist_top_tracks(artist['id'], country='JP')
                preview_track = next((track for track in top_tracks['tracks'] if track['preview_url']), None)
                
                results['artists'].append({
                    'id': artist['id'],
                    'name': artist['name'],
                    'genres': artist['genres'][:3] if artist['genres'] else [],
                    'imageUrl': artist['images'][0]['url'] if artist['images'] else '',
                    'followers': artist['followers']['total'],
                    'popularity': artist['popularity'],
                    'preview_track': {
                        'name': preview_track['name'],
                        'preview_url': preview_track['preview_url']
                    } if preview_track else None,
                    'external_url': artist['external_urls']['spotify'] if 'external_urls' in artist else None
                })

        elif search_type == 'album':
            # アルバム検索
            album_results = spotify.search(q=query, type='album', limit=10, market='JP')
            results['albums'] = []
            for album in album_results['albums']['items']:
                # アルバムの詳細情報を取得
                album_info = spotify.album(album['id'])
                # プレビュー可能な最初のトラックを探す
                preview_track = next((track for track in album_info['tracks']['items'] if track.get('preview_url')), None)
                
                results['albums'].append({
                    'id': album['id'],
                    'name': album['name'],
                    'artist': album['artists'][0]['name'],
                    'imageUrl': album['images'][0]['url'] if album['images'] else '',
                    'release_date': album['release_date'],
                    'total_tracks': album['total_tracks'],
                    'preview_track': {
                        'name': preview_track['name'],
                        'preview_url': preview_track['preview_url']
                    } if preview_track else None,
                    'external_url': album['external_urls']['spotify'] if 'external_urls' in album else None
                })

        return JsonResponse(results)

    except Exception as e:
        logger.error(f"Spotify検索エラー: {str(e)}")
        return JsonResponse({'error': '検索中にエラーが発生しました'}, status=500)

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

@login_required
def add_comment(request, post_id):
    """投稿へのコメント追加"""
    try:
        post = get_object_or_404(MusicPost, id=post_id)
        
        if request.method == 'POST':
            data = json.loads(request.body)
            content = data.get('content')
            
            if not content:
                return JsonResponse({
                    'status': 'error',
                    'message': 'コメント内容を入力してください'
                }, status=400)
            
            comment = Comment.objects.create(
                post=post,
                user=request.user,
                content=content
            )
            
            # 自分の投稿以外の場合は通知を作成
            if request.user != post.user:
                Notification.objects.create(
                    recipient=post.user,
                    sender=request.user,
                    notification_type='comment',
                    post=post,
                    comment=comment
                )
            
            return JsonResponse({
                'status': 'success',
                'comment': {
                    'username': comment.user.username,
                    'avatar_url': comment.user.profile.avatar.url if comment.user.profile.avatar else '/static/images/default-avatar.svg',
                    'content': comment.content,
                    'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M:%S')
                }
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': '無効なJSONデータです'
        }, status=400)
    except Exception as e:
        logger.error(f"コメント追加中にエラーが発生: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'コメントの追加中にエラーが発生しました'
        }, status=500)

    return JsonResponse({'status': 'error', 'message': '無効なリクエストです'}, status=400)

@login_required
def get_artist_analysis(request):
    """アーティスト詳細分析のデータを取得するAPI"""
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # ユーザーの好みのアーティストを取得
        user_artists = request.user.music_taste.favorite_artists if hasattr(request.user, 'music_taste') else []
        
        if not user_artists:
            return JsonResponse({
                'error': 'アーティストデータがありません。音楽の好みを設定してください。'
            }, status=404)
        
        # アーティスト情報を取得
        artists_data = []
        for artist_name in user_artists[:5]:  # 上位5アーティスト
            results = spotify.search(q=artist_name, type='artist', limit=1)
            if results['artists']['items']:
                artist = results['artists']['items'][0]
                artists_data.append({
                    'name': artist['name'],
                    'popularity': artist['popularity'],
                    'genres': artist['genres'],
                    'followers': artist['followers']['total']
                })
        
        # ジャンル分布データ
        genre_counts = {}
        for artist in artists_data:
            for genre in artist['genres']:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
        
        # アーティスト相関データ
        artist_correlation = [
            {
                'x': artist['popularity'],
                'y': artist['followers'] / 10000,  # フォロワー数を正規化
                'r': len(artist['genres']) * 5,  # ジャンル数に基づくバブルサイズ
                'label': artist['name']
            }
            for artist in artists_data
        ]
        
        # トレンドデータ（週間）
        trend_data = {
            'labels': ['月', '火', '水', '木', '金', '土', '日'],
            'data': [random.randint(50, 100) for _ in range(7)]  # ダミーデータ
        }
        
        return JsonResponse({
            'genre_data': {
                'labels': list(genre_counts.keys()),
                'data': list(genre_counts.values())
            },
            'artist_correlation': artist_correlation,
            'trend_data': trend_data
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_mood_recommendations(request, mood_id):
    """ムード別のおすすめプレイリストを取得するAPI"""
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        # ムードに基づく検索クエリのマッピング
        mood_queries = {
            'energetic': 'energy:0.8',
            'relax': 'energy:0.3',
            'focus': 'instrumentalness:0.8',
            'party': 'danceability:0.8'
        }
        
        query = mood_queries.get(mood_id, 'energy:0.5')
        results = spotify.search(
            q=f'{query} year:2024', 
            type='track', 
            market='JP', 
            limit=10
        )
        
        tracks = [{
            'title': track['name'],
            'artist': track['artists'][0]['name'],
            'album_cover': track['album']['images'][0]['url'] if track['album']['images'] else None,
            'preview_url': track['preview_url'],
            'duration': track['duration_ms'] // 1000,  # ミリ秒から秒に変換
            'mood_id': mood_id
        } for track in results['tracks']['items']]
        
        return JsonResponse({'tracks': tracks})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def create_story_modal(request):
    """ストーリー作成モーダルを表示するビュー"""
    return render(request, 'core/create_story_modal.html')

@login_required
def messages_view(request):
    """メッセージ一覧を表示するビュー"""
    conversations = request.user.conversations.all().prefetch_related('participants')
    
    # 各会話の情報を準備
    conversations_data = []
    for conversation in conversations:
        # 会話の相手を取得
        other_user = conversation.participants.exclude(id=request.user.id).first()
        
        # 未読メッセージ数を取得
        unread_count = Message.objects.filter(
            sender=other_user,
            recipient=request.user,
            is_read=False
        ).count()
        
        conversations_data.append({
            'conversation': conversation,
            'other_user': other_user,
            'unread_count': unread_count,
            'last_message': conversation.last_message
        })
    
    return render(request, 'core/messages.html', {
        'conversations_data': conversations_data
    })

@login_required
def conversation_detail(request, conversation_id):
    """特定の会話の詳細を表示するビュー"""
    conversation = get_object_or_404(Conversation, id=conversation_id, participants=request.user)
    other_user = conversation.participants.exclude(id=request.user.id).first()
    
    # この会話の未読メッセージを既読にする
    Message.objects.filter(
        sender=other_user,
        recipient=request.user,
        is_read=False
    ).update(is_read=True)
    
    # 全ての会話を取得（サイドバー用）
    all_conversations = []
    for conv in request.user.conversations.all():
        conv_other_user = conv.participants.exclude(id=request.user.id).first()
        all_conversations.append({
            'conversation': conv,
            'other_user': conv_other_user,
            'is_active': conv.id == conversation_id,
            'last_message': conv.last_message
            
        })
    
    messages = Message.objects.filter(
        sender__in=conversation.participants.all(),
        recipient__in=conversation.participants.all()
    ).order_by('created_at')
    
    # メッセージをJSONシリアライズ可能な形式に変換
    messages_json = []
    for message in messages:
        attachments = [{
            'url': attachment.file.url,
            'type': attachment.file_type
        } for attachment in message.attachments.all()]
        
        messages_json.append({
            'content': message.content,
            'sender_username': message.sender.username,
            'attachments': attachments,
            'created_at': message.created_at.isoformat()
        })
    
    return render(request, 'core/conversation_detail.html', {
        'conversation': conversation,
        'messages': messages,
        'messages_json': json.dumps(messages_json),
        'other_user': other_user,
        'all_conversations': all_conversations
    })

@login_required
def new_conversation(request, username):
    """新しい会話を開始するビュー"""
    other_user = get_object_or_404(User, username=username)
    
    # 既存の会話を探す
    existing_conversation = Conversation.objects.filter(
        participants=request.user
    ).filter(
        participants=other_user
    ).first()
    
    if existing_conversation:
        return redirect('core:conversation_detail', conversation_id=existing_conversation.id)
    
    # 新しい会話を作成
    conversation = Conversation.objects.create()
    conversation.participants.add(request.user, other_user)
    
    return redirect('core:conversation_detail', conversation_id=conversation.id)

@login_required
def send_message(request):
    if request.method == 'POST':
        try:
            recipient_id = request.POST.get('recipient_id')
            content = request.POST.get('content', '')
            
            recipient = get_object_or_404(User, id=recipient_id)
            
            # 会話を取得または作成
            conversation = Conversation.objects.filter(
                participants=request.user
            ).filter(
                participants=recipient
            ).first()
            
            if not conversation:
                conversation = Conversation.objects.create()
                conversation.participants.add(request.user, recipient)
            
            # メッセージを作成
            message = Message.objects.create(
                sender=request.user,
                recipient=recipient,
                content=content
            )

            # 添付ファイルの処理
            attachments = []
            for key in request.FILES:
                if key.startswith('attachment'):
                    file = request.FILES[key]
                    attachment = MessageAttachment.objects.create(
                        message=message,
                        file=file
                    )
                    attachments.append({
                        'url': attachment.file.url,
                        'type': attachment.file_type,
                        'name': file.name
                    })
            
            # 会話の最新メッセージを更新
            conversation.last_message = message
            conversation.save()
            
            return JsonResponse({
                'status': 'success',
                'message': {
                    'id': message.id,
                    'content': message.content,
                    'attachments': attachments,
                    'created_at': message.created_at.isoformat(),
                    'sender_username': message.sender.username,
                    'sender_avatar': message.sender.profile.avatar.url if message.sender.profile.avatar else None
                }
            })
            
        except Exception as e:
            logger.error(f"メッセージ送信エラー: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': '無効なリクエストです'}, status=400)

@login_required
def get_unread_messages_count(request):
    """未読メッセージの総数を取得するAPI"""
    count = Message.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()
    return JsonResponse({'count': count})

@login_required
def toggle_follow(request, username):
    if request.method == 'POST':
        try:
            target_user = User.objects.get(username=username)
            user_profile = request.user.profile
            target_profile = target_user.profile

            if target_profile in user_profile.following.all():
                # フォロー解除
                user_profile.following.remove(target_profile)
                status = 'unfollowed'
            else:
                # フォロー
                user_profile.following.add(target_profile)
                status = 'followed'

            # フォロワー数を取得（target_userをフォローしているユーザー数）
            follower_count = Profile.objects.filter(following=target_profile).count()

            return JsonResponse({
                'status': status,
                'follower_count': follower_count
            })
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def get_post_likes(request, post_id):
    try:
        post = get_object_or_404(MusicPost, id=post_id)
        users = post.likes.all().select_related('profile')
        users_data = [{
            'username': user.username,
            'name': user.get_full_name(),
            'avatar': user.profile.avatar.url if user.profile.avatar else None
        } for user in users]
        
        return JsonResponse({
            'status': 'success',
            'users': users_data
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': 'エラーが発生しました。'
        }, status=500)

def get_post_comments(request, post_id):
    if request.method == 'GET':
        try:
            offset = int(request.GET.get('offset', 0))
            limit = int(request.GET.get('limit', 10))
            post = MusicPost.objects.get(id=post_id)
            
            comments = post.comments.all()[offset:offset+limit]
            comments_data = [{
                'content': comment.content,
                'user': {
                    'username': comment.user.username,
                    'avatar_url': comment.user.profile.avatar.url if comment.user.profile.avatar else None
                }
            } for comment in comments]
            
            return JsonResponse({
                'status': 'success',
                'comments': comments_data
            })
        except MusicPost.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': '投稿が見つかりません。'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({
        'status': 'error',
        'message': '無効なリクエストメソッドです。'
    }, status=405)

def calculate_genre_similarity(user1, user2):
    """二人のユーザー間のジャンルの類似性を計算"""
    try:
        # ユーザー1のジャンルを取得
        user1_genres = set(user1.favorite_genres if user1.favorite_genres else [])
        
        # ユーザー2のジャンルを取得
        user2_genres = set(user2.favorite_genres if user2.favorite_genres else [])
        
        # 共通のジャンル数を計算
        common_genres = user1_genres & user2_genres
        
        # 全ジャンル数を計算
        all_genres = user1_genres | user2_genres
        
        # Jaccard類似度を計算（0から1の範囲）
        if len(all_genres) > 0:
            similarity = len(common_genres) / len(all_genres)
        else:
            similarity = 0
            
        return similarity
        
    except Exception as e:
        logger.error(f"ジャンル類似性計算エラー: {str(e)}")
        return 0

def get_tracks_by_genres(genres, limit=5):
    """ジャンルに基づいて曲を取得"""
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        tracks = []
        # 上位3ジャンルまでで検索
        for genre in genres[:3]:
            try:
                results = spotify.search(
                    q=f'genre:{genre}',
                    type='track',
                    market='JP',
                    limit=limit
                )
                
                for track in results['tracks']['items']:
                    track_info = {
                        'id': track['id'],
                        'name': track['name'],
                        'artist': track['artists'][0]['name'],
                        'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                        'preview_url': track['preview_url']
                    }
                    if track_info not in tracks:  # 重複を避ける
                        tracks.append(track_info)
            except Exception as e:
                logger.error(f"ジャンル {genre} の曲検索に失敗: {str(e)}")
                continue
        
        return tracks
    except Exception as e:
        logger.error(f"ジャンルに基づく曲の取得に失敗: {str(e)}")
        return []

def get_artist_top_tracks(artist_id):
    """アーティストのトップトラックを取得"""
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=settings.SPOTIFY_CLIENT_ID,
            client_secret=settings.SPOTIFY_CLIENT_SECRET
        ))
        
        results = spotify.artist_top_tracks(artist_id, country='JP')
        tracks = []
        
        for track in results['tracks'][:5]:  # 上位5曲を取得
            track_info = {
                'id': track['id'],
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'preview_url': track['preview_url']
            }
            tracks.append(track_info)
            
        return tracks
    except Exception as e:
        logger.error(f"アーティストのトップトラック取得に失敗: {str(e)}")
        return []