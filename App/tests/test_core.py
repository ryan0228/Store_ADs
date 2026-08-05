from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from shopads.ai_plan import normalize_output_names, validate_plan
from shopads.errors import ShopAdsError
from shopads.job_ops import create_job
from shopads.markdown import parse_sections
from shopads.validation import filter_duplicate_images, inspect_job, natural_key, resolve_job_dir


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.toml"


class CoreTests(unittest.TestCase):
    def test_store_banner_reads_only_markdown_list_items(self) -> None:
        from shopads.compositor import _banner_lines

        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "store-banner.md"
            path.write_text("# 標題\n\n這是說明。\n\n- 第一則\n- 第二則\n", encoding="utf-8")
            self.assertEqual(_banner_lines(path), ["第一則", "第二則"])

    def test_plan_rejects_more_than_two_static_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            job = Path(temp_name) / "20260805-01"
            input_dir = job / "Input"
            input_dir.mkdir(parents=True)
            (job / "Product_Description.md").write_text("# 商品名稱\n測試\n# 商品說明\n說明\n", encoding="utf-8")
            for index, name in enumerate(("1.png", "2.png", "3.png"), start=1):
                (input_dir / name).write_bytes(f"unique-{index}".encode())
            payload = {"schema_version": 1, "outputs": [{"output": "01.png", "type": "static", "layout": "three_cards", "images": ["1.png", "2.png", "3.png"], "top_title": "標題", "description": "說明", "bottom_title": "下標題"}], "rejected": []}
            with self.assertRaises(ShopAdsError) as context:
                validate_plan(payload, job)
            self.assertEqual(context.exception.code, "E608")

    def test_restore_inherited_permissions_uses_icacls_on_windows(self) -> None:
        from shopads.cli import _restore_inherited_permissions

        with patch("shopads.cli.os.name", "nt"), patch("shopads.cli.subprocess.run", return_value=Mock(returncode=0)) as run:
            _restore_inherited_permissions(Path("output.gif"))
        self.assertEqual(run.call_args.args[0], ["icacls", "output.gif", "/inheritance:e"])

    def test_generated_cleanup_restores_permissions_before_unlink(self) -> None:
        from shopads.cli import _safe_cleanup_generated

        with tempfile.TemporaryDirectory() as temp_name:
            generated = Path(temp_name) / "Generated"
            generated.mkdir()
            output = generated / "01.gif"
            output.write_bytes(b"gif")
            with patch("shopads.cli._restore_inherited_permissions") as restore:
                self.assertEqual(_safe_cleanup_generated(generated), ["01.gif"])
            restore.assert_called_once_with(output)

    def test_ai_output_names_are_normalized_by_type_and_order(self) -> None:
        payload = {"outputs": [{"output": "wrong.gif", "type": "static"}, {"output": "wrong.png", "type": "gif"}]}
        normalize_output_names(payload)
        self.assertEqual([item["output"] for item in payload["outputs"]], ["01.png", "02.gif"])

    def test_ai_prompt_requires_claims_to_be_grounded_in_product_text(self) -> None:
        from shopads.ai_provider import _prompt

        prompt = _prompt({"商品名稱": "測試", "商品說明": "360度按摩頭"}, ["front.jpg"], [], 3)
        self.assertIn("材質、結構、功能與效果性文字必須能在商品資料原文或圖片清楚文字中直接找到依據", prompt)
        self.assertIn("不可自行加上「可彎曲」", prompt)
        self.assertIn("至少有 3 項具體且可驗證的資訊", prompt)
        self.assertIn("每張成品最多使用 2 張", prompt)
        self.assertIn("先根據確認資訊生成一段簡短自然的「商品亮點」文案", prompt)

    def test_new_job_uses_next_sequence_and_complete_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            first = create_job(root, "2026-08-04")
            second = create_job(root, "2026-08-04")
            self.assertEqual(first.name, "20260804-01")
            self.assertEqual(second.name, "20260804-02")
            self.assertTrue((second / "Product_Description.md").is_file())
            self.assertTrue((second / "Input").is_dir())
            self.assertTrue((second / "Result" / "Generated").is_dir())
            self.assertTrue((second / "Result" / "Final").is_dir())

    def test_new_job_refuses_more_than_ten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            for _ in range(10):
                create_job(root, "2026-08-04")
            with self.assertRaises(ShopAdsError) as context:
                create_job(root, "2026-08-04")
            self.assertEqual(context.exception.code, "E133")

    def test_parse_utf8_markdown_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "description.md"
            path.write_text("# 商品名稱\n測試\n# 商品說明\n說明\n# 商品用途\n用途\n", encoding="utf-8")
            result = parse_sections(path, ("商品名稱", "商品說明", "商品用途"))
            self.assertEqual(result["商品說明"], "說明")

    def test_natural_filename_order(self) -> None:
        paths = [Path("10.png"), Path("2.png"), Path("01.png")]
        self.assertEqual([item.name for item in sorted(paths, key=natural_key)], ["01.png", "2.png", "10.png"])

    def test_exact_duplicate_filter_keeps_first_natural_filename_for_any_format(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            first = root / "2.jpg"
            duplicate = root / "10.png"
            other = root / "11.webp"
            first.write_bytes(b"same-image-payload")
            duplicate.write_bytes(b"same-image-payload")
            other.write_bytes(b"different-image-payload")
            unique, duplicates = filter_duplicate_images(sorted([duplicate, other, first], key=natural_key))
            self.assertEqual([item.name for item in unique], ["2.jpg", "11.webp"])
            self.assertEqual([(item[0].name, item[1].name) for item in duplicates], [("10.png", "2.jpg")])

    def test_latest_job_uses_date_and_two_digit_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            for name in ("20260804-01", "20260804-10", "20260803-02", "20260804-11"):
                (root / name).mkdir()
            self.assertEqual(resolve_job_dir(None, root).name, "20260804-10")


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from PIL import Image  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest("Pillow 尚未安裝") from exc

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.job = Path(self.temp.name) / "20260804-01"
        self.input_dir = self.job / "Input"
        self.input_dir.mkdir(parents=True)
        (self.job / "Product_Description.md").write_text("# 商品名稱\n測試商品\n# 商品說明\n測試商品說明\n# 商品用途\n居家使用\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_png(self, name: str, color: tuple[int, int, int]) -> None:
        from PIL import Image
        Image.new("RGB", (320, 480), color).save(self.input_dir / name)

    def _save_plan(self, outputs: list[dict[str, object]]) -> None:
        work = self.job / "Work"
        work.mkdir()
        payload = {"schema_version": 1, "outputs": outputs, "rejected": []}
        validate_plan(payload, self.job)
        (work / "ai-plan.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_plan_driven_generation_cleanup_final_and_package(self) -> None:
        from shopads.cli import main
        from shopads.package_ops import verify_package

        for name, color in (("1.png", (220, 60, 60)), ("2.png", (60, 180, 100))):
            self._create_png(name, color)
        self._save_plan([{"output": "01.png", "type": "static", "layout": "two_cards", "images": ["1.png", "2.png"], "top_title": "兩張商品細節", "description": "只使用提供的原始圖片", "bottom_title": "清楚呈現"}])
        self.assertEqual(main(["--config", str(CONFIG_PATH), "generate", str(self.job)]), 0)
        generated = self.job / "Result" / "Generated"
        self.assertEqual([item.name for item in generated.iterdir()], ["01.png"])
        from PIL import Image
        with Image.open(generated / "01.png") as rendered:
            brand_crop = rendered.crop((20, 950, 175, 1055)).convert("RGB")
            self.assertGreater(len(brand_crop.getcolors(maxcolors=100000) or []), 20)
        final = self.job / "Result" / "Final"
        shutil.copyfile(generated / "01.png", final / "01.png")
        before = (final / "01.png").read_bytes()
        self.assertEqual(main(["--config", str(CONFIG_PATH), "generate", str(self.job)]), 0)
        self.assertEqual((final / "01.png").read_bytes(), before)
        self.assertEqual(main(["--config", str(CONFIG_PATH), "check-final", str(self.job)]), 0)
        self.assertEqual(main(["--config", str(CONFIG_PATH), "package", str(self.job)]), 0)
        package = next((self.job / "PublishPackages").glob("*.zip"))
        self.assertGreater(verify_package(package), 0)

    def test_multiple_animated_gifs_are_copied_without_reencoding(self) -> None:
        from PIL import Image
        from shopads.cli import main

        first = self.input_dir / "first.gif"
        second = self.input_dir / "second.gif"
        frames_a = [Image.new("RGB", (24, 24), color) for color in ("red", "green", "blue")]
        frames_b = [Image.new("RGB", (24, 24), color) for color in ("yellow", "purple")]
        frames_a[0].save(first, format="GIF", save_all=True, append_images=frames_a[1:], duration=80, loop=0, optimize=False)
        frames_b[0].save(second, format="GIF", save_all=True, append_images=frames_b[1:], duration=100, loop=0, optimize=False)
        expected_first = first.read_bytes()
        expected_second = second.read_bytes()
        self._save_plan([
            {"output": "01.gif", "type": "gif", "layout": "original_gif", "images": ["second.gif"]},
            {"output": "02.gif", "type": "gif", "layout": "original_gif", "images": ["first.gif"]},
        ])
        self.assertEqual(main(["--config", str(CONFIG_PATH), "generate", str(self.job)]), 0)
        self.assertEqual((self.job / "Result" / "Generated" / "01.gif").read_bytes(), expected_second)
        self.assertEqual((self.job / "Result" / "Generated" / "02.gif").read_bytes(), expected_first)

    def test_inspect_job_filters_duplicate_static_and_animated_files(self) -> None:
        from PIL import Image

        self._create_png("01.png", (30, 60, 90))
        shutil.copyfile(self.input_dir / "01.png", self.input_dir / "02.jpg")
        animated = self.input_dir / "03.gif"
        frames = [Image.new("RGB", (20, 20), color) for color in ("red", "blue")]
        frames[0].save(animated, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0, optimize=False)
        shutil.copyfile(animated, self.input_dir / "04.gif")
        job = inspect_job(self.job)
        self.assertEqual([item.name for item in job.images], ["01.png", "03.gif"])
        self.assertEqual([item.name for item in job.animated_gifs], ["03.gif"])
        self.assertEqual([(item[0].name, item[1].name) for item in job.duplicate_images], [("02.jpg", "01.png"), ("04.gif", "03.gif")])

    def test_single_frame_gif_is_static_branded_png(self) -> None:
        from PIL import Image
        from shopads.cli import main

        source = self.input_dir / "still.gif"
        Image.new("P", (240, 240), 3).save(source, format="GIF")
        self._save_plan([{"output": "01.png", "type": "static", "layout": "hero", "images": ["still.gif"], "top_title": "單影格 GIF", "description": "視為靜態商品圖片", "bottom_title": "加入品牌頁尾"}])
        self.assertEqual(main(["--config", str(CONFIG_PATH), "generate", str(self.job)]), 0)
        output = self.job / "Result" / "Generated" / "01.png"
        self.assertTrue(output.is_file())
        with Image.open(output) as rendered:
            self.assertEqual(rendered.size, (1080, 1080))
            brand_crop = rendered.crop((20, 950, 175, 1055)).convert("RGB")
            self.assertGreater(len(brand_crop.getcolors(maxcolors=100000) or []), 20)

    def test_animated_gif_preview_is_small_jpeg(self) -> None:
        from PIL import Image
        from shopads.ai_provider import _analysis_gif_preview

        source = self.input_dir / "preview.gif"
        frames = [Image.new("RGB", (640, 480), color) for color in ("red", "green", "blue")]
        frames[0].save(source, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
        label, encoded = _analysis_gif_preview(source, 768)
        import base64, io
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as preview:
            self.assertEqual(preview.size, (768, 256))
        self.assertIn("首／中／末", label)

    def test_vendor_text_is_last_branded_png(self) -> None:
        from shopads.cli import main

        (self.job / "Product_Description.md").write_text("# 商品名稱\n測試商品\n# 商品說明\n商品說明\n# 商品用途\n居家使用\n# 廠商文字說明\n日本語の説明です。\n", encoding="utf-8")
        self._create_png("front.png", (120, 80, 160))
        self._save_plan([
            {"output": "01.png", "type": "static", "layout": "hero", "images": ["front.png"], "top_title": "商品主視覺", "description": "使用原始商品圖片", "bottom_title": "情趣時光"},
            {"output": "02.png", "type": "text", "layout": "vendor_text", "images": [], "top_title": "廠商商品資訊", "description": "廠商說明已翻譯並整理為繁體中文。", "bottom_title": "購買前請詳閱"},
        ])
        self.assertEqual(main(["--config", str(CONFIG_PATH), "generate", str(self.job)]), 0)
        self.assertEqual(sorted(path.name for path in (self.job / "Result" / "Generated").iterdir()), ["01.png", "02.png"])

    def test_image_text_summary_is_allowed_without_vendor_text(self) -> None:
        from shopads.cli import main

        self._create_png("front.png", (60, 100, 140))
        self._save_plan([
            {"output": "01.png", "type": "static", "layout": "hero", "images": ["front.png"], "top_title": "商品主視覺", "description": "使用原始商品圖片", "bottom_title": "清楚呈現"},
            {"output": "02.png", "type": "text", "layout": "vendor_text", "images": [], "top_title": "商品資訊總覽", "description": "• 10段變頻\n• USB充電\n• 生活防水", "bottom_title": "詳細資訊一次掌握"},
        ])
        self.assertEqual(main(["--config", str(CONFIG_PATH), "generate", str(self.job)]), 0)
        self.assertTrue((self.job / "Result" / "Generated" / "02.png").is_file())


if __name__ == "__main__":
    unittest.main()
