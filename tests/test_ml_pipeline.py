"""
Self-check for the ML pipeline.

Validates without a real Kite connection:
  - FeatureEngine produces the right output shape
  - FeatureEngine seeding (online path) matches training path shape
  - OnlineModel partial_fit runs without error
  - load_model() returns None gracefully when no model file exists

Run:
    python3 tests/test_ml_pipeline.py
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ml.feature_engine import FeatureEngine, N_FEATURES, FEATURE_NAMES


def _make_candle(i: int) -> dict:
    """Synthetic candle — enough price variation to avoid division-by-zero."""
    base = 100 + i * 0.1
    return {
        'open':  base,
        'high':  base + 1.5,
        'low':   base - 1.0,
        'close': base + 0.5 + (0.3 if i % 2 == 0 else -0.3),
        'volume': 100_000 + i * 500,
        'day_high': base + 3.0,
        'day_low':  base - 2.0,
    }


def test_feature_engine_shape():
    fe = FeatureEngine(maxlen=50)
    # Feed 40 candles — not enough for all indicators (need ≥30)
    for i in range(40):
        fe.update(_make_candle(i))
    vec = fe.latest_vector()
    assert vec is not None, "Expected vector after 40 candles"
    assert vec.shape == (N_FEATURES,), f"Expected ({N_FEATURES},), got {vec.shape}"
    assert not np.any(np.isnan(vec)), "Feature vector contains NaN"
    assert not np.any(np.isinf(vec)), "Feature vector contains Inf"
    print(f"  ✓ feature_engine shape: {vec.shape}")


def test_feature_engine_returns_none_when_insufficient():
    fe = FeatureEngine(maxlen=50)
    for i in range(10):   # only 10 candles — below min_bars threshold
        fe.update(_make_candle(i))
    vec = fe.latest_vector()
    assert vec is None, "Expected None with < 30 candles"
    print("  ✓ feature_engine returns None when insufficient data")


def test_feature_names_match_n_features():
    assert len(FEATURE_NAMES) == N_FEATURES, (
        f"FEATURE_NAMES has {len(FEATURE_NAMES)} items but N_FEATURES={N_FEATURES}"
    )
    print(f"  ✓ FEATURE_NAMES length matches N_FEATURES ({N_FEATURES})")


def test_online_model_partial_fit():
    from src.ml.online_model import OnlineModel
    model = OnlineModel()
    # Need ≥10 samples with both classes to clear the warmup buffer
    for i in range(15):
        fe = FeatureEngine(maxlen=50)
        # Use varied price series to avoid NaN in indicators
        for j in range(40):
            fe.update(_make_candle(j + i * 7))
        vec = fe.latest_vector()
        if vec is None:
            continue
        # Ensure no NaN slips through (constant-price edge case in test data)
        if np.any(np.isnan(vec)):
            vec = np.nan_to_num(vec, nan=0.0)
        label = 1 if i % 2 == 0 else 0
        model.update(vec, label)
    # warmup requires 10 samples with both classes; after that n_updates > 0
    assert model.n_updates > 0, (
        f"Expected n_updates > 0 after 15 samples; got {model.n_updates}. "
        "Warmup buffer may not have flushed — check warmup logic."
    )
    print(f"  ✓ online_model.partial_fit ran, n_updates={model.n_updates}")


def test_load_model_no_file():
    from src.ml.model_trainer import load_model, MODEL_PATH
    # Only test graceful None return if model.joblib doesn't exist
    if not os.path.exists(MODEL_PATH):
        pipeline, meta = load_model()
        assert pipeline is None and meta is None, "Expected (None,None) when model missing"
        print("  ✓ load_model() returns (None, None) gracefully when no model file")
    else:
        # Model already trained — just check it loads
        pipeline, meta = load_model()
        assert pipeline is not None, "Model file exists but load failed"
        assert 'cv_accuracy_mean' in meta, "Metadata missing cv_accuracy_mean"
        print(f"  ✓ load_model() loaded existing model, accuracy={meta['cv_accuracy_mean']:.1%}")


def test_from_backtester_arrays():
    """FeatureEngine.from_backtester_arrays matches shape of online update."""
    n = 50
    closes  = np.array([100.5 + i * 0.1 + (0.3 if i%2==0 else -0.3) for i in range(n)], dtype=np.float32)
    highs   = np.array([101.5 + i * 0.1 for i in range(n)], dtype=np.float32)
    lows    = np.array([99.0  + i * 0.1 for i in range(n)], dtype=np.float32)
    volumes = np.array([100_000 + i * 500 for i in range(n)], dtype=np.float32)
    arrs = {
        'close':  closes,
        'high':   highs,
        'low':    lows,
        'open':   closes - 0.3,
        'volume': volumes,
        'dh':     highs + 1.0,   # day high
        'dl':     lows  - 1.0,   # day low
    }
    fe = FeatureEngine()
    X = fe.from_backtester_arrays(arrs)
    assert X is not None, "from_backtester_arrays returned None"
    assert X.ndim == 2, f"Expected 2D array, got ndim={X.ndim}"
    assert X.shape[1] == N_FEATURES, f"Expected {N_FEATURES} cols, got {X.shape[1]}"
    assert not np.any(np.isnan(X)), "feature_matrix contains NaN"
    print(f"  ✓ from_backtester_arrays: matrix shape {X.shape}")


if __name__ == '__main__':
    tests = [
        test_feature_names_match_n_features,
        test_feature_engine_shape,
        test_feature_engine_returns_none_when_insufficient,
        test_online_model_partial_fit,
        test_load_model_no_file,
        test_from_backtester_arrays,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            print(f"\nRunning {t.__name__}...")
            t()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
