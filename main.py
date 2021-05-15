#!/usr/bin/env python

import cloudwatcher
import time
cw = cloudwatcher.CloudWatcher("/dev/ttyUSB0")

#print(f"Rebooting.")
#v = cw.reboot()
#print(f"Was version {v}")
#cw.update("AAG_CloudWatcher582.has")
#cw.update("AAG_CloudWatcher573.has")

while cw.serial.is_open:
    # print(cw.get_version())
    # print(cw.get_sky_ir_temp())
    # print(cw.get_wind_speed())
    # print(cw.get_temperature())
    # print(cw.get_rel_humidity())
    # print(cw.get_ambient_light())
    print(cw.get_ir_sensor_temperature())
    print(cw.get_ir_sensor_ambient_temperature())
