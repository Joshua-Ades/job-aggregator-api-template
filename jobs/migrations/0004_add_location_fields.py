from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0003_add_remote_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="city",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=100,
                help_text="AI-extracted, normalized city name (e.g. 'Tel Aviv').",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="state",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=100,
                help_text="AI-extracted, normalized district/state (e.g. 'Tel Aviv District').",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="region",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=100,
                help_text="AI-extracted, normalized broader region (e.g. 'Center', 'North').",
            ),
        ),
        migrations.RemoveField(
            model_name="skill",
            name="frequency",
        ),
        migrations.AlterModelOptions(
            name="skill",
            options={"ordering": ["name"]},
        ),
    ]
