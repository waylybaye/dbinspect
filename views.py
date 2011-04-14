# coding: utf-8
from django.db import connection, transaction, models
from django.http import HttpResponse
from django.shortcuts import render_to_response
import re

class Error:
    def __init__(self, model, attr_name, error):
        self.model = model
        self.model_name = model._meta.object_name
        self.app_label = model._meta.app_label
        self.attr_name = attr_name
        self.error = error

def inspect(request):
    """
    """
    cursor  = connection.cursor()
    site_models = models.get_models()

    create_sqls = []
    errors = []
    mapping = {
        'integer':  'int(11)',
        'smallint': 'smallint(6)',
        'bool':     'tinyint(1)',
        'integer AUTO_INCREMENT': 'int(11)',
    }

    for model in site_models:
        model_fields = []
        table_name = model._meta.db_table
        try:
            # will raised an exception if table doesn't exist
            cursor.execute("show create table " + table_name)
        except Exception, e:
            errors.append(Error(model, "", e))
            continue

        sql = cursor.fetchone()[1]
        create_sqls.append(sql)

        defined_indexs = []

        # iterate all the model fields
        for field in model._meta.fields:
            model_fields.append(field.attname)
            column_name = field.column or field.attname

            # test type unmatch
            results = re.search('`%s`\s([^\s^,]+)[,\s]' % column_name, sql)
            if results:
                db_type = results.groups()[0]
                field_type = mapping.get(field.db_type(), field.db_type())
                if  db_type != field_type:
                    errors.append(
                        Error( model, field.attname,
                            'defined "%s" but "%s" in db' % (field.db_type(), db_type)
                        ))


            # search the unique key definition in sql
            results = re.search('UNIQUE KEY `%s` \(`%s`\)' % (column_name, column_name), sql)
            if results and not field.unique:
                errors.append(Error( model, field.attname,
                    "was unique in db but not defined in model"
                ))

            if field.unique and not results:
                if not field.primary_key:
                    errors.append( Error( model, field.attname,
                        "defined unique but not unique in db",
                    ))

            # unique will create index
            if field.unique and not field.primary_key:
                defined_indexs.append(column_name)

            # db_index attr in field
            if field.db_index and not field.primary_key:
                defined_indexs.append(column_name)

        db_columns = re.findall("\n\s+`([^`.]+)`", sql)
        if table_name in db_columns:
            db_columns.remove(table_name)

        missing_column = set(db_columns) - set(model_fields)
        for column in missing_column:
            errors.append( Error( model, column,
                "exist in db but not defined",
            ))

        # test indexs
        cursor.execute("show index from %s;" % table_name)
        indexs_records = cursor.fetchall()

        # ignore parimary key
        indexed_columns = [ record[4] for record in indexs_records if not record[2] == 'PRIMARY' ]

        # test unique together
        for unique_together in model._meta.unique_together:
            for _name in unique_together:
                defined_indexs.append(_name)

        missing_index = set(defined_indexs) - set(indexed_columns)
        missing_defined = set(indexed_columns) - set(defined_indexs)

        for name in missing_index:
            errors.append(Error( model, name, "missing index in db",))

        for name in missing_defined:
            errors.append(Error( model, name,
                "missing index defination in model."
            ))
            #print indexs_records

    return render_to_response("dbinpect.html", {'errors': errors})
