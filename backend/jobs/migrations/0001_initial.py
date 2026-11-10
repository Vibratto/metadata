

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='JobRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(db_index=True, max_length=50, verbose_name='kind')),
                ('params', models.JSONField(blank=True, default=dict, verbose_name='parameters')),
                ('status', models.CharField(choices=[('pending', 'pending'), ('running', 'running'), ('stopping', 'stopping'), ('stopped', 'stopped'), ('succeeded', 'succeeded'), ('failed', 'failed'), ('interrupted', 'interrupted')], default='pending', max_length=11, verbose_name='status')),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='started')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='finished')),
                ('done', models.PositiveIntegerField(default=0, verbose_name='done')),
                ('total', models.PositiveIntegerField(default=0, verbose_name='total')),
                ('current', models.CharField(blank=True, max_length=255, verbose_name='current item')),
                ('summary', models.JSONField(blank=True, default=dict, verbose_name='summary')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='job_runs', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'ordering': ['-started_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='JobRunLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveIntegerField(verbose_name='position')),
                ('level', models.CharField(choices=[('info', 'information'), ('warning', 'warning'), ('error', 'error')], default='info', max_length=7, verbose_name='level')),
                ('message', models.TextField(verbose_name='message')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date')),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lines', to='jobs.jobrun', verbose_name='run')),
            ],
            options={
                'ordering': ['run_id', 'position'],
                'constraints': [models.UniqueConstraint(fields=('run', 'position'), name='jobrunline_run_position_uniq')],
            },
        ),
    ]
