# Generated by Django 5.0 on 2025-01-16 07:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_musicstory_storyview'),
    ]

    operations = [
        migrations.AddField(
            model_name='musicpost',
            name='analysis_points',
            field=models.JSONField(blank=True, default=list, help_text='楽曲の分析ポイント'),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='listening_context',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='lyrics_excerpt',
            field=models.TextField(blank=True, help_text='印象的な歌詞を共有'),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='music_elements',
            field=models.JSONField(blank=True, default=list, help_text='印象的な楽器やサウンド'),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='post_type',
            field=models.CharField(choices=[('review', 'レビュー'), ('analysis', '楽曲分析'), ('memory', '思い出'), ('recommendation', 'おすすめ'), ('playlist', 'プレイリスト紹介')], default='review', max_length=50),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='rating',
            field=models.IntegerField(blank=True, choices=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)], null=True),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='recommended_for',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='related_artists',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='musicpost',
            name='tags',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='musicstory',
            name='background_theme',
            field=models.CharField(choices=[('default', 'デフォルト'), ('wave', '波形'), ('stars', '星空'), ('gradient', 'グラデーション'), ('vinyl', 'レコード')], default='default', max_length=50),
        ),
        migrations.AddField(
            model_name='musicstory',
            name='listening_status',
            field=models.CharField(choices=[('now_playing', '今聴いている'), ('just_discovered', '発見した'), ('recommendation', 'おすすめ'), ('memory', '思い出の一曲')], default='now_playing', max_length=50),
        ),
        migrations.AddField(
            model_name='musicstory',
            name='quick_reactions',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='musicstory',
            name='reaction_count',
            field=models.IntegerField(default=0),
        ),
    ]
