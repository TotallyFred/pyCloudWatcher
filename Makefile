all: distribution

distribution: setup.py
	python setup.py check
	python setup.py sdist

install:
	pip install .

clean:
	pip uninstall pyCloudWatcher
