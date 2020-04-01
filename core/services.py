#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import socket
import logging
import datetime
from functools import partial
from tornado.ioloop import IOLoop
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor

from core.models import Device, EventMessage

class SyslogService(object):
    def __init__(self, db_engine, host, port):
        self.db_engine = db_engine
        self.host = host
        self.port = port
        self.fd_map = {}
        self.executor = ThreadPoolExecutor(10)
        self.ioloop = IOLoop.instance()

    @run_on_executor
    def process_msg(self, msg):
        mac, ip, state = self.get_mac_and_state(msg)
        if mac is None:
            return
        
        try:
            with self.db_engine:
                query = Device.update(state=state).where((Device.mac == mac) |
                                                         (Device.host == ip))
                query.execute()
        except Exception as err:
            logging.error("SyslogService process msg: %s", str(err))

    @staticmethod
    def get_mac_and_state(msg):
        mac = ''
        state = 0

        if msg.find(' AP ') <> -1: #AP
            #ip_and_mac = re.findall(r"\((.+)\)", msg).split('；')
            ip_and_mac = re.findall(r"\(IP (.+)；MAC (.+)\)", msg)
            #[('172.16.45.56', 'DC-FE-18-4A-9A-C4')]
            if len(ip_and_mac) <> 1:
                return (None, None, state)
            else:
                ip, mac = ip_and_mac[0]
                ip = ip.strip()
                mac = mac.strip()

                if msg.find("成功接入") <> -1:
                    state = 1
                return (mac, ip, state)
        else: # 
            mac = re.findall(r"STA\(MAC (.+)\)断开连接", msg)
            if len(mac) <> 1:
                mac = re.findall(r"STA\(MAC (.+)\)成功连接", msg)
                state = 1
                if len(mac) <> 1:
                    return (None, None, None)

            return (mac[0].strip(), None, state)
            
    @run_on_executor
    def redo_msg(self, start_time, end_time):
        try:
            message_list = []
            with self.db_engine:
                for event in EventMessage.select(EventMessage.message).where(EventMessage.created_time.between(start_time, end_time)):
                    message_list.append(event.message)
            for m in message_list:
                self.process_msg(m)
        except Exception as err:
            logging.error("SyslogService redo message: %s", str(err))
                    
    def handle_client(self, cli_addr, fd, event):
        s = self.fd_map[fd]
        
        if event & IOLoop.READ:
            data = s.recv(1024)
            if data:
                logging.debug("Receive %s from %s", data, cli_addr)
                self.process_msg(data)
            else:
                logging.debug("Closing %s", cli_addr)
                self.ioloop.remove_handler(fd)
                s.close()
        if event & IOLoop.WRITE:
            pass
        if event & IOLoop.ERROR:
            logging.exception("cli: %s", cli_addr)
            self.ioloop.remove_handler(fd)
            s.close()

    def handle_server(self, fd, event):
        s = self.fd_map[fd]
        
        if event & IOLoop.READ:
            conn, cli_addr = s.accept()
            logging.debug("New connection %s", cli_addr[0])
            conn.setblocking(0)
            conn_fd = conn.fileno()
            self.fd_map[conn_fd] = conn
            handle = partial(self.handle_client, cli_addr[0])
            
            self.ioloop.add_handler(conn_fd, handle, IOLoop.READ)
                    
    def start(self, redo_start_time):
        logging.debug("SyslogService start...")

        if redo_start_time:
            end_time = datetime.datetime.now() + datetime.timedelta(seconds=20)
            self.redo_msg(redo_start_time, end_time)
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.sock.setblocking(0)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        fd = self.sock.fileno()
        self.fd_map[fd] = self.sock

        self.ioloop.add_handler(fd, self.handle_server, IOLoop.READ)
        self.ioloop.start()

    def stop(self):
        logging.debug("SyslogService stop...")
        #self.ioloop.add_callback(self.ioloop.stop)
        self.ioloop.stop()
        self.executor.shutdown()
