#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import logging
from oid_translate import ObjectId
import pytz
import re
import struct
import socket
import time

_TIME_STRING_RE = re.compile(
    r"(?:(?P<days>\d+)d)?"
    r"(?:(?P<hours>\d+)h)?"
    r"(?:(?P<minutes>\d+)m)?"
    r"(?:(?P<seconds>\d+)s)?"
)

DATEANDTIME_SLICES = (
    (slice(1, None, -1), "h"), # year
    (2, "b"),  # month
    (3, "b"),  # day
    (4, "b"),  # hour
    (5, "b"),  # minutes
    (6, "b"),  # seconds
    (7, "b"),  # deci seconds
    (8, "c"),  # direction from UTC
    (9, "b"),  # hours from UTC
    (10, "b"), # minutes from UTC
)


def parse_time_string(time_string):
    times = _TIME_STRING_RE.match(time_string).groupdict()
    for key, value in times.iteritems():
        if value is None:
            times[key] = 0
        else:
            times[key] = int(value)

    return times


def to_mibname(oid):
    return ObjectId(oid).name


def varbind_pretty_value(varbind):
    output = varbind.value
    objid = ObjectId(varbind.oid)

    if varbind.value_type == "ipaddress":
        try:
            name = socket.gethostbyaddr(varbind.value)[0]
            output = "%s (%s)" % (name, output)
        except socket.error:
            pass
    elif varbind.value_type == "oid":
        output = to_mibname(varbind.value)
    elif varbind.value_type == "octet":
        if objid.textual == "DateAndTime":
            output = decode_date(varbind.value)

    if objid.enums and varbind.value.isdigit():
        val = int(varbind.value)
        output = objid.enums.get(val, val)

    if objid.units:
        output = "%s %s" % (output, objid.units)

    return output


def decode_date(hex_string):
    format_values = [
        0, 0, 0, 0,
        0, 0, 0, "+",
        0, 0
    ]

    if hex_string.startswith("0x"):
        hex_string = hex_string[2:].decode("hex")

    for idx, (_slice, s_type) in enumerate(DATEANDTIME_SLICES):
        try:
            value = hex_string[_slice]
        except IndexError:
            break
        format_values[idx] = struct.unpack(s_type, value)[0]

    return "%d-%d-%d,%d:%d:%d.%d,%s%d:%d" % tuple(format_values)


def get_loglevel(args):
    verbose = args.verbose * 10
    quiet = args.quiet * 10
    return logging.getLogger().level - verbose + quiet


def utcnow():
    return datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
