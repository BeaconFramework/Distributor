# Copyright 2016 IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#

"""create amphora cluster table

Revision ID: e9573113afd2
Revises: 94135f95e292
Create Date: 2016-06-08 17:23:13.405002

"""

# revision identifiers, used by Alembic.
revision = 'e9573113afd2'
down_revision = '94135f95e292'

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        u'amphora_cluster',
        sa.Column(u'id', sa.String(36), nullable=False),
        sa.Column(u'cluster_name', sa.String(36), nullable=True),
        sa.Column(u'cooldown', sa.Integer(), nullable=True),
        sa.Column(u'desired_capacity', sa.Integer(), nullable=True),
        sa.Column(u'max_size', sa.Integer(), nullable=True),
        sa.Column(u'min_size', sa.Integer(), nullable=True),
        sa.Column(u'measurement_period', sa.Integer(), nullable=True),
        sa.Column(u'number_measurement_periods', sa.Integer(), nullable=True),
        sa.Column(u'scale_up_threshold', sa.Integer(), nullable=True),
        sa.Column(u'scale_down_threshold', sa.Integer(), nullable=True),
        sa.Column(u'load_balancer_id', sa.String(36), nullable=True),
        sa.Column(u'distributor_id', sa.String(36), nullable=True),
        sa.Column(u'provisioning_status', sa.String(16), nullable=True),
        sa.Column(u'operating_status', sa.String(16), nullable=True),
        sa.Column(u'enabled', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint(u'id'),
        sa.ForeignKeyConstraint([u'load_balancer_id'],
                                [u'load_balancer.id'],
                                name=u'fk_amphora_cluster_load_balancer_id'),
        sa.ForeignKeyConstraint([u'distributor_id'],
                                [u'distributor.id'],
                                name=u'fk_amphora_cluster_distributor_id'),
        sa.ForeignKeyConstraint([u'provisioning_status'],
                                [u'provisioning_status.name'],
                                name=
                                u'fk_amphora_cluster_provisioning_status_name'
                                ),
        sa.ForeignKeyConstraint([u'operating_status'],
                                [u'operating_status.name'],
                                name=
                                u'fk_amphora_cluster_operating_status_name')
    )