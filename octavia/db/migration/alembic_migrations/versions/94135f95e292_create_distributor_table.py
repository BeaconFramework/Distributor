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

"""create distributor table

Revision ID: 94135f95e292
Revises: 443fe6676637
Create Date: 2016-05-04 16:50:45.781429

"""

# revision identifiers, used by Alembic.
revision = '94135f95e292'
down_revision = '443fe6676637'

from alembic import op
import sqlalchemy as sa
from sqlalchemy import sql


def upgrade():

    op.create_table(
        u'distributor_provisioning_status',
        sa.Column(u'name', sa.String(30), primary_key=True),
        sa.Column(u'description', sa.String(255), nullable=True)
    )

    insert_table = sql.table(
        u'distributor_provisioning_status',
        sql.column(u'name', sa.String),
        sql.column(u'description', sa.String)
    )

    op.bulk_insert(
        insert_table,
        [
            {'name': 'DISTRIBUTOR_ACTIVE'},
            {'name': 'DISTRIBUTOR_ALLOCATED'},
            {'name': 'DISTRIBUTOR_BOOTING'},
            {'name': 'DISTRIBUTOR_READY'},
            {'name': 'DISTRIBUTOR_PENDING_CREATE'},
            {'name': 'DISTRIBUTOR_PENDING_UPDATE'},
            {'name': 'DISTRIBUTOR_PENDING_DELETE'},
            {'name': 'DISTRIBUTOR_DELETED'},
            {'name': 'DISTRIBUTOR_ERROR'}
        ]
    )

    op.create_table(
        u'distributor',
        sa.Column(u'id', sa.String(36), nullable=False),
        sa.Column(u'compute_id', sa.String(36), nullable=True),
        sa.Column(u'lb_network_ip', sa.String(64), nullable=True),
        sa.Column(u'status', sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint(u'id'),
        sa.ForeignKeyConstraint(
            [u'status'],
            [u'distributor_provisioning_status.name'],
            name=u'fk_distributor_provisioning_status_name'
        )
    )
