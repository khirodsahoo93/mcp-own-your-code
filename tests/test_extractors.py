"""Tests for multi-language extractor abstraction."""
import textwrap
import pytest

from src.extractors.python_extractor import PythonExtractor
from src.extractors.typescript_extractor import TypeScriptExtractor
from src.extractors.go_extractor import GoExtractor
from src.extractors import get_extractor, SUPPORTED_EXTENSIONS
from src.extractor import scan_project_multi


# ── Python ──────────────────────────────────────────────────────────────────

def test_python_extractor_basic():
    src = textwrap.dedent("""\
        def add(a: int, b: int) -> int:
            return a + b

        class Greeter:
            def hello(self, name: str) -> str:
                return f"Hello, {name}"
    """)
    ext = PythonExtractor()
    fns = ext.extract(src, "math.py")
    names = [f["qualname"] for f in fns]
    assert "add" in names
    assert "Greeter.hello" in names
    for fn in fns:
        assert fn["language"] == "python"


def test_python_extractor_async():
    src = "async def fetch(url: str): pass\n"
    fns = PythonExtractor().extract(src, "net.py")
    assert fns[0]["is_async"] is True


# ── TypeScript ───────────────────────────────────────────────────────────────

def test_typescript_extractor_function_declaration():
    src = "function greet(name) { return `Hello ${name}`; }\n"
    fns = TypeScriptExtractor().extract(src, "greet.ts")
    assert len(fns) >= 1
    assert any(f["name"] == "greet" for f in fns)
    for fn in fns:
        assert fn["language"] == "typescript"


def test_typescript_extractor_arrow_function():
    src = "const double = (x) => x * 2;\n"
    fns = TypeScriptExtractor().extract(src, "math.ts")
    # tree-sitter or regex should capture this
    assert len(fns) >= 1


def test_typescript_extractor_class_method():
    src = textwrap.dedent("""\
        class Calculator {
          add(a, b) { return a + b; }
          async fetchResult(url) { return fetch(url); }
        }
    """)
    fns = TypeScriptExtractor().extract(src, "calc.ts")
    assert len(fns) >= 1


# ── Go ───────────────────────────────────────────────────────────────────────

def test_go_extractor_function():
    src = textwrap.dedent("""\
        package main

        import "fmt"

        func Hello(name string) string {
            return fmt.Sprintf("Hello, %s", name)
        }

        func Add(a, b int) int {
            return a + b
        }
    """)
    fns = GoExtractor().extract(src, "main.go")
    names = [f["name"] for f in fns]
    assert "Hello" in names
    assert "Add" in names
    for fn in fns:
        assert fn["language"] == "go"


def test_go_extractor_method():
    src = textwrap.dedent("""\
        package service

        type UserService struct{}

        func (s *UserService) GetUser(id int) (*User, error) {
            return nil, nil
        }
    """)
    fns = GoExtractor().extract(src, "service.go")
    assert len(fns) >= 1
    method = fns[0]
    assert method["is_method"] is True
    assert method["class_name"] == "UserService"
    assert method["qualname"] == "UserService.GetUser"


# ── Registry ─────────────────────────────────────────────────────────────────

def test_registry_extensions():
    for ext in [".py", ".ts", ".tsx", ".js", ".jsx", ".go"]:
        assert ext in SUPPORTED_EXTENSIONS
        assert get_extractor(ext) is not None


def test_unsupported_extension():
    assert get_extractor(".rb") is None
    assert get_extractor(".java") is None


# ── scan_project_multi ────────────────────────────────────────────────────────

def test_scan_project_multi_python_only(tmp_path):
    (tmp_path / "app.py").write_text("def run(): pass\n")
    (tmp_path / "main.ts").write_text("function start() {}\n")
    fns, errors = scan_project_multi(str(tmp_path), languages=["python"])
    langs = {f["language"] for f in fns}
    assert "python" in langs
    assert "typescript" not in langs
    assert errors == []


def test_scan_project_multi_all_languages(tmp_path):
    (tmp_path / "app.py").write_text("def run(): pass\n")
    (tmp_path / "main.ts").write_text("function start() {}\n")
    go_src = "package main\nfunc Main() {}\n"
    (tmp_path / "main.go").write_text(go_src)
    fns, _ = scan_project_multi(str(tmp_path))
    langs = {f["language"] for f in fns}
    assert "python" in langs
    assert "typescript" in langs
    assert "go" in langs


def test_scan_project_multi_include_globs(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "api.py").write_text("def handle(): pass\n")
    (tmp_path / "other.py").write_text("def ignore(): pass\n")
    fns, _ = scan_project_multi(str(tmp_path), include_globs=["src/**/*.py"])
    names = [f["name"] for f in fns]
    assert "handle" in names
    assert "ignore" not in names


def test_scan_project_multi_ignore_dirs(tmp_path):
    (tmp_path / "app.py").write_text("def keep(): pass\n")
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "lib.py").write_text("def skip(): pass\n")
    fns, _ = scan_project_multi(str(tmp_path), ignore_dirs=["vendor"])
    names = [f["name"] for f in fns]
    assert "keep" in names
    assert "skip" not in names


def test_scan_project_multi_skips_extra_venv_and_site_packages(tmp_path):
    (tmp_path / "good.py").write_text("def keep(): pass\n")
    nested = tmp_path / ".venv-pypi-test" / "lib" / "site-packages" / "pkg"
    nested.mkdir(parents=True)
    (nested / "noise.py").write_text("def skip_me(): pass\n")
    fns, _ = scan_project_multi(str(tmp_path))
    names = [f["name"] for f in fns]
    assert "keep" in names
    assert "skip_me" not in names


def test_scan_project_multi_skips_egg_info_dir_name(tmp_path):
    (tmp_path / "app.py").write_text("def keep(): pass\n")
    egg = tmp_path / "mydist-0.1.egg-info"
    egg.mkdir()
    (egg / "fake.py").write_text("def bogus(): pass\n")
    fns, _ = scan_project_multi(str(tmp_path))
    names = [f["name"] for f in fns]
    assert "keep" in names
    assert "bogus" not in names
