"""
cloudwatcher

Native Python bindings for the LunaticoAstro's CloudWatcher weather station API.
"""

__version__ = "1.0.0"
__author__ = "Frederic Detienne"

from typing import Dict, Union, Tuple, Optional
import serial
import time
import math
from enum import Enum


def _default_progress_tracker(
    preamble_count,
    low_part_progress,
    high_part_progress,
    firmware_len,
    unknown_count,
    complete=False,
    upload=False,
):
    if upload:
        print(
            f"Preamble:{preamble_count} Progress:{low_part_progress+high_part_progress}/{firmware_len} ({low_part_progress}/{high_part_progress}) Unknown:{unknown_count}",
            end="\r",
        )
    else:
        print(f"Preamble:{preamble_count} Unknown:{unknown_count}", end="\r")

    if complete:
        print("\nDone")
        return


class CloudWatcherException(Exception):
    pass


class Anemometer(Enum):
    black = 0
    gray = 1


class CloudWatcher:
    serial: serial.Serial
    errors: int
    analog_cache: Dict[str, int]
    analog_cache_lifetime_ms: int
    analog_cache_timestamp: float  # The actual format of a timestamp
    constants: Dict[str, float]

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

    def __init__(self, port: str, cache_lifetime_ms: int = 1000):
        self.errors = 0
        self.serial = serial.Serial(
            port=port,
            baudrate=9600,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            xonxoff=False,
            timeout=2,
        )
        self.constants = {}
        self.analog_cache = {}
        self.analog_cache_lifetime_ms = cache_lifetime_ms
        self.analog_cache_timestamp = 0

    def flush_io(self):
        # flush the output buffer
        self.serial.flush()

        # flush the input buffer
        if self.serial.in_waiting > 0:
            timeout = self.serial.timeout
            while self.serial.read() != b"":
                pass
            self.serial.timeout = 1

        # notify CW to reset its IO buffers
        self.reset_io()

    def get_internal_name(self) -> str:
        """
        Reads the name of the CloudWatcher unit.

        :return: A string containing the name of the CloudWatcher unit. Typically, it would be always "CloudWatcher"
        """
        self.serial.write(b"A!")
        internal_name = self.__extract_string(self.__read_response(1)[0], b"!N")

        return internal_name

    def get_version(self) -> str:
        """
        Reads the version number of the CloudWatcher unit.

        :return: A string containing the version number of the CloudWatcher unit
        """
        self.serial.write(b"B!")
        serial_number = self.__extract_string(self.__read_response(1)[0], b"!V")
        return serial_number

    def get_serial(self) -> str:
        """
        Reads the serial number of the CloudWatcher unit.

        :return: A string containing the serial number of the CloudWatcher unit
        """
        self.serial.write(b"K!")
        version = self.__extract_string(self.__read_response(1)[0], b"!K")

        return version

    def reset_io(self) -> None:
        """
        Reset the rx/tx buffers.

        :returns: nothing
        """

        self.serial.write(b"z!")
        self.__read_response(0)

    def reboot(self) -> str:
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

        serial = self.__extract_string(self.__read_response(3)[0], b"!V")
        return serial

    def upgrade(
        self, firmware: Union[bytes, str], status_tracker=_default_progress_tracker
    ) -> None:
        """
        Upgrade CloudWatcher with the firmware (passed as bytes) or the file (filename when passed as string.

        :firmware: bytes containing the firmware or string identifying a file containing the firmware
        :status_tracker: a lambda or function that can display the update progress. Set it to None if you do not need progress feedback and want the update(). Provide your own if you want to display something else than the default.
        :returns: the new firmware version
        """

        def _update_tracker(
            status_tracker,
            preamble_count,
            indexf,
            indexl,
            firmware_len,
            unknown_count,
            done,
            upload,
        ):
            if status_tracker is not None:
                status_tracker(
                    preamble_count,
                    indexf,
                    indexl,
                    firmware_len,
                    unknown_count,
                    done,
                    upload,
                )

        if isinstance(firmware, str):
            # load binary from file
            with open(firmware, "rb") as f:
                firmware = f.read()

        firmware_len = int(len(firmware))
        half_len = int(firmware_len / 2)

        # split firmware in 2 halves (low and high part) and compute the half file length (2 bytes).
        two_bytes_half_len = half_len.to_bytes(2, "big")
        lenf = two_bytes_half_len[0].to_bytes(1, "big")
        lenl = two_bytes_half_len[1].to_bytes(1, "big")

        buff = firmware[:half_len]
        bufl = firmware[half_len:]

        # save RS-232 parameters
        baudrate = self.serial.baudrate
        timeout = self.serial.timeout

        indexf = -1
        indexl = -1
        preamble_count = 0
        unknown_count = 0

        # switch serial to upgrade mode
        self.serial.baudrate = 57600
        self.timeout = 5

        # Process upgrade preamble. Wait to have enough "c" chars to consider the preamble valid.
        # This helps getting rid of potential garbage in the buffer which could mess up with the protocol
        while preamble_count < 10:
            msg = self.serial.read(1)
            if msg == b"":
                # Timeout. Abort upgrade
                raise ValueError("Upgrade failed - timeout before transfer")
            elif msg == b"c" or msg == b"\xff":
                # 0xFF may occur after a B!O!O!T! -triggered reboot. Not on power-on. Funny.
                preamble_count += 1
            else:
                # Unknown message from CW. Should we abort ? Count just in case.
                unknown_count += 1
            _update_tracker(
                status_tracker,
                preamble_count,
                indexf,
                indexl,
                firmware_len,
                unknown_count,
                False,
                False,
            )

        # Signal CW that we are ready to transfer
        self.serial.write(b"d")

        # remain at 57600 bps but lower the timeout.
        self.timeout = 1

        # Actual firmware upload
        while indexf < half_len or indexl < half_len:
            msg = self.serial.read(1)
            if msg == b"":
                # Timeout. End transfer
                raise ValueError("Upgrade failed - timeout during transfer")
            elif msg == b"c" or msg == b"\xff":
                # Absorb excess "c" that may occur after sending "d". 0xFF occur after sending "d" in B!O!O!T! triggered sequences but not on power-on.
                preamble_count += 1
            elif msg == b"0":
                if indexf < 0:
                    self.serial.write(lenf)
                else:
                    self.serial.write(buff[indexf].to_bytes(1, "big"))
                indexf += 1
            elif msg == b"1":
                if indexl < 0:
                    self.serial.write(lenl)
                else:
                    self.serial.write(bufl[indexl].to_bytes(1, "big"))
                indexl += 1
            else:
                # Unknown message from CW. Should we abort ? Count just in case.
                unknown_count += 1

            _update_tracker(
                status_tracker,
                preamble_count,
                indexf,
                indexl,
                firmware_len,
                unknown_count,
                False,
                True,
            )

        # Tell the progress tracker we're done
        _update_tracker(
            status_tracker,
            preamble_count,
            indexf,
            indexl,
            firmware_len,
            unknown_count,
            True,
            True,
        )

        # CW should now be rebooting. It will be in upgrade mode for a few more seconds and send a bunch of "c"
        # Let's wait until it is over.
        char_count = 0
        err_count = 0
        while char_count < 1000:
            msg = self.serial.read()
            char_count += 1
            if msg == b"":
                # Timeout. Done with the upgrade-ready pattern.
                # restore RS-232 parameters and return to end the upload process
                self.serial.baudrate = baudrate
                self.serial.timeout = timeout
                return
            elif msg != b"c":
                err_count += 1

        # If the loop ended, CW is still in upgrade mode. This means the upgrade failed. Troubleshoot.
        raise ValueError("Upgrade failed - stuck in upgrade mode")

    def get_analog_values(self) -> Dict[str, int]:
        """
        Reads the zener voltage, light detector voltage and rain sensor temperature DACs.
        Only 3 values as per Part 2 (Addendum)

        returns: a dictionary containing the raw reading zener_voltage, ldr_voltage, rain_sensor_temp. All values are in integer in [0,1023]
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

    def _update_analog_value_cache(self, force: bool = False) -> None:
        now = time.time()

        if (
            force
            or (len(self.analog_cache) == 0)
            or (self.analog_cache_timestamp - now) > self.analog_cache_lifetime_ms
        ):
            self.analog_cache = self.get_analog_values()

    @property
    def raw_zener_voltage(self) -> int:
        """
        Analog to Digital readout of the zener voltage

        :return: an integer in [0,1023]
        """
        self._update_analog_value_cache()
        return self.analog_cache["zener_voltage"]

    @property
    def raw_ldr_voltage(self) -> int:
        """
        Analog to Digital readout of the LDR (Light Dependent Resistor) sensor

        :return: an integer in [0,1023]
        """
        self._update_analog_value_cache()
        return self.analog_cache["ldr_voltage"]

    @property
    def raw_rain_sensor_temp(self) -> int:
        """
        Analog to Digital readout of the rain sensor temperature

        :return: an integer in [0,1023]
        """
        self._update_analog_value_cache()
        return self.analog_cache["rain_sensor_temp"]

    def get_capacitive_rain_sensor_temp(
        self, rain_sensor_temp: Optional[int] = None
    ) -> float:
        """
        Reads or convert the capacitive rain sensor temperature analog output (0-1023) into degrees Celsius.
        If the analog value is provided, it is converted. If it is None, the sensor value is read from the CloudWatcher.

        :rain_sensor_temp: analog value from the capacitive rain sensor. If None, the value will be read from the sensor.
        :return: the temperature of the sensor in degrees Celsius
        """
        # TODO: these values were hardcoded but now are taken from the CW.
        # Check which way is the "true" way based on the sensor type (capacitive vs Hydredon)
        # rain_pull_up_resistance = 1
        # rain_res_at_25 = 1
        # rain_beta = 3450
        absolute_zero = 273.15

        if rain_sensor_temp is None:
            rain_sensor_temp = self.raw_rain_sensor_temp

        if rain_sensor_temp < 1:
            rain_sensor_temp = 1
        elif rain_sensor_temp > 1022:
            rain_sensor_temp = 1022

        r = self.rain_pull_up_resistance / ((1023 / rain_sensor_temp) - 1)
        r = math.log(r / self.rain_res_at_25)

        return 1 / (r / self.rain_beta + 1 / (absolute_zero + 25)) - absolute_zero

    def get_ambient_light(self, ldr_voltage: Optional[int] = None) -> float:
        """
        Reads or convert the ambient light LDR (Light Dependent Resistor) value.

        If the LDR voltage is given, the value is converted using the internal LDR pull up resistance.
        If the LDR voltage is not given, the LDR voltage is fetched from the unit and converted into an LDR resistance.

        :ldr_voltage: the LDR voltage. If None, the value is fetched from the CloudWatcher
        :returns: a float that represents the LDR resistance in ohms.
        """
        if ldr_voltage is None:
            ldr_voltage = self.raw_ldr_voltage

        if ldr_voltage > 1022:
            ldr_voltage = 1022
        if ldr_voltage < 1:
            ldr_voltage = 1

        return self.ldr_pull_up_resistance / ((1023 / ldr_voltage) - 1)

    def get_relative_ambient_light(self, ldr_voltage: Optional[int] = None) -> float:
        """
        Reads or convert the ambient light LDR (Light Dependent Resistor) value to a percentage.
        get_ambient_light() returns a resistance value that is only really meaningful if the max LDR resistance is known.

        This method returns the ambient light as a float between 0 and 1 that represents the ratio of the LDR value to its max value

        If the LDR voltage is given, the value is converted using the internal LDR pull up resistance.
        If the LDR voltage is not given, the LDR voltage is fetched from the unit and converted into an LDR resistance.

        :ldr_voltage: the LDR voltage. If None, the value is fetched from the CloudWatcher
        :returns: a float in [0,1] that represents the LDR resistance ratio to its maximum value and reflects ambient light. 0: very dark; 1: very bright
        """
        return round(1 - self.get_ambient_light() / self.ldr_max_resistance, 2)

    def get_internal_errors(self) -> Dict[str, int]:
        """
        Reads the internal error status

        :returns: a dictionary containing 4 keys: first_address_byte_errors, command_byte_erross, second_address_byte_errors and PEC_byte_errors
        """
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
        Reads the relay switch status.

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
        Reads the relay switch open status.

        returns: True if open, False if closed
        """
        self.serial.write(b"G!")
        switch_open = self.__extract_string(self.__read_response(1)[0], b"!X")

        return switch_open == "Switch Open"

    def get_switch_close(self) -> bool:
        """
        Checks relay switch closed status.

        returns: True if closed, False if opened
        """
        self.serial.write(b"H!")
        switch_open = self.__extract_string(self.__read_response(1)[0], b"!Y")

        return switch_open == "Switch Close"

    def rain_sensor_heater_pwm(self, pwm: Union[int, None] = None) -> int:
        """
        Reads or sets the PWM value for the capacitive rain sensor heater.

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

    def get_sky_ir_temperature(self) -> float:
        """
        Reads and return the sky IR (infrared) temperature in Celsius.

        returns: IR sky temperature in Celsius
        """
        self.serial.write(b"S!")
        sky_ir_temp = self.__extract_int(self.__read_response(1)[0], b"!1")

        return round(sky_ir_temp / 100, 2)

    def get_ir_sensor_temperature(self) -> float:
        """
        Return the infrared sensor temperature in Celsius.

        returns: the IR sensor temperature in degrees Celsius
        """
        self.serial.write(b"T!")
        ir_sensor_temp = self.__extract_int(self.__read_response(1)[0], b"!2")

        return round(ir_sensor_temp / 100, 2)

    def get_constants(self) -> Dict[str, int]:
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

    def _update_constants_cache(self) -> None:
        if self.constants is None:
            self.constants = self.get_constants()

    @property
    def zener_voltage(self) -> float:
        self._update_constants_cache()
        return self.constants["zener_voltage"]

    @property
    def ldr_max_resistance(self) -> float:
        self._update_constants_cache()
        return self.constants["ldr_max_resistance"]

    @property
    def ldr_pull_up_resistance(self) -> float:
        self._update_constants_cache()
        return self.constants["ldr_pull_up_resistance"]

    @property
    def rain_beta(self) -> float:
        self._update_constants_cache()
        return self.constants["rain_beta"]

    @property
    def rain_res_at_25(self) -> float:
        self._update_constants_cache()
        return self.constants["rain_res_at_25"]

    @property
    def rain_pull_up_resistance(self) -> float:
        self._update_constants_cache()
        return self.constants["rain_pull_up_resistance"]

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

    def get_wind_speed(self, anemometer_type: Anemometer = Anemometer.black) -> float:
        """
        Returns the wind speed according to the anemometer model.
        From Part 4 (addendum/erratum).

        @black_anemometer: True if you have the black model. False if the old grey.
        :returns: returns the wind speed (float)
        """
        wind_sensor = self.get_wind_sensor()

        if anemometer_type == Anemometer.black:
            if wind_sensor > 0:
                wind_speed = (wind_sensor * 0.84) + 3
            else:
                wind_speed = 0
        elif anemometer_type == Anemometer.gray:
            wind_speed = wind_sensor
        else:
            raise NotImplementedError("Unsupported anemometer type")

        return round(wind_speed, 2)

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
