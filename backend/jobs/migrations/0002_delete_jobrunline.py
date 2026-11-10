from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(
            name='JobRunLine',
        ),
    ]
