#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import logging
import socket
import subprocess
import multiprocessing.pool
from urllib import urlopen

from oid_translate import ObjectId
from pyasn1.codec.ber import decoder
from pyasn1.type.error import ValueConstraintError
from pysnmp.proto import api
from pysnmp.proto.error import ProtocolError

from core.dde import DdeNotification
from core.constants import SNMP_VERSIONS
from core.message import Notification, Metrics
from core.utils import parse_time_string
from core.models import Target, FPingMessage, Device, Port

try:
    from dde_plugin import run as dde_run
except ImportError as err:
    def dde_run(notification):
        pass

class TrapperCallback(object):
    def __init__(self, db_engine, config, community):
        self.db_engine = db_engine
        self.config = config
        self.hostname = socket.gethostname()
        self.community = community

    def __call__(self, *args, **kwargs):
        try:
            self._call(*args, **kwargs)
        except Exception as err:
            logging.exception("TrapperCallback Failed: %s", err)

    def _send_mail(self, handler, trap, is_duplicate):
        pass

    def _call(self, transport_dispatcher, transport_domain, transport_address, whole_msg):
        if not whole_msg:
            return

        msg_version = int(api.decodeMessageVersion(whole_msg))

        if msg_version in api.protoModules:
            proto_module = api.protoModules[msg_version]
        else:
            return

        host = transport_address[0]
        version = SNMP_VERSIONS[msg_version]

        try:
            req_msg, whole_msg = decoder.decode(whole_msg, asn1Spec=proto_module.Message(),)
        except (ProtocolError, ValueConstraintError) as err:
            return
        req_pdu = proto_module.apiMessage.getPDU(req_msg)

        community = proto_module.apiMessage.getCommunity(req_msg)
        if self.community and community != self.community:
            return

        if not req_pdu.isSameTypeWith(proto_module.TrapPDU()):
            logging.warning("Received non-trap notification from %s", host)
            return

        if msg_version not in (api.protoVersion1, api.protoVersion2c):
            logging.warning("Received trap not in v1 or v2c")
            return

        trap = Notification.from_pdu(host, proto_module, version, req_pdu)
        if trap is None:
            logging.warning("Invalid trap from %s: %s", host, req_pdu)
            return

        dde = DdeNotification(trap, self.config.handlers[trap.oid])
        dde_run(dde)
        handler = dde.handler

        trap.severity = handler["severity"]
        trap.manager = self.hostname

        if handler.get("expiration", None):
            expires = parse_time_string(handler["expiration"])
            expires = datetime.timedelta(**expires)
            trap.expires = trap.sent + expires

        objid = ObjectId(trap.oid)
        if handler.get("blackhole", False):
            return


        duplicate = False
        try:
            # TODO: DB write
            pass
        except Exception as err:
            logging.exception("TODO")
        
        self._send_mail(handler, trap, duplicate)

class FPingTarget(object):
    def __init__(self, host, idx, state):
        self.host = host
        self.idx = idx
        self.state = state

def generate_fping_metrics(target, count):
    host = target.host
    metrics = []
        
    try:
        subp = subprocess.Popen(COMMAND,
                                shell=True,
                                stdout=subprocess.PIPE)
        output = subp.communicate()[0]
    except Exception:
        logging.error("unexpected error while execute cmd : %s" % COMMAND)
        return None

    data = output.split()
    if len(data) == 7:
        host_str, xmt, rcv, loss_rate, _min, _avg, _max = data
    elif len(data) == 4:
        host_str, xmt, rcv, loss_rate = data
        _min = _avg = _max = 0
    else:
        _avg = 0
        loss_rate = '100%'
        #return None

    state = 1 if _avg > 0 else 0
    metrics = Metrics(target.idx, target.host, target.state, state,
                      float(_avg), float(loss_rate.replace('%', '')))
    return metrics

class FPingCallback(object):
    def __init__(self, db_engine):
        self.db_engine = db_engine

    @staticmethod
    def connected(host="http://www.test.com"):
        try:
            urlopen(host)
            return True
        except:
            return False
    
    def __call__(self, *args, **kwargs):
        try:
            self._call(*args, **kwargs)
        except Exception as err:
            logging.exception("FPingCallback Failed: %s", str(err))

    def _send_mail(self, handler, fping, is_duplicate):
        pass

    def _call(self, process_count, fping_count):
        result = []
        targets = []

        if self.connected() == False:
            logging.error("NOTE!!! HealthCheck is not connected")
            return
        
        try:
            with self.db_engine:
                #for target in Target.select():
                for target in Device.select().where(Device.host.is_null(False), Device.device_type != 3, Device.enable == 1):
                    targets.append(FPingTarget(target.host, target.id, target.state))
        except Exception as err:
            logging.error("FPingCallback get targets: %s", str(err))
            return

        try:
            multi_process_pool = multiprocessing.Pool(process_count)
            for t in targets:
                result.append(multi_process_pool.apply_async(generate_fping_metrics, (t, fping_count)))
        except Exception as err:
            logging.error("FPingCallback multiprocessing pool: %s", str(err))
        finally:
            multi_process_pool.close()
            multi_process_pool.join()
    
        # multi_process_pool.close()
        # multi_process_pool.join()

        try:
            with self.db_engine:
                for res in result:
                    m = res.get()
                    last_time = datetime.datetime.now()
                    query = Device.update(state=m.state, avg=m.avg,
                                          loss_rate=m.loss_rate, last_time=last_time).where(Device.id == m.idx)
                    query.execute()
                    
                    query = Port.update(state=m.state).where(Port.device_id == m.idx)
                    query.execute()

                    query = Target.update(state=m.state).where(Target.device_id == m.idx)
                    query.execute()
                    if m.old_state <> m.state:
                        info = 'linkUp' if m.state == 1 else 'linkDown'
                        FPingMessage.create(host=m.host, info=info)
        except Exception as err:
            logging.error("FPingCallback update state: %s", str(err))
