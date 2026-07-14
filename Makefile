setup:
	pip install -e ".[dev]"
once:
	python -m geopulse.l1_ingestion_detection.run_local once
loop:
	python -m geopulse.l1_ingestion_detection.run_local loop
drain:
	python -m geopulse.l1_ingestion_detection.run_local drain
test:
	pytest tests/ -q
dashboard:
	streamlit run l3_dashboard/dashboard.py
