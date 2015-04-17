# Copyright (c) 2014 ChinaNetCenter
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import sqlalchemy


def downgrade_region_table_with_column_drop(meta, migrate_engine):
    region_table = sqlalchemy.Table('region', meta, autoload=True)
    region_table.drop_column('owner')


def upgrade_region_table(meta, migrate_engine):
    region_table = sqlalchemy.Table('region', meta, autoload=True)
    region_table.create_column(sqlalchemy.Column('owner',
                                                 sqlalchemy.String(64)))


def upgrade(migrate_engine):
    meta = sqlalchemy.MetaData()
    meta.bind = migrate_engine
    upgrade_region_table(meta, migrate_engine)


def downgrade(migrate_engine):
    meta = sqlalchemy.MetaData()
    meta.bind = migrate_engine
    downgrade_region_table_with_column_drop(meta, migrate_engine)
