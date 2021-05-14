all: distribution install

distribution: setup.py
	python setup.py check
	python setup.py sdist

install: pyCloudWatcher-1.0.0.tar.gz
	pip install .

clean:
	pip uninstall --yes pyCloudWatcher
