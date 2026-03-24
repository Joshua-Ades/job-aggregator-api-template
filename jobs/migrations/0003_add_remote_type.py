from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0002_add_tracking_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="remote_type",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=50,
                help_text='AI-extracted work arrangement: "Remote", "Hybrid", or "On-site".',
            ),
        ),
    ]
