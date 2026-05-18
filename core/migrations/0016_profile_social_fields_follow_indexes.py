# Generated for the profile social redesign.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_customuser_cover_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_private',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='customuser',
            name='is_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='customuser',
            name='location',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='customuser',
            name='website',
            field=models.URLField(blank=True, default=''),
        ),
        migrations.AddIndex(
            model_name='follow',
            index=models.Index(fields=['follower', 'created_at'], name='core_follow_followe_1b666a_idx'),
        ),
        migrations.AddIndex(
            model_name='follow',
            index=models.Index(fields=['following', 'created_at'], name='core_follow_followi_ada48c_idx'),
        ),
        migrations.AddIndex(
            model_name='follow',
            index=models.Index(fields=['follower', 'following'], name='core_follow_followe_26835a_idx'),
        ),
    ]
