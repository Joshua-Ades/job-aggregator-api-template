from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0005_remove_jobskill_is_required"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="skill",
            table="skill",
        ),
        migrations.AlterModelTable(
            name="job",
            table="job",
        ),
        migrations.AlterModelTable(
            name="jobskill",
            table="job_skill",
        ),
    ]
