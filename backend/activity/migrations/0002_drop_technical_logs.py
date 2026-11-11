from django.db import migrations


class Migration(migrations.Migration):
    """Technical logs are no longer stored: the table of the removed logging app goes."""

    dependencies = [
        ('activity', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            'DROP TABLE IF EXISTS django_db_logger_statuslog',
            migrations.RunSQL.noop,
        ),
    ]
