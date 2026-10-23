import os, sys, pathlib
os.environ["LLM_MODE"] = "mock"
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
