PY ?= python3
export PYTHONPATH := .

.PHONY: setup test demo exp report all clean
setup:
	$(PY) -m pip install -r requirements.txt
test:
	$(PY) -m pytest -q
demo:
	$(PY) -m tdmaopt.demo
exp:
	$(PY) -m experiments.exp_baselines
	$(PY) -m experiments.exp_scaling
	$(PY) -m experiments.exp_exact
	$(PY) -m experiments.exp_sinr
	$(PY) -m experiments.exp_dynamic
	$(PY) -m experiments.exp_coverage
report:
	$(PY) scripts/make_report.py
all: test exp report
clean:
	rm -f results/*.json results/*.png docs/RESULTS.md
