# Copyright 2015 Hewlett-Packard Development Company, L.P.
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

import datetime

from oslo_config import cfg
from oslo_log import log as logging
import six
import sqlalchemy
from stevedore import driver as stevedore_driver

from octavia.common import constants
from octavia.common import stats
from octavia.controller.healthmanager import update_serializer
from octavia.controller.queue import event_queue
from octavia.db import api as db_api
from octavia.db import repositories as repo
from octavia.i18n import _LE, _LW


LOG = logging.getLogger(__name__)


class UpdateHealthDb(object):
    def __init__(self):
        super(UpdateHealthDb, self).__init__()
        # first setup repo for amphora, listener,member(nodes),pool repo
        self.event_streamer = stevedore_driver.DriverManager(
            namespace='octavia.controller.queues',
            name=cfg.CONF.health_manager.event_streamer_driver,
            invoke_on_load=True).driver
        self.amphora_repo = repo.AmphoraRepository()
        self.amphora_health_repo = repo.AmphoraHealthRepository()
        self.listener_repo = repo.ListenerRepository()
        self.loadbalancer_repo = repo.LoadBalancerRepository()
        self.member_repo = repo.MemberRepository()
        self.pool_repo = repo.PoolRepository()

    def emit(self, info_type, info_id, info_obj):
        cnt = update_serializer.InfoContainer(info_type, info_id, info_obj)
        self.event_streamer.emit(cnt)

    def _update_status_and_emit_event(self, session, repo, entity_type,
                                      entity_id, new_op_status):
        entity = repo.get(session, id=entity_id)
        if entity.operating_status.lower() != new_op_status.lower():
            LOG.debug("%s %s status has changed from %s to "
                      "%s. Updating db and sending event.",
                      entity_type, entity_id, entity.operating_status,
                      new_op_status)
            repo.update(session, entity_id, operating_status=new_op_status)
            self.emit(
                entity_type, entity_id,
                {constants.OPERATING_STATUS: new_op_status})

    def update_health(self, health):
        """This function is to update db info based on amphora status

        :param health: map object that contains amphora, listener, member info
        :type map: string
        :returns: null

        The input health data structure is shown as below:

        health = {
            "id": self.FAKE_UUID_1,
            "listeners": {
                "listener-id-1": {"status": constants.OPEN, "pools": {
                    "pool-id-1": {"status": constants.UP,
                                  "members": {"member-id-1": constants.ONLINE}
                                  }
                }
                }
            }
        }

        """
        session = db_api.get_session()

        # We need to see if all of the listeners are reporting in
        expected_listener_count = 0
        lbs_on_amp = self.amphora_repo.get_all_lbs_on_amphora(session,
                                                              health['id'])
        for lb in lbs_on_amp:
            listener_count = self.listener_repo.count(session,
                                                      load_balancer_id=lb.id)
            expected_listener_count += listener_count

        listeners = health['listeners']

        # Do not update amphora health if the reporting listener count
        # does not match the expected listener count
        if len(listeners) == expected_listener_count:

            # if the input amphora is healthy, we update its db info
            self.amphora_health_repo.replace(session, health['id'],
                                             last_update=(datetime.
                                                          datetime.utcnow()))
        else:
            LOG.warning(_LW('Amphora %(id)s health message reports %(found)i '
                            'listeners when %(expected)i expected'),
                        {'id': health['id'],
                         'found': len(listeners),
                         'expected': expected_listener_count})

        # We got a heartbeat so lb is healthy until proven otherwise
        lb_status = constants.ONLINE

        # update listener and nodes db information
        for listener_id, listener in six.iteritems(listeners):

            listener_status = None
            # OPEN = HAProxy listener status nbconn < maxconn
            if listener.get('status') == constants.OPEN:
                listener_status = constants.ONLINE
            # FULL = HAProxy listener status not nbconn < maxconn
            elif listener.get('status') == constants.FULL:
                listener_status = constants.DEGRADED
                if lb_status == constants.ONLINE:
                    lb_status = constants.DEGRADED
            else:
                LOG.warning(_LW('Listener %(list)s reported status of '
                                '%(status)s'), {'list': listener_id,
                            'status': listener.get('status')})

            try:
                if listener_status is not None:
                    self._update_status_and_emit_event(
                        session, self.listener_repo, constants.LISTENER,
                        listener_id, listener_status
                    )
            except sqlalchemy.orm.exc.NoResultFound:
                LOG.error(_LE("Listener %s is not in DB"), listener_id)

            pools = listener['pools']
            for pool_id, pool in six.iteritems(pools):

                pool_status = None
                # UP = HAProxy backend has working or no servers
                if pool.get('status') == constants.UP:
                    pool_status = constants.ONLINE
                # DOWN = HAProxy backend has no working servers
                elif pool.get('status') == constants.DOWN:
                    pool_status = constants.ERROR
                    lb_status = constants.ERROR
                else:
                    LOG.warning(_LW('Pool %(pool)s reported status of '
                                    '%(status)s'), {'pool': pool_id,
                                'status': pool.get('status')})

                members = pool['members']
                for member_id, status in six.iteritems(members):

                    member_status = None
                    if status == constants.UP:
                        member_status = constants.ONLINE
                    elif status == constants.DOWN:
                        member_status = constants.ERROR
                        if pool_status == constants.ONLINE:
                            pool_status = constants.DEGRADED
                            if lb_status == constants.ONLINE:
                                lb_status = constants.DEGRADED
                    elif status == constants.NO_CHECK:
                        member_status = constants.NO_MONITOR
                    else:
                        LOG.warning(_LW('Member %(mem)s reported status of '
                                        '%(status)s'), {'mem': member_id,
                                    'status': status})

                    try:
                        if member_status is not None:
                            self._update_status_and_emit_event(
                                session, self.member_repo, constants.MEMBER,
                                member_id, member_status
                            )
                    except sqlalchemy.orm.exc.NoResultFound:
                        LOG.error(_LE("Member %s is not able to update "
                                      "in DB"), member_id)

                try:
                    if pool_status is not None:
                        self._update_status_and_emit_event(
                            session, self.pool_repo, constants.POOL,
                            pool_id, pool_status
                        )
                except sqlalchemy.orm.exc.NoResultFound:
                    LOG.error(_LE("Pool %s is not in DB"), pool_id)

        # Update the load balancer status last
        # TODO(sbalukoff): This logic will need to be adjusted if we
        # start supporting multiple load balancers per amphora
        lb_id = self.amphora_repo.get(
            session, id=health['id']).load_balancer_id
        if lb_id is not None:
            try:
                self._update_status_and_emit_event(
                    session, self.loadbalancer_repo,
                    constants.LOADBALANCER, lb_id, lb_status
                )
            except sqlalchemy.orm.exc.NoResultFound:
                LOG.error(_LE("Load balancer %s is not in DB"), lb_id)


