"""Tests for scripts/dev/clean_caches.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dev import clean_caches


def _make_tree(root: Path, structure: dict[str, str | dict]) -> None:
    """Create a directory tree from a nested dict."""
    for name, content in structure.items():
        path = root / name
        if isinstance(content, dict):
            path.mkdir(parents=True, exist_ok=True)
            _make_tree(path, content)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """Create a fake project root with known structure."""
    structure: dict[str, str | dict] = {
        "src": {
            "main.py": "print('hello')",
            "utils": {
                "__pycache__": {
                    "cache.pyc": "fake",
                },
                "__init__.py": "",
            },
        },
        ".venv": {
            "lib": {
                "__pycache__": {
                    "lib_cache.pyc": "fake",
                },
            },
        },
        "netwatch": {
            "location": {
                "data": {
                    "china_district_centers.csv": "lat,lon,name",
                    "sample_boundary.geojson": '{"type":"Feature"}',
                },
            },
        },
        "tests": {
            "fixtures": {
                "data.geojson": '{"type":"Feature"}',
                "info.csv": "a,b",
            },
            "unit": {
                "__pycache__": {
                    "test_module.pyc": "fake",
                },
            },
        },
        "build": {
            "temp.o": "binary",
        },
        "temp.pyc": "fake",
        "temp.pyo": "fake",
    }
    _make_tree(tmp_path, structure)
    return tmp_path


@pytest.fixture
def patched_env(
    monkeypatch: pytest.MonkeyPatch, fake_root: Path
) -> None:
    """Point clean_caches module at fake_root."""
    monkeypatch.setattr(clean_caches, "REPO_ROOT", fake_root)
    monkeypatch.setattr(
        clean_caches,
        "PROTECTED_PATHS",
        [
            fake_root / ".venv",
            fake_root / "netwatch" / "location" / "data",
            fake_root / "tests" / "fixtures",
        ],
    )


# ---------------------------------------------------------------------------
# Unit: is_under_protected
# ---------------------------------------------------------------------------


class TestIsUnderProtected:
    def test_venv_is_protected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "project"
        root.mkdir()
        protected = [root / ".venv"]
        monkeypatch.setattr(clean_caches, "PROTECTED_PATHS", protected)

        p = root / ".venv" / "lib" / "cache.pyc"
        assert clean_caches.is_under_protected(p)

    def test_location_data_is_protected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "project"
        root.mkdir()
        protected = [root / "netwatch" / "location" / "data"]
        monkeypatch.setattr(clean_caches, "PROTECTED_PATHS", protected)

        p = root / "netwatch" / "location" / "data" / "centers.csv"
        assert clean_caches.is_under_protected(p)

    def test_fixtures_is_protected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "project"
        root.mkdir()
        protected = [root / "tests" / "fixtures"]
        monkeypatch.setattr(clean_caches, "PROTECTED_PATHS", protected)

        p = root / "tests" / "fixtures" / "data.geojson"
        assert clean_caches.is_under_protected(p)

    def test_src_pycache_is_not_protected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "project"
        root.mkdir()
        monkeypatch.setattr(clean_caches, "PROTECTED_PATHS", [])

        p = root / "src" / "__pycache__" / "cache.pyc"
        assert not clean_caches.is_under_protected(p)


# ---------------------------------------------------------------------------
# Unit: is_protected_extension
# ---------------------------------------------------------------------------


class TestIsProtectedExtension:
    def test_geojson_is_protected(self) -> None:
        assert clean_caches.is_protected_extension(Path("data.geojson"))

    def test_csv_is_protected(self) -> None:
        assert clean_caches.is_protected_extension(Path("info.csv"))

    def test_md_is_protected(self) -> None:
        assert clean_caches.is_protected_extension(Path("readme.md"))

    def test_py_is_protected(self) -> None:
        assert clean_caches.is_protected_extension(Path("main.py"))

    def test_pyc_is_not_protected(self) -> None:
        assert not clean_caches.is_protected_extension(Path("temp.pyc"))

    def test_o_is_not_protected(self) -> None:
        assert not clean_caches.is_protected_extension(Path("temp.o"))


# ---------------------------------------------------------------------------
# Integration: collect_candidates
# ---------------------------------------------------------------------------


class TestCollectCandidates:
    def test_detects_pycache_dirs(
        self, patched_env: None, fake_root: Path
    ) -> None:
        dirs, files, skipped = clean_caches.collect_candidates()
        dir_rel = {str(d.relative_to(fake_root)) for d in dirs}
        assert "src/utils/__pycache__" in dir_rel
        assert "tests/unit/__pycache__" in dir_rel

    def test_detects_named_dirs(
        self, patched_env: None, fake_root: Path
    ) -> None:
        dirs, files, skipped = clean_caches.collect_candidates()
        dir_rel = {str(d.relative_to(fake_root)) for d in dirs}
        assert "build" in dir_rel

    def test_detects_pyc_files(
        self, patched_env: None, fake_root: Path
    ) -> None:
        dirs, files, skipped = clean_caches.collect_candidates()
        file_rel = {str(f.relative_to(fake_root)) for f in files}
        assert "temp.pyc" in file_rel
        assert "temp.pyo" in file_rel

    def test_skips_protected_pycache(
        self, patched_env: None, fake_root: Path
    ) -> None:
        """__pycache__ under .venv must be skipped."""
        dirs, files, skipped = clean_caches.collect_candidates()
        dir_rel = {str(d.relative_to(fake_root)) for d in dirs}
        assert ".venv/lib/__pycache__" not in dir_rel

    def test_skips_protected_extensions(
        self, patched_env: None, fake_root: Path
    ) -> None:
        """.geojson and .csv under data must be skipped."""
        dirs, files, skipped = clean_caches.collect_candidates()
        file_rel = {str(f.relative_to(fake_root)) for f in files}
        assert "netwatch/location/data/china_district_centers.csv" not in file_rel
        assert "netwatch/location/data/sample_boundary.geojson" not in file_rel
        assert "tests/fixtures/data.geojson" not in file_rel

    def test_skipped_count_positive(
        self, patched_env: None, fake_root: Path
    ) -> None:
        dirs, files, skipped = clean_caches.collect_candidates()
        assert skipped > 0

    def test_no_false_negative_on_protected_path(
        self, patched_env: None, fake_root: Path
    ) -> None:
        """Ensure non-protected pycache dirs are not accidentally skipped."""
        # .venv's __pycache__ is the only one under protected paths in our fixture
        dirs, files, skipped = clean_caches.collect_candidates()
        dir_rel = {str(d.relative_to(fake_root)) for d in dirs}
        assert "src/utils/__pycache__" in dir_rel
        assert "tests/unit/__pycache__" in dir_rel


# ---------------------------------------------------------------------------
# Integration: dry-run does not delete
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_flag_preserves_files(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "test_dry"
        root.mkdir()
        cache = root / "__pycache__"
        cache.mkdir(parents=True)
        pyc = cache / "dummy.pyc"
        pyc.touch()
        geojson = root / "keep.geojson"
        geojson.touch()

        monkeypatch.setattr(clean_caches, "REPO_ROOT", root)
        monkeypatch.setattr(clean_caches, "PROTECTED_PATHS", [])

        # Call collect_candidates (dry-run is just a check, never deletes)
        dirs, files, skipped = clean_caches.collect_candidates()
        assert len(dirs) >= 1
        assert len(files) >= 1

        # Files must still exist after collect_candidates (it's read-only)
        assert cache.exists()
        assert pyc.exists()
        assert geojson.exists()

    def test_dry_run_main_exit_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main() with --dry-run returns 0 and does not error."""
        monkeypatch.setattr("sys.argv", ["clean_caches.py", "--dry-run"])
        rc = clean_caches.main()
        assert rc == 0


