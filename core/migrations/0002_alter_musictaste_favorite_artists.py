# Generated by Django 5.0 on 2025-01-16 05:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_profile_favorite_artists'),
    ]

    operations = [
        migrations.AlterField(
            model_name='musictaste',
            name='favorite_artists',
            field=models.JSONField(default=list),
        ),
    ]
