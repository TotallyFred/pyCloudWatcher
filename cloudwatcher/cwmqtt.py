#!/usr/bin/env python3

"""
A simple mqtt publisher example. Lots of hardcoded stuff in here.
"""

import random
import time
import json

from paho.mqtt import client as mqtt_client
import cloudwatcher

def connect_mqtt():
    broker = 'lmpi.local'
    port = 1883
    client_id = f'python-mqtt-{random.randint(0, 1000)}'

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)
    # Set Connecting Client ID
    client = mqtt_client.Client(client_id)
    #client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client


def publish(client):
    cw = cloudwatcher.CloudWatcher("/dev/ttyUSB0")
    cw.initialize()
    
    topic = "/CloudWatcher/Home"

    while True:
        cw_update = {}
        cw_update["sky_ir_temp"] = cw.get_sky_ir_temperature()
        cw_update["ir_temp"] = cw.get_ir_sensor_temperature()
        cw_update["temp"] = cw.get_temperature()
        cw_update["wind_speed"] = cw.get_wind_speed()
        cw_update["rel_humidity"] = cw.get_rel_humidity()
        cw_update["rain_freq"] = cw.get_rain_frequency()
        cw_update["ambient_light_rel"] = cw.get_relative_ambient_light()
        # cw_update["ambient_light_max_r"] = cw.constants["ldr_max_resistance"]
        # cw_update["ambient_light_r"] = cw.get_ambient_light()

        msg = json.dumps(cw_update)

        result = client.publish(topic, msg)
        # result: [0, 1]
        status = result[0]
        if status == 0:
            print(f"Sent`{msg}` to topic `{topic}`")
        else:
            print(f"Failed to send message to topic {topic}")
        time.sleep(1)

def main():
    client = connect_mqtt()
    client.loop_start()
    publish(client)


if __name__ == '__main__':
    main()