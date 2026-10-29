import os
import random

import numpy as np
from dotenv import load_dotenv

load_dotenv()
SEED = int(os.getenv("SEED", "42"))


def set_seed(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
