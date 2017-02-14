#    Copyright 2014 Rackspace
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

import logging

from oslo_config import cfg
from pecan import rest
from stevedore import driver as stevedore_driver

from octavia.common import data_models
from octavia.common import exceptions
from octavia.db import repositories
from octavia.i18n import _LE

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseController(rest.RestController):

    def __init__(self):
        super(BaseController, self).__init__()
        self.repositories = repositories.Repositories()
        self.handler = stevedore_driver.DriverManager(
            namespace='octavia.api.handlers',
            name=CONF.api_handler,
            invoke_on_load=True
        ).driver

    @staticmethod
    def _convert_db_to_type(db_entity, to_type, children=False):
        """Converts a data model into an Octavia WSME type

        :param db_entity: data model to convert
        :param to_type: converts db_entity to this time
        """
        if isinstance(to_type, list):
            to_type = to_type[0]

        def _convert(db_obj):
            return to_type.from_data_model(db_obj, children=children)
        if isinstance(db_entity, list):
            converted = [_convert(db_obj) for db_obj in db_entity]
        else:
            converted = _convert(db_entity)
        return converted

    @staticmethod
    def _get_db_obj(session, repo, data_model, id):
        """Gets an object from the database and returns it."""
        db_obj = repo.get(session, id=id)
        if not db_obj:
            LOG.exception(_LE("{name} {id} not found").format(
                name=data_model._name(), id=id))
            raise exceptions.NotFound(
                resource=data_model._name(), id=id)
        return db_obj

    def _get_db_lb(self, session, id):
        """Get a load balancer from the database."""
        return self._get_db_obj(session, self.repositories.load_balancer,
                                data_models.LoadBalancer, id)

    def _get_db_listener(self, session, id):
        """Get a listener from the database."""
        return self._get_db_obj(session, self.repositories.listener,
                                data_models.Listener, id)

    def _get_db_pool(self, session, id):
        """Get a pool from the database."""
        return self._get_db_obj(session, self.repositories.pool,
                                data_models.Pool, id)

    def _get_db_member(self, session, id):
        """Get a member from the database."""
        return self._get_db_obj(session, self.repositories.member,
                                data_models.Member, id)

    def _get_db_l7policy(self, session, id):
        """Get a L7 Policy from the database."""
        return self._get_db_obj(session, self.repositories.l7policy,
                                data_models.L7Policy, id)

    def _get_db_l7rule(self, session, id):
        """Get a L7 Rule from the database."""
        return self._get_db_obj(session, self.repositories.l7rule,
                                data_models.L7Rule, id)

    def _get_default_quotas(self, project_id):
        """Gets the project's default quotas."""
        quotas = data_models.Quotas(
            project_id=project_id,
            load_balancer=CONF.quotas.default_load_balancer_quota,
            listener=CONF.quotas.default_listener_quota,
            pool=CONF.quotas.default_pool_quota,
            health_monitor=CONF.quotas.default_health_monitor_quota,
            member=CONF.quotas.default_member_quota)
        return quotas

    def _get_db_quotas(self, session, project_id):
        """Gets the project's quotas from the database, or responds with the

        default quotas.
        """
        # At this point project_id should not ever be None or Unset
        db_quotas = self.repositories.quotas.get(
            session, project_id=project_id)
        if not db_quotas:
            LOG.debug("No custom quotas for project %s. Returning "
                      "defaults...", project_id)
            db_quotas = self._get_default_quotas(project_id=project_id)
        else:
            # Fill in any that are using the configured defaults
            if db_quotas.load_balancer is None:
                db_quotas.load_balancer = (CONF.quotas.
                                           default_load_balancer_quota)
            if db_quotas.listener is None:
                db_quotas.listener = CONF.quotas.default_listener_quota
            if db_quotas.pool is None:
                db_quotas.pool = CONF.quotas.default_pool_quota
            if db_quotas.health_monitor is None:
                db_quotas.health_monitor = (CONF.quotas.
                                            default_health_monitor_quota)
            if db_quotas.member is None:
                db_quotas.member = CONF.quotas.default_member_quota
        return db_quotas

    def _get_lb_project_id(self, session, id):
        """Get the project_id of the load balancer from the database."""
        lb = self._get_db_obj(session, self.repositories.load_balancer,
                              data_models.LoadBalancer, id)
        return lb.project_id
