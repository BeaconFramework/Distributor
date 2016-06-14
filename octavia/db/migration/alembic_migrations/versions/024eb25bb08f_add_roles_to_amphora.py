#    Copyright 2016 IBM Corp.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""add_roles_to_amphora

Revision ID: 024eb25bb08f
Revises: e9573113afd2
Create Date: 2016-08-15 15:56:22.588796

"""

# revision identifiers, used by Alembic.
revision = '024eb25bb08f'
down_revision = 'e9573113afd2'

from alembic import op
import sqlalchemy as sa
from sqlalchemy import sql


def upgrade():
    insert_table = sql.table(
        u'amphora_roles',
        sql.column(u'name', sa.String),
        sql.column(u'description', sa.String)
    )

    op.bulk_insert(
        insert_table,
        [
            {'name': 'ACTIVE_ACTIVE'},
            {'name': 'ACTIVE_STANDBY'}
        ]
    )