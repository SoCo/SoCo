
lint: soco
	flake8 soco
	pylint --rcfile=.pylintrc soco

.PHONY: lint
