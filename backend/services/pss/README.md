# Predictive Simulation Service (PSS)

Train **XGBoost** regressors on completed mass-run jobs and predict `result_fields` without starting OpenFOAM.

## Port

- Compose: internal **8003** (`pss` service)
- Not published to host; browser uses BFF proxies

## Data flow

1. User assigns mass runs to training/testing on **Simulation predictive model** (`predictive_models` Mongo collection, keyed by `simulation_id`).
2. `POST /api/simulations/{sim_id}/predictive-models/train` loads rows via simulation `GET /api/mass-runs/{id}/results.csv` (completed jobs only).
3. Features: simulation `input_fields` labels (numeric). Targets: `result_fields` (one XGBoost model per target).
4. Artifacts: `joblib` files under `PSS_MODELS_ROOT` (default `/pss_models`, Compose volume `pss_models`).
5. Metadata: Mongo `pss_trained_models`.

## Metrics (test set)

Per target: **RMSE**, **MAE**, **R²**. **Aggregate** = unweighted mean across targets (see `metrics.note` in API responses). If no testing mass runs are configured, test metrics are `null`.

Minimum **5** completed training rows (`MIN_TRAIN_ROWS` in `dataset.py`).

## API (internal; BFF proxies)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health |
| GET | `/api/simulations/{sim_id}/predictive-models` | List trained models |
| POST | `/api/simulations/{sim_id}/predictive-models/train` | Train (`technique`, optional mass run ID overrides) |
| GET | `/api/predictive-models/{model_id}` | Model detail + metrics |
| POST | `/api/predictive-models/{model_id}/predict` | Body `{ "inputs": { field_key: value } }` |

Train/test split config (simulation service): `GET/PUT /api/simulations/{id}/predictive-model` (singular).

## Environment

| Variable | Default |
|----------|---------|
| `MONGODB_URI` | `mongodb://mongo:27017` |
| `MONGODB_DB` | `forge_web` |
| `SIMULATION_SERVICE_URL` | `http://simulation:8001` |
| `PSS_MODELS_ROOT` | `/pss_models` |

## Dependencies

`xgboost`, `scikit-learn`, `numpy`, `pandas`, `joblib` (see root `backend/requirements.txt` and optional `requirements-pss.txt`).

## Local run

```bash
cd backend
pip install -r requirements.txt
export MONGODB_URI=mongodb://127.0.0.1:27017
export SIMULATION_SERVICE_URL=http://127.0.0.1:8001
export PSS_MODELS_ROOT=./data/pss_models
uvicorn services.pss.app:app --host 0.0.0.0 --port 8003
```
