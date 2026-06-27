VENV_DIR ?= .venv
PYTHON ?= $(VENV_DIR)/bin/python
BENCHMARK_CASES ?= 100
BENCHMARK_DATASET ?= .benchmarks/v2_opaque_labels/dataset.json
BENCHMARK_OUTPUT_DIR ?= .benchmarks/dmu
BENCHMARK_TOP_K ?= 5
BENCHMARK_CANDIDATE_LIMIT ?= 50

.PHONY: bootstrap test benchmark ci standalone-benchmark standalone-benchmark-chroma standalone-benchmark-all

bootstrap: $(VENV_DIR)/.bootstrap.stamp

$(VENV_DIR)/.bootstrap.stamp: scripts/bootstrap_venv.sh pyproject.toml requirements.txt
	./scripts/bootstrap_venv.sh
	@mkdir -p $(VENV_DIR)
	@touch $@

test: bootstrap
	$(PYTHON) -m pytest -q 		tests/test_anchor_dashboard.py 		tests/test_dmu_retrieval_benchmark.py 		tests/test_trinity_caseflow.py 		tests/test_sync_logs.py

benchmark: bootstrap
	$(PYTHON) scripts/dmu_retrieval_benchmark.py 		--cases $(BENCHMARK_CASES) 		--output-dir $(BENCHMARK_OUTPUT_DIR)

ci: test benchmark

standalone-benchmark: bootstrap
	$(PYTHON) scripts/standalone_dmu_comparison_runner.py \
		--dataset $(BENCHMARK_DATASET) \
		--backend synthetic \
		--cases $(BENCHMARK_CASES) \
		--top-k $(BENCHMARK_TOP_K) \
		--candidate-limit $(BENCHMARK_CANDIDATE_LIMIT) \
		--output-dir $(BENCHMARK_OUTPUT_DIR)

standalone-benchmark-chroma: bootstrap
	DRIFT_CHROMA_PERSIST_DIR=$${DRIFT_CHROMA_PERSIST_DIR:-./chroma_db} DRIFT_MEMORY_COLLECTION=$${DRIFT_MEMORY_COLLECTION:-drift_memory} DRIFT_EMBEDDING_MODEL=$${DRIFT_EMBEDDING_MODEL:-all-MiniLM-L6-v2} \
	$(PYTHON) scripts/standalone_dmu_comparison_runner.py \
		--dataset $(BENCHMARK_DATASET) \
		--mode chroma \
		--top-k $(BENCHMARK_TOP_K) \
		--candidate-limit $(BENCHMARK_CANDIDATE_LIMIT) \
		--output-dir $(BENCHMARK_OUTPUT_DIR) \
		--chroma-persist-dir "$${DRIFT_CHROMA_PERSIST_DIR}" \
		--chroma-collection-name "$${DRIFT_MEMORY_COLLECTION}" \
		--chroma-embedding-model "$${DRIFT_EMBEDDING_MODEL}"

standalone-benchmark-all: standalone-benchmark standalone-benchmark-chroma
	@echo "✓ Both synthetic and ChromaDB benchmark runs complete."
