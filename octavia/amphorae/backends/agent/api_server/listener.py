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

import hashlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess

import flask
import jinja2
import six
from werkzeug import exceptions

from octavia.amphorae.backends.agent.api_server import osutils
from octavia.amphorae.backends.agent.api_server import util
from octavia.amphorae.backends.utils import haproxy_query as query
from octavia.common import constants as consts
from octavia.common import utils as octavia_utils
from octavia.i18n import _LE

LOG = logging.getLogger(__name__)
BUFFER = 100

UPSTART_CONF = 'upstart.conf.j2'
SYSVINIT_CONF = 'sysvinit.conf.j2'
SYSTEMD_CONF = 'systemd.conf.j2'

JINJA_ENV = jinja2.Environment(
    autoescape=True,
    loader=jinja2.FileSystemLoader(os.path.dirname(
        os.path.realpath(__file__)
    ) + consts.AGENT_API_TEMPLATES))
UPSTART_TEMPLATE = JINJA_ENV.get_template(UPSTART_CONF)
SYSVINIT_TEMPLATE = JINJA_ENV.get_template(SYSVINIT_CONF)
SYSTEMD_TEMPLATE = JINJA_ENV.get_template(SYSTEMD_CONF)


class ParsingError(Exception):
    pass


# Wrap a stream so we can compute the md5 while reading
class Wrapped(object):
    def __init__(self, stream_):
        self.stream = stream_
        self.hash = hashlib.md5()  # nosec

    def read(self, l):
        block = self.stream.read(l)
        if block:
            self.hash.update(block)
        return block

    def get_md5(self):
        return self.hash.hexdigest()

    def __getattr__(self, attr):
        return getattr(self.stream, attr)


