#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pysnmp.proto import rfc1155
from pysnmp.proto import rfc1902
from pyasn1.type import univ


SEVERITIES = ("informational", "warning", "critical")

SNMP_VERSIONS = {
    0: "v1",
    1: "v2c",
}

SNMP_TRAP_OID = "1.3.6.1.6.3.1.1.4.1.0"

ASN_TO_NAME_MAP = {
    univ.OctetString: "octet",
    univ.ObjectIdentifier: "oid",
    rfc1155.IpAddress: "ipaddress",
    univ.Boolean: "boolean",
    univ.BitString: "bit",
    rfc1902.Unsigned32: "unsigned",
    univ.Null: "null",
    rfc1155.Opaque: "opaque",
    rfc1902.Opaque: "opaque",
    rfc1155.Counter: "counter",
    rfc1902.Counter32: "counter",
    rfc1902.Counter64: "counter64",
}

NAME_TO_PY_MAP = {
    "octet": str,
    "oid": str,
    "opaque": str,
    "ipaddress": str,
    "timeticks": float,
    "unsigned": long,
    "counter": long,
    "counter64": long,
    "boolean": bool,
    "null": lambda x: None,
}