class UpdateDistributorHealthDb(object):
    def __init__(self):
        super(UpdateDistributorHealthDb, self).__init__()
        self.event_streamer = stevedore_driver.DriverManager(
            namespace='octavia.controller.queues',
            name=cfg.CONF.health_manager.event_streamer_driver,
            invoke_on_load=True).driver
        self.loadbalancer_repo = repo.LoadBalancerRepository()
        self.distributor_repo = repo.DistributorRepository()

    def emit(self, info_type, info_id, info_obj):
        cnt = update_serializer.InfoContainer(info_type, info_id, info_obj)
        self.event_streamer.emit(cnt)

    def update_distributor_health(self, health):
        """This function is to update db info based on amphora status

        :type health: dict
        :param health: map object that contains distributor, amphora info

        The input health data structure is shown as below:

        health = {
            "distributor-id": self.FAKE_UUID_1,
            "provisioning-state": {
                "state": service provisioning status,
                "reason": str
            }
            "loadbalancers": {
                "lb-id-1": {
                    "status": instance provisioning status
                    "size": int
                    "registered": int
                }
            }
        }

        """
        session = db_api.get_session()
        distributor_id = health['distributor_id']
        distributor_state = health['provisioning_state']['state']
        if distributor_state == constants.DISTRIBUTOR_BOOTING:
            LOG.debug("Distributor %s is still booting -- skipping"
                      " health message.", distributor_id)
            # nothing to report
            return
        elif distributor_state == constants.DISTRIBUTOR_FULL:
            # @TODO handle FULL state -- eg, set quota limit
            LOG.warning(_LW("Distributor %s is unavailable for new"
                            " requests."),
                        distributor_id)
        elif distributor_state == constants.DISTRIBUTOR_ERROR:
            LOG.warning(_LW("Distributor %s is in error state"),
                        distributor_id)
            # @TODO set state of distributor so it is recycled

        expected_lbs = self.distributor_repo.get_all_lbs_on_distributor(
            session, distributor_id)
        reported_lbs = health.get('loadbalancers', {})

        if any(lb not in expected_lbs for lb in reported_lbs):
            LOG.warning(_LW("Distributor %s reported unexpected"
                            " loadbalancer ids"), distributor_id)
            # @TODO something is wrong here we should recycle

        # NO_MONITOR for all missing lbs
        reported_lbs.update(
            (lb, {'status': constants.NO_MONITOR})
            for lb in expected_lbs if lb not in reported_lbs)

        # do actual update per lb
        for lb_id, lb in six.iteritems(reported_lbs):
            try:
                lb_in_db = self.loadbalancer_repo.get(session, id=lb_id)
            except sqlalchemy.orm.exc.NoResultFound:
                LOG.error(_LE("Load balancer %s is not in DB"), lb_id)
                continue

            reported_lb_op_status = lb['status']
            if (reported_lb_op_status == constants.ERROR or
                    distributor_state == constants.DISTRIBUTOR_ERROR):
                # Distributor error currently sets all LBs to error too.
                # This is conservative. Could try to recycle Distributor
                # without recycling the LBs
                new_lb_op_status = constants.ERROR
            elif (reported_lb_op_status == constants.DEGRADED and
                    lb_in_db.operating_status == constants.ONLINE):
                new_lb_op_status = constants.DEGRADED
            elif (reported_lb_op_status == constants.NO_MONITOR and
                  lb_in_db.operating_status == constants.ONLINE):
                # @TODO Ignoring for now. Should we do anything here?
                new_lb_op_status = None
            else:
                new_lb_op_status = None
            # @TODO verify size and registered
            if new_lb_op_status:
                LOG.debug("%s %s status has changed from %s to "
                          "%s. Updating db and sending event.",
                          constants.LOADBALANCER, lb_id,
                          lb_in_db.operating_status,
                          new_lb_op_status)
                self.loadbalancer_repo.update(
                    session, lb_id, operating_status=new_lb_op_status)
                self.emit(constants.LOADBALANCER, lb_id,
                          {constants.OPERATING_STATUS: new_lb_op_status})


