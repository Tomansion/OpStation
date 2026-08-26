# Everyday commands. `make help` lists them.
PY := .venv/bin/python

.PHONY: help venv test serve generate station sheets portraits voices clean

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t22

venv:  ## create .venv and install everything needed for development
	python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r backend/requirements-dev.txt

test:  ## run the test suite
	cd backend && ../$(PY) -m pytest tests -q

serve:  ## run the game on http://localhost:3000
	$(PY) -m uvicorn --app-dir backend websrv:app --reload --host 0.0.0.0 --port 3000 

generate:  ## generate one scenario into the bank (ARGS="--finale invasion")
	cd backend && ../$(PY) -m opstation.generate $(ARGS)

station:  ## rebuild station/preview.html from station.json
	$(PY) station/build_preview.py

sheets:  ## rebuild the printable sector handbook
	$(PY) station/build_sector_sheets.py

portraits:  ## regenerate the placeholder actor portraits
	$(PY) assets/make_placeholder_portraits.py

voices:  ## download the six pinned Piper voice models
	$(PY) assets/download_voices.py

clean:  ## remove caches
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
