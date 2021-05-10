#!/usr/bin/env python

import CloudWatcher
import time

cw = CloudWatcher.CloudWatcher("/dev/ttyUSB0")

#print(f"Rebooting.")
#v = cw.reboot()
#print(f"Was version {v}")
cw.update("AAG_CloudWatcher582.has")

exit()
# while cw.serial.is_open:
#     # print(cw.get_version())
#     print(cw.get_ir_sensor_temp())
#     print(cw.get_wind_speed())
#     print(cw.reboot())
#     exit()
#     #print(cw.get_temperature())
