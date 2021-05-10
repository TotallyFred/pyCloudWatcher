from typing import Dict, Union, Tuple, Optional
import serial
import time


def update_progress_tracker(c_count, ff, fl, firmware_len, unknown_count, complete=False):
    if complete:
        print("\nDone")
        return

    print(
        f"c:{c_count} {ff+fl}/{firmware_len} ({ff}/{fl}) Unknown:{unknown_count}",
        end="\r",
    )


class CloudWatcherException(Exception):
    pass


class CloudWatcher:
    serial: serial.Serial
    errors: int

    def __validate_handshake(self, response: bytes) -> None:
        assert (
            response == b"\x21\x11\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x30"
        )

    def __extract_string(self, response: bytes, pattern: bytes) -> str:
        assert response[0 : len(pattern)] == pattern

        return str(response[len(pattern) :], "ascii").strip()

    def __extract_int(self, response: bytes, pattern: bytes) -> int:
        return int(self.__extract_string(response, pattern))

    def __handle_con_failure(self, exception: Exception) -> None:
        self.errors += 1
        if self.errors > 3:
            try:
                self.serial.close()
            except Exception:
                pass

            try:
                self.serial.open()
            except Exception:
                raise CloudWatcherException("Fatal exception: cannot open port")
        self.errors = 0

    def __read_blocks(self, numblocks: int) -> list:
        result = []
        try:
            for i in range(numblocks):
                block = self.serial.read(15)
                result.append(block)
        except Exception as exception:
            self.__handle_con_failure(exception)
            raise

        self.errors = 0
        return result

    def __read_response(self, numblocks: int) -> list:
        result = self.__read_blocks(numblocks + 1)
        try:
            self.__validate_handshake(result[-1])
        except Exception as exception:
            self.__handle_con_failure(exception)
            raise
        return result[:-1]

    def __init__(self, port: str):
        self.errors = 0
        self.serial = serial.Serial(
            port=port,
            baudrate=9600,
            parity=serial.PARITY_ODD,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            xonxoff=False,
            timeout=2,
            inter_byte_timeout=2,
        )

    def get_internal_name(self) -> str:
        self.serial.write(b"A!")
        internal_name = self.__extract_string(self.__read_response(1)[0], b"!N")

        return internal_name

    def get_version(self) -> str:
        self.serial.write(b"B!")
        serial = self.__extract_string(self.__read_response(1)[0], b"!V")

        return serial

    def get_serial(self) -> str:
        self.serial.write(b"K!")
        version = self.__extract_string(self.__read_response(1)[0], b"!K")

        return version

    def reset(self) -> None:
        """
        Reset the rx/tx buffers.
        """

        self.serial.write(b"z!")
        self.__read_response(0)

    def reboot(self) -> None:
        """
        Reboot the whole system and allow firmware upgrade.
        From Part 4 (Appendix/Erratum)

        returns: the firmware version
        """

        self.serial.write(b"B!")
        time.sleep(0.2)
        self.serial.write(b"O!")
        time.sleep(0.2)
        self.serial.write(b"O!")
        time.sleep(0.2)
        self.serial.write(b"T!")
        time.sleep(0.2)
        serial = self.__extract_string(self.__read_response(1)[0], b"!V")
        return serial

    def update(self, firmware: Union[bytes, str], status_tracker=update_progress_tracker) -> None:
        """
        Upgrades the cloudwatcher with the firmware passed as bytes or as a filename when passed as string.

        :firmware: bytes containing the firmware or string identifying a file containing the firmware
        :returns: the new firmware version
        """
        if isinstance(firmware, str):
            # load binary from file
            with open(firmware, "rb") as f:
                firmware = f.read()

        firmware_len = int(len(firmware))
        half_len = int(firmware_len / 2)

        buff = firmware[:half_len]
        bufl = firmware[half_len:]

        # save RS-232 parameters
        baudrate = self.serial.baudrate
        timeout = self.serial.timeout

        # switch to upgrade mode
        self.serial.baudrate = 57600
        self.timeout = 20

        indexf = -1
        indexl = -1
        c_count = 0
        unknown_count = 0
        while indexf < half_len and indexl < half_len:
            msg = self.serial.read(1)
            if msg == b"":
                # Timeout... end transfer
                break
            elif msg == b"c":
                c_count += 1
                self.serial.write(b"d")
            elif msg == b"0":
                if indexf == -1:
                    l = int(half_len / 256)
                    self.serial.write(chr(l).encode())
                else:
                    self.serial.write(buff[indexf])
                indexf += 1
            elif msg == b"1":
                if indexl == -1:
                    l = int(half_len % 256)
                    self.serial.write(chr(int(l)).encode())
                else:
                    self.serial.write(buff[indexl])
                indexl += 1
            else:
                # Unknown message from CW. Should we abort ? Just count in case.
                unknown_count += 1

            if status_tracker is not None:
                status_tracker(c_count, indexf, indexl, firmware_len, unknown_count)

        # restore RS-232 parameters
        self.serial.baudrate = baudrate
        self.serial.timeout = timeout

        # Tell the progress tracker we're done
        if status_tracker is not None:
            status_tracker(c_count, indexf, indexl, firmware_len, unknown_count, True)

    def get_values(self) -> Dict[str, int]:
        """
        Get the zener voltage, light detector voltage and rain sensor temperature.
        Only 3 values as per Part 2 (Addendum)

        returns: a dictionary containing the raw reading zener_voltage, ldr_voltage, rain_sensor_temp
        """
        self.serial.write(b"C!")
        values = self.__read_response(3)
        zener_voltage = self.__extract_int(values[0], b"!6")
        ldr_voltage = self.__extract_int(values[1], b"!4")
        rain_sensor_temp = self.__extract_int(values[2], b"!5")

        return {
            "zener_voltage": zener_voltage,
            "ldr_voltage": ldr_voltage,
            "rain_sensor_temp": rain_sensor_temp,
        }

    def get_internal_errors(self) -> Dict[str, int]:
        self.serial.write(b"D!")
        values = self.__read_response(4)
        first_address_byte_errors = self.__extract_int(values[0], b"!E1")
        command_byte_errors = self.__extract_int(values[1], b"!E2")
        second_address_byte_errors = self.__extract_int(values[2], b"!E3")
        PEC_byte_errors = self.__extract_int(values[3], b"!E4")

        return {
            "first_address_byte_errors": first_address_byte_errors,
            "command_byte_errors": command_byte_errors,
            "second_address_byte_errors": second_address_byte_errors,
            "PEC_byte_errors": PEC_byte_errors,
        }

    def get_rain_frequency(self) -> int:
        """
        Reads the rain frequency from the rain sensor.

        Returns: a value between 0 and ~6000 (range updated by Part 4 addendum)
        """
        self.serial.write(b"E!")
        rain_freq = self.__extract_int(self.__read_response(1)[0], b"!R")

        return rain_freq

    def get_switch_status(self) -> bool:
        """
        Checks relay switch status.

        returns: True if open, False if closed
        """
        opened = True
        self.serial.write(b"F!")
        response = self.__read_response(1)[0]
        try:
            switch_status = self.__extract_string(response, b"!X")
            opened = True
        except:
            switch_status = self.__extract_string(response, b"!Y")
            opened = False

        closed = not opened

        if (opened and switch_status != "Switch Open") or (
            closed and switch_status != "Switch Close"
        ):
            raise CloudWatcherException(f"Invalid status {switch_status}")

        return opened

    def get_switch_open(self) -> bool:
        """
        Checks relay switch status.

        returns: True if open, False if closed
        """
        self.serial.write(b"G!")
        switch_open = self.__extract_string(self.__read_response(1)[0], b"!X")

        return switch_open == "Switch Open"

    def get_switch_close(self) -> bool:
        """
        Checks relay switch status.

        returns: True if closed, False if opened
        """
        self.serial.write(b"H!")
        switch_open = self.__extract_string(self.__read_response(1)[0], b"!Y")

        return switch_open == "Switch Close"

    def pwm(self, pwm: Union[int, None] = None) -> int:
        """
        Returns or sets the PWM value for the capacitive rain sensor heater.

        :pwm: if provided (0<pwm<1024), sets the CW pwm to the requested value. If None, reads the current pwm value from the CW.
        :returns: the value of the PWM sensor as set or read
        """
        if pwm is None:
            self.serial.write(b"Q!")
        else:
            assert 0 < pwm < 1024
            self.serial.write(bytes(f"P{pwm:04}!", "ASCII"))

        values = self.__read_response(1)
        pwm = self.__extract_int(values[0], b"!Q")
        return pwm

    def get_sky_ir_temp(self) -> int:
        """
        Return the infrared sensor value.

        returns: temperature
        """
        self.serial.write(b"S!")
        ir_temp = self.__extract_int(self.__read_response(1)[0], b"!1")

        return ir_temp

    def get_ir_sensor_temp(self) -> int:
        """
        Return the infrared sensor temperature.

        returns: temperature
        """
        self.serial.write(b"T!")
        ir_sensor_temp = self.__extract_int(self.__read_response(1)[0], b"!2")

        return ir_sensor_temp

    def get_electrical_constants(self) -> Dict[str, int]:
        """
        Returns electrical constants.
        From Part 2 (addendum)

        returns: a dictionary
        """
        self.serial.write(b"M!")
        values = self.__read_response(1)[0]
        assert values[0:2] == b"!M"
        v = values[2:]

        zener_voltage = (256 * v[1] + v[2]) / 100
        ldr_max_resistance = 256 * v[3] + v[4]
        ldr_pull_up_resistance = (256 * v[5] + v[6]) / 10
        rain_beta = 256 * v[7] + v[8]
        rain_res_at_25 = (256 * v[9] + v[10]) / 10
        rain_pull_up_resistance = (256 * v[11] + v[12]) / 10

        return {
            "zener_voltage": zener_voltage,
            "ldr_max_resistance": ldr_max_resistance,
            "ldr_pull_up_resistance": ldr_pull_up_resistance,
            "rain_beta": rain_beta,
            "rain_res_at_25": rain_res_at_25,
            "rain_pull_up_resistance": rain_pull_up_resistance,
        }

    def get_wind_sensor_presence(self) -> bool:
        """
        Returns the presence of the wind sensor.
        From Part 3 (addendum/erratum)

        :returns: True if a wind sensor is present; False otherwise
        """
        self.serial.write(b"v!")
        wind_sensor = self.__extract_int(self.__read_response(1)[0], b"!v")

        return wind_sensor == 1

    def get_wind_sensor(self) -> int:
        """
        Returns the wind sensor value.
        From Part 3 (addendum/erratum)

        :returns: the wind sensor raw value as an integer
        """
        self.serial.write(b"V!")
        wind_sensor = self.__extract_int(self.__read_response(1)[0], b"!w")

        return wind_sensor

    def get_wind_speed(self, black_anemometer: bool = True) -> float:
        """
        Returns the wind speed according to the anemometer model.
        From Part 4 (addendum/erratum).

        @black_anemometer: True if you have the black model. False if the old grey.
        :returns: returns the wind speed (float)
        """
        wind_sensor = self.get_wind_sensor()

        if black_anemometer:
            if wind_sensor > 0:
                wind_speed = (wind_sensor * 0.84) + 3
            else:
                wind_speed = 0
        else:
            wind_speed = wind_sensor

        return wind_speed

    def get_rel_humidity_sensor(self) -> Tuple[str, int]:
        """
        Returns the relative humidity (from the integrated temp / rel humd. sensor).
        From Part 4 (addendum/erratum).

        There are two types of sensor

        returns: a string differentiating the high precission (hh) from the low precision (h) sensor
        followed by the raw relative humidity from the sensor (int)
        """
        self.serial.write(b"h!")
        rhel_sensor = self.__read_response(1)[0]
        if rhel_sensor[0:3] == b"!hh":
            rhel_sensor = self.__extract_int(rhel_sensor, b"!hh")
            # if we get 65536, the sensor is not connected
            if rhel_sensor == 65535:
                raise CloudWatcherException(
                    "High precision RHEL/temp sensor not connected"
                )
            return "hh", rhel_sensor
        else:
            rhel_sensor = self.__extract_int(rhel_sensor, b"!h")
            # if we get 100, the sensor is not connected
            if rhel_sensor == 100:
                raise CloudWatcherException(
                    "Low precision RHEL/temp sensor not connected"
                )
            return "h", rhel_sensor

    def get_rel_humidity(
        self, sensitivity: Optional[str] = None, rhel_sensor: Optional[int] = None
    ) -> float:
        """
        Returns the relative humidity (from the integrated temp / rel humd. sensor).
        From Part 4 (addendum/erratum)

        This method can act as a converter from optional raw data passed as argument to RHEL.
        If the raw data is not passed as argument, the data will be fetched from the sensor.

        :sensitivity: string ("t" or "th") or None. If None, fetch value from the sensor. t for low precision sensor conversion. th for high precision.
        :rhel_sensor: an integer coming from the sensor. If None, fetch the value from the sensor.
        returns: the relative humidity (float)
        """
        if sensitivity is None or rhel_sensor is None:
            sensitivity, rhel_sensor = self.get_rel_humidity_sensor()
        if sensitivity == "hh":
            rh = rhel_sensor * 125 / 65536 - 6
        elif sensitivity == "h":
            rh = rhel_sensor * 125 / 100 - 6
        else:
            raise CloudWatcherException(f"Unknown rhel sensor type {sensitivity}")
        return rh

    def get_temperature_sensor(self) -> Tuple[str, int]:
        """
        Returns the raw temperature data (from the integrated temp / rel humd. sensor).
        From Part 4 (addendum/erratum)

        returns: a pair. 1st element is a string ("t" for low precision, "th" for high precision) followed by the raw data (int)
        """
        self.serial.write(b"t!")
        temp_sensor = self.__read_response(1)[0]
        if temp_sensor[0:3] == b"!th":
            temp_sensor = self.__extract_int(temp_sensor, b"!th")
            # if we get 65536, the sensor is not connected
            if temp_sensor == 65535:
                raise CloudWatcherException(
                    "High precision RHEL/temp sensor not connected"
                )
            return "th", temp_sensor
        else:
            temp_sensor = self.__extract_int(temp_sensor, b"!t")
            # if we get 100, the sensor is not connected
            if temp_sensor == 100:
                raise CloudWatcherException(
                    "Low precision RHEL/temp sensor not connected"
                )
            return "t", temp_sensor

    def get_temperature(
        self, sensitivity: Optional[str] = None, temp_sensor: Optional[int] = None
    ) -> float:
        """
        Returns the temperature (from the integrated temp / rel humd. sensor).
        From Part 4 (addendum/erratum)

        This method can act as a converter from optional raw data passed as argument to temperature.
        If the raw data is not passed as argument, the data will be fetched from the sensor.

        :sensitivity: string ("h" or "hh") or None. If None, fetch value from the sensor. h for low sensitivity sensor conversion. hh for high sensitivity.
        :temp_sensor: an integer coming from the sensor. If None, fetch the value from the sensor.
        returns: the temperature (float)
        """
        if sensitivity is None or temp_sensor is None:
            sensitivity, temp_sensor = self.get_temperature_sensor()
        if sensitivity == "th":
            temp = temp_sensor * 175.72 / 65536 - 46.85
        elif sensitivity == "t":
            temp = temp_sensor * 1.7572 - 46.85
        else:
            raise CloudWatcherException(
                f"Unknown temperature sensor type {sensitivity}"
            )

        return temp
