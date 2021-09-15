# pyCloudWatcher
## What is this ?
This project aims at offering a native Python SDK for the CloudWatcher weather station by Lunatico Astro:

https://lunaticoastro.com/aag-cloud-watcher/
https://eu.lunaticoastro.com/product/aag-cloudwatcher-hydreon-rain-sensor-version/

The technical documentation can be found at:

https://lunaticoastro.com/aag-cloud-watcher/moreinfo/

Particularly, the protocol description is in the section called "Information for developers / integrators" (bottom right corner).

I can only recommend LunaticoAstro. Their staff is super friendly and responsive; even for technical questions around the CloudWatcher serial protocol (yes, they do support the hardcore stuff).

I will likely purchase their Pocket CW as it supports the same API as the stationary CloudWatcher. If you happen to have a PocketCW to test with, please report feedback.

Please note: I do not have a CW unit with the capacitive rain sensor. Mine has the hydreon. I can't test anything around these sensors and related parameters. If you want me to check that out, please consider sending me the relevant equipment as a donation :-)

## API Documentation
Once you cloned the repository, install the project with `make install`.

The python API can be used by simply by importing the main module: `import cloudwatcher`. Each API call is documented within the source code of this project. More precisely in `cloudwatcher/__init__.py`.

You will find an example use case of the library in `cwmqtt.py`; a sample script that reads data from a CloudWatcher and publishes it via MQTT.

## Upgrade utility
`cwupgrade.py` upgrades the microcode of your CloudWatcher. Check out `cwupgrade.py --help` for instructions. It is rather simple.
