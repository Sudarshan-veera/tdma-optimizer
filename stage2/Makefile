R ?= 100
PY ?= python3
export PYTHONPATH := .

.PHONY: setup test demo exp report all clean graphs
N ?= 18
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
graphs:
	$(PY) -m tdmaopt.viz --n $(N) $(ARGS)
report:
	$(PY) scripts/make_report.py
all: test exp report
clean:
	rm -f results/*.json results/*.png docs/RESULTS.md

analyze:
	$(PY) -m tdmaopt.analyze --n $(N) --range $(R) $(ARGS)

optimize:
	$(PY) -m tdmaopt.hetero $(ARGS)

paper:
	python -m tdmaopt.paper --heavy
	cd paper && pdflatex main && pdflatex main
