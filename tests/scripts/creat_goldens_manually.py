import os
from pathlib import Path
# go up to levels
os.chdir(Path(__file__).parent.parent.parent)
from tests.configs import load_model, ALL_MODEL_CONFIGS
from tests.helpers.generate_all_goldens import generate_all_for_model


for model_config in ALL_MODEL_CONFIGS:
    generate_all_for_model(model_config)
