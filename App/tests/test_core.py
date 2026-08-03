from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from shopads.markdown import parse_sections
from shopads.validation import natural_key


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.toml"


class MarkdownTests(unittest.TestCase):
    def test_parse_utf8_markdown_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "description.md"
            path.write_text("# 上標題\n主標\n## 說明\n第一行\n第二行\n# 下標題\n結尾\n", encoding="utf-8")
            result = parse_sections(path, ("上標題", "說明", "下標題"))
            self.assertEqual(result["說明"], "第一行\n第二行")

    def test_natural_filename_order(self) -> None:
        paths = [Path("10.png"), Path("2.png"), Path("01.png")]
        self.assertEqual([item.name for item in sorted(paths, key=natural_key)], ["01.png", "2.png", "10.png"])


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from PIL import Image  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest("Pillow 尚未安裝") from exc

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.job = Path(self.temp.name) / "20260803"
        self.job.mkdir()
        (self.job / "Prod_Description.md").write_text(
            "# 商品名稱\n測試商品\n# 使用情境\n居家使用\n# 商品說明\n測試商品說明\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_group_description(self, group: Path) -> None:
        (group / "Img_Description.md").write_text(
            "# 上標題\n乾淨商業風格\n# 說明\n依照檔名順序呈現商品圖片\n# 下標題\n立即瞭解更多\n",
            encoding="utf-8",
        )

    def _create_png(self, path: Path, color: tuple[int, int, int]) -> None:
        from PIL import Image

        Image.new("RGB", (320, 480), color).save(path)

    def test_generate_cleanup_final_protection_and_package(self) -> None:
        from shopads.cli import main
        from shopads.package_ops import verify_package

        group = self.job / "01"
        group.mkdir()
        self._write_group_description(group)
        for name, color in (
            ("1.png", (220, 60, 60)),
            ("2.png", (60, 180, 100)),
            ("10.png", (70, 110, 220)),
            ("11.png", (220, 170, 40)),
        ):
            self._create_png(group / name, color)

        rc = main(["--config", str(CONFIG_PATH), "generate", str(self.job)])
        self.assertEqual(rc, 0)
        generated = self.job / "Result" / "Generated"
        self.assertEqual(sorted(item.name for item in generated.iterdir()), ["01-1.png", "01-2.png"])

        final = self.job / "Result" / "Final"
        shutil.copyfile(generated / "01-1.png", final / "01-1.png")
        protected_hash = (final / "01-1.png").read_bytes()

        (group / "11.png").unlink()
        rc = main(["--config", str(CONFIG_PATH), "generate", str(self.job)])
        self.assertEqual(rc, 0)
        self.assertEqual([item.name for item in generated.iterdir()], ["01.png"])
        self.assertEqual((final / "01-1.png").read_bytes(), protected_hash)

        shutil.copyfile(generated / "01.png", final / "01.png")
        self.assertEqual(main(["--config", str(CONFIG_PATH), "check-final", str(self.job)]), 0)
        self.assertEqual(main(["--config", str(CONFIG_PATH), "package", str(self.job)]), 0)
        packages = list((self.job / "PublishPackages").glob("*.zip"))
        self.assertEqual(len(packages), 1)
        self.assertGreater(verify_package(packages[0]), 0)
        manifest = json.loads((self.job / "run-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "success")

    def test_single_gif_is_copied_without_reencoding(self) -> None:
        from PIL import Image
        from shopads.cli import main

        group = self.job / "02"
        group.mkdir()
        source = group / "animation.gif"
        Image.new("P", (24, 24), 1).save(source, format="GIF")
        expected = source.read_bytes()
        rc = main(["--config", str(CONFIG_PATH), "generate", str(self.job)])
        self.assertEqual(rc, 0)
        output = self.job / "Result" / "Generated" / "02.gif"
        self.assertEqual(output.read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
