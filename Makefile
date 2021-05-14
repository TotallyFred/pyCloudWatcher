all: distribution install

distribution: setup.py cloudwatcher/*
	python setup.py check
	python setup.py sdist
	python setup.py bdist_wheel --universal

install:
	pip install .

clean:
	pip uninstall --yes cloudwatcher
