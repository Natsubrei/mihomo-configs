"""公开目录和文档链接契约；只读取仓库内容。"""
import re
import unittest
from urllib.parse import unquote, urlsplit

from tools.render import ROOT, public_entries


class RepositoryTests(unittest.TestCase):
    def test_public_entries_are_in_dist(self):
        self.assertEqual(
            {path.relative_to(ROOT).as_posix() for path in public_entries()},
            {"dist/mihomo-party.yaml", "dist/mihomo-linux.yaml"},
        )

    def test_relative_document_links_exist(self):
        documents = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
        for document in documents:
            text = document.read_text(encoding="utf-8")
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                url = urlsplit(link)
                if url.scheme or url.netloc or not url.path:
                    continue
                with self.subTest(document=document.name, link=link):
                    target = (document.parent / unquote(url.path)).resolve()
                    self.assertTrue(target.is_relative_to(ROOT.resolve()))
                    self.assertTrue(target.is_file(), "本地文档链接不存在")

    def test_download_links_use_direct_raw_urls(self):
        base = "https://raw.githubusercontent.com/Natsubrei/mihomo-configs/main/dist/"
        documents = {
            "README.md": {"mihomo-party.yaml", "mihomo-linux.yaml"},
            "docs/mihomo-party.md": {"mihomo-party.yaml"},
            "docs/linux.md": {"mihomo-linux.yaml"},
        }
        for name, entries in documents.items():
            text = (ROOT / name).read_text(encoding="utf-8")
            links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
            with self.subTest(document=name):
                self.assertTrue({base + entry for entry in entries} <= set(links))
                # Download links must bypass GitHub's blob-page navigation.
                self.assertFalse(any("raw=" in urlsplit(link).query for link in links))
                for entry in entries:
                    self.assertTrue((ROOT / "dist" / entry).is_file())

    def test_workflow_dependencies_exist(self):
        workflow = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        requirements = re.findall(r"pip install -r (\S+)", workflow)
        self.assertTrue(requirements)
        for path in requirements:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())


if __name__ == "__main__":
    unittest.main()
