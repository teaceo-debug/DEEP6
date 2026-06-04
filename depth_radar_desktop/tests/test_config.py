from __future__ import annotations
from depth_radar_desktop.config import load_config, PROJECT_ROOT


def test_config_defaults():
    c = load_config()
    assert c.rithmic_symbol == "NQM6"
    assert c.rithmic_exchange == "CME"
    assert c.min_wall_size == 50
    assert c.update_interval_ms == 500
    assert c.rth_only is True
    assert c.source == "rithmic"


def test_config_model_dir_absolute():
    c = load_config()
    assert c.model_dir.is_absolute()
    assert "deep6" in str(c.model_dir) or "models" in str(c.model_dir)


def test_config_training_output_dir_absolute():
    c = load_config()
    assert c.training_output_dir.is_absolute()


def test_config_intent_model_path():
    c = load_config()
    assert c.intent_model_path.name == "intent_classifier_v4.joblib"


def test_config_interaction_model_path():
    c = load_config()
    assert c.interaction_model_path.name == "interaction_predictor_v4.joblib"


def test_config_rithmic_not_configured_by_default():
    c = load_config()
    assert c.rithmic_configured is False


def test_project_root_found():
    assert PROJECT_ROOT.exists()
    assert (PROJECT_ROOT / "deep6").exists() or (PROJECT_ROOT / ".git").exists()
