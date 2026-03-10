from django.db import migrations


def create_missing_tables(apps, schema_editor):
    connection = schema_editor.connection
    existing_tables = set(connection.introspection.table_names())

    models_to_create = [
        apps.get_model("contracts", "ContractChannelContent"),
        apps.get_model("contracts", "ContractChannelDailyMetric"),
        apps.get_model("contracts", "ContractChannelInsightSnapshot"),
    ]

    for model in models_to_create:
        if model._meta.db_table not in existing_tables:
            schema_editor.create_model(model)
            existing_tables.add(model._meta.db_table)


def reverse_drop_tables(apps, schema_editor):
    connection = schema_editor.connection
    existing_tables = set(connection.introspection.table_names())

    models_to_drop = [
        apps.get_model("contracts", "ContractChannelInsightSnapshot"),
        apps.get_model("contracts", "ContractChannelDailyMetric"),
        apps.get_model("contracts", "ContractChannelContent"),
    ]

    for model in models_to_drop:
        if model._meta.db_table in existing_tables:
            schema_editor.delete_model(model)
            existing_tables.remove(model._meta.db_table)


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_missing_tables, reverse_drop_tables),
    ]