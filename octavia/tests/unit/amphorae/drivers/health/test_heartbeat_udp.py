# Copyright 2015 Hewlett-Packard Development Company, L.P.
# Copyright (c) 2015 Rackspace
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

import binascii
import random
import socket

import mock
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture

from octavia.amphorae.drivers.health import heartbeat_udp
from octavia.common import exceptions
from octavia.tests.unit import base


FAKE_ID = 1
KEY = 'TEST'
IP = '192.0.2.10'
PORT = random.randrange(1, 9000)
RLIMIT = random.randrange(1, 100)
FAKE_ADDRINFO = (
    socket.AF_INET,
    socket.SOCK_DGRAM,
    socket.IPPROTO_UDP,
    '',
    (IP, PORT)
)


class TestHeartbeatUDP(base.TestCase):

    def setUp(self):
        super(TestHeartbeatUDP, self).setUp()
        self.health_update = mock.Mock()
        self.stats_update = mock.Mock()

        self.conf = oslo_fixture.Config(cfg.CONF)
        self.conf.config(group="health_manager", heartbeat_key=KEY)
        self.conf.config(group="health_manager", bind_ip=IP)
        self.conf.config(group="health_manager", bind_port=PORT)
        self.conf.config(group="health_manager", sock_rlimit=0)

    @mock.patch('socket.getaddrinfo')
    @mock.patch('socket.socket')
    def test_update(self, mock_socket, mock_getaddrinfo):
        socket_mock = mock.MagicMock()
        mock_socket.return_value = socket_mock
        mock_getaddrinfo.return_value = [FAKE_ADDRINFO]
        bind_mock = mock.MagicMock()
        socket_mock.bind = bind_mock

        getter = heartbeat_udp.UDPStatusGetter(None, None)

        mock_getaddrinfo.assert_called_with(IP, PORT, 0, socket.SOCK_DGRAM)
        self.assertEqual((IP, PORT), getter.sockaddr)
        mock_socket.assert_called_with(socket.AF_INET, socket.SOCK_DGRAM)
        bind_mock.assert_called_once_with((IP, PORT))

        self.conf.config(group="health_manager", sock_rlimit=RLIMIT)
        mock_getaddrinfo.return_value = [FAKE_ADDRINFO, FAKE_ADDRINFO]
        getter.update(KEY, IP, PORT)

    @mock.patch('socket.getaddrinfo')
    @mock.patch('socket.socket')
    def test_dorecv(self, mock_socket, mock_getaddrinfo):
        socket_mock = mock.MagicMock()
        mock_socket.return_value = socket_mock
        mock_getaddrinfo.return_value = [range(1, 6)]
        recvfrom = mock.MagicMock()
        socket_mock.recvfrom = recvfrom

        getter = heartbeat_udp.UDPStatusGetter(None, None)

        # key = 'TEST' msg = {"testkey": "TEST"}
        sample_msg = ('78daab562a492d2ec94ead54b252500a710d0e5'
                      '1aa050041b506245806e5c1971e79951818394e'
                      'a6e71ad989ff950945f9573f4ab6f83e25db8ed7')
        bin_msg = binascii.unhexlify(sample_msg)
        recvfrom.return_value = bin_msg, 2
        (obj, srcaddr) = getter.dorecv()
        self.assertEqual(2, srcaddr)
        self.assertEqual({"testkey": "TEST"}, obj)

    @mock.patch('socket.getaddrinfo')
    @mock.patch('socket.socket')
    def test_check(self, mock_socket, mock_getaddrinfo):
        socket_mock = mock.MagicMock()
        mock_socket.return_value = socket_mock
        mock_getaddrinfo.return_value = [range(1, 6)]
        mock_dorecv = mock.Mock()

        getter = heartbeat_udp.UDPStatusGetter(
            self.health_update, self.stats_update)
        getter.dorecv = mock_dorecv
        mock_dorecv.side_effect = [(dict(id=FAKE_ID), 2)]

        getter.check()
        getter.executor.shutdown()
        self.health_update.update_health.assert_called_once_with({'id': 1})
        self.stats_update.update_stats.assert_called_once_with({'id': 1})

    @mock.patch('socket.getaddrinfo')
    @mock.patch('socket.socket')
    def test_check_no_mixins(self, mock_socket, mock_getaddrinfo):
        self.mock_socket = mock_socket
        self.mock_getaddrinfo = mock_getaddrinfo
        self.mock_getaddrinfo.return_value = [range(1, 6)]

        mock_dorecv = mock.Mock()
        getter = heartbeat_udp.UDPStatusGetter(None, None)

        getter.dorecv = mock_dorecv
        mock_dorecv.side_effect = [(dict(id=FAKE_ID), 2)]

        getter.check()

    @mock.patch('socket.getaddrinfo')
    @mock.patch('socket.socket')
    def test_socket_except(self, mock_socket, mock_getaddrinfo):
        self.assertRaises(exceptions.NetworkConfig,
                          heartbeat_udp.UDPStatusGetter, None, None)

    @mock.patch('concurrent.futures.ThreadPoolExecutor.submit')
    @mock.patch('socket.getaddrinfo')
    @mock.patch('socket.socket')
    def test_check_exception(self, mock_socket, mock_getaddrinfo, mock_submit):
        self.mock_socket = mock_socket
        self.mock_getaddrinfo = mock_getaddrinfo
        self.mock_getaddrinfo.return_value = [range(1, 6)]

        mock_dorecv = mock.Mock()
        getter = heartbeat_udp.UDPStatusGetter(None, None)

        getter.dorecv = mock_dorecv
        mock_dorecv.side_effect = exceptions.InvalidHMACException

        getter.check()
        self.assertFalse(mock_submit.called)
