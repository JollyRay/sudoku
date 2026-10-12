import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from sudoku.settings import STATICFILES_STORAGE as PRODUCTION_STATICFILES_STORAGE


class SudokuV2StaticTests(SimpleTestCase):
    def test_collectstatic_builds_manifest_for_gridstack_assets(self) -> None:
        with TemporaryDirectory(prefix="sudoku-v2-static-") as static_root:
            with override_settings(
                DEBUG=False,
                STATIC_ROOT=static_root,
                STATICFILES_STORAGE=PRODUCTION_STATICFILES_STORAGE,
            ):
                call_command("collectstatic", interactive=False, verbosity=0)

            manifest = json.loads(Path(static_root, "staticfiles.json").read_text())
            for filename in ("gridstack-all.js", "gridstack.min.css"):
                asset = f"sudoku_v2/vendor/gridstack/14.0.0/{filename}"
                with self.subTest(asset=asset):
                    collected_name = manifest["paths"][asset]
                    self.assertNotEqual(collected_name, asset)
                    self.assertTrue(Path(static_root, collected_name).is_file())