# ---------------------------------------------------------------------------
# Integration: actual cleanup deletes targets, preserves protected
# ---------------------------------------------------------------------------


class TestActualCleanup:
    def test_removes_pycache_and_pyc(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "test_clean"
        root.mkdir()
        cache = root / "__pycache__"
        cache.mkdir(parents=True)
        pyc = root / "temp.pyc"
        pyc.touch()
        geojson = root / "data.geojson"
        geojson.touch()

        monkeypatch.setattr(clean_caches, "REPO_ROOT", root)
        monkeypatch.setattr(clean_caches, "PROTECTED_PATHS", [])

        dirs, files, skipped = clean_caches.collect_candidates()

        # Simulate main() cleanup logic (without CLI parsing)
        import shutil

        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)
        for f in files:
            if clean_caches.is_protected_extension(f):
                continue
            f.unlink(missing_ok=True)

        assert not cache.exists(), "__pycache__ should be deleted"
        assert not pyc.exists(), ".pyc file should be deleted"
        assert geojson.exists(), ".geojson should survive (protected extension)"

    def test_protected_dir_survives(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "test_prot"
        root.mkdir()
        protected_dir = root / "netwatch" / "location" / "data"
        protected_dir.mkdir(parents=True)
        data_file = protected_dir / "centers.csv"
        data_file.touch()

        monkeypatch.setattr(clean_caches, "REPO_ROOT", root)
        monkeypatch.setattr(
            clean_caches,
            "PROTECTED_PATHS",
            [protected_dir],
        )

        dirs, files, skipped = clean_caches.collect_candidates()

        import shutil
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)
        for f in files:
            if clean_caches.is_protected_extension(f):
                continue
            f.unlink(missing_ok=True)

        assert protected_dir.exists(), "protected directory must survive"
        assert data_file.exists(), "file under protected directory must survive"
