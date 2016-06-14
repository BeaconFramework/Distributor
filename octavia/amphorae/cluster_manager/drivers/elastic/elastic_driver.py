# Copyright 2016 IBM
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

from oslo_log import log as logging

from octavia.amphorae.cluster_manager.drivers import driver_base

LOG = logging.getLogger(__name__)


class ActiveActiveManager(object):
    def __init__(self):
        super(ActiveActiveManager, self).__init__()


class AmphoraClusterDriver(driver_base.AmphoraClusterDriver):
    def __init__(self):
        super(AmphoraClusterDriver, self).__init__()
        self.driver = ActiveActiveManager()