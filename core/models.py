#!/usr/bin/env python
# -*- coding: utf-8 -*-

from peewee import Model
from peewee import CharField, SmallIntegerField, IntegerField
from peewee import FloatField, DateTimeField

class BaseModel(Model):
    pass

class Target(BaseModel):
    device_id = IntegerField()
    host      = CharField(column_name="ip")
    state     = SmallIntegerField(column_name='state', default=0)
    avg       = FloatField()
    loss_rate = FloatField()
    last_time = DateTimeField()

    class Meta:
        table_name = 'device_ip'

class Device(BaseModel):
    name  = CharField()
    device_type = IntegerField()
    mac   = CharField()
    host = CharField(column_name='ipaddress')
    state = SmallIntegerField(column_name='state', default=0)
    enable = SmallIntegerField(default=1)
    avg       = FloatField()
    loss_rate = FloatField()
    last_time = DateTimeField()

    class Meta:
        table_name = 'device'

class Port(BaseModel):
    device_id = IntegerField()
    state = SmallIntegerField(column_name='state', default=0)

    class Meta:
        table_name = "device_ifx"

class FPingMessage(BaseModel):
    host = CharField()
    info = CharField()

    class Meta:
        table_name = 'monitor_message'

class EventMessage(BaseModel):
    message = CharField(column_name='Message')
    created_time = DateTimeField(column_name='CreatedAt')

    class Meta:
        table_name = 'SystemEvents'