class Listener(object):

    def __init__(self):
        self._osutils = osutils.BaseOS.get_os_util()

    def get_haproxy_config(self, listener_id):
        """Gets the haproxy config

        :param listener_id: the id of the listener
        """
        self._check_listener_exists(listener_id)
        with open(util.config_path(listener_id), 'r') as file:
            cfg = file.read()
            resp = flask.Response(cfg, mimetype='text/plain', )
            resp.headers['ETag'] = hashlib.md5(six.b(cfg)).hexdigest()  # nosec
            return resp

    def upload_haproxy_config(self, amphora_id, listener_id):
        """Upload the haproxy config

        :param amphora_id: The id of the amphora to update
        :param listener_id: The id of the listener
        """
        stream = Wrapped(flask.request.stream)
        # We have to hash here because HAProxy has a string length limitation
        # in the configuration file "peer <peername>" lines
        peer_name = octavia_utils.base64_sha1_string(amphora_id).rstrip('=')
        if not os.path.exists(util.haproxy_dir(listener_id)):
            os.makedirs(util.haproxy_dir(listener_id))

        name = os.path.join(util.haproxy_dir(listener_id), 'haproxy.cfg.new')
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        # mode 00600
        mode = stat.S_IRUSR | stat.S_IWUSR
        with os.fdopen(os.open(name, flags, mode), 'wb') as file:
            b = stream.read(BUFFER)
            while (b):
                file.write(b)
                b = stream.read(BUFFER)

        # use haproxy to check the config
        cmd = "haproxy -c -L {peer} -f {config_file}".format(config_file=name,
                                                             peer=peer_name)

        try:
            subprocess.check_output(cmd.split(), stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            LOG.error(_LE("Failed to verify haproxy file: %s"), e)
            os.remove(name)  # delete file
            return flask.make_response(flask.jsonify(dict(
                message="Invalid request",
                details=e.output)), 400)

        # file ok - move it
        os.rename(name, util.config_path(listener_id))

        try:

            init_system = util.get_os_init_system()

            LOG.debug('Found init system: {0}'.format(init_system))

            init_path = util.init_path(listener_id, init_system)

            if init_system == consts.INIT_SYSTEMD:
                template = SYSTEMD_TEMPLATE
                init_enable_cmd = "systemctl enable haproxy-{list}".format(
                                  list=listener_id)
            elif init_system == consts.INIT_UPSTART:
                template = UPSTART_TEMPLATE
            elif init_system == consts.INIT_SYSVINIT:
                template = SYSVINIT_TEMPLATE
                init_enable_cmd = "insserv {file}".format(file=init_path)
            else:
                raise util.UnknownInitError()

        except util.UnknownInitError:
            LOG.error(_LE("Unknown init system found."))
            return flask.make_response(flask.jsonify(dict(
                message="Unknown init system in amphora",
                details="The amphora image is running an unknown init "
                        "system.  We can't create the init configuration "
                        "file for the load balancing process.")), 500)

        if init_system == consts.INIT_SYSTEMD:
            # mode 00644
            mode = (stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        else:
            # mode 00755
            mode = (stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP |
                    stat.S_IROTH | stat.S_IXOTH)
        if not os.path.exists(init_path):
            with os.fdopen(os.open(init_path, flags, mode), 'w') as text_file:

                text = template.render(
                    peer_name=peer_name,
                    haproxy_pid=util.pid_path(listener_id),
                    haproxy_cmd=util.CONF.haproxy_amphora.haproxy_cmd,
                    haproxy_cfg=util.config_path(listener_id),
                    respawn_count=util.CONF.haproxy_amphora.respawn_count,
                    respawn_interval=(util.CONF.haproxy_amphora.
                                      respawn_interval),
                    amphora_nsname=consts.AMPHORA_NAMESPACE,
                    HasIFUPAll=self._osutils.has_ifup_all()
                )
                text_file.write(text)

        # Make sure the new service is enabled on boot
        if init_system != consts.INIT_UPSTART:
            try:
                subprocess.check_output(init_enable_cmd.split(),
                                        stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                LOG.error(_LE("Failed to enable haproxy-%(list)s "
                              "service: %(err)s"),
                          {'list': listener_id, 'err': e})
                return flask.make_response(flask.jsonify(dict(
                    message="Error enabling haproxy-{0} service".format(
                            listener_id), details=e.output)), 500)

        res = flask.make_response(flask.jsonify({
            'message': 'OK'}), 202)
        res.headers['ETag'] = stream.get_md5()
        return res

    def start_stop_listener(self, listener_id, action):
        action = action.lower()
        if action not in [consts.AMP_ACTION_START,
                          consts.AMP_ACTION_STOP,
                          consts.AMP_ACTION_RELOAD]:
            return flask.make_response(flask.jsonify(dict(
                message='Invalid Request',
                details="Unknown action: {0}".format(action))), 400)

        self._check_listener_exists(listener_id)

        # Since this script should be created at LB create time
        # we can check for this path to see if VRRP is enabled
        # on this amphora and not write the file if VRRP is not in use
        if os.path.exists(util.keepalived_check_script_path()):
            self.vrrp_check_script_update(listener_id, action)

        # HAProxy does not start the process when given a reload
        # so start it if haproxy is not already running
        if action == consts.AMP_ACTION_RELOAD:
            if consts.OFFLINE == self._check_haproxy_status(listener_id):
                action = consts.AMP_ACTION_START

        cmd = ("/usr/sbin/service haproxy-{listener_id} {action}".format(
            listener_id=listener_id, action=action))

        try:
            subprocess.check_output(cmd.split(), stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            if 'Job is already running' not in e.output:
                LOG.debug("Failed to %(action)s HAProxy service: %(err)s",
                          {'action': action, 'err': e})
                return flask.make_response(flask.jsonify(dict(
                    message="Error {0}ing haproxy".format(action),
                    details=e.output)), 500)
        if action in [consts.AMP_ACTION_STOP,
                      consts.AMP_ACTION_RELOAD]:
            return flask.make_response(flask.jsonify(
                dict(message='OK',
                     details='Listener {listener_id} {action}ed'.format(
                         listener_id=listener_id, action=action))), 202)

        details = (
            'Configuration file is valid\n'
            'haproxy daemon for {0} started'.format(listener_id)
        )

        return flask.make_response(flask.jsonify(
            dict(message='OK',
                 details=details)), 202)

    def delete_listener(self, listener_id):
        self._check_listener_exists(listener_id)

        # check if that haproxy is still running and if stop it
        if os.path.exists(util.pid_path(listener_id)) and os.path.exists(
                os.path.join('/proc', util.get_haproxy_pid(listener_id))):
            cmd = "/usr/sbin/service haproxy-{0} stop".format(listener_id)
            try:
                subprocess.check_output(cmd.split(), stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                LOG.error(_LE("Failed to stop HAProxy service: %s"), e)
                return flask.make_response(flask.jsonify(dict(
                    message="Error stopping haproxy",
                    details=e.output)), 500)

        # parse config and delete stats socket
        try:
            cfg = self._parse_haproxy_file(listener_id)
            os.remove(cfg['stats_socket'])
        except Exception:
            pass

        # delete the ssl files
        try:
            shutil.rmtree(self._cert_dir(listener_id))
        except Exception:
            pass

        # disable the service
        init_system = util.get_os_init_system()
        init_path = util.init_path(listener_id, init_system)

        if init_system == consts.INIT_SYSTEMD:
            init_disable_cmd = "systemctl disable haproxy-{list}".format(
                               list=listener_id)
        elif init_system == consts.INIT_SYSVINIT:
            init_disable_cmd = "insserv -r {file}".format(file=init_path)
        elif init_system != consts.INIT_UPSTART:
            raise util.UnknownInitError()

        if init_system != consts.INIT_UPSTART:
            try:
                subprocess.check_output(init_disable_cmd.split(),
                                        stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                LOG.error(_LE("Failed to disable haproxy-%(list)s "
                              "service: %(err)s"),
                          {'list': listener_id, 'err': e})
                return flask.make_response(flask.jsonify(dict(
                    message="Error disabling haproxy-{0} service".format(
                            listener_id), details=e.output)), 500)

        # delete the directory + init script for that listener
        shutil.rmtree(util.haproxy_dir(listener_id))
        if os.path.exists(init_path):
            os.remove(init_path)

        return flask.jsonify({'message': 'OK'})

    def get_all_listeners_status(self):
        """Gets the status of all listeners

        This method will not consult the stats socket
        so a listener might show as ACTIVE but still be
        in ERROR

        Currently type==SSL is also not detected
        """
        listeners = list()

        for listener in util.get_listeners():
            status = self._check_listener_status(listener)
            listener_type = ''

            if status == consts.ACTIVE:
                listener_type = self._parse_haproxy_file(listener)['mode']

            listeners.append({
                'status': status,
                'uuid': listener,
                'type': listener_type,
            })

        # Can't use jsonify since lists are not supported
        # for security reason: http://stackoverflow.com/
        # questions/12435297/how-do-i-jsonify-a-list-in-flask
        return flask.Response(json.dumps(listeners),
                              mimetype='application/json')

    def get_listener_status(self, listener_id):
        """Gets the status of a listener

        This method will consult the stats socket
        so calling this method will interfere with
        the health daemon with the risk of the amphora
        shut down

        Currently type==SSL is not detected
        :param listener_id: The id of the listener
        """
        self._check_listener_exists(listener_id)

        status = self._check_listener_status(listener_id)

        if status != consts.ACTIVE:
            stats = dict(
                status=status,
                uuid=listener_id,
                type=''
            )
            return flask.jsonify(stats)

        cfg = self._parse_haproxy_file(listener_id)
        stats = dict(
            status=status,
            uuid=listener_id,
            type=cfg['mode']
        )

        # read stats socket
        q = query.HAProxyQuery(cfg['stats_socket'])
        servers = q.get_pool_status()
        stats['pools'] = list(servers.values())
        return flask.jsonify(stats)

    def upload_certificate(self, listener_id, filename):
        self._check_ssl_filename_format(filename)

        # create directory if not already there
        if not os.path.exists(self._cert_dir(listener_id)):
            os.makedirs(self._cert_dir(listener_id))

        stream = Wrapped(flask.request.stream)
        file = self._cert_file_path(listener_id, filename)
        flags = os.O_WRONLY | os.O_CREAT
        # mode 00600
        mode = stat.S_IRUSR | stat.S_IWUSR
        with os.fdopen(os.open(file, flags, mode), 'wb') as crt_file:
            b = stream.read(BUFFER)
            while (b):
                crt_file.write(b)
                b = stream.read(BUFFER)

        resp = flask.jsonify(dict(message='OK'))
        resp.headers['ETag'] = stream.get_md5()
        return resp

    def get_certificate_md5(self, listener_id, filename):
        self._check_ssl_filename_format(filename)

        cert_path = self._cert_file_path(listener_id, filename)
        path_exists = os.path.exists(cert_path)
        if not path_exists:
            return flask.make_response(flask.jsonify(dict(
                message='Certificate Not Found',
                details="No certificate with filename: {f}".format(
                    f=filename))), 404)

        with open(cert_path, 'r') as crt_file:
            cert = crt_file.read()
            md5 = hashlib.md5(six.b(cert)).hexdigest()  # nosec
            resp = flask.jsonify(dict(md5sum=md5))
            resp.headers['ETag'] = md5
            return resp

    def delete_certificate(self, listener_id, filename):
        self._check_ssl_filename_format(filename)
        if not os.path.exists(self._cert_file_path(listener_id, filename)):
            return flask.make_response(flask.jsonify(dict(
                message='Certificate Not Found',
                details="No certificate with filename: {f}".format(
                    f=filename))), 404)

        os.remove(self._cert_file_path(listener_id, filename))
        return flask.jsonify(dict(message='OK'))

    def _check_listener_status(self, listener_id):
        if os.path.exists(util.pid_path(listener_id)):
            if os.path.exists(
                    os.path.join('/proc', util.get_haproxy_pid(listener_id))):
                # Check if the listener is disabled
                with open(util.config_path(listener_id), 'r') as file:
                    cfg = file.read()
                    m = re.search('frontend {}'.format(listener_id), cfg)
                    if m:
                        return consts.ACTIVE
                    else:
                        return consts.OFFLINE
            else:  # pid file but no process...
                return consts.ERROR
        else:
            return consts.OFFLINE

    def _parse_haproxy_file(self, listener_id):
        with open(util.config_path(listener_id), 'r') as file:
            cfg = file.read()

            m = re.search('mode\s+(http|tcp)', cfg)
            if not m:
                raise ParsingError()
            mode = m.group(1).upper()

            m = re.search('stats socket\s+(\S+)', cfg)
            if not m:
                raise ParsingError()
            stats_socket = m.group(1)

            m = re.search('ssl crt\s+(\S+)', cfg)
            ssl_crt = None
            if m:
                ssl_crt = m.group(1)
                mode = 'TERMINATED_HTTPS'

            return dict(mode=mode,
                        stats_socket=stats_socket,
                        ssl_crt=ssl_crt)

    def _check_listener_exists(self, listener_id):
        # check if we know about that listener
        if not os.path.exists(util.config_path(listener_id)):
            raise exceptions.HTTPException(
                response=flask.make_response(flask.jsonify(dict(
                    message='Listener Not Found',
                    details="No listener with UUID: {0}".format(
                        listener_id))), 404))

    def _check_ssl_filename_format(self, filename):
        # check if the format is (xxx.)*xxx.pem
        if not re.search('(\w.)+pem', filename):
            raise exceptions.HTTPException(
                response=flask.make_response(flask.jsonify(dict(
                    message='Filename has wrong format')), 400))

    def _cert_dir(self, listener_id):
        return os.path.join(util.CONF.haproxy_amphora.base_cert_dir,
                            listener_id)

    def _cert_file_path(self, listener_id, filename):
        return os.path.join(self._cert_dir(listener_id), filename)

    def vrrp_check_script_update(self, listener_id, action):
        listener_ids = util.get_listeners()
        if action == consts.AMP_ACTION_STOP:
            listener_ids.remove(listener_id)
        args = []
        for listener_id in listener_ids:
            args.append(util.haproxy_sock_path(listener_id))

        if not os.path.exists(util.keepalived_dir()):
            os.makedirs(util.keepalived_dir())
            os.makedirs(util.keepalived_check_scripts_dir())

        cmd = 'haproxy-vrrp-check {args}; exit $?'.format(args=' '.join(args))
        with open(util.haproxy_check_script_path(), 'w') as text_file:
            text_file.write(cmd)

    def _check_haproxy_status(self, listener_id):
        if os.path.exists(util.pid_path(listener_id)):
            if os.path.exists(
                    os.path.join('/proc', util.get_haproxy_pid(listener_id))):
                return consts.ACTIVE
            else:  # pid file but no process...
                return consts.OFFLINE
        else:
            return consts.OFFLINE
