# Generated by Django 5.0 on 2025-01-17 08:03

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_playlist_likes_playlistcomment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Music',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='曲名')),
                ('artist', models.CharField(max_length=200, verbose_name='アーティスト')),
                ('album_art', models.URLField(blank=True, null=True, verbose_name='アルバムアート')),
                ('spotify_id', models.CharField(max_length=100, unique=True, verbose_name='Spotify ID')),
                ('preview_url', models.URLField(blank=True, null=True, verbose_name='プレビューURL')),
                ('duration_ms', models.IntegerField(default=0, verbose_name='再生時間(ms)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': '楽曲',
                'verbose_name_plural': '楽曲',
            },
        ),
        migrations.AlterModelOptions(
            name='playlist',
            options={'verbose_name': 'プレイリスト', 'verbose_name_plural': 'プレイリスト'},
        ),
        migrations.RemoveField(
            model_name='playlist',
            name='posts',
        ),
        migrations.AlterField(
            model_name='playlist',
            name='description',
            field=models.TextField(blank=True, verbose_name='説明'),
        ),
        migrations.AlterField(
            model_name='playlist',
            name='is_public',
            field=models.BooleanField(default=True, verbose_name='公開'),
        ),
        migrations.AlterField(
            model_name='playlist',
            name='likes',
            field=models.ManyToManyField(blank=True, related_name='liked_playlists', to=settings.AUTH_USER_MODEL, verbose_name='いいね'),
        ),
        migrations.AlterField(
            model_name='playlist',
            name='title',
            field=models.CharField(max_length=200, verbose_name='プレイリスト名'),
        ),
        migrations.AlterField(
            model_name='playlist',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='playlists', to=settings.AUTH_USER_MODEL, verbose_name='作成者'),
        ),
        migrations.CreateModel(
            name='PlaylistMusic',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.IntegerField(default=0, verbose_name='順番')),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('music', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.music', verbose_name='楽曲')),
                ('playlist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.playlist', verbose_name='プレイリスト')),
            ],
            options={
                'verbose_name': 'プレイリスト楽曲',
                'verbose_name_plural': 'プレイリスト楽曲',
                'ordering': ['order'],
                'unique_together': {('playlist', 'music')},
            },
        ),
        migrations.AddField(
            model_name='playlist',
            name='music',
            field=models.ManyToManyField(related_name='playlists', through='core.PlaylistMusic', to='core.music', verbose_name='楽曲'),
        ),
    ]
