#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import logging
import datetime

import oid_translate
from pysnmp.carrier.asynsock.dispatch import AsynsockDispatcher
from pysnmp.carrier.asynsock.dgram import udp, udp6

import multiprocessing.pool
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from playhouse.pool import PooledMySQLDatabase

from core.callbacks import TrapperCallback, FPingCallback
from core.services import SyslogService
from core.config import Config
from core.models import Target, FPingMessage, Device, EventMessage, Port
from core.utils import get_loglevel
from core import __version__

LOGFILE = "/var/log/healthchecker/health.log"
LOGFORMAT = "%(asctime)-15s %(levelname)-5s [%(module)s] %(message)s"
def main():

    parser = argparse.ArgumentParser(description="HEALTH CHECKER.")
    parser.add_argument("-c", "--config", default="/etc/healthchecker.yaml",
                        help="Path to config file.")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase logging verbosity.")
    parser.add_argument("-q", "--quiet", action="count", default=0, help="Decrease logging verbosity.")
    parser.add_argument("-V", "--version", action="version",
                        version="%%(prog)s %s" % __version__,
                        help="Display version information.")

    args = parser.parse_args()

    oid_translate.load_mibs()

    config = Config.from_file(args.config)

    db_host, db_port, db_name, db_user, db_passwd = config.get_database_config()
    db_engine = PooledMySQLDatabase(db_name, **{'host': db_host, 'port': db_port,
                                                'password': db_passwd, 'user': db_user})
    models = [Target, FPingMessage, Device, EventMessage, Port]
    db_engine.bind(models)
    
    community = config["community"]
    if not community:
        community = None
    ipv6_server = config["ipv6"]
    if not ipv6_server:
        ipv6_server = None
    
    trap_cb = TrapperCallback(db_engine, config, community)

    logging.basicConfig(filename=LOGFILE, level=10, #get_loglevel(args),
                        format=LOGFORMAT)

    transport_dispatcher = AsynsockDispatcher()
    transport_dispatcher.registerRecvCbFun(trap_cb)
    if ipv6_server:
        transport_dispatcher.registerTransport(
            udp6.domainName, udp6.Udp6SocketTransport().openServerMode(("::1", int(config["trap_port"])))
        )
    transport_dispatcher.registerTransport(
        udp.domainName, udp.UdpSocketTransport().openServerMode(("0.0.0.0", int(config["trap_port"])))
    )
    transport_dispatcher.jobStarted(1)

    process_count = config['process_count']
    if not process_count:
        process_count = (multiprocessing.cpu_count() * 2 + 1) if (multiprocessing.cpu_count() * 2 + 1) < 11 else 10
    logging.info("multiprocess count is : %s" % process_count)

    fping_count = int(config['fping_count'])
    if not fping_count:
        fping_count = 5
    logging.info("fping count is : %d" % fping_count)

    interval_time = int(config['interval_time'])
    if not interval_time:
        interval_time = 1
    
    fping_cb = FPingCallback(db_engine)
    scheduler = BackgroundScheduler()
    trigger= IntervalTrigger(minutes=interval_time) # FIX PYINSTALL BUG
    scheduler.add_job(fping_cb, trigger, args=(process_count, fping_count), max_instances=10)
    #scheduler.add_job(fping_cb, trigger='interval', args=(process_count, fping_count),
    #                  max_instances=10, minutes=interval_time)

    ## syslog service
    host = '127.0.0.1'
    port = 8889
    syslog_service = SyslogService(db_engine, host, port)

    TRAP = False
    try:
        scheduler.start()
        if TRAP:#TODO new thread
            transport_dispatcher.runDispatcher()
        else:
            #redo_start_time = datetime.datetime.now() + datetime.timedelta(seconds=-20)
            redo_start_time = config.get("redo_start_time")
            if redo_start_time is None:
                redo_start_time = False
            syslog_service.start(redo_start_time)
    except KeyboardInterrupt:
        pass
    finally:
        logging.info("Shutdown Scheduler...")
        scheduler.shutdown()

        if TRAP:
            logging.info("Stopping Transport Dispatcher...")
            transport_dispatcher.closeDispatcher()
        else:
            syslog_service.stop()
        logging.info("Bye")

if __name__ == "__main__":
    main()