class UpdateStatsDb(stats.StatsMixin):

    def __init__(self):
        super(UpdateStatsDb, self).__init__()
        self.event_streamer = event_queue.EventStreamerNeutron()
        self.repo_listener = repo.ListenerRepository()

    def emit(self, info_type, info_id, info_obj):
        cnt = update_serializer.InfoContainer(info_type, info_id, info_obj)
        self.event_streamer.emit(cnt)

    def update_stats(self, health_message):
        """This function is to update the db with listener stats

        :param health_message: The health message containing the listener stats
        :type map: string
        :returns: null

        health = {
            "id": self.FAKE_UUID_1,
            "listeners": {
                "listener-id-1": {
                    "status": constants.OPEN,
                    "stats": {
                        "ereq":0,
                        "conns": 0,
                        "totconns": 0,
                        "rx": 0,
                        "tx": 0,
                    },
                    "pools": {
                        "pool-id-1": {
                            "status": constants.UP,
                            "members": {"member-id-1": constants.ONLINE}
                        }
                    }
                }
            }
        }

        """
        session = db_api.get_session()

        amphora_id = health_message['id']
        listeners = health_message['listeners']
        for listener_id, listener in six.iteritems(listeners):

            stats = listener.get('stats')
            stats = {'bytes_in': stats['rx'], 'bytes_out': stats['tx'],
                     'active_connections': stats['conns'],
                     'total_connections': stats['totconns'],
                     'request_errors': stats['ereq']}
            LOG.debug("Updating listener stats in db and sending event.")
            LOG.debug("Listener %s / Amphora %s stats: %s",
                      listener_id, amphora_id, stats)
            self.listener_stats_repo.replace(
                session, listener_id, amphora_id, **stats)

            listener_stats = self.get_listener_stats(session, listener_id)
            self.emit(
                'listener_stats', listener_id, listener_stats.get_stats())

            listener_db = self.repo_listener.get(session, id=listener_id)
            lb_stats = self.get_loadbalancer_stats(
                session, listener_db.load_balancer_id)
            self.emit('loadbalancer_stats',
                      listener_db.load_balancer_id, lb_stats.get_stats())
