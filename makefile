
lint: soco
	flake8 soco
	flake8 --ignore=F401,F841 tests
	pylint soco

test:
	py.test

docs:
	$(MAKE) -C doc html
	@echo "\033[95m\n\nBuild successful! View the docs at doc/_build/html/index.html.\n\033[0m"

clean:
	find . -name '*.py[co]' -delete

	find . -name '*~' -delete
	find . -name '__pycache__' -delete
	rm -rf soco.egg-info
	rm -rf dist
	$(MAKE) -C doc clean

.PHONY: lint docs test clean
