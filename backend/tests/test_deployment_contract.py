import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def read_json(relative_path: str) -> dict:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def assert_no_literal_openai_key(config: dict) -> None:
    serialized = json.dumps(config)
    assert "OPENAI_API_KEY" not in serialized
    assert "sk-" not in serialized


def test_backend_vercel_json_versions_fastapi_deploy_contract():
    config = read_json("backend/vercel.json")

    assert config["$schema"] == "https://openapi.vercel.sh/vercel.json"
    assert config["framework"] == "fastapi"
    assert set(config["functions"]) == {"api/**/*.py"}
    function_config = config["functions"]["api/**/*.py"]
    assert function_config["maxDuration"] == 10
    assert "tests/**" in function_config["excludeFiles"]
    assert ".venv/**" in function_config["excludeFiles"]
    assert_no_literal_openai_key(config)


def test_frontend_vercel_json_versions_vite_deploy_contract():
    config = read_json("frontend/vercel.json")

    assert config["$schema"] == "https://openapi.vercel.sh/vercel.json"
    assert config["framework"] == "vite"
    assert config["installCommand"] == "npm install"
    assert config["buildCommand"] == "npm run build"
    assert config["outputDirectory"] == "dist"
    assert config["build"]["env"] == {
        "VITE_API_BASE_URL": "https://backend-rho-amber-37.vercel.app"
    }
    assert config["rewrites"] == [{"source": "/(.*)", "destination": "/index.html"}]
    assert_no_literal_openai_key(config)
