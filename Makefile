VENV_DIR ?= .venv
PYTHON ?= $(VENV_DIR)/bin/python
STANDALONE_RUNNER := $(PYTHON) scripts/standalone_dmu_comparison_runner.py
EXPORT_DATASET := $(PYTHON) scripts/export_dmu_benchmark_dataset.py

BENCHMARK_CASES ?= 100
BENCHMARK_DATASET ?= benchmarks/v2_opaque_labels/dataset.json
BENCHMARK_OUTPUT ?= benchmarks/comparison_runs
BENCHMARK_METHODS ?= cosine,guarded_dmu,rrf
BENCHMARK_TOP_K ?= 5
BENCHMARK_CANDIDATE_LIMIT ?= 50

.PHONY: bootstrap test benchmark ci export-benchmark-dataset standalone-benchmark standalone-benchmark-chroma standalone-benchmark-all

bootstrap: $(VENV_DIR)/.bootstrap.stamp

$(VENV_DIR)/.bootstrap.stamp: scripts/bootstrap_venv.sh pyproject.toml requirements.txt
	./scripts/bootstrap_venv.sh
	@mkdir -p $(VENV_DIR)
	@touch $@

test: bootstrap
	$(PYTHON) -m pytest -q \
		tests/test_anchor_dashboard.py \
		tests/test_dmu_retrieval_benchmark.py \
		tests/test_standalone_dmu_comparison_runner.py \
		tests/test_memory_store_config.py \
		tests/test_trinity_caseflow.py \
		tests/test_sync_logs.py

benchmark: bootstrap
	$(PYTHON) scripts/dmu_retrieval_benchmark.py \
		--cases $(BENCHMARK_CASES) \
		--output-dir $(BENCHMARK_OUTPUT)

ci: test benchmark

export-benchmark-dataset: bootstrap
	$(EXPORT_DATASET) --cases $(BENCHMARK_CASES) --output $(BENCHMARK_DATASET)

standalone-benchmark: bootstrap export-benchmark-dataset
	@echo "▶ Running DMU comparative benchmark (synthetic mode)..."
	$(STANDALONE_RUNNER) \
		--backend synthetic \
		--cases $(BENCHMARK_CASES) \
		--dataset-version v2_opaque_labels \
		--methods $(BENCHMARK_METHODS) \
		--top-k $(BENCHMARK_TOP_K) \
		--candidate-limit $(BENCHMARK_CANDIDATE_LIMIT) \
		--output-dir $(BENCHMARK_OUTPUT)

standalone-benchmark-chroma: bootstrap export-benchmark-dataset
	@echo "▶ Running DMU comparative benchmark (ChromaDB mode)..."
	@DRIFT_CHROMA_PERSIST_DIR=$(or $(DRIFT_CHROMA_PERSIST_DIR),./chroma_db) \
	 DRIFT_MEMORY_COLLECTION=$(or $(DRIFT_MEMORY_COLLECTION),drift_memory) \
	 DRIFT_EMBEDDING_MODEL=$(or $(DRIFT_EMBEDDING_MODEL),all-MiniLM-L6-v2) \
	 DRIFT_DEFAULT_N_RESULTS=$(or $(DRIFT_DEFAULT_N_RESULTS),$(BENCHMARK_CANDIDATE_LIMIT)) \
	 $(STANDALONE_RUNNER) \
		--dataset $(BENCHMARK_DATASET) \
		--backend chroma \
		--methods $(BENCHMARK_METHODS) \
		--top-k $(BENCHMARK_TOP_K) \
		--candidate-limit $(BENCHMARK_CANDIDATE_LIMIT) \
		--output-dir $(BENCHMARK_OUTPUT) \
		--chroma-persist-dir "$(or $(DRIFT_CHROMA_PERSIST_DIR),./chroma_db)" \
		--chroma-collection-name "$(or $(DRIFT_MEMORY_COLLECTION),drift_memory)" \
		--chroma-embedding-model "$(or $(DRIFT_EMBEDDING_MODEL),all-MiniLM-L6-v2)"

standalone-benchmark-all: standalone-benchmark standalone-benchmark-chroma
	@echo "✓ Both synthetic and ChromaDB benchmark runs complete."
