from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="last_seen_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Timestamp of the most recent fetch cycle that returned this job.",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text="False when the job no longer appears in API results.",
            ),
        ),
    ]
