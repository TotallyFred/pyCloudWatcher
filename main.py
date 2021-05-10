#!/usr/bin/env python

import CloudWatcher

cw = CloudWatcher.CloudWatcher("/dev/ttyUSB0")

#print(f"Rebooting.")
#v = cw.reboot()
#print(f"Was version {v}")
#cw.update("AAG_CloudWatcher582.has")
cw.update("AAG_CloudWatcher573.has")

# while cw.serial.is_open:
#     # print(cw.get_version())
#     print(cw.get_ir_sensor_temp())
#     print(cw.get_wind_speed())
#     #print(cw.get_temperature())
