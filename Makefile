PY=.venv/bin/python

bootstrap:
	bash scripts/bootstrap_mac.sh

seed:
	$(PY) scripts/seed_universe.py

research:
	$(PY) scripts/research_universe.py

export:
	$(PY) scripts/export_due_diligence.py

train:
	$(PY) scripts/train_priority_model.py

test:
	$(PY) -m pytest packages/research/tests -q

public-check:
	$(PY) scripts/public_release_check.py

dev:
	bash scripts/dev.sh
