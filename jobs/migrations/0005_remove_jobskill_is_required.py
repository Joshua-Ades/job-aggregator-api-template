from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0004_add_location_fields"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="jobskill",
            name="is_required",
        ),
    ]
