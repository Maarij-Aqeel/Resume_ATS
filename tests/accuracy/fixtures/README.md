# Accuracy Fixtures

To run the accuracy benchmark, place resume files + matching ground-truth JSON here:

```
fixtures/
  alice_smith.pdf
  alice_smith.gt.json
  bob_jones.docx
  bob_jones.gt.json
  ...
```

Each `*.gt.json` file must contain a ground-truth object with the same shape
as `ResumeSchema` (or at least the fields your benchmark will score).

Place 20 manually verified pairs before running:

```
pytest tests/accuracy/ --benchmark
```

The benchmark will fail if any of the per-field thresholds in
`tests/accuracy/benchmark.py::TARGETS` are missed.
