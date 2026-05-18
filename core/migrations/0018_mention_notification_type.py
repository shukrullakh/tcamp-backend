from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def remove_self_follows(apps, schema_editor):
    Follow = apps.get_model('core', 'Follow')
    Follow.objects.filter(follower_id=models.F('following_id')).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_searchquery_repost_quote_text'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(choices=[('like', 'Like'), ('answer', 'Answer'), ('reply', 'Reply'), ('follow', 'Follow'), ('new_question', 'New Question'), ('mention', 'Mention')], max_length=20),
        ),
        migrations.CreateModel(
            name='Mention',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('mentioned_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions_made', to=settings.AUTH_USER_MODEL)),
                ('mentioned_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions_received', to=settings.AUTH_USER_MODEL)),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='core.question')),
            ],
            options={
                'indexes': [models.Index(fields=['mentioned_user', 'created_at'], name='core_mentio_mention_0979a0_idx'), models.Index(fields=['question', 'mentioned_user'], name='core_mentio_questio_2ae15a_idx')],
                'unique_together': {('mentioned_user', 'question')},
            },
        ),
        migrations.RunPython(remove_self_follows, migrations.RunPython.noop),
    ]
